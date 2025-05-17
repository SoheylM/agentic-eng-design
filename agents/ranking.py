# ranking_node.py
from __future__ import annotations

from typing import List, Optional, Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from data_models import (
    State,
    Proposal,          # long-term container (content is a DesignState)
    SingleRanking,     # pydantic model for one score
)
from prompts import RA_PROMPT, RESEARCH_PROMPT_RANKING
from llm_models import ranking_agent, base_model_reasoning
from utils import remove_think_tags


# ──────────────────────────────────────────────────────────────────────────────
def ranking_node(state: State) -> Command[Literal["orchestrator", "evolution"]]:
    """Score each DSG proposal, possibly ask for extra research, update counters."""
    print("\n🔺 [RANK] Ranking node")

    iter_now = state.ranking_iteration
    max_iter = state.max_iterations
    print(f"   • iteration {iter_now + 1}/{max_iter}")

    if iter_now >= max_iter:
        print("   ⚠️  max-iterations reached; skipping ranking.")
        return Command(
            update={
                "ranking_notes": [f"Stopped after {max_iter} ranking loops."],
                "ranking_iteration": iter_now - 1,
            },
            goto="evolution",
        )

    # ---------------------------------------------------------------- context
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No supervisor instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    recent_props: List[Proposal] = [
        p for p in state.proposals
        if p.current_step_index        == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_props:
        print("   ⚠️  no proposals → forward to evolution")
        return Command(
            update={"ranking_notes": ["No proposals to rank."]},
            goto="evolution",
        )

    print(f"   • ranking {len(recent_props)} proposals")

    # compact summary for LLM
    prop_briefs = [
        {
            "index": i,
            "title": p.title,
            "n_nodes": len(p.content.nodes),
            "n_edges": len(p.content.edges),
            "prev_score": p.grade,
            "feedback": p.feedback or "None",
        }
        for i, p in enumerate(recent_props)
    ]

    # ---------------------------------------------------------------- LLM call
    llm_resp = ranking_agent.invoke([
        SystemMessage(content=RA_PROMPT),
        HumanMessage(content=f"""
Supervisor instructions → {sup_instr}

Cahier des Charges → {cdc_text}

Proposal briefs →
{prop_briefs}

Return JSON 'rankings' per the schema.
""")
    ])

    print(f"   • LLM produced {len(llm_resp.rankings)} scores")

    # ---------------------------------------------------------------- store scores
    for r in llm_resp.rankings:
        idx = r.proposal_index
        if 0 <= idx < len(recent_props):
            recent_props[idx].grade                   = r.grade
            recent_props[idx].ranking_justification   = r.ranking_justification
            recent_props[idx].ranking_iteration_index = iter_now
            print(f"     ↳ proposal {idx} → {r.grade:.2f}")
        else:
            print(f"     ⚠️  invalid index {idx} ignored")

    # ---------------------------------------------------------------- research?
    orch_request = _need_more_research_ranking(recent_props, state)

    if orch_request:
        preview = (orch_request[:77] + "…") if len(orch_request) > 80 else orch_request
        print(f"   🧠 requesting research: {preview}")
        return Command(
            update={
                "orchestrator_orders":  [orch_request],
                "current_requesting_agent": "ranking",
                "current_tasks_count": 0,
                "ranking_iteration":  iter_now + 1,
                "ranking_notes":     [f"Research requested at rank-iter {iter_now + 1}"],
            },
            goto="orchestrator",
        )

    # normal exit
    print("   ✅ ranking complete → evolution")
    return Command(
        update={
            "ranking_iteration": iter_now,
            "ranking_notes":    [f"Completed rank-iter {iter_now}"],
            "current_tasks_count": 0,
        },
        goto="evolution",
    )

# ──────────────────────────────────────────────────────────────────────────────
def _need_more_research_ranking(
    props: List[Proposal],
    state: State,
) -> Optional[str]:
    """Ask an LLM if extra data/tools are needed to justify the scores."""
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    question = f"""
Supervisor instructions → {sup_instr}

Cahier des Charges → {cdc_text}

Current rankings (truncated):
{[
    {"idx": i,
     "score": p.grade,
     "excerpt": (p.ranking_justification or "")[:120] + ("…" if p.ranking_justification and len(p.ranking_justification) > 120 else "")}
    for i, p in enumerate(props)
]}

Should we request **additional web / code / calc research** to improve confidence in these scores?
If yes, output ONE clear task line for the Orchestrator.
If no, answer exactly:  "No additional research is needed."
"""

    resp = base_model_reasoning.invoke([
        SystemMessage(content=RESEARCH_PROMPT_RANKING),
        HumanMessage(content=question),
    ]).content

    clean = remove_think_tags(resp).strip()
    if clean.lower().startswith("no additional research"):
        print("   • no extra research required")
        return None
    print("   • extra research required")
    return clean
