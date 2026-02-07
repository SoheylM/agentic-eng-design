# workflows/pair_workflow.py
# ---------------------------------------------------------------------------
#  2-Agent “ablation” workflow: Generation ↔ Reflection loop
# ---------------------------------------------------------------------------

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

from agents.generation_pair import generation_pair_node
from agents.reflection_pair import reflection_pair_node
from config import config  # Add config import
from data_models import PairState


def build_app():
    config.setup_langsmith_tracing("Agent-Pair-v4")  # Add LangSmith tracing
    g = StateGraph(PairState)
    g.set_entry_point("generation_pair")
    g.add_node("generation_pair", generation_pair_node)
    g.add_node("reflection_pair", reflection_pair_node)
    return g.compile(checkpointer=MemorySaver())


def run_once(request: str, thread_id: str = "0") -> PairState:
    app = build_app()
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}
    app.invoke({"messages": [HumanMessage(content=request)], "thread_id": thread_id}, config=cfg)
    return app.get_state(cfg)
