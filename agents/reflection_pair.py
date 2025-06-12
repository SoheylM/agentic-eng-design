from typing import List, Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage
from data_models import PairState, Proposal
from llm_models import pair_reflection_agent
from prompts import RE_PAIR_PROMPT
from graph_utils import summarize_design_state_func, visualize_design_state_func
from utils import save_dsg
from langgraph.graph import END


def reflection_pair_node(state: PairState) -> Command[Literal["generation_pair", END]]:
    """
    Critiques DSG proposals and saves snapshots into the unified batch/run folder.
    """
    print("\n🔎 [REF] Reflection pair node")
    print(f"   • Number of proposals in state: {len(state.proposals)}")
    print(f"   • Current generation iteration: {state.generation_iteration}")

    iter_now = state.reflection_iteration
    print(f"   • iteration {iter_now + 1}")

    # Determine save folder: first use existing, else thread_id (batch/run)
    save_folder = state.dsg_save_folder or state.thread_id

    # Filter proposals from the most recent generation
    recent_props: List[Proposal] = [
        p for p in state.proposals
        if p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_props:
        print("   ⚠️  no proposals available → forward to generation")
        return Command(
            update={"reflection_notes": ["No proposals to critique."],
                    "dsg_save_folder": save_folder},
            goto="generation_pair",
        )

    # Build summaries
    full_summaries = [
        f"### Proposal {idx}: {p.title or 'Untitled'}\n"
        + summarize_design_state_func(p.content)
        for idx, p in enumerate(recent_props)
    ]

    llm_resp = pair_reflection_agent.invoke([
        SystemMessage(content=RE_PAIR_PROMPT),
        HumanMessage(
            content=(
                f"User request: {state.user_request}\n\n"
                "# Design-State Graph proposals\n\n"
                + "\n\n".join(full_summaries)
                + "\n\nProvide structured feedback for **each** proposal."
            )
        ),
    ])

    # Attach feedback and status
    for item in llm_resp.reflections:
        idx = item.proposal_index
        if 0 <= idx < len(recent_props):
            prop = recent_props[idx]
            prop.feedback = item.feedback
            prop.reflection_iteration_index = iter_now
            prop.status = item.final_status
            prop.reason_for_status = item.reason
            print(f"     ↳ proposal {idx} → {item.final_status}")
        else:
            print(f"     ⚠️  bad index {idx} in LLM output – ignored")

    selected_idx = llm_resp.selected_proposal_index
    chosen_dsg = None
    if 0 <= selected_idx < len(recent_props):
        chosen_prop = recent_props[selected_idx]
        chosen_dsg = chosen_prop.content
        print(f"   ✅ proposal {selected_idx} selected – storing DSG snapshot")
    else:
        print("   ⚠️  no valid proposal selected")

    # Save chosen DSG snapshot
    if chosen_dsg is not None:
        try:
            out_path = save_dsg(
                chosen_dsg,
                thread_id=save_folder,
                step_idx=iter_now,
                save_folder=save_folder,
            )
            print(f"💾 [Reflection] DSG snapshot saved → {out_path}")
            visualize_design_state_func(chosen_dsg)
        except Exception as e:
            print(f"⚠️  [Reflection] failed to save/visualize DSG: {e}")

    # Prepare state updates
    update: dict = {
        "selected_proposal_index": selected_idx,
        "workflow_complete": llm_resp.workflow_complete,
        "reflection_iteration": iter_now + 1,
        "dsg_save_folder": save_folder,
    }
    if chosen_dsg is not None:
        update["design_graph_history"] = [chosen_dsg]
        update["detailed_summary_for_graph"] = [llm_resp.detailed_summary_for_graph]

    goto = "generation_pair" if not llm_resp.workflow_complete else END
    return Command(update=update, goto=goto)
