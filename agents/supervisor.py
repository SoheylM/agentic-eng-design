# agents/supervisor.py  – counter-safe, batch-aligned DSG saving
from __future__ import annotations
from typing import Literal
from datetime import datetime, UTC

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from langgraph.graph import END

import json

from data_models import State, DesignState, CahierDesCharges, SupervisorDecision
from prompts import SUPERVISOR_PROMPT
from llm_models import supervisor_model
from graph_utils import summarize_design_state_func, visualize_design_state_func
from utils import remove_think_tags, save_dsg


def supervisor_node(state: State) -> Command[Literal["generation", END]]:
    """
    Decide whether the current Design-State Graph is complete and meets requirements,
    and save snapshots under a batch-aligned folder structure.
    """
    print("\n🔎  [Supervisor] invoked")

    # 1) Gather current CDC and DSG --------------------------------------------------
    if not state.cahier_des_charges:
        print("⚠️  no Cahier des Charges → END")
        return Command(goto=END)

    dsg = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    cdc = state.cahier_des_charges
    cdc_js = cdc.model_dump_json() if isinstance(cdc, CahierDesCharges) else json.dumps(cdc or {}, indent=2)

    meta_notes = state.meta_review_notes[-1] if state.meta_review_notes else "No meta-review notes available."
    last_instructions = state.supervisor_instructions[-1] if len(state.supervisor_instructions) > 1 else "No previous instructions."

    # 2) Invoke structured LLM for decision -----------------------------------------
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
{last_instructions}""")
    ])

    status = "✅" if decision.step_completed else "🔄"
    print(f"{status} Design State: {'Complete' if decision.step_completed else 'Needs iteration'}")
    if not decision.step_completed:
        print(f"   Reason: {decision.reason_for_iteration}")

    # 3) Update control flags and iteration counters -------------------------------
    redo_flag = not decision.step_completed
    new_max_iter = max(
        state.max_iterations,
        state.generation_iteration,
        state.reflection_iteration,
        state.ranking_iteration,
        state.evolution_iteration,
    ) + 1

    new_step_index = state.current_step_index
    if decision.step_completed and not decision.workflow_complete:
        new_step_index += 1

    # 4) Determine save folder, aligned with batch/thread_id ------------------------
    # Use the incoming thread_id (which includes batch_id/run_folder_name) as base path
    base_folder = state.thread_id  # set by run_pipeline's thread_id param
    if state.supervisor_visit_counter == 0:
        # on first visit, initialize save folder to thread_id path
        save_folder = base_folder
    else:
        save_folder = state.dsg_save_folder  # persist thereafter

    # 5) Mark workflow completion on DSG --------------------------------------------
    if state.design_graph_history and decision.workflow_complete:
        dsg.workflow_complete = True
        state.design_graph_history[-1] = dsg

    # 6) Save current DSG snapshot --------------------------------------------------
    if state.design_graph_history:
        try:
            dsg_now = state.design_graph_history[-1]
            out_path = save_dsg(
                dsg_now,
                thread_id=save_folder,
                step_idx=state.supervisor_visit_counter,
                save_folder=save_folder,
            )
            print(f"💾 [Supervisor] DSG snapshot saved → {out_path}")
            visualize_design_state_func(dsg_now)
        except Exception as e:
            print(f"⚠️  [Supervisor] failed to save/visualize DSG: {e}")

    # 7) Prepare state update -------------------------------------------------------
    update = {
        "supervisor_instructions": [decision.instructions],
        "redo_work": redo_flag,
        "redo_reason": decision.reason_for_iteration,
        "max_iterations": new_max_iter,
        "current_step_index": new_step_index,
        "supervisor_visit_counter": state.supervisor_visit_counter + 1,
        "dsg_save_folder": save_folder,
        "supervisor_status": f"supervised_{datetime.utcnow().isoformat(timespec='seconds')}"
    }

    goto = "generation" if not decision.workflow_complete else END
    return Command(update=update, goto=goto)
