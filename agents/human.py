from langgraph.types import Command,interrupt
from typing import Literal
from data_models import State



def human_node(state: State) -> Command[Literal["requirements", "planner"]]:
    """Handles user interaction and dynamically routes to the next agent."""
    print("📝 [DEBUG] HUMAN NODE ACCESSED")

    messages = state.messages
    print("DEBUG: HUMAN INTERRUPT")
    user_input = interrupt(value=f"Ready for user input. This is what the agent has come up with {messages}")

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
