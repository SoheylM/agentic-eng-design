from dataclasses import dataclass
from typing import List, Literal

@dataclass
class ExperimentConfig:
    llm_type: Literal["non_reasoning", "reasoning"]
    temperature: float
    workflow_type: Literal["mas", "pair"]
    run_id: int  # 0-9 for the 10 runs per combination

    @property
    def run_folder_name(self) -> str:
        """Generate a unique folder name for this experiment run."""
        return f"{self.llm_type}_t{self.temperature:.1f}_{self.workflow_type}_run{self.run_id:02d}"

# Experiment combinations
LLM_TYPES = ["non_reasoning", "reasoning"]
TEMPERATURES = [0.0, 0.3, 0.5, 0.7]
WORKFLOW_TYPES = ["mas", "pair"]
RUNS_PER_COMBINATION = 5

def generate_experiment_configs() -> List[ExperimentConfig]:
    """Generate all experiment configurations."""
    configs = []
    for llm in LLM_TYPES:
        for temp in TEMPERATURES:
            for wf in WORKFLOW_TYPES:
                for run in range(RUNS_PER_COMBINATION):
                    configs.append(ExperimentConfig(
                        llm_type=llm,
                        temperature=temp,
                        workflow_type=wf,
                        run_id=run
                    ))
    return configs 