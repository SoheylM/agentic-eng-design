"""
workflows/pair_workflow.py
Builds the 2-Agent ablation workflow (generator + reflection loop).
"""

from langgraph.graph            import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types            import Command
from dataclasses                import dataclass, field
import operator

# --------------------------------------------------------------------------- #
# Import the two nodes you wrote earlier
# --------------------------------------------------------------------------- #
from agents.generation_pair  import node   as generation_pair_node
from agents.reflection_pair  import node   as reflection_pair_node
from agents.generation_pair  import PairState   # dataclass shared by both
# --------------------------------------------------------------------------- #


def build_app() -> "langgraph.App":
    g = StateGraph(PairState)
    g.set_entry_point("generation_pair")
    g.add_node("generation_pair", generation_pair_node)
    g.add_node("reflection_pair", reflection_pair_node)
    return g.compile(checkpointer=MemorySaver())


def run_once(request: str,
             thread_id: str = "0") -> PairState:
    app = build_app()
    cfg = {"configurable": {"thread_id": f"pair-{thread_id}"}, "recursion_limit": 500}
    app.invoke({"messages": [request]}, config=cfg)
    return app.get_state(cfg)
