# agents/generation_pair.py
from typing import List, Literal
from langgraph.types import Command
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from data_models import PairState
from llm_models import pair_generation_agent
from prompts import GE_PAIR_PROMPT
from IPython.display import display, Markdown
from graph_utils import summarize_design_state_func
from utils import remove_think_tags
from eval_saved import evaluate_dsg  # Import the evaluation function
from validation import filter_valid_proposals  # Import our validation functions
from data_models import Proposal

def generation_pair_node(state: PairState) -> Command[Literal["reflection_pair"]]:
    """
    • Generates *N* DSG proposals (defined in GE_PROMPT_STRUCTURED).
    """
    print("\n🔧 [GEN] Generation pair node")
    # ── Counters ────────────────────────────────────────────────────────────
    iter_now      = state.generation_iteration
    print(f"   • iteration {iter_now + 1}")

    # just a mechanism to save the user request in the first pass
    # I guess I will not need cdc_text
    first_pass = state.first_pass
    if first_pass: 
        user_request = state.messages[-1]
    else:
        user_request = state.user_request

    # ── Context strings for the LLM ────────────────────────────────────────
    graph_now   = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    graph_sum   = summarize_design_state_func(graph_now)

    human_msg = f"""
        User request:
        {user_request}

        Current DSG summary:
        {graph_sum}

        Generate **DSG proposals**.
        """
    

    # ── LLM call (structured) ──────────────────────────────────────────────
    llm_out = pair_generation_agent.invoke([
        SystemMessage(content=GE_PAIR_PROMPT),
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
            current_step_index=state.supervisor_visit_counter,  # Add current step index
            generation_iteration_index=iter_now,
            reflection_iteration_index=state.reflection_iteration,
            ranking_iteration_index=state.ranking_iteration,
            evolution_iteration_index=state.evolution_iteration,
            meta_review_iteration_index=state.meta_review_iteration
        )
        for i, p in enumerate(dsg_proposals)
    ]

    # Otherwise go straight to reflection
    print(" ✅ generation complete → reflection")
    return Command(
        update={
            "proposals":          new_entries,
            "user_request": user_request,
            "first_pass": False,
            "generation_iteration": iter_now + 1,              # keep counter
        },
        goto="reflection_pair",
    )
        
