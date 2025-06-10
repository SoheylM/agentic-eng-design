import re
import json
import uuid
from langchain_core.messages import ToolMessage  # Ensure correct import
from typing import List, Optional
from tools import python_repl_tool, tavily_tool, duckduckgo_tool, arxiv_search_tool, summarize_design_state_tool, visualize_design_state_tool, add_node_tool, delete_node_tool

from pathlib import Path
import json
from datetime import datetime, UTC
from data_models import DesignState

def remove_think_tags(text):
    return re.sub(r'^.*?</think>\s*', '', text, flags=re.DOTALL)

def separate_think_tags(text):
    """
    Separates content within think tags from the rest of the text.
    Returns a tuple of (think_content, rest_content) where:
    - think_content is the text within <think> tags
    - rest_content is everything else
    """
    think_pattern = r'<think>(.*?)</think>'
    think_match = re.search(think_pattern, text, flags=re.DOTALL)
    
    think_content = think_match.group(1) if think_match else ""
    rest_content = re.sub(think_pattern, '', text, flags=re.DOTALL).strip()
    
    return think_content, rest_content

def remove_think_tags_ollama(text):
    return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)


def process_tool_calls(ai_msg) -> List[ToolMessage]:
    """
    Extracts and executes any tool calls issued by the LLM in ai_msg, 
    returning new messages (ToolMessage or AIMessage) with the tool outputs.
    """
    tool_calls = None

    # 1) Try to parse JSON from ai_msg.content
    try:
        parsed_content = json.loads(ai_msg.content)
        print(f"🔍 [DEBUG] Parsed content in process_tool_calls: {parsed_content}")
        # Handle both dictionary and list formats
        if isinstance(parsed_content, dict):
            if parsed_content.get("type") == "function":
                # Handle nested function structure
                function_data = parsed_content.get("function", {})
                name = function_data.get("name")
                if not name:
                    print("🚨 [DEBUG] Function call missing name field, skipping...")
                else:
                    tool_calls = [{
                        "name": name,
                        "args": function_data.get("parameters", {}),
                        "id": str(uuid.uuid4())
                    }]
        elif isinstance(parsed_content, list):
            # Assume each item in the list is a tool call
            tool_calls = []
            for item in parsed_content:
                if isinstance(item, dict):
                    # Handle both direct and nested function structures
                    name = None
                    args = {}
                    
                    if "function" in item:
                        # Nested structure
                        function_data = item.get("function", {})
                        name = function_data.get("name")
                        args = function_data.get("parameters", {})
                    else:
                        # Direct structure
                        name = item.get("name")
                        args = item.get("args", {})
                    
                    if name:
                        tool_calls.append({
                            "name": name,
                            "args": args,
                            "id": str(uuid.uuid4())
                        })
    except (json.JSONDecodeError, TypeError) as e:
        print(f"🔍 [DEBUG] JSON parsing error: {e}")
        pass

    # 2) Or check if the model attached tool_calls in ai_msg.tool_calls
    if not tool_calls and hasattr(ai_msg, "tool_calls"):
        tool_calls = ai_msg.tool_calls

    # If no calls, just return an empty list
    if not tool_calls:
        print("🔍 [DEBUG] No tool calls detected.")
        return []

    print("🔧 [DEBUG] Tool calls detected. Processing...\n")
    new_messages = []

    for call in tool_calls:
        try:
            # Safely get the tool name and args with defaults
            tool_name = call.get("name", "").lower()
            if not tool_name:
                print("🚨 [DEBUG] Tool call missing name field, skipping...")
                continue
                
            tool_args = call.get("args", {})
            tool_id = call.get("id", str(uuid.uuid4()))

            print("🟡 [DEBUG] Processing tool call:")
            print(f"   🔹 Tool Name: {tool_name}")
            print(f"   🔹 Arguments: {tool_args}")
            print(f"   🔹 Tool Call ID: {tool_id}")

            # Wrap the invocation in try-except to catch errors.
            try:
                if tool_name == "python_repl_tool":
                    print("🟠 [DEBUG] Invoking Python REPL Tool...")
                    tool_output = python_repl_tool.invoke(tool_args)

                elif tool_name == "tavily_search_results_json":
                    print("🟠 [DEBUG] Invoking Web Search Tool (Tavily)...")
                    tool_output = tavily_tool.invoke(tool_args)
                    # Extract relevant content from search results
                    if isinstance(tool_output, list):
                        tool_output = " ".join(
                            [f"{i+1}) {item.get('content', 'No Content')}" for i, item in enumerate(tool_output)]
                        )

                elif tool_name == "duckduckgo_results_json":
                    print("🟠 [DEBUG] Invoking Web Search Tool (DuckDuckGo)...")
                    tool_output = duckduckgo_tool.invoke(tool_args)
                    # Extract relevant content from search results
                    if isinstance(tool_output, list):
                        tool_output = " ".join(
                            [f"{i+1}) {item.get('content', 'No Content')}" for i, item in enumerate(tool_output)]
                        )

                elif tool_name == "arxiv_search":
                    print("🟠 [DEBUG] Invoking Arxiv Search Tool...")
                    tool_output = arxiv_search_tool.invoke(tool_args)

                elif tool_name == "add_node":
                    print("🟠 [DEBUG] Invoking Add Node Tool...")
                    tool_output = add_node_tool.invoke(tool_args)

                elif tool_name == "delete_node":
                    print("🟠 [DEBUG] Invoking Delete Node Tool...")
                    tool_output = delete_node_tool.invoke(tool_args)

                elif tool_name == "summarize_design_state":
                    print("🟠 [DEBUG] Invoking Summarize Design State Tool...")
                    tool_output = summarize_design_state_tool.invoke(tool_args)

                elif tool_name == "visualize_design_state":
                    print("🟠 [DEBUG] Invoking Visualize Design State Tool...")
                    tool_output = visualize_design_state_tool.invoke(tool_args)

                else:
                    tool_output = f"❌ Error: Unrecognized tool '{tool_name}'"
                    print(f"🚨 [DEBUG] Unknown tool call received: {tool_name}")
            except Exception as e:
                tool_output = f"❌ Error invoking tool '{tool_name}': {repr(e)}"
                print(f"🚨 [DEBUG] Exception during tool call: {tool_output}")

            print(f"🟢 [DEBUG] Tool Output: {tool_output}\n")

            new_messages.append(
                ToolMessage(content=tool_output, tool_call_id=tool_id)
            )
        except Exception as e:
            print(f"🚨 [DEBUG] Error processing tool call: {e}")

    print("🟡 [DEBUG] Finished processing tool calls.")
    return new_messages


def save_dsg(
    dsg: DesignState,
    thread_id: str,
    step_idx: int,
    save_folder: Optional[str] = None,
) -> Path:
    """
    Dump one Design-State Graph to
        runs/<timestamp>_<uuid>/DSG_<index>.json
    and return the file path.
    """
    if save_folder is None:
        # Create new folder with timestamp and UUID
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        base_dir = Path("runs") / f"{ts}_{thread_id}"
    else:
        # Use existing folder
        base_dir = Path("runs") / save_folder

    base_dir.mkdir(parents=True, exist_ok=True)

    # Simple sequential naming
    fname = f"DSG_{step_idx}.json"
    path = base_dir / fname
    path.write_text(json.dumps(json.loads(dsg.model_dump_json()), indent=2))
    return path