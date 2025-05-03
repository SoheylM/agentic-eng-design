from langgraph.types import Command
from typing import Literal
from data_models import State
import streamlit as st



def human_node(state: State) -> Command[Literal["requirements", "planner"]]:
    """Handles user interaction and dynamically routes to the next agent."""
    print("📝 [DEBUG] HUMAN NODE ACCESSED")

    messages = state.messages
    print("DEBUG: HUMAN INTERRUPT")
    
    # Get the last user message from the state
    user_input = messages[-1]["content"] if messages else ""

    if user_input.upper() == "END":
        print("✅ Ending discussion, finalizing requirements, moving to planner.")
        return Command(
            update={
                "messages": [{"role": "user", "content": user_input}],
                "active_agent": "planner"  # ✅ Set planner as the next active agent
            },
            goto="planner"
        )

    return Command(
        update={"messages": [{"role": "user", "content": user_input}]},
        goto="requirements"
    )
