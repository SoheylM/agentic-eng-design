from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from langgraph.types import Command
from typing import Literal, List, Optional
from data_models import State, SingleProposal, Proposal
from prompts import ME_PROMPT, RESEARCH_PROMPT_META_REVIEW, REASON_REFINEMENT_PROMPT
from llm_models import meta_reviewer_agent, base_model_reasoning
from utils import remove_think_tags


def meta_review_node(state: State) -> Command[Literal["orchestrator", "synthesizer"]]:
    """
    Meta-Review Agent:
    - Evaluates final proposals based on structured feedback and assigns final statuses.
    - Requests additional research if needed.
    """
    print("\n🔎 [DEBUG] Meta-Review node invoked.")

    iteration = state.meta_review_iteration
    max_iterations = state.max_iterations

    print(f"\n🔄 [DEBUG] Meta-Review iteration {iteration + 1}/{max_iterations}...")

    if iteration >= max_iterations:
        print("⚠️ [DEBUG] Max iterations reached. Proceeding to synthesizer.")
        return Command(
            update={"meta_review_notes": [f"Stopped after {max_iterations} iterations."],
                    "meta_review_iteration": iteration - 1,
                    },
            goto="synthesizer"
        )

    # Retrieve Supervisor Instructions & Cahier des Charges
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No Cahier des Charges available."

    # Retrieve the most recent proposals
    recent_proposals = [
        p for p in state.proposals
        if p.current_step_index == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]

    if not recent_proposals:
        print("⚠️ [DEBUG] No valid proposals found. Skipping meta-review.")
        return Command(
            update={"meta_review_notes": ["No proposals available for meta-review."]},
            goto="synthesizer"
        )

    print(f"🔍 [DEBUG] Reviewing {len(recent_proposals)} proposals.")

    # **Invoke Meta-Review Agent**
    mr_output = meta_reviewer_agent.invoke([
        SystemMessage(content=ME_PROMPT),
        HumanMessage(content=f"""
### **Supervisor's Instructions for This Design Step**:
{supervisor_instructions}

### **Cahier des Charges Summary**:
{cahier_des_charges}

### **Proposals Under Review**:
{[p.content for p in recent_proposals]}

---

## **🔹 Task for the Meta-Review Agent**
1. **Assign final statuses** to each proposal (selected, rejected, or needs more iteration).
2. **Ensure decisions align with Supervisor's objectives and Cahier des Charges.**
3. **Return structured JSON output with final statuses and reasons.**
""")
    ])

    print(f"📝 [DEBUG] Received meta-review decisions for {len(mr_output.decisions)} proposals.")

    # **Refine reason for status for each proposal**
    for idx, dec in enumerate(mr_output.decisions):
        #idx = dec.proposal_index
        if 0 <= idx < len(recent_proposals):
            refined_reason = refine_reason(recent_proposals[idx], state, dec.reason)
            recent_proposals[idx].reason_for_status = refined_reason
            recent_proposals[idx].status = dec.final_status
            recent_proposals[idx].meta_review_iteration_index = iteration
            print(f"✅ [DEBUG] Refined Reason for Proposal {idx}: {refined_reason}")

    # **Determine if additional research is needed**
    orchestrator_order = decide_if_more_research_needed_meta_review(state)
    if orchestrator_order:
        print(f"🧠 [DEBUG] Sending order to orchestrator: {orchestrator_order}")
        return Command(
            update={
                "orchestrator_orders": [orchestrator_order],
                "meta_review_notes": [f"Requested more worker tasks after iteration {iteration + 1}."],
                "current_requesting_agent": "meta_review",
                "current_tasks_count": 0,
                "meta_review_iteration": iteration + 1,
            },
            goto="orchestrator"
        )

    # **Store the final decision for the Design Graph Agent**
    big_summary = f"Meta-Review Summary:\n{mr_output.detailed_summary_for_graph}"
    print(f"⚠️ [DEBUG] Meta-review big summary: {big_summary}.")

    print("✅ [DEBUG] Meta-review complete. Proceeding to synthesizer.")
    return Command(
        update={
            "selected_proposal_index": mr_output.selected_proposal_index,
            "meta_review_notes": [big_summary],
            "meta_review_iteration": iteration #+ 1,
        },
        goto="synthesizer"
    )


def decide_if_more_research_needed_meta_review(state: State) -> Optional[str]:
    """
    Determines whether additional research is required to improve the final selection in Meta-Review.
    Sends a clear request to the Orchestrator if needed.
    """
    print("\n🔍 [DEBUG] Checking if additional research is needed for Meta-Review Agent.")

    # **Retrieve Supervisor Instructions & Cahier des Charges**
    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges_summary = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    # **Retrieve Selected Proposal**
    recent_proposals = [
        p for p in state.proposals
        if p.current_step_index == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]
    selected_proposal = next((p for p in recent_proposals if p.status == "selected"), None)

    if not selected_proposal:
        print("⚠️ [DEBUG] No selected proposal found. Skipping research validation.")
        return None

    # **Retrieve Worker Analyses (if available)**
    worker_analyses = [
        f"Task '{a.from_task}': {a.content}" for a in state.analyses if a.called_by_agent == "meta_review"
    ]
    worker_analyses_text = "\n\n---\n\n".join(worker_analyses) if worker_analyses else "No additional worker analyses available."

    # **Prepare research validation request**
    research_request = f"""
### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges Summary:**
{cahier_des_charges_summary}

### **Selected Proposal for Final Review:**
- **Content:** {selected_proposal.content}
- **Reflection Feedback:** {selected_proposal.feedback or "No prior feedback"}
- **Ranking Grade:** {selected_proposal.grade if selected_proposal.grade is not None else "Not yet scored"}
- **Evolved Content:** {selected_proposal.evolved_content or "No evolution applied"}
- **Final Status:** {selected_proposal.status}
- **Reason for Status:** {selected_proposal.reason_for_status or "No justification provided."}

### **Worker Analyses (if available):**
{worker_analyses_text}

---

## **🔹 Task for the Meta-Review Agent**
- Evaluate whether the **selected proposal is complete, well-validated, and technically sound**.
- Identify **any missing research, validation, or external factors that require verification**.
- If additional research is required, **define a precise task request for the Orchestrator** (expert validation, case studies, industry standards).
- If no research is required, state explicitly: `"No additional research is needed."`
"""

    # **Invoke base model for open-ended meta-review validation**
    decision_output = base_model_reasoning.invoke([
        SystemMessage(content=RESEARCH_PROMPT_META_REVIEW),
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


# 🔹 **Refining Reason for Status with Additional LLM Call**
def refine_reason(proposal: Proposal, state: State, raw_reason: str) -> str:
    """
    Uses an additional LLM call to refine the reason given for a proposal's final status.
    Ensures **structured, actionable, and precise justification**.
    """
    print(f"📝 [DEBUG] Refining reason for proposal: {proposal.title}")

    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    refinement_prompt = [
        SystemMessage(content=REASON_REFINEMENT_PROMPT),
        HumanMessage(content=f"""
### **Proposal Title:**
{proposal.title}

### **Proposal Content:**
{proposal.content}

### **Raw Reason for Status:**
{raw_reason}

---

### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges (Engineering Constraints):**
{cahier_des_charges}

### **Reflection Feedback:**
{proposal.feedback or "No prior feedback"}

### **Ranking Score:**
{proposal.grade if proposal.grade is not None else "Not yet scored"}

### **Evolution Justification:**
{proposal.evolution_justification or "No evolution applied"}

---

### **Your Task:**
1. **Refine the reason for status** to ensure:
   - It is **specific, actionable, and structured**.
   - It provides **clear technical reasoning**.
   - It integrates **any relevant engineering constraints**.
2. **If the reason is already optimal**, keep it unchanged.
3. **Return only the refined reason text.**
""")
    ]

    #refined_reason = base_model.invoke(refinement_prompt).content
    refined_reason = remove_think_tags(base_model_reasoning.invoke(refinement_prompt).content)
    return refined_reason