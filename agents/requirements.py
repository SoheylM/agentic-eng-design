from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from typing import Literal
from data_models import State
from prompts import REQ_PROMPT
from llm_models import base_model
from IPython.display import display, Markdown
from llm_models import req_structured_model
from utils import remove_think_tags

def requirements_node(state: State) -> Command[Literal["human", "planner"]]:
    """Iterates with the human until requirements are finalized, then outputs a structured Cahier des Charges."""
    print("📝 [DEBUG] REQUIREMENTS NODE ACCESSED")

    # **Step 1: Base LLM for Interactive Discussion**
    messages = [SystemMessage(content=REQ_PROMPT), *state.messages]
    req_output = base_model.invoke(messages)
    req_output.content = remove_think_tags(req_output.content).strip()

    display(Markdown(f"### 📜 Requirements Agent Response:\n\n{req_output.content}"))


    # **Step 2: If FINALIZED, Generate Structured Cahier des Charges**
    if "FINALIZED" in req_output.content:
        print("✅ Cahier des Charges finalized. Generating structured output...")

        # Invoke **structured LLM** to format the final Cahier des Charges
        structured_output = req_structured_model.invoke([
            SystemMessage(content="Convert the finalized requirements into a structured Cahier des Charges."),
            HumanMessage(content=req_output.content)
        ])
        structured_output = remove_think_tags(structured_output).strip()

        print(f"📜 Generated Cahier des Charges:\n{structured_output.model_dump_json()}")


        return Command(
            update={
                "cahier_des_charges": structured_output,  # ✅ Store the structured output
                "active_agent": "planner"  # ✅ Move to Planner
            },
            goto="planner"
        )

    # **Step 3: Continue Iteration with Human**
    return Command(
        update={"messages": [AIMessage(content=req_output.content)]},  
        goto="human"
    )
