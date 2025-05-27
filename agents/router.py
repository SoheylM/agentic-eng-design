from langgraph.types import Command
from typing import Literal
from data_models import State

# TODO: Check if this is needed
def router_node(state: State) -> Command[Literal["human", "supervisor"]]:
    """Routes to the correct agent based on `active_agent` state variable."""
    return Command(
        goto=state.active_agent 
    )