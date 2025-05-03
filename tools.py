from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.utilities import ArxivAPIWrapper
from langchain_community.document_loaders import ArxivLoader
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.retrievers import ArxivRetriever
from langchain_experimental.utilities import PythonREPL
from langchain_core.tools import tool
from typing import Annotated, List, Tuple
from graph_utils import update_node_func, visualize_design_state_func, summarize_design_state_func, add_node_func, delete_node_func
import plotly.graph_objects as go
import networkx as nx
from data_models import State, DesignState
from config import config

# TODO: fix all tools as they cannot use state as argumen;, and only design_graph is needed
# 🔹 **Tool decorator for LangGraph**
@tool("update_node", return_direct=True)
def update_node_tool(state: State, node_id: str, updates: dict) -> str:
    """
    Tool for updating a node in the design graph.
    """
    current_design_graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    return update_node_func(current_design_graph, node_id, updates)

@tool("visualize_design_state", return_direct=True)
def visualize_design_state_tool(state: State) -> str:
    """
    Generate and display an interactive visualization of the current design state's node graph.
    Uses Plotly to produce the visualization and calls fig.show() to open the figure.
    
    Returns:
        A confirmation message indicating that the visualization has been displayed.
    """
    current_design_graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    return visualize_design_state_func(current_design_graph)

@tool("summarize_design_state", return_direct=True)
def summarize_design_state_tool(state: State) -> str:
    """
    Generate a summary of the current design state.
    
    Returns:
        A string containing the summary of the design state.
    """
    current_design_graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    return summarize_design_state_func(current_design_graph)

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

# Initialize Arxiv API wrapper
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

# Initialize search tools lazily
def get_tavily_tool():
    return TavilySearchResults(api_key=config.tavily_api_key, max_results=1)

def get_duckduckgo_tool():
    return DuckDuckGoSearchResults(max_results=1)

# Initialize tools when needed
tavily_tool = get_tavily_tool()
duckduckgo_tool = get_duckduckgo_tool()

@tool("add_node", return_direct=True)
def add_node_tool(state: State, node_info: dict, edges_to_add: List[Tuple[str, str]] = []) -> str:
    """
    Tool for adding a new node to the design graph and optionally connecting it to other nodes.
    
    Args:
        state: The current state containing the design graph
        node_info: A dictionary containing node attributes such as 'node_id', 'node_type', 'name', 'payload', and 'status'
        edges_to_add: A list of (source_id, target_id) tuples representing directed edges to add
    
    Returns:
        A confirmation message indicating the node was added successfully
    """
    current_design_graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    return add_node_func(current_design_graph, node_info, edges_to_add)

@tool("delete_node", return_direct=True)
def delete_node_tool(state: State, node_id: str, recursive: bool = True) -> str:
    """
    Tool for deleting a node from the design graph and optionally its children.
    
    Args:
        state: The current state containing the design graph
        node_id: The ID of the node to delete
        recursive: Whether to recursively delete child nodes that have no other parents
    
    Returns:
        A confirmation message indicating the node was deleted successfully
    """
    current_design_graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    return delete_node_func(current_design_graph, node_id, recursive)