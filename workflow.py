from langgraph.graph import StateGraph
from agents.router import router_node
from agents.human import human_node
from agents.requirements import requirements_node
from agents.planner import planner_node
from agents.supervisor import supervisor_node
from agents.orchestrator import orchestrator_node
from agents.worker import worker_node
from agents.generation import generation_node
from agents.reflection import reflection_node
from agents.ranking import ranking_node
from agents.evolution import evolution_node
from agents.meta_review import meta_review_node
from agents.synthesizer import synthesizer_node
from agents.graph_designer import graph_designer_node
from data_models import State
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from config import config

def initialize_workflow():
    """Initialize the workflow with proper configuration."""
    # Set up LangSmith tracing
    config.setup_langsmith_tracing("IDETC25-MassoudiFuge-v2")
    
    # Create a state graph builder
    graph_builder = StateGraph(State)
    
    # **Entry Point: Human Interaction**
    graph_builder.set_entry_point("router")
    
    # Add all nodes
    graph_builder.add_node("router", router_node)
    graph_builder.add_node("human", human_node)
    graph_builder.add_node("requirements", requirements_node)
    graph_builder.add_node("planner", planner_node)
    graph_builder.add_node("supervisor", supervisor_node)
    graph_builder.add_node("orchestrator", orchestrator_node)
    graph_builder.add_node("worker", worker_node)
    graph_builder.add_node("generation", generation_node)
    graph_builder.add_node("reflection", reflection_node)
    graph_builder.add_node("ranking", ranking_node)
    graph_builder.add_node("evolution", evolution_node)
    graph_builder.add_node("meta_review", meta_review_node)
    graph_builder.add_node("synthesizer", synthesizer_node)
    graph_builder.add_node("graph_designer", graph_designer_node)
    
    # Compile the workflow
    checkpointer = MemorySaver()
    app = graph_builder.compile(checkpointer=checkpointer)
    
    return app

def main():
    """Main workflow execution."""
    # Initialize the workflow
    app = initialize_workflow()
    
    # Invoke the workflow with the client request
    request = "I want to create a water filtration system that is solar powered."
    workflow_config = {"configurable": {"thread_id": "17"}, "recursion_limit": 500}
    app.invoke({"messages": [request]}, config=workflow_config)
    
    while True:
        STATE = app.get_state(workflow_config)
        
        # **Interrupt for Human Input**
        human_answer = input("Provide input to the agent (or type END to finish): ")
        
        if human_answer.upper() == "END":
            print("✅ Finalizing requirements manually. Moving to main workflow.")
            app.invoke(Command(update={"active_agent": "planner"}), config=workflow_config)
            break
        
        # Resume conversation with human input
        app.invoke(Command(resume=human_answer), config=workflow_config)
    
    print("✅ Engineering workflow completed.")

if __name__ == "__main__":
    main()
