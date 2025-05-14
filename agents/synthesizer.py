# synthesizer.py  ────────────────────────────────────────────────────────────
from typing import Literal, List

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from llm_models import synthesizer_llm, base_model_reasoning
from data_models  import (
    State,
    Proposal,
    DesignState,
    NodeOp,   # NEW dataclass names
    EdgeOp,
)
from prompts     import SY_PROMPT, SUMMARY_REFINEMENT_PROMPT
from utils       import remove_think_tags
from graph_utils import summarize_design_state_func


# ────────────────────────────────────────────────────────────────────────────
def synthesizer_node(state: State) -> Command[Literal["graph_designer"]]:
    """
    Synthesizer Agent
    · Takes the supervisor-selected proposal.
    · Produces lists of NodeOp / EdgeOp that will later be applied
      by the Graph-Designer.
    """

    print("\n🔔 [DEBUG] Synthesizer node invoked.")

    # ------------------------------------------------------------------ 0. Gather context
    supervisor_instructions = (
        "\n".join(state.supervisor_instructions) if state.supervisor_instructions else
        "No specific guidance provided."
    )
    cahier_des_charges_summary = state.cahier_des_charges or "No formal constraints provided."

    # Locate the **selected** proposal in the current step
    recent: List[Proposal] = [
        p for p in state.proposals
        if p.current_step_index       == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]
    selected = next((p for p in recent if p.status == "selected"), None)

    if not selected:
        print("⚠️  [DEBUG] No selected proposal found – skipping synthesis.")
        return Command(
            update={"synthesizer_notes": ["No selected proposal for synthesis."]},
            goto="graph_designer",
        )

    # Current graph snapshot (empty if first round)
    current_graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    graph_summary = summarize_design_state_func(current_graph)

    # ------------------------------------------------------------------ 1. Ask LLM for ops
    print("🔄 [DEBUG] Calling Synthesizer LLM for structured NodeOps / EdgeOps …")

    synth_output = synthesizer_llm.invoke(
        [
            SystemMessage(content=SY_PROMPT),
            HumanMessage(
                content=f"""
### Supervisor instructions
{supervisor_instructions}

### Cahier des Charges (summary)
{cahier_des_charges_summary}

### Selected proposal (post-evolution)
{selected.evolved_content or selected.content}

### Current Design Graph (summary)
{graph_summary}

---
## Your tasks
1. Analyse the proposal and decide what graph changes are required.
2. Return them **strictly** as NodeOp / EdgeOp lists that match the provided JSON schema.
"""
            ),
        ]
    )

    print("✅  [DEBUG] Synthesizer LLM responded with {len(synth_output.nodes)} NodeOps "
          f"and {len(synth_output.edges)} EdgeOps.")

    # ------------------------------------------------------------------ 2. Refine textual summary (OPTIONAL but useful)
    refined_summary = _refine_summary(selected, state, synth_output.summary_explanation)

    # ------------------------------------------------------------------ 3. Push ops to State so Graph-Designer can consume them
    return Command(
        update={
            "synthesizer_notes":  [refined_summary],
            "pending_node_ops":  [synth_output.nodes],  # List[NodeOp]
            "pending_edge_ops":  [synth_output.edges],  # List[EdgeOp]
        },
        goto="graph_designer",
    )


# ────────────────────────────────────────────────────────────────────────────
def _refine_summary(proposal: Proposal, state: State, raw: str) -> str:
    """One extra LLM call to polish the human-readable explanation."""
    print("📝 [DEBUG] Refining Synthesizer summary explanation …")

    supervisor_instructions = (
        state.supervisor_instructions[-1] if state.supervisor_instructions else
        "No specific instructions provided."
    )
    cahier = state.cahier_des_charges or "No formal constraints provided."

    prompt = [
        SystemMessage(content=SUMMARY_REFINEMENT_PROMPT),
        HumanMessage(
            content=f"""
### Supervisor instructions
{supervisor_instructions}

### Cahier des Charges
{cahier}

### Proposal content
{proposal.evolved_content or proposal.content}

### Raw summary to refine
{raw}

---
Return a concise, well-structured refinement.  No additional markup.
"""
        ),
    ]

    refined = remove_think_tags(base_model_reasoning.invoke(prompt).content)
    return refined
