from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from typing import Literal, List, Optional
from data_models import State, SingleProposal
from prompts import REFLECTION_PROMPT, RESEARCH_PROMPT_REFLECTION
from llm_models import reflection_agent, base_model_reasoning
from utils import remove_think_tags


# 🔹 **Reflection Node (With Structured/Unstructured Refinement)**
def reflection_node(state: State) -> Command[Literal["orchestrator", "ranking"]]:
    """
    Reflection Agent:
    - Evaluates and refines proposals, ensuring technical and constraint compliance.
    - Requests additional research if needed.
    """
    print("\n🔎 [DEBUG] Reflection node invoked.")

    iteration = state.reflection_iteration
    max_iterations = state.max_iterations

    print(f"\n🔄 [DEBUG] Reflection iteration {iteration + 1}/{max_iterations}...")

    if iteration >= max_iterations:
        print("⚠️ [DEBUG] Max iterations reached. Proceeding to ranking.")
        return Command(
            update={"reflection_notes": [f"Stopped after {max_iterations} iterations."],
                    "reflection_iteration": iteration - 1,
                    },
            goto="ranking"
        )

    # Retrieve Supervisor Instructions & Cahier des Charges
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No Cahier des Charges available."

    # Retrieve the most recent proposals
    recent_proposals = [
        p for p in state.proposals
        if p.current_step_index == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_proposals:
        print("⚠️ [DEBUG] No valid proposals found. Skipping reflection.")
        return Command(
            update={"reflection_notes": ["No proposals available for reflection."]},
            goto="ranking"
        )

    print(f"🔍 [DEBUG] Reviewing {len(recent_proposals)} proposals.")

    # Construct the reflection prompt
    reflection_prompt = [
        SystemMessage(content=REFLECTION_PROMPT),
        HumanMessage(content=f"""
### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges:**
{cahier_des_charges}

### **Proposals Under Review:**
{[p.content for p in recent_proposals]}

---

## **🔹 Task for the Reflection Agent**
1. **Critique each proposal individually**, ensuring:
   - Alignment with Supervisor Instructions.
   - Compliance with the Cahier des Charges.
   - Technical feasibility and completeness.
2. **If worker analyses are available, integrate them into feedback.**
3. **If no changes are needed, explicitly state so.**
4. **Return structured feedback in JSON format.**
""")
    ]

    # **Invoke Reflection Agent**
    re_output = reflection_agent.invoke(reflection_prompt)
    print(f"📝 [DEBUG] Received {len(re_output.reflections)} refined reflections.")

    # **Refine feedback for each proposal**
    for i, r_item in enumerate(re_output.reflections):
        if i < len(recent_proposals):
            refined_feedback = refine_feedback(recent_proposals[i], state, r_item.feedback)
            recent_proposals[i].feedback = refined_feedback
            recent_proposals[i].reflection_iteration_index = iteration
            print(f"✅ [DEBUG] Updated feedback for Proposal {i}: {refined_feedback}")

    # **Determine if additional research is needed**
    orchestrator_order = decide_if_more_research_needed_reflection(recent_proposals, state)

    if orchestrator_order:
        print(f"🧠 [DEBUG] Sending order to orchestrator: {orchestrator_order}")
        return Command(
            update={
                "orchestrator_orders": [orchestrator_order],
                "reflection_notes": [f"Requested more research after iteration {iteration + 1}."],
                "current_requesting_agent": "reflection",
                "current_tasks_count": 0,
                "reflection_iteration": iteration + 1,
            },
            goto="orchestrator"
        )

    print("✅ [DEBUG] Reflection complete. Proceeding to ranking.")
    return Command(
        update={
            "reflection_notes": [f"Completed reflection at step {state.current_step_index}."],
            "reflection_iteration": iteration,
        },
        goto="ranking"
    )


def decide_if_more_research_needed_reflection(proposals: List[SingleProposal], state: State) -> Optional[str]:
    """
    Determines whether additional research is required to improve proposal critiques.
    Sends a clear request to the Orchestrator if needed.
    """
    print("\n🔍 [DEBUG] Checking if additional research is needed for Reflection Agent.")

    # **Retrieve Supervisor Instructions & Cahier des Charges**
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges_summary = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    # **Retrieve Worker Analyses (if available)**
    worker_analyses = [
        f"Task '{a.from_task}': {a.content}" for a in state.analyses if a.called_by_agent == "reflection"
    ]
    worker_analyses_text = "\n\n---\n\n".join(worker_analyses) if worker_analyses else "No additional worker analyses available."

    # **Prepare research validation request**
    research_request = f"""
### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges Summary:**
{cahier_des_charges_summary}

### **Current Proposal Critiques:**
{[{"Index": i, "Feedback": p.feedback} for i, p in enumerate(proposals)]}

### **Worker Analyses (if available):**
{worker_analyses_text}

---

## **🔹 Task for the Reflection Agent**
- Evaluate whether the critiques are **detailed, feasible, and complete**.
- **Identify any missing data or research gaps** that prevent a fully informed critique.
- If additional research is required, **define a precise task request for the Orchestrator** (web searches, simulations, calculations).
- If no research is required, state explicitly: `"No additional research is needed."`
"""

    # **Invoke base model for open-ended reflection**
    decision_output = base_model_reasoning.invoke([
        SystemMessage(content=RESEARCH_PROMPT_REFLECTION),
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



# 🔹 **Refining Feedback with Additional LLM Call**
def refine_feedback(proposal: SingleProposal, state: State, raw_feedback: str) -> str:
    """
    Uses an additional LLM call to refine the feedback given to each proposal.
    Ensures **structured, actionable, and precise critique**.
    """
    print(f"📝 [DEBUG] Refining feedback for proposal: {proposal.title}")

    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    refinement_prompt = [
        SystemMessage(content=REFLECTION_PROMPT),
        HumanMessage(content=f"""
### **Proposal Title:**
{proposal.title}

### **Proposal Content:**
{proposal.content}

### **Raw Feedback:**
{raw_feedback}

---

### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges (Engineering Constraints):**
{cahier_des_charges}

---

### **Your Task:**
1. **Refine the feedback** to ensure:
   - It is **specific, actionable, and structured**.
   - It provides **clear technical reasoning**.
   - It integrates **any relevant engineering constraints**.
2. **If the proposal is already optimal**, state so explicitly.
3. **Return only the refined feedback text.**
""")
    ]

    #refined_feedback = base_model.invoke(refinement_prompt).content
    refined_feedback = remove_think_tags(base_model_reasoning.invoke(refinement_prompt).content)
    return refined_feedback
# 🔹 **Refining Feedback with Additional LLM Call**
def refine_feedback(proposal: SingleProposal, state: State, raw_feedback: str) -> str:
    """
    Uses an additional LLM call to refine the feedback given to each proposal.
    Ensures **structured, actionable, and precise critique**.
    """
    print(f"📝 [DEBUG] Refining feedback for proposal: {proposal.title}")

    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    refinement_prompt = [
        SystemMessage(content=REFLECTION_PROMPT),
        HumanMessage(content=f"""
### **Proposal Title:**
{proposal.title}

### **Proposal Content:**
{proposal.content}

### **Raw Feedback:**
{raw_feedback}

---

### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges (Engineering Constraints):**
{cahier_des_charges}

---

### **Your Task:**
1. **Refine the feedback** to ensure:
   - It is **specific, actionable, and structured**.
   - It provides **clear technical reasoning**.
   - It integrates **any relevant engineering constraints**.
2. **If the proposal is already optimal**, state so explicitly.
3. **Return only the refined feedback text.**
""")
    ]

    #refined_feedback = base_model.invoke(refinement_prompt).content
    refined_feedback = remove_think_tags(base_model_reasoning.invoke(refinement_prompt).content)

    return refined_feedback