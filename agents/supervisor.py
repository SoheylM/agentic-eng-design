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


# ─────────────────────────────────────────────────────────────────────────────
def supervisor_node(state: State) -> Command[Literal["generation", END]]:
    """
    Decide whether the current Design-Plan step is complete.
    *No* second refinement pass; counters behave exactly like the
    original long version you had.
    """

    print("\n🔎  [Supervisor] invoked")

    # 1) plan + step ------------------------------------------------------------
    if not state.design_plan:
        print("⚠️  no DesignPlan → END")
        return Command(goto=END)

    steps = state.design_plan.steps
    idx   = state.current_step_index
    if idx >= len(steps):
        print("🎉 all steps done")
        return Command(goto=END)

    step   = steps[idx]
    dsg    = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    cdc    = state.cahier_des_charges
    cdc_js = (cdc.model_dump_json() if isinstance(cdc, CahierDesCharges)
              else json.dumps(cdc or {}, indent=2))

    # 2) structured LLM call ---------------------------------------------------
    decision: SupervisorDecision = supervisor_model.invoke([
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=f"""
### Current step
ID: {step.step_id}
Name: {step.name}
Objectives: {step.objectives}
Expected outputs: {step.expected_outputs}

### Design-State Graph (summary)
{summarize_design_state_func(dsg)}

### Cahier-des-Charges
{cdc_js}
""")
    ])

    # Print concise decision summary
    status = "✅" if decision.step_completed else "🔄"
    print(f"{status} Step {step.step_id} ({step.name}): {'Completed' if decision.step_completed else 'Needs iteration'}")
    if not decision.step_completed:
        print(f"   Reason: {decision.reason_for_iteration}")

    # 3) counter / flag maintenance --------------------------------------------
    next_idx   = idx + 1 if decision.step_completed else idx
    redo_flag  = not decision.step_completed

    # keep max_iterations monotonically increasing so other agents
    # never see 0/0
    new_max_iter = max(
        state.max_iterations,
        state.generation_iteration,
        state.reflection_iteration,
        state.ranking_iteration,
        state.evolution_iteration,
    ) + 1

    update = {
        "supervisor_instructions": [decision.instructions],
        "current_step_index": next_idx,
        "redo_work": redo_flag,
        "redo_reason": decision.reason_for_iteration,
        "max_iterations": new_max_iter,
        # trace for debugging
        "supervisor_status": f"step{idx}_decided_{datetime.utcnow().isoformat(timespec='seconds')}",
    }

    goto = "generation" if next_idx < len(steps) and not decision.workflow_complete else END
    return Command(update=update, goto=goto)
