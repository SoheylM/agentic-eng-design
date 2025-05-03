
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.utilities import ArxivAPIWrapper
from langchain_community.document_loaders import ArxivLoader
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.retrievers import ArxivRetriever
from langchain_experimental.utilities import PythonREPL
from langchain_core.tools import tool
from typing import Annotated
from graph_utils import update_node_func
import plotly.graph_objects as go
import networkx as nx

# 🔹 **Tool decorator for LangGraph**
@tool("update_node", return_direct=True)
def update_node_tool(node_id: str, updates: dict) -> str:
    """
    Update an existing node's attributes in the global design state.

    Args:
        node_id (str): The ID of the node to update.
        updates (dict): Dictionary containing attributes to modify.
                        Possible keys: 'name', 'node_type', 'status', 'payload', 'parents', 'children'.

    Returns:
        str: Confirmation message indicating the update status.
    """
    return update_node_func(node_id, updates)

@tool("visualize_design_state", return_direct=True)
def visualize_design_state_tool() -> str:
    """
    Generate and display an interactive visualization of the current design state's node graph.
    Uses Plotly to produce the visualization and calls fig.show() to open the figure.
    
    Returns:
        A confirmation message indicating that the visualization has been displayed.
    """
    G = nx.DiGraph()
    for node_id, node in DESIGN_STATE.nodes.items():
        G.add_node(node_id, name=node.name, node_type=node.node_type, payload=node.payload, status=node.status)
        for child in node.children:
            G.add_edge(node_id, child)
    pos = nx.spring_layout(G, seed=42)
    color_map = {
        "user_request": 'lightblue',
        "requirement":  'lightgreen',
        "objective_constraint": 'limegreen',
        "functional_decomposition": 'gold',
        "subfunction":  'orange',
        "subsystem":    'violet',
        "discipline":   'pink'
    }
    node_x, node_y, node_text, node_colors = [], [], [], []
    for node_id, data in G.nodes(data=True):
        x, y = pos[node_id]
        node_x.append(x)
        node_y.append(y)
        hover_text = (f"ID: {node_id}<br>Name: {data.get('name')}<br>"
                      f"Type: {data.get('node_type')}<br>Status: {data.get('status')}<br>"
                      f"Payload: {data.get('payload')}")
        node_text.append(hover_text)
        node_colors.append(color_map.get(data.get('node_type'), 'gray'))
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers',
        hoverinfo='text',
        text=node_text,
        marker=dict(color=node_colors, size=20, line_width=2)
    )
    edge_x, edge_y = [], []
    for source, target in G.edges():
        x0, y0 = pos[source]
        x1, y1 = pos[target]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1, color='#888'),
        hoverinfo='none',
        mode='lines'
    )
    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title=dict(text='<br>Organized Design State Tree', font=dict(size=16)),
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=40),
            annotations=[dict(
                text="Node colors represent node types",
                showarrow=False,
                xref="paper", yref="paper",
                x=0.005, y=-0.002
            )],
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
    )
    # Show the figure. This should open it in a new browser window or display inline depending on the environment.
    fig.show()
    return "Visualization displayed successfully."

# Initialize Python REPL Tool
repl = PythonREPL()

@tool
def python_repl_tool(
    code: Annotated[str, "The Python code to execute."],
):
    """Use this tool to execute Python code and return results."""
    try:
        result = repl.run(code)
    except BaseException as e:
        return f"Failed to execute. Error: {repr(e)}"
    
    return f"Successfully executed:\n```\n{code}\n```\nStdout: {result}"

arxiv = ArxivAPIWrapper()


@tool("arxiv_search", return_direct=True)
def arxiv_search_tool(
    query: Annotated[str, "The search query string for Arxiv papers."]
) -> str:
    """
    Use this tool to search for papers on Arxiv based on a query.
    
    Args:
        query: A string representing the search query (e.g., "gas bearing rotor").
    
    Returns:
        A string containing the search results.
    """
    try:
        results = arxiv.run(query)
    except Exception as e:
        return f"Error during Arxiv search: {str(e)}"
    
    return results

tavily_tool = TavilySearchResults(max_results=1)
duckduckgo_tool = DuckDuckGoSearchResults(max_results=1)