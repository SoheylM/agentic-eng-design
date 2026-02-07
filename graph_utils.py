from data_models import DesignNode, DesignState, NodeOp


def add_node_to_state(design_graph: DesignState, node: DesignNode) -> None:
    """
    Adds a node to the design graph.
    """
    design_graph.nodes[node.node_id] = node


def add_edges_to_state(design_graph: DesignState, edges: list[tuple[str, str]]) -> None:
    """
    Adds directed edges between existing nodes in the design graph.

    Args:
        design_graph: The design graph.
        edges: A list of (source_id, target_id) tuples representing directed edges.
    """
    for source_id, target_id in edges:
        if source_id in design_graph.nodes and target_id in design_graph.nodes:
            # Add to the single source of truth
            if [source_id, target_id] not in design_graph.edges:
                design_graph.edges.append([source_id, target_id])
        else:
            print(f"⚠️ Warning: Edge ({source_id} -> {target_id}) could not be added. One or both nodes are missing.")


def get_node_edges(design_graph: DesignState, node_id: str) -> tuple[list[str], list[str]]:
    """
    Get incoming and outgoing edges for a node by filtering the edges list.

    Args:
        design_graph: The design graph.
        node_id: The ID of the node to get edges for.

    Returns:
        Tuple of (incoming_edge_ids, outgoing_edge_ids)
    """
    incoming = []
    outgoing = []
    for edge in design_graph.edges:
        if edge[1] == node_id:  # target is our node
            incoming.append(edge[0])
        if edge[0] == node_id:  # source is our node
            outgoing.append(edge[1])
    return incoming, outgoing


def add_node_func(design_graph: DesignState, op: NodeOp) -> str:
    """
    Process a NodeOp of type "add": insert the new DesignNode into the graph
    and wire up any initial edges.

    Args:
        design_graph: The DesignState to modify.
        op: A NodeOp with op=="add", containing:
            - op.node: the DesignNode to insert
            - op.updates: optional dict containing 'edges_to_add' as a list of (src_id, dst_id) tuples

    Returns:
        A confirmation message.

    Raises:
        ValueError: if op.op != "add".
    """
    if op.op != "add":
        raise ValueError(f"add_node_func only handles add-ops, got '{op.op}'")

    new_node: DesignNode = op.node

    # 1) Insert node
    add_node_to_state(design_graph, new_node)

    # 2) Wire up any initial edges from the updates dict
    if op.updates and "edges_to_add" in op.updates:
        add_edges_to_state(design_graph, op.updates["edges_to_add"])

    return f"✅ DesignNode '{new_node.name}' ({new_node.node_id}) added successfully."


def delete_node_func(design_graph: DesignState, node_id: str, recursive: bool = True) -> str:
    """
    Deletes a node from the design graph and removes all associated edges.

    Args:
        design_graph: The design graph to modify
        node_id (str): The ID of the node to delete.
        recursive (bool): Whether to recursively delete child nodes that have no other parents.

    Returns:
        str: Confirmation message.
    """

    def _delete(design_graph: DesignState, nid: str, rec: bool):
        if nid not in design_graph.nodes:
            return

        # Get all edges connected to this node
        _incoming, outgoing = get_node_edges(design_graph, nid)

        # Remove all edges connected to this node
        design_graph.edges = [edge for edge in design_graph.edges if edge[0] != nid and edge[1] != nid]

        # Recursively delete nodes that have no other parents
        if rec:
            for target_id in outgoing:
                # Check if target has any remaining incoming edges
                remaining_incoming = [edge[0] for edge in design_graph.edges if edge[1] == target_id]
                if not remaining_incoming:
                    _delete(design_graph, target_id, rec)

        # Remove node from the design graph
        del design_graph.nodes[nid]

    _delete(design_graph, node_id, recursive)
    return f"✅ DesignNode {node_id} deleted successfully."


def update_node_func(design_graph: DesignState, op: NodeOp) -> str:
    """
    Process a NodeOp of type "update": replace the existing DesignNode
    in the graph with the one supplied in op.node, preserving its connectivity.

    Args:
        design_graph: the in-memory DesignState to modify.
        op: a NodeOp with op=="update", whose .node is the new version.

    Returns:
        A confirmation string.

    Raises:
        ValueError: if op.op != "update".
    """
    if op.op != "update":
        raise ValueError(f"update_node_func only handles update-ops, got '{op.op}'")

    node_id = op.node_id
    if node_id not in design_graph.nodes:
        return f"❌ Error: DesignNode '{node_id}' not found in the design graph."

    # The new node from the NodeOp
    new_node: DesignNode = op.node

    # Enforce the same ID
    new_node.node_id = node_id

    # Swap it in
    design_graph.nodes[node_id] = new_node

    return f"✅ DesignNode '{node_id}' updated successfully."


def visualize_design_state_func(design_graph: DesignState) -> str:
    import re

    import networkx as nx
    import plotly.graph_objects as go

    def is_uuid(text):
        """Check if a string is a UUID format."""
        uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
        return bool(uuid_pattern.match(text))

    def get_display_name(node_id, node_name):
        """Get the display name for a node - use name if available, otherwise ID."""
        if is_uuid(node_id):
            # If it's a UUID, prefer the name if it exists and is not empty
            if node_name and node_name.strip():
                return node_name
            else:
                # If no name, use a shortened version of the UUID
                return node_id[:8] + "..."
        else:
            # If it's not a UUID, use the ID as is
            return node_id

    G = nx.DiGraph()
    for nid, node in design_graph.nodes.items():
        G.add_node(
            nid,
            name=node.name,
            kind=node.node_kind,
            maturity=node.maturity,
            desc=node.description,
            principle=node.embodiment.principle,
            n_models=len(node.physics_models),
        )
    for edge in design_graph.edges:
        src, dst = edge  # Unpack the list into source and destination
        if src in G and dst in G:
            G.add_edge(src, dst)

    # Use spring layout with tighter spacing (k=1.0 instead of default ~3.0)
    # and more iterations for better convergence
    pos = nx.spring_layout(G, k=1.0, iterations=50, seed=42)

    color_map = {
        "function": "gold",
        "subfunction": "orange",
        "requirement": "lightgreen",
        "constraint": "salmon",
        "component": "lightblue",
        "subsystem": "lightcoral",
        # add others as needed
    }

    node_x, node_y, node_text, node_colors = [], [], [], []
    annotations = []
    for nid, data in G.nodes(data=True):
        x, y = pos[nid]
        node_x.append(x)
        node_y.append(y)

        # Get display name for the annotation
        display_name = get_display_name(nid, data["name"])

        hover = (
            f"ID: {nid}<br>"
            f"Name: {data['name']}<br>"
            f"Kind: {data['kind']}<br>"
            f"Maturity: {data['maturity']}<br>"
            f"Embodiment: {data['principle']}<br>"
            f"#Models: {data['n_models']}<br>"
            f"Desc: {data['desc'][:80]}…"
        )
        node_text.append(hover)
        node_colors.append(color_map.get(data["kind"], "gray"))
        annotations.append(
            {
                "x": x + 0.02,
                "y": y + 0.02,
                "text": display_name,
                "showarrow": False,
                "font": {"size": 16, "color": "black", "family": "Arial Black"},  # Increased font size
            }
        )

    edge_x, edge_y = [], []
    arrow_anns = []
    for src, dst in G.edges():
        x0, y0 = pos[src]
        x1, y1 = pos[dst]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
        arrow_anns.append(
            {
                "ax": x0,
                "ay": y0,
                "x": x1,
                "y": y1,
                "showarrow": True,
                "arrowhead": 3,
                "arrowsize": 1.5,
                "arrowwidth": 1.5,
            }
        )

    edge_trace = go.Scatter(x=edge_x, y=edge_y, mode="lines", line={"width": 2})  # Increased line width
    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers",
        marker={"color": node_colors, "size": 25},  # Increased node size
        hoverinfo="text",
        text=node_text,
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title={
                "text": "Design State Graph",
                "font": {"size": 20, "family": "Arial Black"},  # Larger title
            },
            showlegend=False,
            hovermode="closest",
            annotations=annotations + arrow_anns,
            xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            # Reduce margins to bring nodes closer to edges
            margin={"l": 20, "r": 20, "t": 40, "b": 20},
            # Set a fixed height and width for better control
            height=700,
            width=900,
        ),
    )
    fig.show()
    return "Visualization displayed successfully."


def summarize_design_state_func(design_graph: DesignState) -> str:
    """
    Summarize the current design graph in full detail:
      - DesignNode ID, Name, Kind, Description
      - Embodiment (principle, description, parameters, cost, mass, status)
      - Physics Models (name, equations, python_code, assumptions, status)
      - Maturity & Tags
      - Incoming & Outgoing Edges
    """
    lines = []
    for nid, node in design_graph.nodes.items():
        # Get connectivity from the single source of truth
        incoming, outgoing = get_node_edges(design_graph, nid)
        incoming_str = ", ".join(incoming) or "None"
        outgoing_str = ", ".join(outgoing) or "None"

        # Embodiment block
        emb = node.embodiment
        emb_params = ", ".join(f"{k}={v}" for k, v in emb.design_parameters.items()) or "None"
        emb_block = (
            f"  Embodiment:\n"
            f"    Principle      : {emb.principle}\n"
            f"    Description    : {emb.description}\n"
            f"    Parameters     : {emb_params}\n"
            f"    Cost Estimate  : {emb.cost_estimate}\n"
            f"    Mass Estimate  : {emb.mass_estimate}\n"
            f"    EmbodimentStat : {emb.status}\n"
        )

        # Physics models block
        if node.physics_models:
            pm_lines = []
            for pm in node.physics_models:
                assumptions = "; ".join(pm.assumptions) or "None"
                pm_lines.append(
                    "    • Model Name   : " + pm.name + "\n"
                    "      Equations    : " + pm.equations + "\n"
                    "      Python Code  : " + pm.python_code + "\n"
                    "      Assumptions  : " + assumptions + "\n"
                    "      Status       : " + pm.status
                )
            pm_block = "  Physics Models:\n" + "\n".join(pm_lines) + "\n"
        else:
            pm_block = "  Physics Models: None\n"

        # Tags
        tags = ", ".join(node.tags) or "None"

        block = (
            f"ID: {nid}\n"
            f"  Name       : {node.name}\n"
            f"  Kind       : {node.node_kind}\n"
            f"  Description: {node.description}\n\n" + emb_block + "\n" + pm_block + "\n"
            f"  Maturity   : {node.maturity}\n"
            f"  Tags       : {tags}\n\n"
            f"  Incoming Edges: {incoming_str}\n"
            f"  Outgoing Edges: {outgoing_str}\n" + "-" * 60
        )
        lines.append(block)

    return "\n".join(lines)


def analyze_node_func(design_graph: DesignState, node_id: str) -> str:
    """
    Analyze a specific node in the design graph.

    This function retrieves the node identified by 'node_id' from the design graph and returns a
    formatted summary that includes:
      - DesignNode ID
      - Name
      - DesignNode type
      - Status
      - Incoming Edges (dependencies)
      - Outgoing Edges (influences)
      - Payload contents

    Args:
        design_graph: The design graph to analyze
        node_id: The unique identifier of the node to analyze.

    Returns:
        A formatted string summarizing the node details.
    """
    if node_id not in design_graph.nodes:
        return f"❌ Error: DesignNode '{node_id}' not found in the design graph."

    node = design_graph.nodes[node_id]
    incoming, outgoing = get_node_edges(design_graph, node_id)
    incoming_str = ", ".join(incoming) if incoming else "None"
    outgoing_str = ", ".join(outgoing) if outgoing else "None"

    summary = (
        f"🔍 **DesignNode Analysis:**\n"
        f"-----------------\n"
        f"🆔 **ID:** {node.node_id}\n"
        f"🏷️ **Name:** {node.name}\n"
        f"🔹 **Type:** {node.node_kind}\n"
        f"📌 **Status:** {node.maturity}\n"
        f"⬅️ **Incoming Edges (dependencies from):** {incoming_str}\n"
        f"➡️ **Outgoing Edges (influences to):** {outgoing_str}\n"
        f"🗃 **Description:** {node.description}\n"
        "-------------------------------------"
    )

    return summary
