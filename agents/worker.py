from typing import Literal

from IPython.display import Markdown, display
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command

from data_models import EngineeringTask, WorkerAnalysis
from llm_models import bra_model
from prompts import BRA_PROMPT
from utils import process_tool_calls, remove_think_tags


def worker_node(task: EngineeringTask) -> Command[Literal["generation"]]:
    """Engineering Worker Agent that can search the web and arxiv."""

    print("\n🔧 [DEBUG] Worker node invoked with task:")
    print(f"📌 Topic: {task.topic}")
    print(f"📌 Description: {task.description}")
    print(f"🔁 Returning to: {task.return_to_agent}")

    display(Markdown(f"**Executing Task**: {task.topic}"))

    # Extract task details
    system_prompt = BRA_PROMPT
    task_str = f"Engineering Task: {task.topic}\n\nDescription: {task.description}"

    # Define messages for the LLM call
    messages = [
        SystemMessage(system_prompt),
        HumanMessage(task_str),
    ]

    print("🟢 [DEBUG] Sending task to Worker Agent LLM...")
    bra_output = bra_model.invoke(messages)
    bra_output.content = remove_think_tags(bra_output.content).strip()

    # Process any tool calls the worker may request (e.g., web search, Python REPL)
    tool_messages = process_tool_calls(bra_output)
    messages.extend(tool_messages)  # TODO: check if that's what I want in the end.

    # Wrap the worker's output with metadata
    worker_analysis = WorkerAnalysis(
        content=bra_output.content,
        from_task=task.topic,
        step_index=0,  # TODO left at zero for now state.current_step_index,
        called_by_agent=task.return_to_agent,  # state.current_requesting_agent or "unknown"
    )

    print(f"✅ [DEBUG] Worker finished. Returning analysis to '{task.return_to_agent}'.")

    # Return the analysis and route back to the calling agent
    return Command(
        update={"analyses": [worker_analysis]},
        goto=task.return_to_agent,  # state.current_requesting_agent
    )
