# workflows/pair_workflow.py
# ---------------------------------------------------------------------------
#  2-Agent “ablation” workflow: Generation ↔ Reflection loop
# ---------------------------------------------------------------------------

from langgraph.graph             import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from data_models import PairState
from agents.generation_pair import generation_pair_node
from agents.reflection_pair import reflection_pair_node
from langchain_core.messages import HumanMessage

def build_app() -> "langgraph.App":
    g = StateGraph(PairState)
    g.set_entry_point("generation_pair")
    g.add_node("generation_pair", generation_pair_node)
    g.add_node("reflection_pair", reflection_pair_node)
    return g.compile(checkpointer=MemorySaver())


def run_once(request: str, thread_id: str = "0") -> PairState:
    app = build_app()
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 500}
    app.invoke({
        "messages": [HumanMessage(content=request)],
        "dsgs_save_folder": thread_id  # This will be used as-is in save_dsg
    }, config=cfg)
    return app.get_state(cfg)
