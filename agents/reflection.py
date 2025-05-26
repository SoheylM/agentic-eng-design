# reflection_node.py
# ---------------------------------------------------------------------------
#  Reflection agent: critiques each DSG proposal created by the Generation
#  agent, may request extra research through the Orchestrator, and keeps
#  iteration / counter logic identical to the previous workflow.
# ---------------------------------------------------------------------------

from __future__ import annotations

from typing import List, Optional, Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from data_models import (
    State,
    Proposal,                         # contains .content -> DesignState
)
from prompts import REFLECTION_PROMPT, RESEARCH_PROMPT_REFLECTION
from llm_models import reflection_agent, base_model_reasoning
from graph_utils import summarize_design_state_func
from utils import remove_think_tags


# ----------------------------------------------------------------------------
def reflection_node(state: State) -> Command[Literal["orchestrator", "ranking"]]:
    """
    • Critiques each DSG proposal produced by Generation.
    • Optionally asks the Orchestrator for more research.
    • Maintains iteration counters identical to the old workflow.
    """
    print("\n🔎 [REF] Reflection node")

    iter_now = state.reflection_iteration
    max_iter = state.max_iterations
    print(f"   • iteration {iter_now + 1}/{max_iter}")

    # ---------------------------------------------------------------- bailout
    if iter_now >= max_iter:
        print("   ⚠️  max-iterations reached; skipping reflection.")
        return Command(
            update={
                "reflection_notes": [f"Stopped after {max_iter} reflection loops."],
                "reflection_iteration": iter_now - 1,
            },
            goto="ranking",
        )

    # ---------------------------------------------------------------- context
    sup_instr = (
        state.supervisor_instructions[-1]
        if state.supervisor_instructions
        else "No supervisor instructions."
    )
    cdc_text = state.cahier_des_charges or "No Cahier des Charges."

    # proposals from the most recent Generation loop
    recent_props: List[Proposal] = [
        p
        for p in state.proposals
        if p.current_step_index == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_props:
        print("   ⚠️  no proposals available → forward to ranking")
        return Command(
            update={"reflection_notes": ["No proposals to critique."]},
            goto="ranking",
        )

    print(f"   • reviewing {len(recent_props)} DSG proposals")

    # Build a deterministic, fully-detailed text summary for each DSG
    full_summaries = [
        f"### Proposal {idx}: {p.title or 'Untitled'}\n"
        + summarize_design_state_func(p.content)
        for idx, p in enumerate(recent_props)
    ]

    # ---------------------------------------------------------------- LLM call
    llm_resp = reflection_agent.invoke(
        [
            SystemMessage(content=REFLECTION_PROMPT),
            HumanMessage(
                content=(
                    f"Supervisor instructions → {sup_instr}\n\n"
                    f"Cahier des Charges → {cdc_text}\n\n"
                    "# Design-State Graph proposals\n\n"
                    + "\n\n".join(full_summaries)
                    + "\n\nProvide structured feedback for **each** proposal."
                )
            ),
        ]
    )
    llm_resp = remove_think_tags(llm_resp).strip()

    print(f"   • LLM returned {len(llm_resp.reflections)} feedback items")

    # ---------------------------------------------------------------- store feedback
    for item in llm_resp.reflections:
        idx = item.proposal_index
        if 0 <= idx < len(recent_props):
            recent_props[idx].feedback = item.feedback
            recent_props[idx].reflection_iteration_index = iter_now
            print(f"     ↳ feedback stored for proposal {idx}")
        else:
            print(f"     ⚠️  bad index {idx} in LLM output – ignored")

    # ---------------------------------------------------------------- need more research?
    orch_request = _need_more_research_reflection(recent_props, state)

    if orch_request:
        preview = (orch_request[:77] + "…") if len(orch_request) > 80 else orch_request
        print(f"   🧠 requesting research: {preview}")
        return Command(
            update={
                "orchestrator_orders": [orch_request],
                "current_requesting_agent": "reflection",
                "current_tasks_count": 0,
                "reflection_iteration": iter_now + 1,
                "reflection_notes": [f"Research requested at ref-iter {iter_now + 1}"],
            },
            goto="orchestrator",
        )

    # ---------------------------------------------------------------- normal exit
    print("   ✅ reflection complete → ranking")
    return Command(
        update={
            "reflection_iteration": iter_now,
            "reflection_notes": [f"Completed ref-iter {iter_now}"],
            "current_tasks_count": 0,
        },
        goto="ranking",
    )


# ----------------------------------------------------------------------------
def _need_more_research_reflection(
    props: List[Proposal],
    state: State,
) -> Optional[str]:
    """Ask a reasoning LLM whether the critiques require extra research."""
    sup_instr = (
        state.supervisor_instructions[-1]
        if state.supervisor_instructions
        else "No instructions."
    )
    cdc_text = state.cahier_des_charges or "No Cahier des Charges."

    question = f"""
Supervisor instructions → {sup_instr}

Cahier des Charges → {cdc_text}

Current critiques (truncated):
{[
    {
        "idx": i,
        "excerpt": (p.feedback or "")[:120] + ("…" if p.feedback and len(p.feedback) > 120 else ""),
    }
    for i, p in enumerate(props)
]}

Should we commission **additional web / code / calc research** to strengthen these critiques?
If yes, output ONE clear task for the Orchestrator.
If no, answer exactly:  "No additional research is needed."
"""

    resp = base_model_reasoning.invoke(
        [
            SystemMessage(content=RESEARCH_PROMPT_REFLECTION),
            HumanMessage(content=question),
        ]
    ).content
    resp_clean = remove_think_tags(resp).strip()

    if resp_clean.lower().startswith("no additional research"):
        print("   • no extra research required")
        return None
    print("   • extra research required")
    return resp_clean
