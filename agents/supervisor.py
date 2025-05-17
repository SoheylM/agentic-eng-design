from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from langgraph.graph import END
from typing import Literal
import json

from data_models   import State, CahierDesCharges, DesignState, SupervisorDecision
from prompts       import SUPERVISOR_PROMPT
from llm_models    import supervisor_model
from graph_utils   import summarize_design_state_func


def supervisor_node(state: State) -> Command[Literal["generation", END]]:
    """Check current step, decide iterate / advance, write instructions."""

    print("\n🔎 [Supervisor] invoked")

    # ------------------------------------------------ plan & step lookup
    if not state.design_plan:
        print("❌ [Supervisor] no DesignPlan — aborting")
        return Command(goto=END)

    steps = state.design_plan.steps
    idx   = state.current_step_index

    if idx >= len(steps):
        print("🎉 [Supervisor] all steps done")
        return Command(goto=END)

    step               = steps[idx]
    design_graph       = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    graph_summary      = summarize_design_state_func(design_graph)
    cdc_json           = (state.cahier_des_charges.model_dump_json()
                          if isinstance(state.cahier_des_charges, CahierDesCharges)
                          else json.dumps(state.cahier_des_charges or {}))

    # ------------------------------------------------ LLM call
    llm_messages = [
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=f"""
### Current step
ID: {step.step_id}
Name: {step.name}
Objectives: {step.objectives}
Expected outputs: {step.expected_outputs}

### DSG summary
{graph_summary}

### Cahier-des-Charges
{cdc_json}
""")
    ]

    try:
        decision: SupervisorDecision = supervisor_model.invoke(llm_messages)
    except Exception as e:
        err = f"❌ [Supervisor] LLM failure → {e}"
        print(err)
        return Command(update={"messages": [err]}, goto=END)

    print(f"✅ [Supervisor] decision: step_completed={decision.step_completed}")

    # ------------------------------------------------ state updates
    next_idx   = idx + 1 if decision.step_completed else idx
    next_agent = "generation" if next_idx < len(steps) and not decision.workflow_complete else END

    update_dict = {
        "supervisor_instructions": [decision.instructions],
        "current_step_index": next_idx,
        "redo_work": not decision.step_completed,
        "redo_reason": decision.reason_for_iteration,
    }

    return Command(update=update_dict, goto=next_agent)