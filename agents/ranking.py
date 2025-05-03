from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from typing import Literal, List, Optional
from data_models import State, SingleRanking
from prompts import RA_PROMPT, RESEARCH_PROMPT_RANKING
from llm_models import ranking_agent, base_model_reasoning
from utils import remove_think_tags

def ranking_node(state: State) -> Command[Literal["orchestrator", "evolution"]]:
    """
    Ranking agent that assigns scores to proposals iteratively, ensuring alignment with:
    - Supervisor Instructions
    - Cahier des Charges
    - Reflection Agent's feedback
    - Past proposal scores
    """
    print("\n🔺 [DEBUG] Ranking node invoked.")

    iteration = state.ranking_iteration
    max_iterations = state.max_iterations  # Adjust as needed

    print(f"\n🔄 [DEBUG] Ranking iteration {iteration + 1}/{max_iterations}...")

    if iteration >= max_iterations:
        print("⚠️ [DEBUG] Max iterations reached. Proceeding to evolution.")
        return Command(
            update={
                "ranking_notes": [f"Stopped after {max_iterations} iterations."],
                "analyses": [],
                "ranking_iteration": iteration - 1,
            },
            goto="evolution"
        )

    # **🔹 Retrieve Supervisor Instructions for this step**
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions available."

    # **🔹 Load the most recent proposals (Reflection + Prior Ranking)**
    for p in state.proposals:
        print(f"⚠️ [DEBUG] p.current_step_index: {p.current_step_index}")
        print(f"⚠️ [DEBUG] state.current_step_index: {state.current_step_index}")
        print(f"⚠️ [DEBUG] p.generation_iteration_index: {p.generation_iteration_index}")
        print(f"⚠️ [DEBUG] state.generation_iteration: {state.generation_iteration}")
        print(f"⚠️ [DEBUG] p.reflection_iteration_index: {p.reflection_iteration_index}")
        print(f"⚠️ [DEBUG] state.reflection_iteration: {state.reflection_iteration}")
        print(f"⚠️ [DEBUG] p.ranking_iteration_index: {p.ranking_iteration_index}")
        print(f"⚠️ [DEBUG] state.ranking_iteration: {state.ranking_iteration}")
    recent_proposals = [
        p for p in state.proposals #TODO: check if ti works
        if (p.current_step_index == state.current_step_index)
        and (p.generation_iteration_index == state.generation_iteration)
        #and (p.reflection_iteration_index == state.reflection_iteration)
        #and (p.ranking_iteration_index == state.ranking_iteration)
    ]

    if not recent_proposals:
        print("⚠️ [DEBUG] No valid proposals found. Skipping ranking.")
        return Command(
            update={
                "ranking_notes": ["No proposals available for ranking."],
                #"ranking_iteration": iteration,
            },
            goto="evolution"
        )

    # **🔹 Extract previous ranking scores if available**
    previous_rankings = "\n".join([
        f"- Proposal {i}: Previous Score = {p.grade}" for i, p in enumerate(recent_proposals) if p.grade is not None
    ]) if any(p.grade is not None for p in recent_proposals) else "No previous scores available."

    previous_ranking_justifications = "\n".join([
        f"- Proposal {i}: Previous Score = {p.ranking_justification}" for i, p in enumerate(recent_proposals) if p.ranking_justification is not None
    ]) if any(p.ranking_justification is not None for p in recent_proposals) else "No previous justifications available."

    # **🔹 Retrieve Cahier des Charges for constraint checking**
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No Cahier des Charges available."

    # **🔹 Construct ranking prompt**
    ranking_prompt = f"""
### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges:**
{cahier_des_charges}

### **Proposals Under Review:**
{[p.content for p in recent_proposals]}

### **Reflection Feedback:**
{[p.feedback or "No prior feedback" for p in recent_proposals]}

### **Previous Scores (if applicable):**
{previous_rankings}

### **Previous Justifications (if applicable):**
{previous_ranking_justifications}
---

## **🔹 Task for the Ranking Agent**
1. **Review each proposal individually** based on:
   - Supervisor’s current design step instructions.
   - Cahier des Charges constraints.
   - Reflection feedback.
   - Prior scores (if available).
2. **If a proposal has improved, increase its score.**
3. **If a proposal has worsened, lower its score.**
4. **If no change is necessary, maintain the same score.**
5. **Output structured JSON rankings for each proposal.**
"""

    # **🔹 Invoke LLM for ranking**
    rk_output = ranking_agent.invoke([
        SystemMessage(content=RA_PROMPT),
        HumanMessage(ranking_prompt)
    ])

    print(f"📝 [DEBUG] Received {len(rk_output.rankings)} updated rankings.")

    # **🔹 Ensure rankings match the number of proposals**
    if len(rk_output.rankings) != len(recent_proposals):
        print(f"⚠️ [DEBUG] Mismatch: {len(rk_output.rankings)} rankings for {len(recent_proposals)} proposals!")

    # **🔹 Update proposals with new scores**
    for r_item in rk_output.rankings:
        idx = r_item.proposal_index
        if 0 <= idx < len(recent_proposals):
            recent_proposals[idx].grade = r_item.grade
            recent_proposals[idx].ranking_justification = r_item.ranking_justification
            recent_proposals[idx].ranking_iteration_index = iteration #+ 1
            print(f"✅ [DEBUG] Updated Proposal {idx}: Score {r_item.grade}")
        else:
            print(f"⚠️ [DEBUG] Invalid proposal index {idx}. Ignoring.")

    # **🔹 Decide if additional research is needed**
    orchestrator_order = decide_if_more_research_needed_ranking(recent_proposals, state)
    if orchestrator_order:
        print(f"🧠 [DEBUG] Sending order to orchestrator: {orchestrator_order}")
        return Command(
            update={
                "orchestrator_orders": [orchestrator_order],
                "ranking_notes": [f"Requested more worker tasks after iteration {iteration + 1}."],
                "current_requesting_agent": "ranking",
                "current_tasks_count": 0,
                "ranking_iteration": iteration + 1,
            },
            goto="orchestrator"
        )

    print("✅ [DEBUG] Ranking complete. Proceeding to evolution.")
    return Command(
        update={
            "ranking_notes": [f"Completed ranking at step {state.current_step_index}."],
            "analyses": [],
            "ranking_iteration": iteration #+ 1,
        },
        goto="evolution"
    )


def decide_if_more_research_needed_ranking(proposals: List[SingleRanking], state: State) -> Optional[str]:
    """
    Determines whether additional research is required to improve proposal rankings.
    Sends a clear request to the Orchestrator if needed.
    """
    print("\n🔍 [DEBUG] Checking if additional research is needed for Ranking Agent.")

    # **Retrieve Supervisor Instructions & Cahier des Charges**
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges_summary = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    # **Retrieve Worker Analyses (if available)**
    worker_analyses = [
        f"Task '{a.from_task}': {a.content}" for a in state.analyses if a.called_by_agent == "ranking"
    ]
    worker_analyses_text = "\n\n---\n\n".join(worker_analyses) if worker_analyses else "No additional worker analyses available."

    # **Prepare research validation request**
    research_request = f"""
### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges Summary:**
{cahier_des_charges_summary}

### **Current Proposal Rankings:**
{[{"Index": i, "Content": p.content, "Score": p.grade, "Justification": p.ranking_justification} for i, p in enumerate(proposals)]}

### **Worker Analyses (if available):**
{worker_analyses_text}

---

## **🔹 Task for the Ranking Agent**
- Evaluate whether rankings are **accurate, justified, and well-supported**.
- **Identify any missing technical validation or research gaps** that could improve ranking accuracy.
- If additional research is required, **define a precise task request for the Orchestrator** (web searches, simulations, calculations).
- If no research is required, state explicitly: `"No additional research is needed."`
"""

    # **Invoke base model for open-ended ranking validation**
    decision_output = base_model_reasoning.invoke([
        SystemMessage(content=RESEARCH_PROMPT_RANKING),
        HumanMessage(content=research_request)
    ])

    # **Process the decision**
    response = remove_think_tags(decision_output.content) #.strip().lower()

    if "No additional research is needed" in response:
        print("✅ [DEBUG] No further research required.")
        return None
    else:
        print(f"🧠 [DEBUG] Additional research requested: {response}")
        return response
