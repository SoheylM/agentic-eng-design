from langgraph.types import Command
from typing import Literal
from data_models import State
from langchain_core.messages import HumanMessage
import streamlit as st



def human_node(state: State) -> Command[Literal["requirements", "supervisor"]]:
    """Handles user interaction and dynamically routes to the next agent."""
    print("📝 [DEBUG] HUMAN NODE ACCESSED")

    # Get the last user message from the state
    if not state.messages:
        print("⚠️ No messages in state")
        return Command(
            update={"messages": []},
            goto="requirements"
        )
    
    last_message = state.messages[-1]
    user_input = last_message.content if hasattr(last_message, 'content') else str(last_message)
    print(f"DEBUG: Processing user input: {user_input}")

    if user_input.upper() == "END":
        print("✅ Ending discussion, finalizing requirements, moving to planner.")
        return Command(
            update={
                "messages": [HumanMessage(content=user_input)],
                "active_agent": "supervisor"
            },
            goto="supervisor"
        )

    return Command(
        update={"messages": [HumanMessage(content=user_input)]},
        goto="requirements"
    )
