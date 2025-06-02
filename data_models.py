from __future__ import annotations
from typing import List, Optional, Annotated, Dict, Literal
import operator
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
import uuid
from dataclasses import dataclass, field


# ────────────────────────────────────────────────
#  Leaves
# ────────────────────────────────────────────────
class PhysicsModel(BaseModel):
    """Analytical / empirical model attached to a design element."""
    name: str = Field(...,
        description="<Unique model name, e.g. 'HeatExchanger1D'.")
    equations: str = Field("",
        description="LaTeX / plain-text governing equations, e.g., 'Q = m_dot * Cp * (T_in - T_out)'.")
    python_code: str = Field("",
        description=("Directives for the coder agent to generate the Python code to simulate the physics model."))
    assumptions: List[str] = Field(default_factory=list,
        description="Assumptions, e.g., [one-dimensional, steady-state, no fouling].")
    status: str = Field("draft",
        description="'draft' | 'reviewed' | 'validated'.")


class Embodiment(BaseModel):
    """Concrete physical realisation of a (sub)function."""
    principle: str = Field(...,
        description="Technology keyword – e.g. 'reverse-osmosis', 'airfoil NACA0012'.")
    description: str = Field("",
        description="1–3 sentence narrative of how the embodiment works.")
    design_parameters: Dict[str, float] = Field(default_factory=dict,
        description="Key variables WITH units, e.g. {'area_m2': 2.5}.")
    cost_estimate: float = Field(-1.0,
        description="USD (−1.0 → not yet estimated).")
    mass_estimate: float = Field(-1.0,
        description="kg (−1.0 → not yet estimated).")
    status: str = Field("draft",
        description="'draft' | 'reviewed' | 'validated'.")


# ────────────────────────────────────────────────
#  Graph node
# ────────────────────────────────────────────────
class DesignNode(BaseModel):
    """
    Atomic element of the Design-State Graph (DSG).
    """
    # ── identity ──────────────────────────────────────────────────────────
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()),
        description="Node identifier.")
    node_kind: str = Field(default_factory=lambda: str(uuid.uuid4()),
        description="Type of node.")
    name: str = Field(..., description="Short label shown in diagrams.")
    description: str = Field("",
        description="Long-form explanation (purpose, behaviour, interfaces).")

    # ── engineering payload ───────────────────────────────────────────────
    embodiment: Embodiment = Field(
        default_factory=Embodiment,
        description="Current physical embodiment of the node, meaning the physical realisation of the node, a system.")
    physics_models: List[PhysicsModel] = Field(default_factory=list,
        description="The physics models that are used to describe the node with the high-fidelity numerical model.")

    # ── traceability & maturity ───────────────────────────────────────────
    linked_reqs: List[str] = Field(default_factory=list,
        description="IDs of requirement nodes this element satisfies.")
    verification_plan: str = Field("",
        description="How compliance will be verified (Inspection / Analysis / Test / Demo).")
    maturity: str = Field("draft",
        description="'draft' | 'reviewed' | 'validated'.")
    tags: List[str] = Field(default_factory=list,
        description="Free keywords.")


# ────────────────────────────────────────────────
#  Whole DSG
# ────────────────────────────────────────────────
class DesignState(BaseModel):
    """Snapshot of the complete directed graph."""
    nodes: Dict[str, DesignNode] = Field(default_factory=dict,
        description="Map node_id to node data.")
    edges: List[List[str]] = Field(default_factory=list,
        description="Single source of truth for graph connectivity. Each item = [source_id, target_id]. The edges_in and edges_out lists in nodes are derived from this list.")


# ────────────────────────────────────────────────
#  Generation-agent output
# ────────────────────────────────────────────────
class DSGListOutput(BaseModel):
    proposals: List[DesignState] = Field(...,
        description="N alternative DSGs generated in one call.")


# ────────────────────────────────────────────────
#  Optional edit ops
# ────────────────────────────────────────────────
class NodeOp(BaseModel):
    op: Literal["add", "update", "delete"]
    node: Optional[DesignNode] = None
    node_id: Optional[str]     = None
    updates: Dict[str, str]    = Field(default_factory=dict)
    justification: str         = ""

class EdgeOp(BaseModel):
    op: Literal["add", "delete"]
    src: str
    dst: str
    justification: str = ""


class Proposal(BaseModel):
    """
    A container for an ephemeral design proposal, capturing the iterative
    contributions and evaluations of various agents across a single design step.
    """
    
    # The raw text or structured content generated by the Generation agent.
    content: DesignState

    # Design step to know in which design step this proposal was formulated
    current_step_index: int = 0
    
    # Reflection agent's critique or suggestions. Could be a short text summary.
    feedback: Optional[str] = None
    
    # Ranking agent's metrics from eval_saved.py evaluation
    grade: Optional[float] = None
    ranking_justification: Optional[str] = None

    # Evolved content from the Evolution agent (could be combined or refined text).
    evolved_content: Optional[DesignState] = None
    evolution_justification: Optional[str] = None
    
    # The final status after the entire iteration: "selected", "rejected", or other.
    status: Optional[str] = None
    
    # Explanation for that status: e.g., "Rejected because it conflicts with top-level constraints"
    reason_for_status: Optional[str] = None

    # Well a title
    title: Optional[str] = None

    # New field to track which iteration this proposal belongs to
    generation_iteration_index:  int = 0
    reflection_iteration_index:  int = 0
    ranking_iteration_index:     int = 0
    evolution_iteration_index:   int = 0
    meta_review_iteration_index: int = 0  
    synthesizer_iteration_index: int = 0  # Tracks the current iteration of the synthesizer loop
    
    #iteration_index: int = 0
    # 

class WorkerAnalysis(BaseModel):
    content: str = Field(..., description="The result from the worker task")
    from_task: str = Field(..., description="Short description of the task")
    step_index: int = Field(..., description="Design step in which this was created")
    called_by_agent: str = Field(..., description="Which agent requested this analysis")

@dataclass
class State:
    """Graph state for the full engineering design workflow."""

    # **General Messages** (for Human & LLM Interactions)
    messages: Annotated[List[BaseMessage], operator.add] = field(default_factory=list)  

    # **🔹 Key Engineering Artifacts**
    cahier_des_charges: Optional[CahierDesCharges] = None  # The structured requirements document
    supervisor_instructions: Annotated[List[str], operator.add] = field(default_factory=list)  # Step-wise instructions
    current_step_index: int = 0  # Track the current design step

    # **🔹 Supervisor Agent Tracking**
    supervisor_decision: Optional[dict] = None  # Stores the last decision made by the Supervisor
    supervisor_status: str = "in_progress"  # Can be ["in_progress", "complete", "redo"]
    redo_reason: Optional[str] = None  # If the step is redone, why?
    supervisor_current_objectives: Annotated[List[str], operator.add] = field(default_factory=list)  # Step-specific objectives
    supervisor_visit_counter: int = 0  # Counter for supervisor visits
    dsg_save_folder: Optional[str] = None  # Folder name for saving DSGs

    # **🔹 Step Execution & Control**
    active_agent: str = "human"  # Tracks the currently active agent
    current_tasks_count: int = 0  # Number of worker tasks dispatched

    # **🔹 Flags for Workflow Iteration**
    redo_work: bool = False  # Set to True if the supervisor requests iteration
    task_complete: bool = False  # Marks if the design step is complete
    next_agent: str = ""  # Which agent should proceed next

    # **🔹 Proposal Tracking**
    proposals: Annotated[List[Proposal], operator.add] = field(default_factory=list)  
    selected_proposal_index: Optional[int] = None
    pending_design_states: Annotated[List[DesignState], operator.add] = field(default_factory=list)

    # **🔹 Proposal Ranking**
    ranking_justification: Optional[str] = None

    # **🔹 Proposal Evolution**
    evolution_justification: Optional[str] = None

    # **🔹 Final Design Graph**
    design_graph_history: Annotated[List[DesignState], operator.add] = field(default_factory=list)
    pending_node_ops: Annotated[List[NodeOp], operator.add] = field(default_factory=list)
    pending_edge_ops: Annotated[List[EdgeOp], operator.add] = field(default_factory=list)
    
    # **🔹 Handover Logs & Iterations**
    generation_notes: Annotated[List[str], operator.add] = field(default_factory=list)
    generation_iteration: int = 0  

    reflection_notes: Annotated[List[str], operator.add] = field(default_factory=list)
    reflection_iteration: int = 0  

    coder_notes: Annotated[List[str], operator.add] = field(default_factory=list)
    coder_iteration: int = 0  

    ranking_notes: Annotated[List[str], operator.add] = field(default_factory=list)
    ranking_iteration: int = 0  

    evolution_notes: Annotated[List[str], operator.add] = field(default_factory=list)
    evolution_iteration: int = 0  

    meta_review_notes: Annotated[List[str], operator.add] = field(default_factory=list)
    meta_review_iteration: int = 0  

    synthesizer_notes: Annotated[List[str], operator.add] = field(default_factory=list)
    synthesizer_iteration: int = 0  

    graph_designer_notes: Annotated[List[str], operator.add] = field(default_factory=list)
    graph_designer_iteration: int = 0  

    proximity_notes: Annotated[List[str], operator.add] = field(default_factory=list)

    # **🔹 Orchestrator & Worker Interactions**
    analyses: Annotated[List[WorkerAnalysis], operator.add] = field(default_factory=list)
    orchestrator_orders: Annotated[List[str], operator.add] = field(default_factory=list)
    current_requesting_agent: str = ""  # Tracks which agent called the orchestrator
    max_iterations: int = 0  # to be increased to account for each new round sent by the planner


class EngineeringTask(BaseModel):
    """An engineering task dispatched to Worker Agents."""

    topic: str = Field(description="Concise title of the engineering task.")
    description: str = Field(
        description="Detailed explanation of the task, its objectives, and expected outputs."
    )
    return_to_agent: str = Field(
        description="Name of the specialized agent to return the analysis to."
    )

class OrchestratorDecision(BaseModel):
    """Decision output from the Orchestrator, breaking down the problem into tasks."""

    response: str = Field(
        description="Rationale behind the task decomposition, including any assumptions, design strategies, or prioritization logic."
    )
    research_tasks: list[EngineeringTask] | None = Field(
        description="List of engineering tasks to assign to Worker Agents."
    )


class FunctionalRequirement(BaseModel):
    id: int = Field(..., description="Unique ID for the functional requirement.")
    description: str = Field(..., description="Detailed explanation of what the system should do.")

class NonFunctionalRequirement(BaseModel):
    id: int = Field(..., description="Unique ID for the non-functional requirement.")
    category: str = Field(..., description="Category such as Performance, Usability, Safety, Compliance, etc.")
    description: str = Field(..., description="Description of the non-functional constraint.")
    
    
    
# ── lowest-level atoms ────────────────────────────────────────────────

class StakeholderNeed(BaseModel):
    """Voice-of-customer item (SN-xx)."""
    code: str              = Field(..., description="e.g. SN-1")
    text: str              = Field(..., description="Need statement")


class Verification(BaseModel):
    """Verification approach for one requirement."""
    method: Literal["I", "A", "T", "D"]  # Inspection | Analysis | Test | Demo
    description: str = ""                # optional extra detail


class SystemRequirement(BaseModel):
    """Engineering requirement (SR-xx)."""
    code: str             = Field(..., description="e.g. SR-03")
    text: str             = Field(..., description="Requirement statement")
    rationale: Optional[str] = None      # why this SR exists
    verifies: List[str] = Field(default_factory=list,
                                description="List of SN codes traced to")
    verification: Verification            # single primary method


class Constraint(BaseModel):
    """Non-negotiable design constraint or external interface."""
    name: str
    text: str


class Deliverable(BaseModel):
    """Design artefact to be produced."""
    name: str
    description: str


# ── top-level Cahier-des-Charges ─────────────────────────────────────

class CahierDesCharges(BaseModel):
    """Full requirements specification (INCOSE-style skeleton)."""

    # 1 – Project overview
    project_title: str
    objective: str                       # single headline objective

    # 2 – Stakeholder needs
    stakeholder_needs: List[StakeholderNeed]

    # 3 – System-level requirements
    system_requirements: List[SystemRequirement]

    # 4 – Constraints & interfaces
    constraints: List[Constraint]

    # 5 – Verification strategy (derived automatically from SR.verification,
    #     but a free text field is handy for extra notes)
    verification_notes: Optional[str] = None

    # 6 – Expected deliverables
    deliverables: List[Deliverable]

    # Free-form final note
    final_note: Optional[str] = None


class SupervisorDecision(BaseModel):
    step_completed: bool = Field(..., description="Indicates if the current step is complete or needs iteration.")
    #next_step_index: int = Field(..., description="The next step index to execute.") #TODO: decide if we want the agent to decide of that later
    instructions: str = Field(..., description="Instructions for the next agent.")
    reason_for_iteration: Optional[str] = Field(None, description="If iterating, explain why rework is needed.")
    workflow_complete: bool = Field(False, description="Indicates whether the entire workflow is completed.")



class SingleProposal(BaseModel):
    title: str = Field(..., description="Concise human-readable summary")
    content: DesignState = Field(
        ..., description="A complete Design-State Graph (DSG) proposal"
    )

class ProposalsOutput(BaseModel):
    proposals: List[SingleProposal]


class CoderOutput(BaseModel):
    """Output from the coder agent for a single physics model."""
    python_code: str = Field(..., description="Complete Python implementation following the 11-point specification.")


class SingleReflection(BaseModel):
    proposal_index: int = Field(..., description="Index of the proposal to which this reflection applies")
    feedback: str = Field(..., description="Critical review or suggestions about the proposal")

class ReflectionOutput(BaseModel):
    reflections: List[SingleReflection] = Field(..., description="List of reflection items for each proposal")


class SingleRanking(BaseModel):
    proposal_index: int = Field(..., description="Index of the proposal being ranked")
    #previous_score: Optional[float] = Field(None, description="Previous ranking score, if applicable")
    grade: float = Field(..., description="Adjusted ranking score for this proposal")
    ranking_justification: Optional[str] = Field(..., description="Clear explanation for ranking decision")
    title: Optional[str] = None  # Retaining title for readability #TODO: to use in the future

class RankingOutput(BaseModel):
    rankings: List[SingleRanking] = Field(..., description="List of ranking decisions for each proposal")


class SingleEvolution(BaseModel):
    proposal_index: int = Field(..., description="Index of the proposal being evolved")
    original_score: Optional[float] = Field(None, description="Previous ranking score, if available")
    new_content: DesignState = Field(..., description="Refined or improved version of the DSG")
    evolution_justification: Optional[str] = Field(..., description="Explanation of what was changed and why")
    title: Optional[str] = None  # Retaining title for readability

class EvolutionOutput(BaseModel):
    evolutions: List[SingleEvolution] = Field(..., description="List of evolved proposals")


class SingleMetaDecision(BaseModel):
    proposal_index: int = Field(..., description="Index of the proposal being finalized")
    final_status: str = Field(..., description="Final decision (selected, rejected, or needs more iteration)")
    reason: str = Field(..., description="Rationale for the decision")

class MetaReviewOutput(BaseModel):
    selected_proposal_index: int = Field(..., description="Index of the chosen proposal (-1 if none are valid)")
    detailed_summary_for_graph: str = Field(..., description="Instructions for improving the selected design graph")
    decisions: List[SingleMetaDecision] = Field(..., description="Final statuses for all proposals")


class SynthesizerOutput(BaseModel):
    """
    Represents the structured output from the Synthesizer Agent.
    """
    summary_explanation: str
    nodes: List[NodeOp]
    edges: List[EdgeOp]


class GraphDesignerPlan(BaseModel):
    """
    Represents the structured plan for modifying the design graph.
    """
    summary_reasoning: str = Field(..., description="A structured explanation of why these graph modifications are needed.")
    
    # List of node modifications (addition, deletion, update)
    nodes: List[NodeOp] = Field(..., description="A list of modifications (add, delete, update) to apply to nodes in the graph.")
    
    # List of edge modifications (addition, deletion)
    edges: List[EdgeOp] = Field(..., description="A list of edge modifications (add, delete) to apply relationships between nodes.")


class PairState(BaseModel):
    """State for the 2-Agent System (Generation + Reflection loop)."""
    messages: Annotated[List[BaseMessage], operator.add] = Field(default_factory=list)
    first_pass: bool = True
    user_request: str = ""
    proposal: Annotated[List[str], operator.add] = Field(default_factory=list)
    feedback: Annotated[List[str], operator.add] = Field(default_factory=list)
    generation_iteration: int = 0
    reflection_iteration: int = 0
    max_iterations: int = 5  # Default max iterations

