"""
Reflection stage for the 2-agent ablation loop.

• Reads the latest proposal that `generation_pair` dropped in state.proposal[-1]
• Produces structured feedback
• If the feedback contains the *exact* sentinel phrase “Garde la peche”
  → the workflow terminates (goto=END)
• Otherwise the loop continues (goto="generation_pair")
"""

from typing import List, Literal
from dataclasses import dataclass, field
import operator
from langgraph.graph import Command, END
from langchain_core.messages import SystemMessage, HumanMessage
from llm_models import get_llm                      # already in repo
from agents.generation_pair import PairState        # re-use the same state dataclass

# --------------------------------------------------------------------------- #
# Prompt template lives in a text file for easy editing
# --------------------------------------------------------------------------- #
_RE_PROMPT = open("prompts/reflection_pair.txt", encoding="utf8").read()

LLM = get_llm()  # same helper you use everywhere else


def node(state: PairState) -> Command[Literal["generation_pair", END]]:
    """
    Produce feedback on the latest proposal.

    Decision rule:
    • if feedback contains “Garde la peche”  → stop (END)
    • else                                   → back to generation
    """
    user_request = state.user_request
    proposal     = state.proposal[-1]        # newest
    prior_fb     = state.feedback[-1] if state.feedback else "—"

    reflection_user_msg = f"""
You are reviewing a design for the request:
    {user_request}

----------  Latest proposal  ----------
{proposal}

----------  Previous feedback (if any) ----------
{prior_fb}

Remember: write **Garde la peche** only when the design fully satisfies
the Cahier des Charges and no more changes are needed.
"""

    output = LLM.invoke([
        SystemMessage(_RE_PROMPT),
        HumanMessage(reflection_user_msg)
    ])

    feedback_text = output.content
    update = {
        "messages": [output],
        "feedback": [feedback_text],
    }

    if "Garde la peche" in feedback_text:
        # Design loop is done – exit
        return Command(update=update, goto=END)

    # Otherwise hand the feedback back to the generator
    return Command(update=update, goto="generation_pair")
