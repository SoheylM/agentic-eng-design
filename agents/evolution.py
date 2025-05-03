from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from typing import Literal, List, Optional
from data_models import State, SingleEvolution
from prompts import EVOLUTION_PROMPT, RESEARCH_PROMPT_EVOLUTION
from llm_models import evolution_agent, base_model_reasoning
from utils import remove_think_tags


def evolution_node(state: State) -> Command[Literal["orchestrator", "meta_review"]]:
    """
    Evolution Agent refines proposals iteratively, ensuring alignment with 
    Supervisor Instructions and the Cahier des Charges.
    If additional research is needed, it calls the Orchestrator before proceeding.
    """
    print("\n🔄 [DEBUG] Evolution node invoked.")

    iteration = state.evolution_iteration
    max_iterations = state.max_iterations

    print(f"\n🔄 [DEBUG] Evolution iteration {iteration + 1}/{max_iterations}...")

    if iteration >= max_iterations:
        print("⚠️ [DEBUG] Max iterations reached. Proceeding to meta-review.")
        return Command(
            update={"evolution_notes": [f"Stopped after {max_iterations} iterations."],
                    "evolution_iteration": iteration - 1,
            },
            goto="meta_review"
        )

    # **Retrieve Supervisor Instructions**
    supervisor_instructions = "\n".join(state.supervisor_instructions) if state.supervisor_instructions else "No specific guidance provided."
    cahier_des_charges_summary = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    # **Retrieve the most recent proposals**
    recent_proposals = [
        p for p in state.proposals
        if (p.current_step_index == state.current_step_index)
        and (p.generation_iteration_index == state.generation_iteration)
    ]

    if not recent_proposals:
        print("⚠️ No proposals available for evolution.")
        return Command(
            update={"evolution_notes": ["No proposals available for evolution."]},
            goto="meta_review"
        )

    print(f"🔄 [DEBUG] Evolving {len(recent_proposals)} proposals.")

    # Prepare input for Evolution LLM
    enumerated_proposals_text = "\n\n".join([
        f"Proposal Index: {i}\n"
        f"Content: {p.content}\n"
        f"Reflection Feedback: {p.feedback or 'No prior feedback'}\n"
        f"Ranking Score: {p.grade if p.grade is not None else 'Not yet scored'}\n"
        f"Previous Evolution: {p.evolved_content if p.evolved_content else 'No prior evolution'}\n"
        f"Previous Evolution Justification: {p.evolution_justification if p.evolution_justification else 'No prior evolution'}\n"
        for i, p in enumerate(recent_proposals)
    ])

    # Prepare messages for Evolution LLM
    messages = [
        SystemMessage(content=EVOLUTION_PROMPT),
        HumanMessage(content=f"""
### **Supervisor's Instructions for This Design Step**:
{supervisor_instructions}

### **Cahier des Charges Summary**:
{cahier_des_charges_summary}

### **Proposals to Refine**:
{enumerated_proposals_text}

### **Task**:
Refine the proposals based on Supervisor Instructions, prior feedback, and ranking scores. 
Only modify a proposal if justified. If no changes are needed, explicitly state why.
""")
    ]

    print("🔄 [DEBUG] Sending proposals to Evolution LLM with structured output.")
    ev_output = evolution_agent.invoke(messages)

    # Process evolved proposals
    for idx, evol in enumerate(ev_output.evolutions):
        if 0 <= idx < len(recent_proposals):
            evolved_proposal = recent_proposals[idx]
            refined_evolution = refine_evolved_proposal(evol, state, recent_proposals[idx].content)
            evolved_proposal.evolved_content = refined_evolution
            evolved_proposal.evolution_justification = evol.evolution_justification
            evolved_proposal.evolution_iteration_index = iteration
            print(f"🔄 [DEBUG] Proposal {idx} evolved: {refined_evolution}.")
        else:
            print(f"⚠️ [DEBUG] Invalid proposal_index={idx}, ignoring.")

        

    # **🔹 Step 2: Research Validation (RESTORED)**
    orchestrator_order = decide_if_more_research_needed_evolution(recent_proposals, state)

    if orchestrator_order:
        print(f"🧠 [DEBUG] Sending research request to Orchestrator: {orchestrator_order}")
        return Command(
            update={
                "orchestrator_orders": [orchestrator_order],
                "evolution_notes": [f"Requested additional research after evolution iteration {iteration + 1}."],
                "current_requesting_agent": "evolution",
                "current_tasks_count": 0,
                "evolution_iteration": iteration + 1,
            },
            goto="orchestrator"
        )

    # **Proceed to Meta-Review if No Research Needed**
    print("✅ [DEBUG] Evolution complete. Proceeding to meta-review.")
    return Command(
        update={
            "evolution_notes": [f"Completed evolution at step {state.current_step_index}."],
            "evolution_iteration": iteration,
        },
        goto="meta_review"
    )


def decide_if_more_research_needed_evolution(proposals: List[SingleEvolution], state: State) -> Optional[str]:
    """
    Determines whether additional research is required to improve evolved proposals.
    Sends a clear request to the Orchestrator if needed.
    """
    print("\n🔍 [DEBUG] Checking if additional research is needed for Evolution Agent.")

    # **Retrieve Supervisor Instructions & Cahier des Charges**
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges_summary = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    # **Retrieve Worker Analyses (if available)**
    worker_analyses = [
        f"Task '{a.from_task}': {a.content}" for a in state.analyses if a.called_by_agent == "evolution"
    ]
    worker_analyses_text = "\n\n---\n\n".join(worker_analyses) if worker_analyses else "No additional worker analyses available."

    # **Prepare research validation request**
    research_request = f"""
### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges Summary:**
{cahier_des_charges_summary}

### **Current Evolved Proposals:**
{[{"Index": i, "New Content": p.evolved_content, "Justification": p.evolution_justification} for i, p in enumerate(proposals)]}

### **Worker Analyses (if available):**
{worker_analyses_text}

---

## **🔹 Task for the Evolution Agent**
- Evaluate whether the evolved proposals are **accurate, justified, and well-supported**.
- **Identify any missing technical validation or research gaps** that could improve proposal refinements.
- If additional research is required, **define a precise task request for the Orchestrator** (web searches, simulations, calculations).
- If no research is required, state explicitly: `"No additional research is needed."`
"""

    # **Invoke base model for open-ended evolution validation**
    decision_output = base_model_reasoning.invoke([
        SystemMessage(content=RESEARCH_PROMPT_EVOLUTION),
        HumanMessage(content=research_request)
    ])

    # **Process the decision**
    response = remove_think_tags(decision_output.content) #.strip().lower()

    if "No additional research is needed" in response:
        print("✅ [DEBUG] No further research required.")
        return None
    else:
        print(f"🧠 [DEBUG] Additional research requested: {response}")
        return response
    
def refine_evolved_proposal(evolved_proposal: SingleEvolution, state: State, original_content: str) -> str:
    """
    Uses an additional LLM call to refine the evolved content.
    Ensures the **refinements are precise, justified, and structured**.
    """
    print(f"📝 [DEBUG] Refining evolved proposal")

    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    refinement_prompt = [
        SystemMessage(content=EVOLUTION_PROMPT),
        HumanMessage(content=f"""
### **Original Proposal Content:**
{original_content}
                     
### **Evolved Proposal Content:**
{evolved_proposal.new_content}

### **Evolution Justification:**
{evolved_proposal.evolution_justification}

---

### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges (Engineering Constraints):**
{cahier_des_charges}
---

### **Your Task:**
1. **Refine the evolved content** to ensure:
   - **Technical soundness and justification**.
   - **Clarity, structure, and consistency with engineering goals**.
   - **Minimal redundant complexity**.
2. **If no further changes are needed**, explicitly state so.
3. **Return only the final refined evolved content.**
""")
    ]

    #refined_evolution = base_model.invoke(refinement_prompt).content
    refined_evolution = remove_think_tags(base_model_reasoning.invoke(refinement_prompt).content)

    return refined_evolution