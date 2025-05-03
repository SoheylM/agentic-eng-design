import uuid
from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from data_models import State, DesignState
from graph_utils import add_node_func, delete_node_func, update_node_func, visualize_design_state_func, summarize_design_state_func
from utils import remove_think_tags
from llm_models import base_model_reasoning

def graph_designer_node(state: State) -> Command[Literal["supervisor"]]:
    """
    Graph Designer Agent:
    - Reads structured node and edge modifications from the Synthesizer Agent.
    - Applies modifications to the Design Graph.
    - Ensures graph consistency after changes.
    - Returns the updated graph to the Supervisor.
    """
    print("\n📐 [DEBUG] Graph Designer node invoked.")

    # **Retrieve Synthesizer Output**
    if not state.synthesizer_notes or not state.design_graph_nodes:
        print("⚠️ [DEBUG] No synthesizer modifications found.")
        return Command(
            update={
                "graph_designer_notes": ["No modifications provided by synthesizer. No changes made."],
            },
            goto="supervisor"
        )

    # Get the current design graph
    current_design_graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()

    # Retrieve the latest instructions and modifications
    synthesizer_summary = state.synthesizer_notes[-1]
    node_modifications = state.design_graph_nodes[-1]  # Extract latest node modifications
    edge_modifications = state.design_graph_edges[-1] if state.design_graph_edges else []  # Extract latest edge modifications

    print(f"\n🔍 [DEBUG] Retrieved synthesizer summary:\n{synthesizer_summary}")
    print(f"\n🔍 [DEBUG] Retrieved {len(node_modifications)} node modifications.")
    print(f"\n🔍 [DEBUG] Retrieved {len(edge_modifications)} edge modifications.")

    # **Step 1: Apply Node Modifications**
    node_results = []
    for mod in node_modifications:
        try:
            if mod.operation == "add":
                result = add_node_func(current_design_graph, {
                    "node_id": mod.node_id or str(uuid.uuid4()),
                    "node_type": mod.node_type,
                    "name": mod.name,
                    "payload": mod.payload,
                    "status": mod.status or "draft"
                })
            elif mod.operation == "delete":
                result = delete_node_func(current_design_graph, mod.node_id)
            elif mod.operation == "update":
                result = update_node_func(current_design_graph, mod)  # ✅ Uses NodeModification directly
            else:
                result = f"❌ Invalid operation '{mod.operation}' for node '{mod.node_id}'. Skipping."

            print(f"✅ [DEBUG] {result}")
            node_results.append(result)
        except Exception as e:
            error_msg = f"❌ Error applying node modification: {mod.node_id} - {str(e)}"
            print(error_msg)
            node_results.append(error_msg)

    # **Step 2: Apply Edge Modifications**
    edge_results = []
    for edge_mod in edge_modifications:
        try:
            if edge_mod.operation == "add":
                if edge_mod.from_node in current_design_graph.nodes and edge_mod.to_node in current_design_graph.nodes:
                    current_design_graph.edges.append((edge_mod.from_node, edge_mod.to_node))  # Store edge
                    result = f"✅ Edge added: {edge_mod.from_node} → {edge_mod.to_node}"
                else:
                    result = f"❌ Error: Cannot add edge, nodes {edge_mod.from_node} or {edge_mod.to_node} not found."
            elif edge_mod.operation == "delete":
                if (edge_mod.from_node, edge_mod.to_node) in current_design_graph.edges:
                    current_design_graph.edges.remove((edge_mod.from_node, edge_mod.to_node))
                    result = f"✅ Edge deleted: {edge_mod.from_node} → {edge_mod.to_node}"
                else:
                    result = f"⚠️ Edge {edge_mod.from_node} → {edge_mod.to_node} not found. No deletion performed."
            else:
                result = f"❌ Invalid edge operation '{edge_mod.operation}' for edge {edge_mod.from_node} → {edge_mod.to_node}. Skipping."

            print(f"✅ [DEBUG] {result}")
            edge_results.append(result)
        except Exception as e:
            error_msg = f"❌ Error applying edge modification: {edge_mod.from_node} → {edge_mod.to_node} - {str(e)}"
            print(error_msg)
            edge_results.append(error_msg)

    # **Step 3: Validate Updated Graph**
    print("\n🔍 [DEBUG] Validating updated design graph.")

    validation_prompt = f"""
    ### **Design Graph Validation**
    
    - **Synthesizer Summary**: {synthesizer_summary}
    - **Applied Node Modifications**: {node_results}
    - **Applied Edge Modifications**: {edge_results}
    - **Current Graph Summary**: {summarize_design_state_func(current_design_graph)}

    **Your Task**:
    1. **Analyze the modifications** and check if they align with design goals.
    2. **Identify missing nodes, inconsistencies, or errors**.
    3. **If any inconsistencies exist, reprocess the modification plan**.

    **Format your response as structured JSON.**
    """

    base_model_output = base_model_reasoning.invoke([
        SystemMessage(content="You are the Graph Validation Agent. Check the consistency of the Design Graph."),
        HumanMessage(content=validation_prompt)
    ])

    print("\n🔍 [DEBUG] Graph Validation Completed.")
    print(f"📝 [DEBUG] Validation Output:\n{remove_think_tags(base_model_output.content)}")

    # **Step 4: Visualize Updated Graph**
    visualize_design_state_func(current_design_graph)

    # **Step 5: Return Updated Graph to Supervisor**
    return Command(
        update={
            "graph_designer_notes": [base_model_output.content],
            "design_graph_history": [current_design_graph],  # Add the updated graph to history
        },
        goto="supervisor"
    )
