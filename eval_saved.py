#!/usr/bin/env python
"""eval_saved.py – quality audit for Design–State Graphs (DSG)

Processes a single batch of runs (identified by a timestamped batch folder)
and calculates metrics M1–M6 for each experiment configuration within that batch.
"""

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
import networkx as nx
from data_models import DesignState

# ──────────────────────────────────────────────
# Static patterns / constants
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
# Helpers for single snapshot evaluation
# ──────────────────────────────────────────────

def try_load_dsg(path: Path) -> DesignState | None:
    try:
        return DesignState(**json.loads(path.read_text()))
    except Exception:
        return None


def req_coverage(dsg: DesignState) -> float:
    hits = {k: False for k in REQ_PATTS}
    for node in dsg.nodes.values():
        blob = json.dumps(node.model_dump()).lower()
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
        import ast
        ast.parse(p.read_text())
        r = subprocess.run(
            [sys.executable, str(p), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PY_TIMEOUT
        )
        return r.returncode == 0
    except Exception:
        return False

# ──────────────────────────────────────────────
# Evaluate a single run-folder (all snapshots)
# ──────────────────────────────────────────────

def evaluate_folder(folder: Path) -> Dict[str, Any]:
    """Calculate aggregated metrics for one run folder."""
    snaps = sorted(folder.glob("*.json"))
    if not snaps:
        return {"run": folder.name, "error": "no_json_files"}

    per_snap = [evaluate_snapshot(fp) for fp in snaps]
    n = len(per_snap)
    # aggregate
    agg = {
        "run": folder.name,
        "n_snapshots": n,
        # average of each metric
        **{m: sum(p[m] for p in per_snap) / n for m in ("M1", "M2", "M3", "M4")},
        "M5": per_snap[-1]["_complete"],
        # wall time from file modification timestamps
        "M6": _compute_wall_time(snaps)
    }
    return agg


def evaluate_snapshot(path: Path) -> Dict[str, float]:
    """Return metrics for one snapshot JSON."""
    res = {"M1": 0.0, "M2": 0.0, "M3": 0.0, "M4": 0.0, "_complete": 0.0}
    dsg = try_load_dsg(path)
    if dsg is None:
        return res
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


def _compute_wall_time(snaps: List[Path]) -> float:
    t0 = datetime.fromtimestamp(snaps[0].stat().st_mtime, tz=tz.utc)
    t1 = datetime.fromtimestamp(snaps[-1].stat().st_mtime, tz=tz.utc)
    return (t1 - t0).total_seconds()

# ──────────────────────────────────────────────
# Main batch processing and report generation
# ──────────────────────────────────────────────

def process_batch(base_dir: Path, batch_id: str) -> pd.DataFrame:
    """Load manifest.json and evaluate each run-folder in the batch."""
    batch_dir = base_dir / batch_id
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with manifest_path.open() as f:
        runs = json.load(f)

    records = []
    for entry in runs:
        folder = entry["run_folder"]
        folder_path = batch_dir / folder
        metrics = evaluate_folder(folder_path)
        if "error" in metrics:
            continue
        records.append({
            **entry,
            **metrics
        })

    return pd.DataFrame.from_records(records)


def generate_report(df: pd.DataFrame, output_dir: Path, batch_id: str):
    """Generate CSV, LaTeX, and plots for the batch."""
    stats = (
        df.groupby(["llm_type", "temperature", "workflow_type"])
        .agg({
            "M1": ["mean", "std"],
            "M2": ["mean", "std"],
            "M3": ["mean", "std"],
            "M4": ["mean", "std"],
            "M5": ["mean", "std"],
            "M6": ["mean", "std"],
            "n_snapshots": ["mean", "std"]
        })
        .round(3)
    )
    
    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"aggregate_metrics_{batch_id}.csv"
    stats.to_csv(csv_path)

    tex_path = output_dir / f"experiment_stats_{batch_id}.tex"
    with tex_path.open("w") as f:
        f.write(stats.to_latex())

    # plots
    import matplotlib.pyplot as plt
    metrics = ["M1", "M2", "M3", "M4", "M5"]
    fig, axes = plt.subplots(len(metrics), 1, figsize=(10, 4 * len(metrics)))
    for ax, metric in zip(axes, metrics):
        for (llm, wf), grp in df.groupby(["llm_type", "workflow_type"]):
            summary = grp.groupby("temperature")[metric].agg(["mean", "std"])
            ax.errorbar(
                summary.index,
                summary["mean"],
                yerr=summary["std"],
                marker="o",
                label=f"{llm}-{wf}"
            )
        ax.set_title(f"{metric} by Temperature")
        ax.set_xlabel("Temperature")
        ax.set_ylabel(metric)
        ax.legend()
        ax.grid(True)
    plt.tight_layout()
    plt.savefig(output_dir / f"experiment_plots_{batch_id}.png")
    plt.close()


def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="Evaluate batch of DSG runs and generate report."
    )
    ap.add_argument(
        "--batch-id", required=True,
        help="Timestamp of the batch folder to evaluate (e.g. 20250612_153045)"
    )
    ap.add_argument(
        "--base-dir", default="runs",
        help="Base directory containing batch folders (default: runs/)"
    )
    ap.add_argument(
        "--output-dir", default="experiment_results",
        help="Directory to save aggregated results and plots"
    )
    args = ap.parse_args()

    base_dir = Path(args.base_dir)
    batch_id = args.batch_id
    output_dir = Path(args.output_dir)

    df = process_batch(base_dir, batch_id)
    generate_report(df, output_dir, batch_id)

    print(f"✅ Batch {batch_id} evaluation complete.")
    print(f"  Results → {output_dir}")


if __name__ == "__main__":
    main()
