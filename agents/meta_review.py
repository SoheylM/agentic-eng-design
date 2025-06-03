# meta_review_node.py  ─────────────────────────────────────────────────────────
from __future__ import annotations

from typing import List, Optional, Literal
from datetime import datetime, UTC

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from data_models import (
    State,
    Proposal,                 # long-term container (contains DesignState)
)
from prompts import ME_PROMPT
from llm_models import meta_reviewer_agent
from graph_utils import (
    summarize_design_state_func,     # new utility; no LLM involved
)

# ─────────────────────────  M E T A - R E V I E W  N O D E  ──────────────────
def meta_review_node(state: State) -> Command[Literal["supervisor"]]:
    """
    • Analyzes DSG proposals from the Generation agent
    • Selects the best overall solution from the list of proposals
    • Appends the selected DSG to `design_graph_history`
    """
    print("Hello World! 🌍")
    print("\n🔎 [META] Meta-Review node")

    it_now   = state.meta_review_iteration
    max_it   = state.max_iterations
    print(f"   • iteration {it_now + 1}/{max_it}")

    if it_now >= max_it:
        print("   ⚠️  max-iterations reached; skipping meta-review.")
        return Command(
            update={
                "meta_review_notes": [f"Stopped after {max_it} meta-review loops."],
                "meta_review_iteration": it_now - 1,
            },
            goto="supervisor",
        )

    # ── Gather context ─────────────────────────────────────────────────────
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No supervisor instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    recent_props: List[Proposal] = [
        p for p in state.proposals
        if p.current_step_index          == state.supervisor_visit_counter
        and p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_props:
        print("   ⚠️  no proposals to review")
        return Command(
            update={"meta_review_notes": ["No proposals available for meta-review."]},
            goto="supervisor",
        )

    print(f"   • reviewing {len(recent_props)} DSG proposals")

    # Compact summaries for the LLM
    dsg_summaries = [
        {
            "index": idx,
            "title": p.title,
            "summary": summarize_design_state_func(p.content),
            "metrics": p.grade,  # Contains all evaluation metrics
            "ranking_justification": p.ranking_justification,  # Add ranking justification
            "reflection_feedback": p.feedback,  # Add reflection feedback
        }
        for idx, p in enumerate(recent_props)
    ]

    # ── LLM call ────────────────────────────────────────────────────────────
    llm_resp = meta_reviewer_agent.invoke([
        SystemMessage(content=ME_PROMPT),
        HumanMessage(content=f"""
Supervisor instructions:
{sup_instr}

Cahier des Charges:
{cdc_text}

Here are the DSG proposals with their rankings and reflection feedback:
{dsg_summaries}

Analyze these proposals considering the rankings and the feedback as objectives.
Return your final decisions.
""")
    ])

    print(f"   • LLM returned decisions for {len(llm_resp.decisions)} proposals")

    # ── Store decisions & rationale ─────────────────────────────────────────
    for dec in llm_resp.decisions:
        idx = dec.proposal_index
        if 0 <= idx < len(recent_props):
            pr = recent_props[idx]
            pr.status               = dec.final_status
            pr.reason_for_status    = dec.reason
            pr.meta_review_iteration_index = it_now
            print(f"     ↳ proposal {idx} → {dec.final_status}")

    selected_idx = llm_resp.selected_proposal_index
    if 0 <= selected_idx < len(recent_props):
        chosen_prop = recent_props[selected_idx]
        chosen_dsg = chosen_prop.content

        state.design_graph_history.append(chosen_dsg)
        print(f"   ✅ proposal {selected_idx} selected – DSG stored to history")
    else:
        chosen_dsg = None
        print("   ⚠️  no proposal selected")

    # ── Normal exit ────────────────────────────────────────────────────────
    note = llm_resp.detailed_summary_for_graph
    print("   ✅ meta-review complete → supervisor")
    return Command(
        update={
            "selected_proposal_index":  selected_idx,
            "meta_review_notes":       [note],
            "meta_review_iteration":   it_now,
        },
        goto="supervisor",
    )
