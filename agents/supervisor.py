from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from typing import Literal
from data_models import State
from prompts import SUPERVISOR_PROMPT
from llm_models import supervisor_model, base_model_reasoning
from utils import remove_think_tags
from langgraph.graph import MessagesState, StateGraph, START, END
from graph_utils import summarize_design_state_func


def supervisor_node(state: State) -> Command[Literal["generation", END]]:
    """
    Supervisor Agent:
    - Monitors workflow progress.
    - Decides whether to **iterate on the current step** or **move to the next step**.
    - Updates the state with **step instructions** before triggering the next agent.
    """

    print("\n🛠️ [DEBUG] Supervisor node invoked.")

    # **Check for a valid design plan**
    if not state.design_plan:
        print("⚠️ No design plan found. Ending workflow.")
        return Command(goto=END)

    steps = state.design_plan.steps
    current_step_idx = state.current_step_index

    # **Check if all steps are complete**
    if current_step_idx >= len(steps):
        print("✅ All steps completed. Ending workflow.")
        return Command(goto=END)

    # **Retrieve the current step details**
    current_step = steps[current_step_idx]

    # **Retrieve current design graph summary**
    design_graph_summary = summarize_design_state_func()

    # **Retrieve Cahier des Charges (Design Requirements)**
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    # **Build prompt for Supervisor Agent**
    messages = [
        SystemMessage(SUPERVISOR_PROMPT),  # Keep full system grounding
        HumanMessage(content=f"""
### **Current Step:**
- **Step ID:** {current_step.step_id}
- **Step Name:** {current_step.name}
- **Step Objectives:** {current_step.objectives}
- **Step Description:** {current_step.description}

### **Current Design Graph Summary:**
{design_graph_summary}

### **Cahier des Charges (Design Requirements):**
{cahier_des_charges}

### **Task for Supervisor Agent:**
Evaluate if the current design graph fulfills the **objectives** of this step.
- If complete, **confirm and move to the next step**.
- If incomplete, **analyze gaps and provide refined instructions**.
- Output a **structured JSON decision** following the schema.
""")
    ]

    # **Invoke the structured LLM for Supervisor Decision**
    decision = supervisor_model.invoke(messages)

    print(f"\n🛠️ [DEBUG] Supervisor Decision: {decision.model_dump_json()}")

    # ✅ **Step 1: Reprocess Instructions with Full Context**
    # Instead of refining just the instructions, we reconstruct the **full Supervisor context**.

    refined_instruction_prompt = [
        SystemMessage(SUPERVISOR_PROMPT),  # Preserve full Supervisor Agent behavior
        HumanMessage(content=f"""
### **Full Context of the Supervisor Decision**
The Supervisor Agent was responsible for ensuring the **engineering design workflow** follows a structured, step-by-step approach.

#### **Original Input Context:**
- **Cahier des Charges (Design Requirements):**  
  {cahier_des_charges}

- **Current Step Objectives:**  
  {current_step.objectives}

- **Design Graph Summary Before Decision:**  
  {design_graph_summary}

#### **Supervisor's Decision Output:**
- **Step Completed:** {decision.step_completed}
- **Instructions Given:** {decision.instructions}
- **Reason for Iteration (if applicable):** {decision.reason_for_iteration}

---

### **Your Task:**
1. **Reprocess and refine the instructions**, ensuring they are:
   - **Structured, clear, and actionable.**
   - **Fully aligned with the engineering design process.**
   - **Detailed enough for the next agent to act precisely.**

2. **If this step involves Numerical Modeling**, ensure the output includes:
   - **A well-documented Python script** implementing the model.
   - **Physics-based modeling methods** (FDM, FEM, analytical equations).
   - **Boundary conditions, argument parsing, and output formatting.**
   - **Execution instructions for reproducibility.**

3. **Do not alter the Supervisor's decision structure** (i.e., keep the step_completed flag the same).
4. **Output only the refined instructions** in text format, suitable for direct use in the workflow.
""")
    ]

    #refined_instructions = base_model.invoke(refined_instruction_prompt).content
    refined_instructions = remove_think_tags(base_model_reasoning.invoke(refined_instruction_prompt).content)

    print(f"\n🛠️ [DEBUG] Refined Instructions: {refined_instructions}")

    # **Determine whether to move forward or reiterate**
    if decision.step_completed:
        print("✅ Step completed! Moving to next design phase.")
        next_step_idx = state.current_step_index + 1  # Move forward
        redo_work = False  # Clear iteration flag
        redo_reason = None  # No reason needed
    else:
        print("🔄 Iterating on the same step with refined guidance.")
        next_step_idx = state.current_step_index  # Stay on this step
        redo_work = True  # Indicate rework required
        redo_reason = decision.reason_for_iteration  # Capture reason

    # **Update state with refined Supervisor Decision**
    state_update = {
        "supervisor_instructions": [refined_instructions],  # Use fully reprocessed instructions
        "current_step_index": next_step_idx,
        "redo_work": redo_work,
        "redo_reason": redo_reason,
        "max_iterations": state.max_iterations + 1
    }

    # **Determine next agent**
    next_agent = "generation" if not decision.workflow_complete else END

    return Command(update=state_update, goto=next_agent)
