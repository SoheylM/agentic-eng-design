from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaEmbeddings
from langchain_ollama import ChatOllama
from data_models import GraphDesignerPlan, CahierDesCharges, SupervisorDecision, OrchestratorDecision, ProposalsOutput, ReflectionOutput, RankingOutput, EvolutionOutput, MetaReviewOutput, SynthesizerOutput, CoderOutput, ReflectionPairOutput
from tools import arxiv_search_tool

def configure_models(llm_type: str, temperature: float, seed: int):
    """
    Configure all agent models based on experiment settings.
    
    Args:
        llm_type: Either "reasoning" or "non_reasoning"
        temperature: Temperature setting for the model (0.0 to 0.7)
        seed: Random seed for reproducibility (0-9 for the 10 runs)
    """

    global base_model
    
    # Configure base model
    if llm_type == "reasoning":
        base_model = ChatOpenAI(
            model="deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
            openai_api_key="None",
            openai_api_base="http://127.0.0.1:8002/v1",
            max_tokens=64000,
            temperature=temperature,
            seed=seed,
            streaming=False
        )
    else:  # non_reasoning
        base_model = ChatOpenAI(
            model="meta-llama/Llama-3.3-70B-Instruct",
            openai_api_key="None",
            openai_api_base="http://127.0.0.1:8003/v1",
            max_tokens=64000,
            temperature=temperature,
            seed=seed,
            streaming=False
        )
    
    # Update global model variables
    global plan_llm, req_structured_model, supervisor_model, cia_model
    global bra_model, generation_agent, coder_agent, reflection_agent
    global ranking_agent, evolution_agent, meta_reviewer_agent, synthesizer_llm
    global pair_generation_agent, pair_reflection_agent
    
    # Configure all agent models
    plan_llm = base_model.with_structured_output(GraphDesignerPlan, method="json_schema")
    req_structured_model = base_model.with_structured_output(CahierDesCharges, method="json_schema")
    supervisor_model = base_model.with_structured_output(SupervisorDecision, method="json_schema")
    cia_model = base_model.with_structured_output(OrchestratorDecision, method="json_schema")
    bra_model = base_model.bind_tools([arxiv_search_tool], tool_choice="auto")
    generation_agent = base_model.with_structured_output(ProposalsOutput, method="json_schema")
    coder_agent = base_model
    reflection_agent = base_model.with_structured_output(ReflectionOutput, method="json_schema")
    ranking_agent = base_model.with_structured_output(RankingOutput, method="json_schema")
    evolution_agent = base_model.with_structured_output(EvolutionOutput, method="json_schema")
    meta_reviewer_agent = base_model.with_structured_output(MetaReviewOutput, method="json_schema")
    synthesizer_llm = base_model.with_structured_output(SynthesizerOutput, method="json_schema")
    
    # 2-Agent System Models
    pair_generation_agent = base_model.with_structured_output(ProposalsOutput, method="json_schema")
    pair_reflection_agent = base_model.with_structured_output(ReflectionPairOutput, method="json_schema")

# Default models for backward compatibility
configure_models("reasoning", 0.3, 42)  # This sets up the default models