from typing import List, Optional, Annotated, Dict, Tuple, Literal
import operator
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
import uuid
from dataclasses import dataclass, field

# ──────────────────────────────────────────────────────────────────────────────
#  Low-level payload leaves
# ──────────────────────────────────────────────────────────────────────────────

class PhysicsModel(BaseModel):
    """Executable or symbolic model attached to a design element."""

    name: str = Field(
        metadata={"desc": "Human-readable identifier (e.g. 'BernoulliPump')"}
    )
    equations: str = Field(
        metadata={"desc": "LaTeX or plain-text formulation of governing eqns"}
    )
    python_code: str = Field(
        metadata={"desc": "Runnable snippet or module import path"}
    )
    assumptions: List[str] = Field(
        default_factory=list,
        metadata={"desc": "Key simplifying assumptions made by the model"},
    )
    status: str = Field(
        default="draft",
        metadata={
            "desc": "Model maturity flag – use 'draft', 'validated', or 'deprecated'"
        },
    )


class Embodiment(BaseModel):
    """How a function/sub-function is physically instantiated."""

    principle: str = Field(
        metadata={"desc": "Primary working principle (e.g. 'reverse-osmosis')"}
    )
    description: str = Field(
        metadata={"desc": "Concise explanation of how the embodiment works"}
    )
    design_parameters: Dict[str, float] = Field(
        default_factory=dict,
        metadata={"desc": "Key design vars with nominal numeric values"},
    )
    cost_estimate: float = Field(
        default=-1.0,
        metadata={"desc": "USD cost estimate; −1.0 means 'not yet estimated'"},
    )
    mass_estimate: float = Field(
        default=-1.0,
        metadata={"desc": "Mass in kg; −1.0 means 'not yet estimated'"},
    )
    status: str = Field(
        default="candidate",
        metadata={
            "desc": "Lifecycle state – 'candidate', 'selected', or 'rejected'"
        },
    )

# ──────────────────────────────────────────────────────────────────────────────
#  The single node that carries everything
# ──────────────────────────────────────────────────────────────────────────────

class DesignNode(BaseModel):
    """
    Self-contained design element.  
    `node_kind` maintains hierarchy while keeping embodiment + models inline.
    """

    node_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={"desc": "Globally unique identifier"},
    )
    node_kind: str = Field(
        metadata={
            "desc": "Token such as 'function', 'subfunction', 'requirement', 'constraint'"
        }
    )
    name: str = Field(
        metadata={"desc": "Short, human-friendly label"}
    )
    description: str = Field(
        default="",
        metadata={"desc": "Long-form text explaining purpose or behaviour"},
    )

    # Rich payload -------------------------------------------------------------
    embodiment: Embodiment = Field(
        default_factory=lambda: Embodiment(
            principle="undefined",
            description="embodiment not yet specified",
        ),
        metadata={"desc": "Current embodiment choice"},
    )
    physics_models: List[PhysicsModel] = Field(
        default_factory=list,
        metadata={"desc": "One or more physics / empirical models"},
    )

    # Meta-fields --------------------------------------------------------------
    maturity: str = Field(
        default="draft",
        metadata={
            "desc": "Overall maturity – 'draft', 'reviewed', or 'validated'"
        },
    )
    tags: List[str] = Field(
        default_factory=list,
        metadata={"desc": "Arbitrary keywords for search / filter"},
    )

    # Graph connectivity -------------------------------------------------------
    edges_in: List[str] = Field(
        default_factory=list,
        metadata={"desc": "IDs of parent nodes"},
    )
    edges_out: List[str] = Field(
        default_factory=list,
        metadata={"desc": "IDs of child nodes"},
    )

class DesignState(BaseModel):
    """
    Pure data container for the evolving design.

    • `nodes`  : mapping from node_id → DesignNode  
    • `edges`  : list of directed pairs (source_id, target_id)

    No helper methods are defined here – keep graph manipulation
    in standalone utility functions or in the agent logic.
    """

    nodes: Dict[str, DesignNode] = Field(
        default_factory=dict,
        metadata={"desc": "All design nodes keyed by their unique node_id"},
    )
    edges: List[Tuple[str, str]] = Field(
        default_factory=list,
        metadata={
            "desc": "Directed edges (source_id, target_id) capturing dependencies"
        },
    )

class DSGListOutput(BaseModel):
    proposals: List[DesignState]


class NodeOp(BaseModel):
    """Atomic modification to a node."""

    op: Literal["add", "update", "delete"]        # required

    # For 'add' you supply a full DesignNode; for update/delete you pass node_id
    node: DesignNode | None = None
    node_id: str | None = None

    updates: Dict[str, str] = Field(
        default_factory=dict,
        description="Shallow key→value edits when op == 'update'",
    )
    justification: str = ""



class EdgeOp(BaseModel):
    """Atomic modification to an edge."""

    op: Literal["add", "delete"] = Field(
        ...,
        description="Edge operation type",
    )
    src: str = Field(
        ...,
        description="Source node_id (tail of the arrow)",
    )
    dst: str = Field(
        ...,
        description="Destination node_id (head of the arrow)",
    )
    justification: str = Field(
        "",
        description="Rationale for adding/removing this dependency",
    )

class Proposal(BaseModel):
    """
    A container for an ephemeral design proposal, capturing the iterative
    contributions and evaluations of various agents across a single design step.
    """
    
    # The raw text or structured content generated by the Generation agent.
    content: str

    # Design step to know in which design step this proposal was formulated
    current_step_index: int = 0
    
    # Reflection agent's critique or suggestions. Could be a short text summary.
    feedback: Optional[str] = None
    
    # Ranking agent's numeric or textual grade. E.g., "score: 8.5"
    grade: Optional[float] = None
    ranking_justification: Optional[str] = None

    # Evolved content from the Evolution agent (could be combined or refined text).
    evolved_content: Optional[str] = None
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

class PlanStep(BaseModel):
    step_id: int = Field(..., description="Unique sequential ID for this design step.")
    name: str = Field(..., description="Descriptive title of the step.")
    description: str = Field(..., description="Explanation of what this step entails.")
    objectives: str = Field(..., description="Goals and deliverables for this step.")
    prerequisites: List[int] = Field(..., description="Step IDs that must be completed first.")
    expected_outputs: str = Field(..., description="Expected deliverables for this step.")

class DesignPlan(BaseModel):
    plan_overview: str = Field(..., description="Summary of the overall engineering design process.")
    steps: List[PlanStep] = Field(..., description="Ordered list of design steps.")

@dataclass
class State:
    """Graph state for the full engineering design workflow."""

    # **General Messages** (for Human & LLM Interactions)
    messages: Annotated[List[BaseMessage], operator.add] = field(default_factory=list)  

    # **🔹 Key Engineering Artifacts**
    cahier_des_charges: Optional[dict] = None  # The structured requirements document
    design_plan: Optional[DesignPlan] = None  # The structured multi-step design plan
    supervisor_instructions: Annotated[List[str], operator.add] = field(default_factory=list)  # Step-wise instructions

    # **🔹 Supervisor Agent Tracking**
    supervisor_decision: Optional[dict] = None  # Stores the last decision made by the Supervisor
    supervisor_status: str = "in_progress"  # Can be ["in_progress", "complete", "redo"]
    redo_reason: Optional[str] = None  # If the step is redone, why?
    supervisor_current_objectives: Annotated[List[str], operator.add] = field(default_factory=list)  # Step-specific objectives

    # **🔹 Step Execution & Control**
    active_agent: str = "human"  # Tracks the currently active agent
    current_step_index: int = 0  # Which step in the design plan we are executing
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
    max_iterations: int = 0 # to be increased to account for each new round sent by the planner


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

class CahierDesCharges(BaseModel):
    project_name: str = Field(..., description="The official name of the project.")
    description: str = Field(..., description="A high-level description of the project scope.")
    objectives: List[str] = Field(..., description="Key objectives the project aims to fulfill.")
    
    functional_requirements: List[FunctionalRequirement] = Field(..., description="List of functional requirements.")
    non_functional_requirements: List[NonFunctionalRequirement] = Field(..., description="List of non-functional requirements.")
    
    constraints: Dict[str, str] = Field(..., description="Constraints such as budget, material limitations, legal constraints.")
    assumptions: List[str] = Field(default_factory=list, description="List of assumptions made during requirements gathering.")
    open_questions: List[str] = Field(default_factory=list, description="Unresolved questions that need clarification before proceeding.")


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
    new_content: str = Field(..., description="Refined or improved version of the proposal")
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
    detailed_summary_for_graph: str = Field(..., description="Instructions for updating the design graph")
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

