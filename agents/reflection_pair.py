"""
Reflection stage for the 2-agent ablation loop.

• Reads the latest proposal that `generation_pair` dropped in state.proposal[-1]
• Produces structured feedback
• If the feedback contains the *exact* sentinel phrase "Garde la peche"
  → the workflow terminates (goto=END)
• Otherwise the loop continues (goto="generation_pair")
"""

from typing import List, Literal
from langgraph.types import Command
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from data_models import PairState
from llm_models import pair_reflection_agent
from prompts import RE_PAIR_PROMPT
from IPython.display import display, Markdown
from langgraph.graph import MessagesState, StateGraph, START, END
from data_models import Proposal

def reflection_pair_node(state: PairState) -> Command[Literal["generation_pair", END]]:
    """
    • Critiques each DSG proposal produced by Generation.
    """
    print("\n🔎 [REF] Reflection pair node")

    iter_now = state.reflection_iteration
    print(f"   • iteration {iter_now + 1}")

    user_request = state.user_request
    # proposals from the most recent Generation loop
    recent_props: List[Proposal] = [
        p
        for p in state.proposals
        if p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_props:
        print("   ⚠️  no proposals available → forward to generation")
        return Command(
            update={"reflection_notes": ["No proposals to critique."]},
            goto="generation_pair",
        )

    print(f"   • reviewing {len(recent_props)} DSG proposals")
    # Build a deterministic, fully-detailed text summary for each DSG
    full_summaries = [
        f"### Proposal {idx}: {p.title or 'Untitled'}\n"
        + summarize_design_state_func(p.content)
        for idx, p in enumerate(recent_props)
    ]

    llm_resp = pair_reflection_agent.invoke(
        [
            SystemMessage(content=RE_PAIR_PROMPT),
            HumanMessage(
                content=(
                    f"User request: {user_request}\n\n"
                    "# Design-State Graph proposals\n\n"
                    + "\n\n".join(full_summaries)
                    + "\n\nProvide structured feedback for **each** proposal."
                )
            ),
        ]
    )

    #proposal_index: int = Field(..., description="Index of the proposal to which this reflection applies")
    #feedback: str = Field(..., description="Critical review or suggestions about the proposal")
    #workflow_complete: bool = Field(False, description="Indicates whether the workflow is complete. Only trigger True when the workflow is complete.")
    #final_status: str = Field(..., description="Final decision (selected, rejected, or needs more iteration)")
    #reason: str = Field(..., description="Rationale for the decision")

    print(f"   • LLM returned {len(llm_resp.reflections)} feedback items")

    for item in llm_resp.reflections:
        idx = item.proposal_index
        if 0 <= idx < len(recent_props):
            recent_props[idx].feedback = item.feedback
            recent_props[idx].reflection_iteration_index = iter_now
            print(f"     ↳ feedback stored for proposal {idx}")
            recent_props[idx].status               = item.final_status
            recent_props[idx].reason_for_status    = item.reason
            print(f"     ↳ proposal {idx} → {item.final_status}")
        else:
            print(f"     ⚠️  bad index {idx} in LLM output – ignored")

    selected_idx = llm_resp.selected_proposal_index
    if 0 <= selected_idx < len(recent_props):
        chosen_prop = recent_props[selected_idx]
        chosen_dsg = chosen_prop.content

        state.design_graph_history.append(chosen_dsg)
        print(f"   ✅ proposal {selected_idx} selected – DSG stored to history")
    else:
        chosen_dsg = None
        print("   ⚠️  no proposal selected")

    note_to_improve = llm_resp.detailed_summary_for_graph
    print(f"   • LLM returned detailed summary for improving graph: {note_to_improve}")

    workflow_complete = llm_resp.workflow_complete
    print(f"   • LLM returned workflow complete: {workflow_complete}")

    update={
            "selected_proposal_index":  selected_idx,
            "detailed_summary_for_graph":       [note_to_improve],
            "workflow_complete":   workflow_complete,
            "reflection_iteration": iter_now + 1,
        },

    goto = "generation_pair" if not workflow_complete else END
    return Command(update=update, goto=goto)

