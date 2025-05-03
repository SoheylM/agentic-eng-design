import uuid
from typing import List, Tuple
from data_models import Node, DesignState, NodeModification


def add_node_to_state(state: DesignState, node: Node) -> None:
    """
    Adds a node to the global design state.
    """
    state.nodes[node.node_id] = node


def add_edges_to_state(state: DesignState, edges: List[Tuple[str, str]]) -> None:
    """
    Adds directed edges between existing nodes in the design state.

    Args:
        state: The global design state.
        edges: A list of (source_id, target_id) tuples representing directed edges.
    """
    for source_id, target_id in edges:
        if source_id in state.nodes and target_id in state.nodes:
            state.nodes[source_id].edges_out.append(target_id)
            state.nodes[target_id].edges_in.append(source_id)
        else:
            print(f"⚠️ Warning: Edge ({source_id} -> {target_id}) could not be added. One or both nodes are missing.")


def add_node_func(node_info: dict, edges_to_add: List[Tuple[str, str]] = []) -> str:
    """
    Adds a node to the global design state and optionally connects it to other nodes via edges.

    Args:
        node_info: A dictionary containing node attributes such as 'node_id', 'node_type', 'name', 'payload', and 'status'.
        edges_to_add: A list of (source_id, target_id) tuples representing directed edges.

    Returns:
        A confirmation message.
    """
    node_id = node_info.get("node_id", str(uuid.uuid4()))
    node_info["node_id"] = node_id

    new_node = Node(
        node_id=node_id,
        node_type=node_info.get("node_type", "unknown"),
        name=node_info.get("name", "Unnamed Node"),
        payload=node_info.get("payload", ""),
        status=node_info.get("status", "draft")
    )

    # Add node to state
    add_node_to_state(DESIGN_STATE, new_node)

    # Add edges if provided
    if edges_to_add:
        add_edges_to_state(DESIGN_STATE, edges_to_add)

    return f"✅ Node '{new_node.name}' ({new_node.node_id}) added successfully."

def delete_node_func(node_id: str, recursive: bool = True) -> str:
    """
    Deletes a node from the global design state and removes all associated edges.
    
    Args:
        node_id (str): The ID of the node to delete.
        recursive (bool): Whether to recursively delete child nodes that have no other parents.

    Returns:
        str: Confirmation message.
    """
    def _delete(state: DesignState, nid: str, rec: bool):
        if nid not in state.nodes:
            return
        
        node = state.nodes[nid]

        # Remove all outgoing edges (disconnect from children)
        for target_id in list(node.edges_out):
            if target_id in state.nodes:
                state.nodes[target_id].edges_in.remove(nid)
        
        # Remove all incoming edges (disconnect from parents)
        for source_id in list(node.edges_in):
            if source_id in state.nodes:
                state.nodes[source_id].edges_out.remove(nid)
        
        # Recursively delete nodes that have no other parents
        if rec:
            for target_id in list(node.edges_out):
                if target_id in state.nodes and not state.nodes[target_id].edges_in:
                    _delete(state, target_id, rec)

        # Remove node from the design state
        del state.nodes[nid]

    _delete(DESIGN_STATE, node_id, recursive)
    return f"✅ Node {node_id} deleted successfully."

def update_node_func(modification: NodeModification) -> str:
    """
    Updates an existing node in the global design state based on a NodeModification object.
    
    This includes updating:
    - Node attributes (name, type, status, payload)
    - Graph structure (adding/removing edges)
    
    Args:
        modification (NodeModification): The modification object containing update details.

    Returns:
        str: Confirmation message indicating the update status.
    """
    node_id = modification.node_id
    if not node_id or node_id not in DESIGN_STATE.nodes:
        return f"❌ Error: Node '{node_id}' not found in the design graph."

    node = DESIGN_STATE.nodes[node_id]

    # **Apply updates to node attributes**
    if modification.name:
        node.name = modification.name
    if modification.node_type:
        node.node_type = modification.node_type
    if modification.status:
        node.status = modification.status
    if modification.payload:
        # Either replace the payload or update it based on the operation
        node.payload = modification.payload

    # **Update edges if provided**
    if modification.updates:
        # If 'edges_add' is in updates, add edges
        if "edges_add" in modification.updates:
            for target_id in modification.updates["edges_add"]:
                if target_id in DESIGN_STATE.nodes and target_id not in node.edges_out:
                    node.edges_out.append(target_id)
                    DESIGN_STATE.nodes[target_id].edges_in.append(node_id)

        # If 'edges_remove' is in updates, remove specified edges
        if "edges_remove" in modification.updates:
            for target_id in modification.updates["edges_remove"]:
                if target_id in node.edges_out:
                    node.edges_out.remove(target_id)
                    DESIGN_STATE.nodes[target_id].edges_in.remove(node_id)

    return f"✅ Node '{node_id}' updated successfully."

def visualize_design_state_func(show_payload: bool = False) -> str:
    """
    Generate and display an interactive visualization of the current design state's node graph.
    Uses Plotly to produce the visualization and calls fig.show() to open the figure.

    Args:
        show_payload (bool): If True, displays the payload in hover text. Default is False.

    Returns:
        A confirmation message indicating that the visualization has been displayed.
    """
    import plotly.graph_objects as go
    import networkx as nx

    # Build a directed graph using NetworkX
    G = nx.DiGraph()

    # Add nodes
    for node_id, node in DESIGN_STATE.nodes.items():
        G.add_node(node_id, 
                   name=node.name, 
                   node_type=node.node_type, 
                   payload=node.payload, 
                   status=node.status)

    # Add edges from DESIGN_STATE.edges
    for source, target in DESIGN_STATE.edges:
        if source in DESIGN_STATE.nodes and target in DESIGN_STATE.nodes:
            G.add_edge(source, target)  # Direction from source → target
        else:
            print(f"⚠️ Warning: Edge ({source} → {target}) skipped because one or both nodes are missing.")

    print(f"📌 [DEBUG] Edge list in graph: {list(G.edges())}")

    # Generate layout positions with a fixed seed for reproducibility
    pos = nx.spring_layout(G, seed=42)

    # Define colors for node types
    color_map = {
        "user_request": 'lightblue',
        "requirement": 'lightgreen',
        "objective_constraint": 'limegreen',
        "functional_decomposition": 'gold',
        "subfunction": 'orange',
        "subsystem": 'violet',
        "discipline": 'pink'
    }

    node_x, node_y, node_text, node_colors = [], [], [], []
    annotations = []  # Store node ID text annotations

    for node_id, data in G.nodes(data=True):
        x, y = pos[node_id]
        node_x.append(x)
        node_y.append(y)

        # Create hover text, excluding payload if show_payload=False
        edges_out = list(G.successors(node_id))
        edges_in = list(G.predecessors(node_id))

        hover_text = (
            f"ID: {node_id}<br>"
            f"Name: {data.get('name')}<br>"
            f"Type: {data.get('node_type')}<br>"
            f"Status: {data.get('status')}<br>"
            f"Edges Out: {', '.join(edges_out) if edges_out else 'None'}<br>"
            f"Edges In: {', '.join(edges_in) if edges_in else 'None'}"
        )

        # Append payload info only if show_payload=True
        if show_payload:
            hover_text += f"<br>Payload: {data.get('payload')}"

        node_text.append(hover_text)
        node_colors.append(color_map.get(data.get('node_type'), 'gray'))

        # Adjust position slightly to prevent overlap
        offset_x, offset_y = 0.02, 0.02
        annotations.append(dict(
            x=x + offset_x, y=y + offset_y, text=node_id, showarrow=False,
            font=dict(size=12, color="black"), xanchor="left", yanchor="bottom"
        ))

    # Create the node trace
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers',
        hoverinfo='text',
        text=node_text,
        marker=dict(color=node_colors, size=20, line_width=2)
    )

    # Create edge traces (with proper arrows)
    edge_x, edge_y = [], []
    arrow_annotations = []  # To store arrow markers

    for source, target in G.edges():
        x0, y0 = pos[source]
        x1, y1 = pos[target]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

        # Add annotation-based arrows
        arrow_annotations.append(dict(
            ax=x0, ay=y0, x=x1, y=y1,
            showarrow=True,
            arrowhead=3,  # Proper arrowhead
            arrowsize=2,
            arrowwidth=2,
            arrowcolor="black"
        ))

    print(f"📌 [DEBUG] Edge Coordinates: {edge_x}, {edge_y}")  # Debugging edge positions

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=2, color='black'),
        hoverinfo='none',
        mode='lines'
    )

    # Create the figure layout
    fig = go.Figure(
        data=[edge_trace, node_trace],  # ✅ Ensure edges are added before nodes
        layout=go.Layout(
            title=dict(text='<br>Directed Design Graph Visualization', font=dict(size=16)),
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=40),
            annotations=annotations + arrow_annotations,  # ✅ Node IDs + Directed Arrows
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            paper_bgcolor="lightblue"  # Background color for better visibility
        )
    )

    # Display the figure (opens a new window or inline, depending on the environment)
    fig.show()
    return "Visualization displayed successfully."

def summarize_design_state_func() -> str:
    """
    Summarize the current design state's node graph.

    This function scans the global DESIGN_STATE and returns a formatted summary that includes:
      - Node ID
      - Name
      - Node Type
      - Status
      - Incoming Edges (nodes pointing to this node)
      - Outgoing Edges (nodes this node points to)
      - Payload (metadata)

    Returns:
        A formatted string summarizing the current design state.
    """
    summary_lines = []
    for node_id, node in DESIGN_STATE.nodes.items():
        incoming = ", ".join(node.edges_in) if node.edges_in else "None"
        outgoing = ", ".join(node.edges_out) if node.edges_out else "None"
        
        line = (
            f"ID: {node_id}\n"
            f"  Name: {node.name}\n"
            f"  Type: {node.node_type}\n"
            f"  Status: {node.status}\n"
            f"  Incoming Edges (from): {incoming}\n"
            f"  Outgoing Edges (to): {outgoing}\n"
            f"  Payload: {node.payload}\n"
            "-------------------------------------"
        )
        summary_lines.append(line)

    return "\n".join(summary_lines)

def analyze_node_func(node_id: str) -> str:
    """
    Analyze a specific node in the global design state.
    
    This function retrieves the node identified by 'node_id' from the global DESIGN_STATE and returns a
    formatted summary that includes:
      - Node ID
      - Name
      - Node type
      - Status
      - Incoming Edges (dependencies)
      - Outgoing Edges (influences)
      - Payload contents
      
    Args:
        node_id: The unique identifier of the node to analyze.
    
    Returns:
        A formatted string summarizing the node details.
    """
    if node_id not in DESIGN_STATE.nodes:
        return f"❌ Error: Node '{node_id}' not found in the design state."
    
    node = DESIGN_STATE.nodes[node_id]
    incoming = ", ".join(node.edges_in) if node.edges_in else "None"
    outgoing = ", ".join(node.edges_out) if node.edges_out else "None"

    summary = (
        f"🔍 **Node Analysis:**\n"
        f"-----------------\n"
        f"🆔 **ID:** {node.node_id}\n"
        f"🏷️ **Name:** {node.name}\n"
        f"🔹 **Type:** {node.node_type}\n"
        f"📌 **Status:** {node.status}\n"
        f"⬅️ **Incoming Edges (dependencies from):** {incoming}\n"
        f"➡️ **Outgoing Edges (influences to):** {outgoing}\n"
        f"🗃 **Payload:** {node.payload}\n"
        "-------------------------------------"
    )
    
    return summary
