# agents/generation_pair.py
from typing import List, Literal
from langgraph.types import Command
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from data_models import PairState, DesignState
from llm_models import pair_generation_agent
from prompts import GE_PAIR_PROMPT
from IPython.display import display, Markdown
from graph_utils import summarize_design_state_func
from utils import remove_think_tags
from validation import filter_valid_proposals
from data_models import Proposal, SingleProposal  # Added SingleProposal import
from datetime import datetime, UTC
import uuid

def generation_pair_node(state: PairState) -> Command[Literal["reflection_pair"]]:
    """
    • Generates *N* DSG proposals (defined in GE_PROMPT_STRUCTURED).
    """
    print("\n🔧 [GEN] Generation pair node")
    # ── Counters ────────────────────────────────────────────────────────────
    iter_now      = state.generation_iteration
    print(f"   • iteration {iter_now + 1}")

    # just a mechanism to save the user request in the first pass
    first_pass = state.first_pass
    if first_pass: 
        user_request = state.messages[-1].content
        print(f"   • user request: {user_request}")
        # Use the thread_id from the pipeline instead of creating a new folder
        new_folder = state.thread_id if hasattr(state, 'thread_id') else None
        if not new_folder:
            print("   ⚠️  No thread_id found in state")
            return Command(
                update={
                    "generation_notes": ["No thread_id available for saving."],
                    "generation_iteration": iter_now,
                },
                goto="generation_pair",
            )
    else:
        user_request = state.user_request
        new_folder = state.dsg_save_folder

    # ── Context strings for the LLM ────────────────────────────────────────
    graph_now   = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    graph_sum   = summarize_design_state_func(graph_now)
    note_to_improve = state.detailed_summary_for_graph[-1] if state.detailed_summary_for_graph else ""

    human_msg = f"""
        User request:
        {user_request}

        If iterating on DSGs, current DSG summary:
        {graph_sum}

        If iterating on DSGs, note to improve the current DSG:
        {note_to_improve}

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
                    "generation_iteration": iter_now,
                },
                goto="generation_pair",
            )

    # ── Wrap into long-term `Proposal` objects and update State ────────────
    new_entries: List[Proposal] = [
        Proposal(
            title=p.title,
            content=p.content,                 # ← the DesignState object
            status="generated",
            generation_iteration_index=iter_now,
            reflection_iteration_index=state.reflection_iteration

        )
        for i, p in enumerate(dsg_proposals)
    ]
    
    print(f"   • Created {len(new_entries)} new proposal entries")
    print(f"   • First proposal title: {new_entries[0].title if new_entries else 'None'}")
    print(f"   • First proposal status: {new_entries[0].status if new_entries else 'None'}")

    # Otherwise go straight to reflection
    print(" ✅ generation complete → reflection")
    return Command(
        update={
            "proposals": new_entries,
            "user_request": user_request,
            "first_pass": False,
            "generation_iteration": iter_now,              # keep counter
            "dsg_save_folder": new_folder,
        },
        goto="reflection_pair",
    )
        
