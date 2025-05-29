# agents/supervisor.py  – counter-safe, no refinement
from __future__ import annotations
from typing  import Literal
from datetime import datetime

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types          import Command
from langgraph.graph          import END

import json

from data_models  import ( State, DesignState, CahierDesCharges,
                           SupervisorDecision )
from prompts      import SUPERVISOR_PROMPT
from llm_models   import supervisor_model
from graph_utils  import summarize_design_state_func
from utils        import remove_think_tags


# ─────────────────────────────────────────────────────────────────────────────
def supervisor_node(state: State) -> Command[Literal["generation", END]]:
    """
    Decide whether the current Design-State Graph is complete and meets requirements.
    """

    print("\n🔎  [Supervisor] invoked")

    # 1) Check CDC and DSG ------------------------------------------------------------
    if not state.cahier_des_charges:
        print("⚠️  no Cahier des Charges → END")
        return Command(goto=END)

    dsg = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    cdc = state.cahier_des_charges
    cdc_js = (cdc.model_dump_json() if isinstance(cdc, CahierDesCharges)
              else json.dumps(cdc or {}, indent=2))

    # Get meta-review notes if available
    meta_notes = state.meta_review_notes[-1] if state.meta_review_notes else "No meta-review notes available."

    # 2) structured LLM call ---------------------------------------------------
    decision: SupervisorDecision = supervisor_model.invoke([
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=f"""
### Current Design State:
{summarize_design_state_func(dsg)}

### Cahier-des-Charges:
{cdc_js}

### Meta-Review Notes:
{meta_notes}
""")
    ])

    # Print concise decision summary
    status = "✅" if decision.step_completed else "🔄"
    print(f"{status} Design State: {'Complete' if decision.step_completed else 'Needs iteration'}")
    if not decision.step_completed:
        print(f"   Reason: {decision.reason_for_iteration}")

    # 3) counter / flag maintenance --------------------------------------------
    redo_flag = not decision.step_completed

    # keep max_iterations monotonically increasing so other agents
    # never see 0/0
    new_max_iter = max(
        state.max_iterations,
        state.generation_iteration,
        state.reflection_iteration,
        state.ranking_iteration,
        state.evolution_iteration,
    ) + 1

    # Update current step index if step is completed
    new_step_index = state.current_step_index
    if decision.step_completed and not decision.workflow_complete:
        new_step_index += 1

    update = {
        "supervisor_instructions": [decision.instructions],
        "redo_work": redo_flag,
        "redo_reason": decision.reason_for_iteration,
        "max_iterations": new_max_iter,
        "current_step_index": new_step_index,
        # trace for debugging
        "supervisor_status": f"supervised_{datetime.utcnow().isoformat(timespec='seconds')}",
    }

    goto = "generation" if not decision.workflow_complete else END
    return Command(update=update, goto=goto)
