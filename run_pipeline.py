#!/usr/bin/env python
"""
Fire-and-forget launcher for MAS or 2-Agent workflows.

• The Meta-Review agent inside every workflow already dumps each Design-State
  Graph (DSG) to:
      runs/<thread_id>/stepXX_metaYY_<timestamp>.json

• This script launches experiments with different combinations of:
  - LLM type (reasoning vs non-reasoning)
  - Temperature (0.0, 0.3, 0.5, 0.7)
  - Workflow type (MAS vs 2-agent pair)
  - 10 runs per combination with seeds 0-9

• For each run, it logs:
  - Success/failure status
  - Number of DSGs generated
  - Any errors encountered
  - Wall time
  - Random seed used

• You can run all combinations or specify a single combination for debugging.
"""

from __future__ import annotations
import argparse
import importlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from prompts import CAHIER_DES_CHARGES_REV_C, CAHIER_DES_CHARGES_REV_C_PAIR
from experiment_config import ExperimentConfig, generate_experiment_configs, LLM_TYPES, TEMPERATURES, WORKFLOW_TYPES
from llm_models import configure_models

# --------------------------------------------------------------------------- helpers
def default_request(workflow_type: str = "mas") -> str:
    """Single-line prompt that embeds the Rev-C Cahier-des-Charges."""
    prompt = CAHIER_DES_CHARGES_REV_C_PAIR if workflow_type == "pair" else CAHIER_DES_CHARGES_REV_C
    return (
        "I want to create a solar-powered water-filtration system that satisfies "
        "the following Cahier-des-Charges Rev C:\n\n"
        + prompt
    )

def _run_once(config: ExperimentConfig, request: str) -> Dict[str, Any]:
    """
    Launch one workflow run and return metadata about the run.
    """
    start_time = time.time()
    run_metadata = {
        "config": {
            "llm_type": config.llm_type,
            "temperature": config.temperature,
            "workflow_type": config.workflow_type,
            "run_id": config.run_id,
            "seed": config.run_id  # Using run_id as seed (0-9)
        },
        "start_time": datetime.now().isoformat(),
        "success": False,
        "error": None,
        "n_dsgs": 0,
        "wall_time": None
    }

    try:
        # Configure all agent models for this experiment
        configure_models(config.llm_type, config.temperature, config.run_id)
        
        # Import and run appropriate workflow
        if config.workflow_type == "mas":
            wf = importlib.import_module("workflows.mas_workflow")
        else:
            wf = importlib.import_module("workflows.pair_workflow")
        
        # Run the workflow
        wf.run_once(request, thread_id=config.run_folder_name)

        # Check results
        outdir = Path("runs") / config.run_folder_name
        if outdir.exists():
            dsgs = list(outdir.glob("*.json"))
            run_metadata.update({
                "success": True,
                "n_dsgs": len(dsgs),
                "wall_time": time.time() - start_time
            })
        else:
            run_metadata["error"] = "No output directory created"

    except Exception as e:
        run_metadata["error"] = str(e)
        run_metadata["wall_time"] = time.time() - start_time

    return run_metadata

def generate_specific_configs(llm_type: str, temperature: float, workflow_type: str, runs: int = 10) -> List[ExperimentConfig]:
    """Generate configurations for a specific experiment combination."""
    return [
        ExperimentConfig(
            llm_type=llm_type,
            temperature=temperature,
            workflow_type=workflow_type,
            run_id=i
        )
        for i in range(runs)
    ]

# --------------------------------------------------------------------------- CLI
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", default=None,
                    help="Initial user request (default embeds Rev-C CDC)")
    
    # Options for running specific combinations
    ap.add_argument("--llm", choices=LLM_TYPES,
                    help="Run only experiments with this LLM type")
    ap.add_argument("--temp", type=float, choices=TEMPERATURES,
                    help="Run only experiments with this temperature")
    ap.add_argument("--workflow", choices=WORKFLOW_TYPES,
                    help="Run only experiments with this workflow type")
    ap.add_argument("--runs", type=int, default=10,
                    help="Number of runs for the specific combination (default: 10)")
    
    args = ap.parse_args()

    # Create experiment log directory
    log_dir = Path("experiment_logs")
    log_dir.mkdir(exist_ok=True)
    
    # Generate timestamp for this experiment batch
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"experiment_log_{timestamp}.jsonl"
    
    # Generate configurations based on arguments
    if args.llm and args.temp and args.workflow:
        # Run specific combination
        configs = generate_specific_configs(args.llm, args.temp, args.workflow, args.runs)
        print(f"Running specific combination: {args.llm}, t={args.temp}, {args.workflow}")
    else:
        # Run all combinations
        configs = generate_experiment_configs()
        print("Running all experiment combinations")
    
    total = len(configs)
    print(f"Total runs: {total}")
    
    with log_file.open("w") as f:
        for i, config in enumerate(configs, 1):
            print(f"\nRun {i}/{total}: {config.run_folder_name}")
            # Use default request based on workflow type if no custom request provided
            request = args.request if args.request else default_request(config.workflow_type)
            metadata = _run_once(config, request)
            f.write(json.dumps(metadata) + "\n")
            f.flush()
            
            status = "✅" if metadata["success"] else "❌"
            print(f"{status} {config.run_folder_name}")
            if not metadata["success"]:
                print(f"  Error: {metadata['error']}")
            else:
                print(f"  Generated {metadata['n_dsgs']} DSGs")
                print(f"  Wall time: {metadata['wall_time']:.1f}s")
                print(f"  Seed: {metadata['config']['seed']}")
    
    print(f"\nExperiment batch complete. Log written to {log_file}")
