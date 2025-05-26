# agents/planner.py
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types import Command
from typing import Literal
import json

from data_models import State, CahierDesCharges, DesignPlan
from prompts     import PLANNER_PROMPT
from llm_models  import planner_model        # single model for everything


def planner_node(state: State) -> Command[Literal["supervisor", "human"]]:
    """Generate one concise DesignPlan and store it in state.design_plan."""

    print("\n📝  [Planner] invoked")

    # ------------------------------------------------------------------ CDC check
    if not state.cahier_des_charges:
        print("❌  [Planner] CDC missing – hand back to human")
        return Command(
            update={"messages": [AIMessage(content="❌ Cahier des Charges missing.")]},
            goto="human",
        )

    cdc_json = (
        state.cahier_des_charges.model_dump_json()
        if isinstance(state.cahier_des_charges, CahierDesCharges)
        else json.dumps(state.cahier_des_charges)
    )

    # ------------------------------------------------------------------ LLM call
    llm_messages = [
        SystemMessage(content=PLANNER_PROMPT),
        HumanMessage(content=cdc_json),
    ]

    try:
        plan: DesignPlan = planner_model.invoke(llm_messages)  # already validated
        plan = remove_think_tags(plan).strip()
    except Exception as e:
        err = f"❌  [Planner] LLM failed → {e}"
        print(err)
        return Command(update={"messages": [AIMessage(content=err)]}, goto="human")

    print(f"✅  [Planner] produced {len(plan.steps)} steps")
    print("\n📋 Design Plan Steps:")
    for step in plan.steps:
        print(f"  {step.step_id}. {step.name}")
        print(f"     Objectives: {step.objectives}")
        print(f"     Outputs: {step.expected_outputs}")

    # ------------------------------------------------------------------ state update
    return Command(
        update={
            "design_plan": plan,
            "messages": [AIMessage(content=f"✅ DesignPlan ready with {len(plan.steps)} steps.")],
            "active_agent": "supervisor",
        },
        goto="supervisor",
    )
