from __future__ import annotations

from typing import List, Optional, Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from data_models import (
    State,
    Proposal,                         # contains .content -> DesignState
    DesignNode,
    PhysicsModel
)
from prompts import CODER_PROMPT
from llm_models import coder_agent
from graph_utils import summarize_design_state_func
from utils import remove_think_tags


def coder_node(state: State) -> Command[Literal["reflection"]]:
    """
    • Takes each DSG proposal from Generation
    • For each DesignNode in the DSG, rewrites the python_code field in its physics_models
    • Maintains iteration counters identical to the workflow
    """
    print("\n💻 [CODE] Coder node")

    iter_now = state.coder_iteration
    max_iter = state.max_iterations
    print(f"   • iteration {iter_now + 1}/{max_iter}")

    if iter_now >= max_iter:
        print("   ⚠️  max-iterations reached; skipping coding.")
        return Command(
            update={
                "coder_notes": [f"Stopped after {max_iter} coding loops."],
                "coder_iteration": iter_now - 1,
            },
            goto="reflection",
        )

    # Get proposals from the most recent Generation loop
    recent_props: List[Proposal] = [
        p for p in state.proposals
        if p.current_step_index == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_props:
        print("   ⚠️  no proposals to code")
        return Command(
            update={"coder_notes": ["No proposals available for coding."]},
            goto="reflection",
        )

    print(f"   • coding {len(recent_props)} DSG proposals")

    # Process each proposal
    for prop_idx, proposal in enumerate(recent_props):
        dsg = proposal.content
        
        # Process each node in the DSG
        for node_id, node in dsg.nodes.items():
            # Process each physics model in the node
            for model_idx, model in enumerate(node.physics_models):
                if not model.python_code:
                    continue
                    
                print(f"     ↳ coding model {model.name} in node {node.name}")
                
                # Prepare context for the LLM
                context = f"""
Node: {node.name}
Model: {model.name}
Equations: {model.equations}
Assumptions: {model.assumptions}
Current Python Code:
{model.python_code}
"""
                
                # Get new code from LLM
                llm_resp = coder_agent.invoke([
                    SystemMessage(content=CODER_PROMPT),
                    HumanMessage(content=context)
                ])
                
                # Update the model's python code
                model.python_code = llm_resp.python_code
                
                # Update iteration tracking
                proposal.coder_iteration_index = iter_now

    print("   ✅ coding complete → reflection")
    return Command(
        update={
            "coder_iteration": iter_now,
            "coder_notes": [f"Completed code-iter {iter_now}"],
        },
        goto="reflection",
    ) 