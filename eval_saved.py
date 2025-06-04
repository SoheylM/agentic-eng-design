#!/usr/bin/env python
"""eval_metrics.py – quality audit for Design‑State Graph (DSG)

Processes experiment logs and calculates metrics M1-M6 for each experiment combination.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone as tz
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
import numpy as np

import networkx as nx
from data_models import DesignState

# ──────────────────────────────────────────────
#  Static patterns / constants
# ──────────────────────────────────────────────

REQ_PATTS: Dict[str, str] = {
    "SR-01": r"10\s*l[\/? ]h",
    "SR-02": r"(4[- ]?log|99\.99\s*%)",
    "SR-03": r"300\s*w\s*/\s*m(?:\^?2|²)",
    "SR-04": r"50\s*w\b",
    "SR-05": r"6\s*h(?:ours?)?",
    "SR-06": r"-?10\s*°?\s*c.*50\s*°?\s*c",
    "SR-07": r"(?:20|80)\s*kg",
    "SR-08": r"60\s*%.*recycl",
    "SR-09": r"start\/stop.*3.*action|<\s*2\s*s",
    "SR-10": r"(?:500|5,?000)\s*\$",
}

FENCE_RE = re.compile(r"```(?:python)?\s+([\s\S]+?)```", re.I)
PY_TIMEOUT = 12  # seconds per script execution

# ──────────────────────────────────────────────
#  Snapshot‑level helpers
# ──────────────────────────────────────────────

def try_load_dsg(path: Path):
    try:
        return DesignState(**json.loads(path.read_text()))
    except Exception:
        return None

def req_coverage(dsg: DesignState) -> float:
    hits = {k: False for k in REQ_PATTS}
    for n in dsg.nodes.values():
        blob = json.dumps(n.model_dump()).lower()
        for k, patt in REQ_PATTS.items():
            if re.search(patt, blob):
                hits[k] = True
    return sum(hits.values()) / len(hits)

def embodiment_ratio(dsg: DesignState) -> float:
    ok = [n for n in dsg.nodes.values()
          if n.embodiment and n.embodiment.principle != "undefined"]
    return len(ok) / len(dsg.nodes) if dsg.nodes else 0.0

def _fenced_blocks(txt: str) -> List[str]:
    blocks = FENCE_RE.findall(txt)
    return blocks if blocks else [txt]

def extract_scripts(dsg: DesignState, outdir: Path) -> List[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    files: List[Path] = []
    for i, node in enumerate(dsg.nodes.values()):
        for j, pm in enumerate(node.physics_models):
            for k, code in enumerate(_fenced_blocks(pm.python_code)):
                p = outdir / f"n{i}_pm{j}_{k}.py"
                p.write_text(textwrap.dedent(code).strip())
                files.append(p)
    return files

def _script_ok(p: Path) -> bool:
    try:
        ast.parse(p.read_text())
        r = subprocess.run([sys.executable, str(p), "--help"],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           timeout=PY_TIMEOUT)
        return r.returncode == 0
    except Exception:
        return False

def evaluate_single(path: Path) -> Dict[str, float]:
    """Return metric contributions for one snapshot."""
    res = {"M1": 0.0, "M2": 0.0, "M3": 0.0, "M4": 0.0, "_complete": 0.0}

    dsg = try_load_dsg(path)
    if dsg is None:
        return res

    # parsed OK
    res["M1"] = 1.0
    res["M2"] = req_coverage(dsg)
    res["M3"] = embodiment_ratio(dsg)
    res["_complete"] = 1.0 if dsg.workflow_complete else 0.0

    tmp = Path(tempfile.mkdtemp(prefix="eval_py_"))
    scripts = extract_scripts(dsg, tmp)
    if scripts:
        good = sum(_script_ok(p) for p in scripts)
        res["M4"] = good / len(scripts)
    return res

def evaluate_folder(folder: Path) -> Dict[str, float]:
    """Evaluate all snapshots in a folder."""
    snaps = sorted(folder.glob("*.json"))
    if not snaps:
        return {"error": "no_json_files", "run": folder.name}

    per = [evaluate_single(fp) for fp in snaps]
    agg = {
        "run": folder.name,
        "n_snapshots": len(per),
        "M1": sum(p["M1"] for p in per) / len(per),
        "M2": sum(p["M2"] for p in per) / len(per),
        "M3": sum(p["M3"] for p in per) / len(per),
        "M4": sum(p["M4"] for p in per) / len(per),
        "M5": per[-1]["_complete"],
    }

    # M6 – wall‑time (first→last) in seconds (UTC)
    t0 = datetime.fromtimestamp(snaps[0].stat().st_mtime, tz=tz.utc)
    t1 = datetime.fromtimestamp(snaps[-1].stat().st_mtime, tz=tz.utc)
    agg["M6"] = (t1 - t0).total_seconds()
    return agg

def process_experiment_log(log_file: Path) -> pd.DataFrame:
    """Process experiment log and calculate metrics for each run."""
    # Read experiment log
    runs = []
    with log_file.open() as f:
        for line in f:
            runs.append(json.loads(line))
    
    # Process each successful run
    results = []
    for run in runs:
        if not run["success"]:
            continue
            
        config = run["config"]
        folder = Path("runs") / f"{config['llm_type']}_t{config['temperature']:.1f}_{config['workflow_type']}_run{config['run_id']:02d}"
        
        metrics = evaluate_folder(folder)
        if "error" in metrics:
            continue
            
        results.append({
            "llm_type": config["llm_type"],
            "temperature": config["temperature"],
            "workflow_type": config["workflow_type"],
            "run_id": config["run_id"],
            **metrics
        })
    
    return pd.DataFrame(results)

def generate_report(df: pd.DataFrame, output_dir: Path):
    """Generate experiment report with statistics."""
    # Group by experiment configuration
    grouped = df.groupby(["llm_type", "temperature", "workflow_type"])
    
    # Calculate statistics
    stats = grouped.agg({
        "M1": ["mean", "std", "count"],
        "M2": ["mean", "std"],
        "M3": ["mean", "std"],
        "M4": ["mean", "std"],
        "M5": ["mean", "std"],
        "M6": ["mean", "std"],
        "n_snapshots": ["mean", "std"]
    }).round(3)
    
    # Save to CSV
    stats.to_csv(output_dir / "experiment_stats.csv")
    
    # Generate LaTeX table
    latex = stats.to_latex()
    with (output_dir / "experiment_stats.tex").open("w") as f:
        f.write(latex)
    
    # Generate summary plots
    import matplotlib.pyplot as plt
    
    metrics = ["M1", "M2", "M3", "M4", "M5"]
    fig, axes = plt.subplots(len(metrics), 1, figsize=(10, 4*len(metrics)))
    
    for ax, metric in zip(axes, metrics):
        for llm in df["llm_type"].unique():
            for wf in df["workflow_type"].unique():
                mask = (df["llm_type"] == llm) & (df["workflow_type"] == wf)
                data = df[mask].pivot_table(
                    values=metric,
                    index="temperature",
                    aggfunc=["mean", "std"]
                )
                ax.errorbar(
                    data.index,
                    data[("mean", metric)],
                    yerr=data[("std", metric)],
                    label=f"{llm} - {wf}",
                    marker="o"
                )
        
        ax.set_title(f"{metric} by Temperature")
        ax.set_xlabel("Temperature")
        ax.set_ylabel("Score")
        ax.legend()
        ax.grid(True)
    
    plt.tight_layout()
    plt.savefig(output_dir / "experiment_plots.png")
    plt.close()

# ──────────────────────────────────────────────
#  CLI entry‑point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    ap = argparse.ArgumentParser(description="Process experiment logs and generate reports.")
    ap.add_argument("log_file", help="Path to experiment log file")
    ap.add_argument("--output-dir", default="experiment_results",
                    help="Directory to save results")
    args = ap.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process experiment log
    df = process_experiment_log(Path(args.log_file))
    
    # Generate report
    generate_report(df, output_dir)
    
    print(f"✅ Results written to {output_dir}")
