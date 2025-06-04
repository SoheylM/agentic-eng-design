# agents/generation_pair.py
from typing import List, Literal
from langgraph.types import Command
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from data_models import PairState
from llm_models import pair_generation_agent
from prompts import GE_PAIR_PROMPT
from IPython.display import display, Markdown
from graph_utils import summarize_design_state_func
from utils import remove_think_tags
from eval_saved import evaluate_dsg  # Import the evaluation function
from validation import filter_valid_proposals  # Import our validation functions

def generation_pair_node(state: PairState) -> Command[Literal["reflection_pair"]]:
    """
    • Generates *N* DSG proposals (defined in GE_PROMPT_STRUCTURED).
    """
    print("\n🔧 [GEN] Generation pair node")

    first_pass = state.first_pass
    if first_pass: 
        user_request = state.messages[-1]
    else:
        user_request = state.user_request

    # ── Context strings for the LLM ────────────────────────────────────────
    cdc_text    = state.cahier_des_charges or "No Cahier des Charges."
    graph_now   = state.design_graph_history[-1] if state.design_graph_history else DesignState()
    graph_sum   = summarize_design_state_func(graph_now)
    

    generation_user_message = f"""
    Develop functional decomposition, subsystem mapping, develop matching numerical code. 
    This is the user request : {user_request}.

    If you have already worked on this, here is your previous work:
    {state.proposal[-1] if not first_pass else "Nope, that's your first pass"}

    And here is the feedback on that prior work from an expert in the field:
    {state.feedback[-1] if not first_pass else "No feedback available yet"}
    """

    base_model_output = pair_generation_agent.invoke([
        SystemMessage(content=GE_PAIR_PROMPT),
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
        
