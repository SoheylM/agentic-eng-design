from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AnyMessage, BaseMessage, SystemMessage
from llm_models import synthesizer_llm, base_model_reasoning
from data_models import State, Proposal, NodeModification, DesignState
from prompts import SY_PROMPT, SUMMARY_REFINEMENT_PROMPT, PAYLOAD_REFINEMENT_PROMPT
from utils import remove_think_tags
from langgraph.types import Command
from typing import Literal
from graph_utils import summarize_design_state_func



def synthesizer_node(state: State) -> Command[Literal["graph_designer"]]:
    """
    Synthesizer Agent:
    - Processes the final selected proposal and determines structured modifications for the Design Graph.
    - Requests additional research if needed.
    """
    print("\n🔔 [DEBUG] Synthesizer node invoked.")

    # Retrieve Supervisor Instructions & Cahier des Charges
    supervisor_instructions = "\n".join(state.supervisor_instructions) if state.supervisor_instructions else "No specific guidance provided."
    cahier_des_charges_summary = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    # Find the final selected proposal
    # Retrieve the most recent proposals
    recent_proposals = [
        p for p in state.proposals
        if p.current_step_index == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]
    selected_proposal = next((p for p in recent_proposals if p.status == "selected"), None)

    if not selected_proposal:
        print("⚠️ [DEBUG] No selected proposal found. Skipping synthesis.")
        return Command(
            update={"synthesizer_notes": ["No selected proposal for synthesis."]},
            goto="graph_designer"
        )

    # Get the current design graph
    current_design_graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()

    # Retrieve the current design graph summary
    current_graph_summary = summarize_design_state_func(current_design_graph)

    print("🔄 [DEBUG] Generating structured synthesis output...")
    synth_output = synthesizer_llm.invoke([
        SystemMessage(content=SY_PROMPT),
        HumanMessage(content=f"""
### **Here are the Supervisor's instructions for this round:**
{supervisor_instructions}

### **Implement the following proposal content:**
{selected_proposal.evolved_content or "No evolution applied"}

### **And here is the current state of the Design Graph you are about to populate**:
{current_graph_summary}

---

## **🔹 Your Tasks**
1. **Analyze the final proposal and its evolution**.
2. **Determine modifications needed in the Design Graph**.
   - What **new nodes** should be added?
   - What **outdated nodes** should be removed?
   - What **relationships (edges) need updating?**
3. **Justify all modifications with a clear explanation**.
4. **If no changes are needed, explain why.**
""")
    ])

    print("✅ [DEBUG] Synthesizer structured output received.")

    # 🔹 **Refine the summary explanation**
    refined_summary = refine_summary_explanation(selected_proposal, state, synth_output.summary_explanation)

    # 🔹 **Refine Each Node's Payload**
    refined_nodes = []
    for mod in synth_output.nodes:
        mod.payload = refine_payload(state, mod)  # ✅ Fix argument order
        print(f"✅ [DEBUG] Refined payload for {mod.name}: {mod.payload}")
        refined_nodes.append(mod)

    print(f"✅ [DEBUG] Refined Summary Explanation: {refined_summary}")

    print("✅ [DEBUG] Synthesis complete. Proceeding to Graph Designer.")
    return Command(
        update={
            "synthesizer_notes": [refined_summary],
            "design_graph_nodes": [refined_nodes],
            "design_graph_edges": [synth_output.edges],
        },
        goto="graph_designer"
    )


def refine_summary_explanation(proposal: Proposal, state: State, raw_summary: str) -> str:
    """
    Uses an additional LLM call to refine the **summary_explanation**.
    Ensures **structured, clear, and precise** reasoning.
    """
    print(f"📝 [DEBUG] Refining summary explanation for selected proposal: {proposal.title}")

    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."

    refinement_prompt = [
        SystemMessage(content=SUMMARY_REFINEMENT_PROMPT),
        HumanMessage(content=f"""
### **Supervisor Instructions:**
{supervisor_instructions}

### **Cahier des Charges (Engineering Constraints):**
{cahier_des_charges}

---

### **Proposal Title:**
{proposal.title or "Title not picked yet"}

### **Proposal Content:**
{proposal.content}

### **Reflection Feedback:**
{proposal.feedback or "No prior feedback"}

### **Ranking Score:**
{proposal.grade if proposal.grade is not None else "Not yet scored"}

### **Proposal Evolved Content:**
{proposal.evolved_content or "No evolution applied"}

### **Evolution Justification:**
{proposal.evolution_justification or "No evolution applied"}

### **Meta-review Analysis:**
{proposal.reason_for_status or "No evolution applied"}

---
### **Raw Summary Explanation to refine:**
{raw_summary}
---


---

### **Your Task:**
1. **Refine the summary explanation** to ensure:
   - It is **specific, structured, and clear**.
   - It provides **strong technical justification**.
   - It integrates **all relevant engineering constraints**.
2. **If the summary is already optimal**, keep it unchanged.
3. **Return only the refined summary text.**
""")
    ]

    #refined_summary = base_model.invoke(refinement_prompt).content
    refined_summary = remove_think_tags(base_model_reasoning.invoke(refinement_prompt).content)
    return refined_summary

def refine_payload(state: State, modification: NodeModification) -> str: #Dict[str, Any]:
    """
    Uses an additional LLM call to refine the payload for a NodeModification.
    Ensures function descriptions, parameters, and code quality are optimal.
    """
    print(f"📝 [DEBUG] Refining payload for node: {modification.name}")

    supervisor_instructions = state.supervisor_instructions[-1] if state.supervisor_instructions else "No specific instructions provided."
    cahier_des_charges = state.cahier_des_charges if state.cahier_des_charges else "No formal constraints provided."
    # Find the final selected proposal
    recent_proposals = [
        p for p in state.proposals
        if p.current_step_index == state.current_step_index
        and p.generation_iteration_index == state.generation_iteration
    ]
    selected_proposal = next((p for p in recent_proposals if p.status == "selected"), None)
    # Retrieve the current design graph summary
    current_graph_summary = summarize_design_state_func(state.design_graph)

    refinement_prompt = [
        SystemMessage(content=PAYLOAD_REFINEMENT_PROMPT),
        HumanMessage(content=f"""
### **Node Name:**
{modification.name}

### **Node Type:**
{modification.node_type}

### **Current Payload (Before Refinement):**
{modification.payload}

---
To provide you more context: this node is implemented alongide other nodes, based on the following proposal content:
### **Proposal Evolved Content:**
{selected_proposal.evolved_content or "No evolution applied"}

### **And here is the current state of the Design Graph, which this node is part of**:
{current_graph_summary}

---

### **Your Task:**
1. **Review the current payload and refine it** to ensure:
   - **Clarity, completeness, and accuracy**.
   - **Well-documented code** (if applicable).
   - **Consistent parameter descriptions**.
2. **If the payload includes numerical modeling code**, improve:
   - **Modularization & readability**.
   - **Reproducibility** (parameter parsing, documentation).
   - **Performance optimization**.
3. **Return only the refined payload.**
""")
    ]

    #refined_payload = base_model.invoke(refinement_prompt).content
    refined_payload = remove_think_tags(base_model_reasoning.invoke(refinement_prompt).content)
    return refined_payload
