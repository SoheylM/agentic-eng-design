from __future__ import annotations

from typing import List, Optional, Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from data_models import State, Proposal                           # long-term container
from prompts      import RA_PROMPT, RESEARCH_PROMPT_RANKING
from llm_models   import ranking_agent, base_model_reasoning
from graph_utils  import summarize_design_state_func
from utils        import remove_think_tags


# ──────────────────────────────────────────────────────────────────────────────
def ranking_node(state: State) -> Command[Literal["orchestrator", "meta_review"]]:
    """
    • Assigns / updates numeric scores for each DSG proposal.
    • May ask the Orchestrator for extra research to validate rankings.
    • Keeps all iteration counters compatible with the rest of the LangGraph.
    """
    print("\n🔺 [RANK] Ranking node")

    iter_now  = state.ranking_iteration
    max_iter  = state.max_iterations
    print(f"   • iteration {iter_now + 1}/{max_iter}")

    if iter_now >= max_iter:
        print("   ⚠️  max-iterations reached; skipping ranking.")
        return Command(
            update={
                "ranking_notes":   [f"Stopped after {max_iter} ranking loops."],
                "ranking_iteration": iter_now - 1,
                "analyses":        [],
            },
            goto="meta_review",
        )

    # ── Context strings ────────────────────────────────────────────────────
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No supervisor instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    # proposals produced in the latest Generation pass (and critiqued in Reflection)
    recent_props: List[Proposal] = [
        p for p in state.proposals
        if p.current_step_index          == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_props:
        print("   ⚠️  no proposals available → meta_review")
        return Command(
            update={"ranking_notes": ["No proposals to rank."]},
            goto="meta_review",
        )

    # short, but information-dense briefs for the LLM
    prop_briefs = [
        {
            "idx":        i,
            "title":      p.title,
            "prev_score": p.grade,
            "feedback":   (p.feedback or "no feedback"),
            "summary":    summarize_design_state_func(p.content)
        }
        for i, p in enumerate(recent_props)
    ]

    # ── LLM call (structured output expected) ──────────────────────────────
    rk_out = ranking_agent.invoke([
        SystemMessage(content=RA_PROMPT),
        HumanMessage(content=f"""
Supervisor instructions: {sup_instr}

Cahier des Charges: {cdc_text}

Proposal briefs:
{prop_briefs}
""")
    ])

    print(f"   • LLM produced {len(rk_out.rankings)} ranking items")

    # ── Store scores & justifications back into Proposal objects ───────────
    for r in rk_out.rankings:
        if 0 <= r.proposal_index < len(recent_props):
            prop = recent_props[r.proposal_index]
            prop.grade                   = r.grade
            prop.ranking_justification   = r.ranking_justification
            prop.ranking_iteration_index = iter_now
            print(f"     ↳ proposal {r.proposal_index} scored {r.grade}")
        else:
            print(f"     ⚠️  invalid proposal index {r.proposal_index} ignored")

    # ── Extra research? ────────────────────────────────────────────────────
    orch_request = _need_more_research_ranking(recent_props, state)

    if orch_request:
        preview = (orch_request[:77] + "…") if len(orch_request) > 80 else orch_request
        print(f"   🧠 requesting research: {preview}")
        return Command(
            update={
                "orchestrator_orders":      [orch_request],
                "current_requesting_agent": "ranking",
                "current_tasks_count":      0,
                "ranking_iteration":        iter_now + 1,
                "ranking_notes":           [f"Research requested at rank-iter {iter_now + 1}"],
            },
            goto="orchestrator",
        )

    # ── Normal exit to meta_review ───────────────────────────────────────────
    print("   ✅ ranking complete → meta_review")
    return Command(
        update={
            "ranking_iteration": iter_now,
            "ranking_notes":    [f"Completed rank-iter {iter_now}"],
            "current_tasks_count": 0,
        },
        goto="meta_review",
    )


# ──────────────────────────────────────────────────────────────────────────────
def _need_more_research_ranking(
    props: List[Proposal],
    state: State
) -> Optional[str]:
    """Ask an LLM whether the ranking stage needs more external research."""
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    critique_overview = [
        {
            "idx":   i,
            "score": p.grade,
            "justif_excerpt": (p.ranking_justification or "")[:120] + ("…" if p.ranking_justification and len(p.ranking_justification) > 120 else ""),
            "summary": summarize_design_state_func(p.content)[:800]   # token guard
        }
        for i, p in enumerate(props)
    ]

    question = f"""
Supervisor instructions: {sup_instr}

Cahier des Charges: {cdc_text}

Current ranking overview:
{critique_overview}

Should we commission **additional web / code / calc research** to improve the validity of these rankings?
If yes, output ONE clear task for the Orchestrator.
If no, answer exactly:  "No additional research is needed."
"""

    resp = base_model_reasoning.invoke([
        SystemMessage(content=RESEARCH_PROMPT_RANKING),
        HumanMessage(content=question),
    ]).content
    resp_clean = remove_think_tags(resp).strip()

    if resp_clean.lower().startswith("no additional research"):
        print("   • no extra research required")
        return None

    print("   • extra research required")
    return resp_clean
