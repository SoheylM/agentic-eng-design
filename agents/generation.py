from typing import List, Optional, Literal
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from data_models import State, SingleProposal, Proposal
from prompts import GE_PROMPT_STRUCTURED, GE_PROMPT_BASE, GEN_RESEARCH_PROMPT
from llm_models import generation_agent, base_model_reasoning
from utils import remove_think_tags
from graph_utils import summarize_design_state_func


def generation_node(state: State) -> Command[Literal["orchestrator", "reflection"]]:
    """
    Generation agent that creates structured proposals, refines them, 
    integrates worker feedback, and determines if additional research is needed.
    """
    print("🔧 [DEBUG] Generation node invoked.")

    iteration = state.generation_iteration
    max_iterations = state.max_iterations

    print(f"\n🔄 [DEBUG] Generation iteration {iteration + 1}/{max_iterations}...")

    if iteration >= max_iterations:
        print("⚠️ [DEBUG] Max iterations reached. Proceeding to reflection.")
        return Command(
            update={
                "generation_notes": [f"Stopped after {max_iterations} iterations."],
                "generation_iteration": iteration - 1, # Prevents artificial iteration increase
            },
            goto="reflection"
        )

    # **Retrieve Supervisor Instructions & Cahier des Charges**
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No cahier des charges available."
    # **Retrieve the current design graph summary**
    current_graph_summary = summarize_design_state_func()

    # **🔹 Determine if Worker Analyses Exist**
    expected_analyses = state.current_tasks_count
    relevant_analyses = [
        analysis for analysis in state.analyses
        if analysis.called_by_agent == "generation"
    ][-expected_analyses:]

    if relevant_analyses:
        print(f"🔍 [DEBUG] Integrating {len(relevant_analyses)} worker analyses.")
        combined_analyses = "\n\n---\n\n".join(
            [f"From Task '{analysis.from_task}':\n{analysis.content}" for analysis in relevant_analyses]
        )
    else:
        print("⚠️ [DEBUG] No worker analyses received. Proceeding with standard proposal generation.")

    # **🔹 Generate or Refine Proposals**
    if relevant_analyses:
        # **Refinement Mode: Worker feedback available**
        refinement_prompt = f"""
We are refining the following proposals based on new analyses from workers.

**Supervisor Instructions:**
{supervisor_instructions}

**Cahier des Charges:**
{cahier_des_charges}

**Current Design Graph Summary**:
{current_graph_summary}

**Worker Analyses:**
{combined_analyses}

Refine each proposal accordingly.
"""
        ge_output = generation_agent.invoke([
            SystemMessage(content=GE_PROMPT_STRUCTURED),
            HumanMessage(refinement_prompt)
        ])
    else:
        # **Generation Mode: No prior proposals or feedback**
        messages = [
            SystemMessage(content=GE_PROMPT_STRUCTURED),
            HumanMessage(content=f"""
This is the Cahier des Charges (technical scope of specifications):
{cahier_des_charges}

For its implementation, the Planner has defined specific design steps,
for which the Supervisor has devised instructions for implementation:
{supervisor_instructions}

### **And here is the current state of the Design Graph that your proposals will help to populate**:
{current_graph_summary}

Generate design proposals **aligned with these instructions**.
Ensure clarity, feasibility, and completeness.
""")
        ]

        ge_output = generation_agent.invoke(messages)

    raw_proposals = ge_output.proposals
    print(f"📝 [DEBUG] Generated {len(raw_proposals)} proposals.")

    # **🔹 Refine Each Proposal Using an Additional LLM Call**
    refined_proposals = [
        SingleProposal(title=proposal.title, content=refine_proposal_content(proposal, state))
        for proposal in raw_proposals
    ]
    
    for proposal in refined_proposals:
        print(f"✅ [DEBUG] Refined proposal: {proposal.title}")

    print("✅ [DEBUG] Proposals refined. Proceeding to research determination.")

    # **🔹 Determine if Additional Research is Needed**
    orchestrator_order = decide_if_more_research_needed_generation(refined_proposals, state)

    # **🔹 Update the State with New Proposals**
    new_proposal_entries = [
        Proposal(
            title=sp.title,
            content=sp.content,
            feedback=None,
            grade=None,
            evolved_content=None,
            status="generated",
            reason_for_status=None,
            current_step_index=state.current_step_index,
            generation_iteration_index=iteration,
            reflection_iteration_index=state.reflection_iteration,
            ranking_iteration_index=state.ranking_iteration,
            evolution_iteration_index=state.evolution_iteration,
            meta_review_iteration_index=state.meta_review_iteration,
        )
        for sp in refined_proposals
    ]

    # **🔹 If Research is Needed, Call the Orchestrator**
    if orchestrator_order:
        print(f"🧠 [DEBUG] Requesting additional research: {orchestrator_order}")
        return Command(
            update={
                "proposals": new_proposal_entries,
                "orchestrator_orders": [orchestrator_order],
                "generation_notes": [f"Requested research at iteration {iteration + 1}."],
                "current_requesting_agent": "generation",
                "current_tasks_count": 0,
                "generation_iteration": iteration + 1,
            },
            goto="orchestrator"
        )

    print("✅ [DEBUG] Generation phase complete. Proceeding to reflection.")
    return Command(
        update={
            "proposals": new_proposal_entries,
            "generation_notes": [f"Completed generation at step {state.current_step_index}."],
            "generation_iteration": iteration,
        },
        goto="reflection"
    )


def decide_if_more_research_needed_generation(proposals: List[SingleProposal], state: State) -> Optional[str]:
    """
    Determines whether additional research is required to improve generated proposals.
    Sends a clear request to the Orchestrator if needed.
    """
    print("\n🔍 [DEBUG] Checking if additional research is needed for Generation Agent.")

    # **Retrieve Supervisor Instructions & Cahier des Charges**
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges_summary = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    # **Prepare evaluation request for the base model**
    research_request = f"""
### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges Summary:**
{cahier_des_charges_summary}

### **Generated Proposals:**
{[{"Title": p.title, "Content": p.content} for p in proposals]}

---

## **🔹 Task for the Reflection Agent**
- Evaluate whether the proposals are **detailed, feasible, and complete**.
- **Identify any missing data or research gaps** that need to be addressed.
- If research is required, **define a precise task request for the Orchestrator** (web searches, simulations, calculations, etc.).
- If no research is required, state explicitly: `"No additional research is needed."`
"""

    # **Invoke base model for open-ended reflection**
    decision_output = base_model_reasoning.invoke([
        SystemMessage(content=GEN_RESEARCH_PROMPT),
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


# 🔹 **Refining Proposal Content**
def refine_proposal_content(proposal: SingleProposal, state: State) -> str:
    """
    Uses an additional LLM call to refine the content of a generated proposal.
    Ensures detailed, engineering-aligned content with structured explanations.
    """
    print(f"📝 [DEBUG] Refining proposal: {proposal.title}")

    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    refinement_prompt = [
        SystemMessage(content=GE_PROMPT_BASE),
        HumanMessage(content=f"""
### **Original Proposal Title:**
{proposal.title}

### **Current Proposal Content:**
{proposal.content}

---

### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges (Engineering Constraints):**
{cahier_des_charges}

---

### **Your Task:**
1. **Refine the proposal content** to make it:
   - More **structured and precise**.
   - Aligned with **engineering principles**.
   - Fully consistent with **design constraints**.
2. **If the proposal relates to Numerical Modeling**, ensure it includes:
   - Well-documented **Python code** implementing a **physical model**.
   - Governing equations (Finite Element, Finite Difference, or Analytical).
   - Parameter parsing for boundary conditions.
   - Execution instructions for reproducibility.

---

### **Refined Proposal Content (Return only the updated text)**
""")
    ]

    #refined_content = base_model.invoke(refinement_prompt).content
    refined_content = remove_think_tags(base_model_reasoning.invoke(refinement_prompt).content)
    return refined_content