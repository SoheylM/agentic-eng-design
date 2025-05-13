"""
workflows/pair_workflow.py
Builds the 2-Agent ablation workflow (generator + reflection loop).
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from data_models import PairState

# Import the two nodes
from agents.generation_pair import generation_pair_node
from agents.reflection_pair import reflection_pair_node

def build_app() -> "langgraph.App":
    """Build the 2-agent workflow graph."""
    g = StateGraph(PairState)
    
    # Set entry point and add nodes
    g.set_entry_point("generation_pair")
    g.add_node("generation_pair", generation_pair_node)
    g.add_node("reflection_pair", reflection_pair_node)
    
    return g.compile(checkpointer=MemorySaver())

def run_once(request: str, thread_id: str = "0") -> PairState:
    """
    Run a single iteration of the 2-agent workflow.
    
    Args:
        request: The initial user request
        thread_id: Optional thread identifier for tracking
        
    Returns:
        The final state after workflow completion
    """
    app = build_app()
    cfg = {
        "configurable": {"thread_id": f"pair-{thread_id}"},
        "recursion_limit": 500
    }
    
    # Initialize with user request
    app.invoke({"messages": [request]}, config=cfg)
    return app.get_state(cfg)
