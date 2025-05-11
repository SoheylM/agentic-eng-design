# agents/generation_pair.py
from typing import List, Literal
from dataclasses import dataclass, field
import operator
from langgraph.graph import Command
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from llm_models import get_llm  # tiny helper you already have

@dataclass
class PairState:
    messages:      List[BaseMessage] = field(default_factory=list)
    first_pass:    bool              = True
    user_request:  str               = ""
    proposal:      List[str]         = field(default_factory=list)
    feedback:      List[str]         = field(default_factory=list)

_GE_PROMPT = open("prompts/generation_pair.txt").read()  # drop the long prompt there

LLM = get_llm()

def node(state: PairState) -> Command[Literal["reflection_pair"]]:
    """Generation step of the 2-agent loop."""
    user_request = state.messages[-1].content if state.first_pass else state.user_request
    gen_user_msg = f"""
Develop functional decomposition → subsystem mapping → numerical code
for:  {user_request}

Prev-proposal: {state.proposal[-1] if not state.first_pass else '—'}
Prev-feedback: {state.feedback[-1] if not state.first_pass else '—'}
"""

    output = LLM.invoke([SystemMessage(_GE_PROMPT), HumanMessage(gen_user_msg)])

    update = {
        "messages": [output],
        "proposal": [output.content],
        "user_request": user_request,
        "first_pass": False,
    }
    return Command(update=update, goto="reflection_pair")
