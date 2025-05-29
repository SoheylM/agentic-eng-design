# generation_node.py  (or wherever you register the vertex)

from __future__ import annotations

from typing import List, Optional, Literal
import tempfile
from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from data_models import (
    State,
    DesignState,
    SingleProposal,          # title + DSG
    Proposal,                # full life-cycle container
)
from prompts import GE_PROMPT_STRUCTURED, GEN_RESEARCH_PROMPT
from llm_models import generation_agent, base_model_reasoning
from graph_utils import summarize_design_state_func
from utils import remove_think_tags
from eval_saved import evaluate_dsg  # Import the evaluation function
from validation import filter_valid_proposals  # Import our validation functions


def generation_node(state: State) -> Command[Literal["orchestrator", "reflection"]]:
    """
    • Generates *N* DSG proposals (defined in GE_PROMPT_STRUCTURED).
    • Decides if extra research is needed.
    • Updates State counters so the Supervisor / Orchestrator loops work identically
      to the previous implementation.
    """
    print("\n🔧 [GEN] Generation node")

    # ── Counters ────────────────────────────────────────────────────────────
    iter_now      = state.generation_iteration
    max_iter      = state.max_iterations
    worker_budget = state.current_tasks_count       # how many analyses we expected

    print(f"   • iteration {iter_now + 1}/{max_iter}")

    if iter_now >= max_iter:
        # Bail-out protection → go straight to reflection
        print("   ⚠️  max-iterations reached; skipping generation.")
        return Command(
            update={
                "generation_notes": [f"Stopped after {max_iter} generation loops."],
                "generation_iteration": iter_now - 1,   # ← keep last valid index
            },
            goto="reflection",
        )

    # ── Context strings for the LLM ────────────────────────────────────────
    sup_instr   = state.supervisor_instructions[-1] if state.supervisor_instructions else "No supervisor instructions."
    cdc_text    = state.cahier_des_charges or "No Cahier des Charges."
    graph_now   = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    graph_sum   = summarize_design_state_func(graph_now)

    # ── Attach worker analyses (if any)──────────────────────────────────────
    analyses = [
        a for a in state.analyses
        if a.called_by_agent == "generation"
    ][-worker_budget:]

    if analyses:
        print(f"Integrating {len(analyses)} worker analyses")
        analysis_block = "\n\n---\n\n".join(
            f"From *{a.from_task}*:\n{a.content}" for a in analyses
        )
        human_msg = f"""
Supervisor → {sup_instr}

Cahier des Charges →
{cdc_text}

Current DSG summary →
{graph_sum}

Worker analyses →
{analysis_block}

Please (re)generate **precise DSG proposals** accordingly.
"""
    else:
        human_msg = f"""
Cahier des Charges →
{cdc_text}

Supervisor instructions →
{sup_instr}

Current DSG summary →
{graph_sum}

Generate **brand-new DSG proposals** (no refinement loop).
"""

    # ── LLM call (structured) ──────────────────────────────────────────────
    llm_out = generation_agent.invoke([
        SystemMessage(content=GE_PROMPT_STRUCTURED),
        HumanMessage(content=human_msg.strip()),
    ])

    dsg_proposals: List[SingleProposal] = llm_out.proposals
    print(f"LLM returned {len(dsg_proposals)} DSGs")
    
    # Validate and sanitize proposals
    valid_proposals = filter_valid_proposals(dsg_proposals)
    if len(valid_proposals) < len(dsg_proposals):
        print(f"⚠️  Filtered out {len(dsg_proposals) - len(valid_proposals)} invalid proposals")
        dsg_proposals = valid_proposals
        if not dsg_proposals:
            print("❌ No valid proposals remaining after filtering")
            return Command(
                update={
                    "generation_notes": ["No valid proposals generated. Retrying..."],
                    "generation_iteration": iter_now + 1,
                },
                goto="generation",
            )

    # ── Wrap into long-term `Proposal` objects and update State ────────────
    new_entries: List[Proposal] = [
        Proposal(
            title=p.title,
            content=p.content,                 # ← the DesignState object
            status="generated",
            current_step_index=state.current_step_index,  # Add current step index
            generation_iteration_index=iter_now,
            reflection_iteration_index=state.reflection_iteration,
            ranking_iteration_index=state.ranking_iteration,
            evolution_iteration_index=state.evolution_iteration,
            meta_review_iteration_index=state.meta_review_iteration
        )
        for i, p in enumerate(dsg_proposals)
    ]

    # ── Decide on extra research (optional orchestrator hop) ───────────────
    orch_request = _need_more_research(dsg_proposals, state)

    if orch_request:
        # Ask Orchestrator, bump counters so the loop calls us again later
        print(f"🧠 requesting research: {orch_request[:80]}…")
        return Command(
            update={
                "proposals":            new_entries,
                "orchestrator_orders":  [orch_request],
                "current_requesting_agent": "generation",
                "current_tasks_count":  0,                 # new tasks will be counted by orchestrator
                "generation_iteration": iter_now + 1,      # next pass
                "generation_notes":    [f"Research requested at gen-iter {iter_now + 1}"],
            },
            goto="orchestrator",
        )

    # Otherwise go straight to reflection
    print(" ✅ generation complete → reflection")
    return Command(
        update={
            "proposals":          new_entries,
            "generation_notes":  [f"Finished gen-iter {iter_now}"],
            "generation_iteration": iter_now,              # keep counter
        },
        goto="reflection",
    )

# --------------------------------------------------------------------------
def _need_more_research(props: List[SingleProposal], state: State) -> Optional[str]:
    """Ask a reasoning LLM whether extra data/tools are required."""
    sup_instr = state.supervisor_instructions[-1] if state.supervisor_instructions else "No instructions."
    cdc_text  = state.cahier_des_charges or "No Cahier des Charges."

    question = f"""
Supervisor instructions → {sup_instr}

Cahier des Charges → {cdc_text}

Here are the DSG proposals (titles + node counts):

{[
    {"title": p.title,
     "n_nodes": len(p.content.nodes),
     "n_edges": len(p.content.edges)}
    for p in props
]}

Should we perform **additional web / code / calc research** before sending these to reflection?
If yes, output a SINGLE clear task for the orchestrator.
If no, answer exactly:  "No additional research is needed."
"""

    resp = base_model_reasoning.invoke([
        SystemMessage(content=GEN_RESEARCH_PROMPT),
        HumanMessage(content=question)
    ]).content
    resp_clean = remove_think_tags(resp).strip()

    if resp_clean.lower().startswith("no additional research"):
        print("No extra research required")
        return None
    print("Extra research required")
    return resp_clean
