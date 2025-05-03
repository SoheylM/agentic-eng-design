from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from typing import Literal
from data_models import State
from prompts import PLANNER_PROMPT
from llm_models import planner_model, base_model_reasoning
import json
from utils import remove_think_tags

def planner_node(state: State) -> Command[Literal["supervisor", "human"]]:
    """Generates a structured design plan and refines its objectives & expected outputs in-place."""

    print("📝 [DEBUG] Planner Node Accessed")

    # **Ensure we have a valid Cahier des Charges**
    if not state.cahier_des_charges:
        print("⚠️ [DEBUG] No Cahier des Charges found. Returning to human.")
        return Command(
            update={"messages": ["⚠️ No Cahier des Charges found. Returning to human."]}, 
            goto="human"
        )

    # **Convert Cahier des Charges to JSON format**
    try:
        if isinstance(state.cahier_des_charges, CahierDesCharges):
            cahier_json = state.cahier_des_charges.model_dump_json()
        else:
            cahier_json = json.dumps(state.cahier_des_charges)  # Fallback for dict-like structures
    except Exception as e:
        print(f"⚠️ [ERROR] Failed to process Cahier des Charges: {e}")
        return Command(update={"messages": ["⚠️ Error processing Cahier des Charges. Returning to human."]}, goto="human")

    # **Generate Initial Plan**
    messages = [
        SystemMessage(PLANNER_PROMPT),
        HumanMessage(content=f"Here is the Cahier des Charges:\n\n{cahier_json}")
    ]

    try:
        plan_output = planner_model.invoke(messages)
    except Exception as e:
        print(f"⚠️ [ERROR] Planner Model failed: {e}")
        return Command(update={"messages": ["⚠️ Planner Model failed. Returning to human."]}, goto="human")

    if not plan_output or not plan_output.steps:
        print("⚠️ [DEBUG] Planner returned no steps. Returning to human.")
        return Command(
            update={"messages": ["⚠️ Planner returned no steps. Refinement needed."]}, 
            goto="human"
        )

    print("✅ [DEBUG] Initial Design Plan Created!")

    # ✅ **Refining Each Step’s Objectives & Expected Outputs In-Place**
    for step in plan_output.steps:
        print(f"🔄 [DEBUG] Refining Step {step.step_id}: {step.name}")

        # 🔹 **Refine Objectives**
        refine_objectives_prompt = [
            SystemMessage(PLANNER_PROMPT),  # Use full planner context
            HumanMessage(content=f"""
### **Step: {step.name}**
**Current Objectives:**
{step.objectives}

---
### **Task for You:**
1. **Clarify and refine the objectives** to ensure:
   - They are **specific and actionable**.
   - They **logically contribute** to the overall design.
   - They ensure a **clear transition** to the next step.

2. If this is a **Numerical Modeling** step, ensure objectives emphasize:
   - **Executable Python scripts** for engineering analysis.
   - **Clear boundary conditions, physics methods (FEM, FDM, analytical), and computational approach**.
   - **Input/output structure for further integration**.

---
### **Refined Objectives:**
Improve and rewrite the objectives with more clarity and depth.
""")
        ]

        try:
            refined_objectives = remove_think_tags(base_model_reasoning.invoke(refine_objectives_prompt).content) #.strip()
            
        except Exception as e:
            print(f"⚠️ [ERROR] Failed to refine objectives for Step {step.step_id}: {e}")
            refined_objectives = step.objectives  # Fallback: keep original

        step.objectives = refined_objectives  # Update the step in-place

        # 🔹 **Refine Expected Outputs**
        refine_outputs_prompt = [
            SystemMessage(PLANNER_PROMPT),
            HumanMessage(content=f"""
### **Step: {step.name}**
**Current Expected Outputs:**
{step.expected_outputs}

---
### **Task for You:**
1. **Clarify and refine the expected outputs** to ensure:
   - They **precisely describe what should be generated** at this step.
   - They align with **previous and next steps**.
   - They include all **necessary deliverables** (diagrams, specifications, code, performance reports).

2. If this is a **Numerical Modeling** step, expected outputs must include:
   - **Python scripts for computational analysis**.
   - **Detailed technical documentation** of the model (assumptions, equations, solver details).
   - **Execution guidelines** (e.g., parameter tuning, runtime expectations).
   - **Structured format** for integrating outputs into the next phase.

---
### **Refined Expected Outputs:**
Improve and rewrite the expected outputs with more clarity and depth.
""")
        ]

        try:
            print(f"[DEBUG]: step.expected_outputs:, {step.expected_outputs}")
            print(f"[DEBUG]: step.expected_outputs type:, {type(step.expected_outputs)}")
            #refined_expected_outputs = base_model.invoke(refine_outputs_prompt).content #.strip()
            refined_expected_outputs = remove_think_tags(base_model_reasoning.invoke(refine_outputs_prompt).content)
            print(f"[DEBUG]: refined_expected_outputs:, {refined_expected_outputs}")
            print(f"[DEBUG]: refined_expected_outputs type:, {type(refined_expected_outputs)}")
        except Exception as e:
            print(f"⚠️ [ERROR] Failed to refine expected outputs for Step {step.step_id}: {e}")
            refined_expected_outputs = step.expected_outputs  # Fallback: keep original

        step.expected_outputs = refined_expected_outputs  # Update the step in-place

    print("✅ [DEBUG] Fully Refined Design Plan Generated!")

    return Command(
        update={"design_plan": plan_output, "active_agent": "supervisor"},
        goto="supervisor"
    )
