# workflows/mas_workflow.py
# ---------------------------------------------------------------------------
#  Builds the full Multi-Agent System LangGraph application
# ---------------------------------------------------------------------------

from langgraph.graph             import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types             import Command
from langchain_core.messages     import HumanMessage
from data_models import State
from config      import config                         # your helper

# --------------------------------------------------------------------------
# 1.  Import every active node
# --------------------------------------------------------------------------
from agents.router        import router_node
from agents.human         import human_node
from agents.requirements  import requirements_node
from agents.supervisor    import supervisor_node
from agents.orchestrator  import orchestrator_node
from agents.worker        import worker_node
from agents.generation    import generation_node
from agents.coder         import coder_node
from agents.reflection    import reflection_node
from agents.ranking       import ranking_node
from agents.evolution     import evolution_node
from agents.meta_review   import meta_review_node
# NOTE:  synthesizer_node  &  graph_designer_node   **removed**

# --------------------------------------------------------------------------
def build_app() -> "langgraph.App":
    """Return a fully-wired MAS LangGraph application."""
    config.setup_langsmith_tracing("IDETC25-MAS-v3")

    g = StateGraph(State)

    g.set_entry_point("router")

    g.add_node("router",         router_node)
    g.add_node("human",          human_node)
    g.add_node("requirements",   requirements_node)
    g.add_node("supervisor",     supervisor_node)
    g.add_node("orchestrator",   orchestrator_node)
    g.add_node("worker",         worker_node)
    g.add_node("generation",     generation_node)
    g.add_node("coder",          coder_node)
    g.add_node("reflection",     reflection_node)
    g.add_node("ranking",        ranking_node)
    g.add_node("meta_review",    meta_review_node)

    return g.compile(checkpointer=MemorySaver())


def run_once(request: str,
             thread_id: str = "0",
             interactive: bool = False) -> State:
    """
    Fire-and-forget helper used by the experiment runner.
    Returns the **final State** for metric evaluation.
    """
    app = build_app()
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}

    app.invoke({
        "messages": [HumanMessage(content=request)],
        "thread_id": thread_id  # Pass thread_id to the state
    }, config=cfg)

    if interactive:
        while True:
            usr = input("Human input (END to stop)> ")
            if usr.upper() == "END":
                app.invoke(Command(update={"active_agent": "supervisor"}), config=cfg)
                break
            app.invoke(Command(resume=usr), config=cfg)

    return app.get_state(cfg)
