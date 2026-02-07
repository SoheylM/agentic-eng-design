#!/usr/bin/env python
"""
Fire-and-forget launcher for MAS or 2-Agent workflows, with
batching and manifest support.

Usage:
    python run_pipeline.py [--output-dir RUNS_DIR] [--request USER_PROMPT]
                           [--llm LLM_TYPE --temp TEMP --workflow WF_TYPE --runs N]

Each invocation creates a new timestamped batch folder under RUNS_DIR
(default "runs/"). Within that batch, each experiment's outputs go into
RUNS_DIR/<batch_id>/<run_folder_name>/, and a top-level manifest.json
records all sub-runs for easy discovery by eval_saved.py.
"""

from __future__ import annotations

import argparse
import importlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from experiment_config import (
    LLM_TYPES,
    TEMPERATURES,
    WORKFLOW_TYPES,
    ExperimentConfig,
    generate_experiment_configs,
)
from prompts import CAHIER_DES_CHARGES_REV_C, CAHIER_DES_CHARGES_REV_C_PAIR, CAHIER_DES_CHARGES_UAM


def default_request(workflow_type: str = "mas", system_type: str = "water") -> str:
    """Single-line prompt that embeds the appropriate Cahier-des-Charges."""
    if system_type == "uam":
        prompt = CAHIER_DES_CHARGES_UAM
        return (
            "I want to create an Urban Air Mobility (UAM) eVTOL aircraft that satisfies "
            "the following Cahier-des-Charges:\n\n" + prompt
        )
    else:  # water system
        prompt = CAHIER_DES_CHARGES_REV_C_PAIR if workflow_type == "pair" else CAHIER_DES_CHARGES_REV_C
        return (
            "I want to create a solar-powered water-filtration system that satisfies "
            "the following Cahier-des-Charges Rev C:\n\n" + prompt
        )


def _run_once(config: ExperimentConfig, request: str, batch_id: str, base_dir: Path) -> dict[str, Any]:
    """
    Launch one workflow run and return metadata about the run.
    DSGs will be written by the workflow into:
        base_dir / batch_id / config.run_folder_name / *.json
    """
    start_time = time.time()
    run_metadata: dict[str, Any] = {
        "config": {
            "llm_type": config.llm_type,
            "temperature": config.temperature,
            "workflow_type": config.workflow_type,
            "run_id": config.run_id,
            "seed": config.run_id,  # Using run_id as seed
        },
        "start_time": datetime.now().isoformat(),
        "success": False,
        "error": None,
        "n_dsgs": 0,
        "wall_time": None,
    }

    try:
        # Configure the LLMs/tools for this experiment
        from llm_models import configure_models

        configure_models(config.llm_type, config.temperature, config.run_id)

        # Import and run the correct workflow
        if config.workflow_type == "mas":
            wf_mod = importlib.import_module("workflows.mas_workflow")
        else:
            wf_mod = importlib.import_module("workflows.pair_workflow")

        # Create the output directory structure
        outdir = base_dir / batch_id / config.run_folder_name
        outdir.mkdir(parents=True, exist_ok=True)

        # Thread ID now includes batch subfolder
        thread_id = f"{batch_id}/{config.run_folder_name}"

        # Run the workflow (it dumps DSGs to "runs/<thread_id>/stepXX_*.json")
        wf_mod.run_once(request, thread_id=thread_id)

        # Collect outputs
        if outdir.exists():
            dsgs = list(outdir.glob("*.json"))
            run_metadata.update(
                {
                    "success": True,
                    "n_dsgs": len(dsgs),
                    "wall_time": time.time() - start_time,
                }
            )
        else:
            run_metadata["error"] = "No output directory created: " + str(outdir)

    except Exception as e:
        run_metadata["error"] = str(e)
        run_metadata["wall_time"] = time.time() - start_time

    return run_metadata


def generate_specific_configs(
    llm_type: str, temperature: float, workflow_type: str, runs: int = 5
) -> list[ExperimentConfig]:
    """Generate configurations for a specific experiment combination."""
    return [
        ExperimentConfig(
            llm_type=llm_type,
            temperature=temperature,
            workflow_type=workflow_type,
            run_id=i,
        )
        for i in range(runs)
    ]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--output-dir",
        type=str,
        default="runs",
        help="Base directory to store all batches (default: runs/)",
    )
    ap.add_argument("--request", default=None, help="Initial user request (overrides default prompt)")
    ap.add_argument(
        "--system",
        choices=["water", "uam"],
        default="water",
        help="System type: water (solar-powered water filtration) or uam (eVTOL aircraft)",
    )
    ap.add_argument("--llm", choices=LLM_TYPES, help="Run only this LLM type")
    ap.add_argument("--temp", type=float, choices=TEMPERATURES, help="Only this temperature")
    ap.add_argument("--workflow", choices=WORKFLOW_TYPES, help="Only this workflow type (mas|pair)")
    ap.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of runs for a specific combination (default: 10)",
    )
    args = ap.parse_args()

    # Set up experiment logging
    log_dir = Path("experiment_logs")
    log_dir.mkdir(exist_ok=True)

    # Create a new batch folder under output-dir
    base_dir = Path(args.output_dir)
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = base_dir / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Decide which configs to run
    if args.llm and args.temp is not None and args.workflow:
        configs = generate_specific_configs(args.llm, args.temp, args.workflow, args.runs)
        print(f"Running specific combination: {args.llm}, t={args.temp}, {args.workflow}")
    else:
        configs = generate_experiment_configs()
        print("Running all experiment combinations")

    total = len(configs)
    print(f"Total runs: {total}\n")

    # Prepare manifest
    manifest: list[dict[str, Any]] = []

    # Open a line-delimited JSONL log for quick debugging
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"experiment_log_{timestamp}.jsonl"

    with log_file.open("w") as lf:
        for idx, cfg in enumerate(configs, start=1):
            print(f"[{idx}/{total}] {cfg.run_folder_name} …")
            request = args.request or default_request(cfg.workflow_type, args.system)

            metadata = _run_once(cfg, request, batch_id, base_dir)
            lf.write(json.dumps(metadata) + "\n")
            lf.flush()

            status = "✅" if metadata["success"] else "❌"
            print(f"  {status} {cfg.run_folder_name}")
            if metadata["success"]:
                print(f"    DSGs: {metadata['n_dsgs']}  Wall time: {metadata['wall_time']:.1f}s  Seed: {cfg.run_id}")
            else:
                print(f"    Error: {metadata['error']}")

            # Add to batch manifest
            manifest.append(
                {
                    "run_folder": cfg.run_folder_name,
                    "llm_type": cfg.llm_type,
                    "temperature": cfg.temperature,
                    "workflow": cfg.workflow_type,
                }
            )

    # Write batch manifest
    with (batch_dir / "manifest.json").open("w") as mf:
        json.dump(manifest, mf, indent=2)

    print(f"\nBatch {batch_id} complete.")
    print(f"  Outputs → {batch_dir}")
    print(f"  Manifest → {batch_dir / 'manifest.json'}")
    print(f"  Log → {log_file}")
