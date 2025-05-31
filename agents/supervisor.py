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
from graph_utils  import summarize_design_state_func, visualize_design_state_func
from utils        import remove_think_tags, save_dsg


# ─────────────────────────────────────────────────────────────────────────────
def supervisor_node(state: State) -> Command[Literal["generation", END]]:
    """
    Decide whether the current Design-State Graph is complete and meets requirements.
    """

    print("\n🔎  [Supervisor] invoked")

    # Increment supervisor visit counter
    state.supervisor_visit_counter += 1

    # Save current DSG if we have one
    if state.design_graph_history:
        try:
            dsg_now = state.design_graph_history[-1]
            out = save_dsg(
                dsg_now,
                thread_id=str(state.supervisor_visit_counter),
                step_idx=state.supervisor_visit_counter,
                meta_iter=0,
            )
            print(f"💾 [Supervisor] DSG snapshot saved → {out}")
            # Visualize the current DSG
            visualize_design_state_func(dsg_now)
        except Exception as e:
            print(f"⚠️  [Supervisor] failed to save/visualize DSG: {e}")

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

    # Get last supervisor instructions if available
    last_instructions = state.supervisor_instructions[-1] if len(state.supervisor_instructions) > 1 else "No previous instructions."

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

### Your Last Instructions:
{last_instructions}
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
