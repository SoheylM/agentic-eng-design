"""
workflows/mas_workflow.py
Builds the full Multi-Agent System (MAS) LangGraph application.

Nothing in your agents changes – we just import them and wire the graph.
"""

from langgraph.graph            import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types            import Command
from data_models                import State
from config                     import config                          # your helper

# ---- import every node ---------------------------------------------------- #
from agents.router        import router_node
from agents.human         import human_node
from agents.requirements  import requirements_node
from agents.planner       import planner_node
from agents.supervisor    import supervisor_node
from agents.orchestrator  import orchestrator_node
from agents.worker        import worker_node
from agents.generation    import generation_node
from agents.reflection    import reflection_node
from agents.ranking       import ranking_node
from agents.evolution     import evolution_node
from agents.meta_review   import meta_review_node
from agents.synthesizer   import synthesizer_node
from agents.graph_designer import graph_designer_node
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def build_app() -> "langgraph.App":
    """
    Return a fully-wired MAS LangGraph application (identical logic to notebook).
    """
    # (optional) tracing
    config.setup_langsmith_tracing("IDETC25-MAS-v2")

    g = StateGraph(State)

    # entry + nodes
    g.set_entry_point("router")
    g.add_node("router",          router_node)
    g.add_node("human",           human_node)
    g.add_node("requirements",    requirements_node)
    g.add_node("planner",         planner_node)
    g.add_node("supervisor",      supervisor_node)
    g.add_node("orchestrator",    orchestrator_node)
    g.add_node("worker",          worker_node)
    g.add_node("generation",      generation_node)
    g.add_node("reflection",      reflection_node)
    g.add_node("ranking",         ranking_node)
    g.add_node("evolution",       evolution_node)
    g.add_node("meta_review",     meta_review_node)
    g.add_node("synthesizer",     synthesizer_node)
    g.add_node("graph_designer",  graph_designer_node)

    return g.compile(checkpointer=MemorySaver())


def run_once(request: str,
             interactive: bool = False,
             thread_id: str = "0") -> State:
    """
    Convenience wrapper used by the experiment runner (`workflow.py`).

    Returns the final LangGraph *state* so evaluation.py can compute metrics.
    """
    app   = build_app()
    cfg   = {"configurable": {"thread_id": thread_id}, "recursion_limit": 500}

    app.invoke({"messages": [request]}, config=cfg)

    if interactive:
        while True:
            usr = input("Human input (END to stop)> ")
            if usr.upper() == "END":
                app.invoke(Command(update={"active_agent": "planner"}), config=cfg)
                break
            app.invoke(Command(resume=usr), config=cfg)

    return app.get_state(cfg)
