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
from prompts import ME_PROMPT, RESEARCH_PROMPT_META_REVIEW
from llm_models import meta_reviewer_agent, base_model_reasoning
from graph_utils import (
    summarize_design_state_func,
    visualize_design_state_func,       # new utility; no LLM involved
)
from utils import remove_think_tags, save_dsg

# ─────────────────────────  M E T A - R E V I E W  N O D E  ──────────────────
def meta_review_node(state: State) -> Command[Literal["orchestrator", "supervisor"]]:
    """
    • Chooses the best DSG proposal.
    • Writes final statuses + rationale into proposals.
    • Optionally requests extra research via Orchestrator.
    • Appends the selected DSG to `design_graph_history`.
    """
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
        if p.current_step_index        == state.current_step_index
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
            "reflection": p.feedback or "No reflection feedback.",
            "grade": p.grade if p.grade is not None else "Not yet scored",
            "evolved": (bool(p.evolved_content) and "Yes") or "No",
        }
        for idx, p in enumerate(recent_props)
    ]

    # ── LLM call ────────────────────────────────────────────────────────────
    llm_resp = meta_reviewer_agent.invoke([
        SystemMessage(content=ME_PROMPT),
        HumanMessage(content=f"""
Supervisor instructions →
{sup_instr}

Cahier des Charges →
{cdc_text}

Here are the DSG proposals (one block per proposal):
{dsg_summaries}

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
        chosen_dsg = recent_props[selected_idx].content
        # append to history & visualise
        state.design_graph_history.append(chosen_dsg)
        print(f"   ✅ proposal {selected_idx} selected - DSG stored to history")
        visualize_design_state_func(chosen_dsg)      # optional GUI pop-up
    else:
        chosen_dsg = None
        print("   ⚠️  no proposal selected")

    # ── after all meta-review logic, just before the normal return ──────────────
    # save latest DSG snapshot ---------------------------------------------------
    try:
        dsg_now = state.design_graph_history[-1]              # last graph

        # ① thread-id is written into State once at workflow launch
        thread_id = getattr(state, "thread_id", "unnamed_run")

        out = save_dsg(
            dsg_now,
            thread_id = thread_id,
            step_idx  = state.current_step_index,
            meta_iter = it_now,                               # current meta-iteration
        )
        print(f"💾 [Meta-Review] DSG snapshot saved → {out}")
    except Exception as e:
        print(f"⚠️  [Meta-Review] failed to save DSG: {e}")


    # ── Extra research? ────────────────────────────────────────────────────
    orch_req = _need_more_research_meta(state, chosen_dsg, dsg_summaries)

    if orch_req:
        preview = (orch_req[:77] + "…") if len(orch_req) > 80 else orch_req
        print(f"   🧠 requesting research: {preview}")
        return Command(
            update={
                "orchestrator_orders":      [orch_req],
                "current_requesting_agent": "meta_review",
                "current_tasks_count":      0,
                "meta_review_iteration":    it_now + 1,
                "meta_review_notes":        ["Research requested by meta-review"],
            },
            goto="orchestrator",
        )

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


# ───────────────────────  R E S E A R C H   C H E C K  ───────────────────────
def _need_more_research_meta(
    state: State,
    chosen_dsg,                      # DesignState | None
    summaries                         # list of dict (for context)
) -> Optional[str]:
    """Ask a reasoning model if the final choice needs extra validation."""
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    question = f"""
Supervisor instructions → {sup_instr}

Cahier des Charges → {cdc_text}

Chosen DSG summary →
{summarize_design_state_func(chosen_dsg) if chosen_dsg else "None selected"}

Other proposal overviews →
{summaries}

Do we need **additional web / simulation / data research** to confirm this final decision?
If yes, output ONE clear task for the Orchestrator.
If no, answer exactly: "No additional research is needed."
"""

    resp = base_model_reasoning.invoke([
        SystemMessage(content=RESEARCH_PROMPT_META_REVIEW),
        HumanMessage(content=question),
    ]).content

    clean = remove_think_tags(resp).strip()
    if clean.lower().startswith("no additional research"):
        print("   • no extra research required")
        return None
    print("   • extra research required")
    return clean
