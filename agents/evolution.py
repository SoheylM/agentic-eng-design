from __future__ import annotations

from typing import List, Optional, Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from data_models  import State, Proposal
from prompts      import EVOLUTION_PROMPT, RESEARCH_PROMPT_EVOLUTION
from llm_models   import evolution_agent, base_model_reasoning
from graph_utils  import summarize_design_state_func
from utils        import remove_think_tags


# ──────────────────────────────────────────────────────────────────────────────
def evolution_node(state: State) -> Command[Literal["orchestrator", "meta_review"]]:
    """
    • Produces evolved DSGs by refining or merging the top-ranked proposals.
    • May request extra research via the Orchestrator.
    • Preserves iteration counters for LangGraph control-flow.
    """
    print("\n🌀 [EVOL] Evolution node")

    iter_now = state.evolution_iteration
    max_iter = state.max_iterations
    print(f"   • iteration {iter_now + 1}/{max_iter}")

    if iter_now >= max_iter:
        print("   ⚠️  max-iterations reached; skipping evolution.")
        return Command(
            update={
                "evolution_notes":   [f"Stopped after {max_iter} evolution loops."],
                "evolution_iteration": iter_now - 1,
            },
            goto="meta_review",
        )

    # ── Context grab ───────────────────────────────────────────────────────
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No supervisor instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    # pick proposals from the latest Ranking pass
    recent_props: List[Proposal] = [
        p for p in state.proposals
        if p.current_step_index          == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
        and p.ranking_iteration_index    == state.ranking_iteration
    ]

    if not recent_props:
        print("   ⚠️  no proposals available → meta-review")
        return Command(
            update={"evolution_notes": ["No proposals to evolve."]},
            goto="meta_review",
        )

    # sort by score (desc) so the LLM sees best first
    recent_props.sort(key=lambda p: (p.grade if p.grade is not None else 0.0), reverse=True)

    briefs = [
        {
            "idx":   i,
            "title": p.title,
            "score": p.grade,
            "feedback": p.feedback or "no feedback",
            "summary": summarize_design_state_func(p.content)
        }
        for i, p in enumerate(recent_props)
    ]

    # ── LLM call ────────────────────────────────────────────────────────────
    evo_out = evolution_agent.invoke([
        SystemMessage(content=EVOLUTION_PROMPT),
        HumanMessage(content=f"""
Supervisor instructions → {sup_instr}

Cahier des Charges → {cdc_text}

Ranked proposal briefs →
{briefs}

Produce refined DSG proposal for each ranked proposal.
""")
    ])

    print(f"   • LLM produced {len(evo_out.evolutions)} evolutions")

    # ── Apply evolutions back into Proposal objects ────────────────────────
    for ev in evo_out.evolutions:
        idx = ev.proposal_index
        if 0 <= idx < len(recent_props):
            prop = recent_props[idx]
            prop.evolved_content          = ev.new_content        # DesignState!
            prop.evolution_justification  = ev.evolution_justification
            prop.evolution_iteration_index = iter_now
            # overwrite DSG with evolved version
            prop.content = ev.new_content
            print(f"     ↳ proposal {idx} evolved")
        else:
            print(f"     ⚠️  invalid proposal index {idx} ignored")

    # ── Need more research? ────────────────────────────────────────────────
    orch_request = _need_more_research_evolution(recent_props, state)

    if orch_request:
        preview = (orch_request[:77] + "…") if len(orch_request) > 80 else orch_request
        print(f"   🧠 requesting research: {preview}")
        return Command(
            update={
                "orchestrator_orders":      [orch_request],
                "current_requesting_agent": "evolution",
                "current_tasks_count":      0,
                "evolution_iteration":      iter_now + 1,
                "evolution_notes":         [f"Research requested at evol-iter {iter_now + 1}"],
            },
            goto="orchestrator",
        )

    # ── Normal exit to Meta-review ─────────────────────────────────────────
    print("   ✅ evolution complete → meta_review")
    return Command(
        update={
            "evolution_iteration": iter_now,
            "evolution_notes":    [f"Completed evol-iter {iter_now}"],
            "current_tasks_count": 0,
        },
        goto="meta_review",
    )


# ──────────────────────────────────────────────────────────────────────────────
def _need_more_research_evolution(
    props: List[Proposal],
    state: State
) -> Optional[str]:
    """Ask an LLM if evolved DSGs need extra research before meta-review."""
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    evo_briefs = [
        {
            "idx":   i,
            "score": p.grade,
            "evo_ex": (p.evolution_justification or "")[:120] + ("…" if p.evolution_justification and len(p.evolution_justification) > 120 else ""),
            "summary": summarize_design_state_func(p.content)[:800]   # token guard
        }
        for i, p in enumerate(props)
    ]

    question = f"""
Supervisor instructions → {sup_instr}

Cahier des Charges → {cdc_text}

Overview of evolved proposals →
{evo_briefs}

Should we perform extra web / code / calc research to validate or improve these evolutions?
If yes, output ONE clear task for the Orchestrator.
If no, answer exactly:  "No additional research is needed."
"""

    resp = base_model_reasoning.invoke([
        SystemMessage(content=RESEARCH_PROMPT_EVOLUTION),
        HumanMessage(content=question),
    ]).content
    resp_clean = remove_think_tags(resp).strip()

    if resp_clean.lower().startswith("no additional research"):
        print("   • no extra research required")
        return None
    print("   • extra research required")
    return resp_clean
