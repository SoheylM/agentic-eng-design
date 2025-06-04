# agents/generation_pair.py
from typing import List, Literal
from langgraph.types import Command
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from data_models import PairState
from llm_models import pair_generation_agent
from prompts import GE_PROMPT_STRUCTURED
from IPython.display import display, Markdown

def generation_pair_node(state: PairState) -> Command[Literal["reflection_pair"]]:

    first_pass = state.first_pass
    if first_pass: 
        user_request = state.messages[-1]
    else:
        user_request = state.user_request
    

    generation_user_message = f"""
    Develop functional decomposition, subsystem mapping, develop matching numerical code. 
    This is the user request : {user_request}.

    If you have already worked on this, here is your previous work:
    {state.proposal[-1] if not first_pass else "Nope, that's your first pass"}

    And here is the feedback on that prior work from an expert in the field:
    {state.feedback[-1] if not first_pass else "No feedback available yet"}
    """

    base_model_output = pair_generation_agent.invoke([
        SystemMessage(content=GE_PROMPT_STRUCTURED),
        HumanMessage(content=generation_user_message)
    ])

    display(Markdown(f"**Generator Response:** {base_model_output.content}"))


    if first_pass:
        return Command(
            update={
                "messages": [base_model_output.content],
                "user_request": user_request,
                "first_pass": False,
                "proposal": [base_model_output.content],
            },
            goto="reflection_pair"
        )
    else:
        return Command(
            update={
                "messages": [base_model_output.content],
                "proposal": [base_model_output.content],
            },
            goto="reflection_pair"
        )
        
