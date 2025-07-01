#!/usr/bin/env python
"""eval_saved.py – quality audit for Design–State Graphs (DSG)

Processes a single batch of runs (identified by a timestamped batch folder)
and calculates metrics M1–M7 for each experiment configuration within that batch.
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
          if n.embodiment] #and n.embodiment.principle != "undefined"]
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

def evaluate_snapshot(path: Path) -> Dict[str, float]:
    """Return metrics for one snapshot JSON."""
    # now includes M7: number of nodes in this DSG
    res = {"M1": 0.0, "M2": 0.0, "M3": 0.0, "M4": 0.0, "_complete": 0.0, "M7": 0}

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

    # M7: number of nodes in this DSG snapshot
    res["M7"] = len(dsg.nodes)
    return res


def evaluate_folder(folder: Path) -> Dict[str, Any]:
    """Calculate aggregated metrics for one run folder."""
    snaps = sorted(folder.glob("*.json"))
    if not snaps:
        return {"run": folder.name, "error": "no_json_files"}

    per_snap = [evaluate_snapshot(fp) for fp in snaps]
    n = len(per_snap)

    # aggregate per-run:
    #  - average M1–M4 across snapshots
    #  - M5 and M6 will be set from experiment logs in process_batch
    #  - M7 = node-count in the final snapshot
    agg = {
        "run": folder.name,
        "n_snapshots": n,
        **{m: sum(p[m] for p in per_snap) / n for m in ("M1", "M2", "M3", "M4")},
        "M5": per_snap[-1]["_complete"],  # Will be overridden by experiment logs
        "M6": _compute_wall_time(snaps),  # Will be overridden by experiment logs
        "M7": per_snap[-1]["M7"],
    }

    return agg


def _compute_wall_time(snaps: List[Path]) -> float:
    t0 = datetime.fromtimestamp(snaps[0].stat().st_mtime, tz=tz.utc)
    t1 = datetime.fromtimestamp(snaps[-1].stat().st_mtime, tz=tz.utc)
    return (t1 - t0).total_seconds()

# ──────────────────────────────────────────────
# Main batch processing and report generation
# ──────────────────────────────────────────────

def load_experiment_logs(batch_id: str) -> Dict[str, Dict]:
    """Load experimental logs for the batch and create a mapping from run_id to success status and wall_time."""
    log_file = Path("experiment_logs") / f"experiment_log_{batch_id}.jsonl"
    if not log_file.exists():
        return {}
    
    run_data_map = {}
    with open(log_file, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                config = data["config"]
                run_id = config["run_id"]
                success = data["success"]
                wall_time = data.get("wall_time", 0.0)  # Get wall_time from experiment logs
                run_data_map[run_id] = {
                    "success": success,
                    "wall_time": wall_time
                }
    
    return run_data_map


def process_batch(base_dir: Path, batch_id: str) -> pd.DataFrame:
    """Load manifest.json and evaluate each run-folder in the batch."""
    batch_dir = base_dir / batch_id
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with manifest_path.open() as f:
        runs = json.load(f)

    # Load experimental logs for success/failure data
    experiment_logs = load_experiment_logs(batch_id)

    records = []
    for i, entry in enumerate(runs):
        folder = entry["run_folder"]
        folder_path = batch_dir / folder
        metrics = evaluate_folder(folder_path)
        if "error" in metrics:
            continue
        
        # Update M5 and M6 with data from experimental logs
        if i in experiment_logs:
            metrics["M5"] = 1.0 if experiment_logs[i]["success"] else 0.0
            metrics["M6"] = experiment_logs[i]["wall_time"]
        
        records.append({
            **entry,
            **metrics
        })

    return pd.DataFrame.from_records(records)


def generate_report(df: pd.DataFrame, output_dir: Path, batch_id: str):
    """Generate CSV, LaTeX, and plots for the batch."""
    # Calculate statistics - M5 as count, others as mean/std
    stats_m5 = (
        df.groupby(["llm_type", "temperature", "workflow"])
        .agg({
            "M5": ["sum"],  # Count successful runs
        })
        .round(0)  # No decimals for counts
    )
    
    stats_others = (
        df.groupby(["llm_type", "temperature", "workflow"])
        .agg({
            "M1": ["mean", "std"],
            "M2": ["mean", "std"],
            "M3": ["mean", "std"],
            "M4": ["mean", "std"],
            "M6": ["mean", "std"],
            "M7": ["mean", "std"],
        })
        .round(3)
    )
    
    # Combine the statistics
    stats = pd.concat([stats_m5, stats_others], axis=1)
    
    # Save CSV
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"aggregate_metrics_{batch_id}.csv"
    stats.to_csv(csv_path)

    # Generate custom LaTeX table
    tex_path = output_dir / f"experiment_stats_{batch_id}.tex"
    try:
        generate_latex_table(df, tex_path, batch_id)
        print(f"✅ LaTeX table generated: {tex_path}")
    except Exception as e:
        print(f"⚠️  LaTeX table generation failed: {e}")

    # plots
    try:
        import matplotlib.pyplot as plt
        print(f"Generating plots for batch: {batch_id}")
        print(f"DataFrame shape: {df.shape}")
        print(f"DataFrame columns: {df.columns.tolist()}")
        
        # plot all percentage metrics plus M7 (node counts)
        metrics = ["M1", "M2", "M3", "M4", "M7"]
        fig, axes = plt.subplots(len(metrics), 1, figsize=(10, 4 * len(metrics)))
        for ax, metric in zip(axes, metrics):
            print(f"  Plotting metric: {metric}")
            for (llm, wf), grp in df.groupby(["llm_type", "workflow"]):
                print(f"    Group: {llm}, {wf}, size: {len(grp)}")
                summary = grp.groupby("temperature")[metric].agg(["mean", "std"])
                print(f"      Summary index: {summary.index.tolist()}")
                if summary.empty:
                    print(f"      No data for {llm}, {wf}, {metric}")
                    continue
                ax.errorbar(
                    summary.index,
                    summary["mean"],
                    yerr=summary["std"],
                    marker="o",
                    label=f"{llm}-{wf}",
                )
            ax.set_title(f"{metric} by Temperature")
            ax.set_xlabel("Temperature")
            ax.set_ylabel(metric)
            ax.legend()
            ax.grid(True)
        plt.tight_layout()
        plot_path = output_dir / f"experiment_plots_{batch_id}.png"
        print(f"Saving plot to: {plot_path}")
        plt.savefig(plot_path)
        plt.close()
        print(f"✅ Plot generated: {plot_path}")
    except Exception as e:
        print(f"⚠️  Plot generation failed: {e}")
        import traceback
        traceback.print_exc()


def format_mean_std(mean_val, std_val):
    """Format mean ± std with appropriate precision based on std value."""
    # Check for missing or invalid values
    if pd.isna(mean_val) or pd.isna(std_val):
        return r"\tbd\,$\pm$\,\tbd"
    
    # Convert to float to handle any numeric types
    try:
        mean_val = float(mean_val)
        std_val = float(std_val)
    except (ValueError, TypeError):
        return r"\tbd\,$\pm$\,\tbd"
    
    # Determine precision based on std value
    if std_val == 0:
        precision = 0
    elif std_val < 0.01:
        precision = 4
    elif std_val < 0.1:
        precision = 3
    elif std_val < 1:
        precision = 2
    elif std_val < 10:
        precision = 1
    else:
        precision = 0
    
    # Format with fixed precision
    mf = f"{mean_val:.{precision}f}"
    sf = f"{std_val:.{precision}f}"
    
    # Only strip trailing zeros and dot if there's a decimal point
    if "." in mf:
        mf = mf.rstrip("0").rstrip(".")
    if "." in sf:
        sf = sf.rstrip("0").rstrip(".")
    
    return f"{mf}\\,$\\pm$\\,{sf}"


def generate_latex_table(df: pd.DataFrame, output_path: Path, batch_id: str):
    """Generate custom LaTeX table in the specified format."""
    
    try:
        # Calculate statistics - M5 as count, others as mean/std
        stats_m5 = (
            df.groupby(["llm_type", "temperature", "workflow"])
            .agg({
                "M5": ["sum"],  # Count successful runs
            })
            .round(0)  # No decimals for counts
        )
        
        stats_others = (
            df.groupby(["llm_type", "temperature", "workflow"])
            .agg({
                "M1": ["mean", "std"],
                "M2": ["mean", "std"],
                "M3": ["mean", "std"],
                "M4": ["mean", "std"],
                "M6": ["mean", "std"],
                "M7": ["mean", "std"],
            })
            .round(3)
        )
        
        # Combine the statistics
        stats = pd.concat([stats_m5, stats_others], axis=1)
        
        # Get unique values from data
        llm_types = sorted(df["llm_type"].unique())
        workflows = sorted(df["workflow"].unique())
        temperatures = sorted(df["temperature"].unique())
        
        print(f"LaTeX table - LLM types: {llm_types}")
        print(f"LaTeX table - Workflows: {workflows}")
        print(f"LaTeX table - Temperatures: {temperatures}")
        
        # LLM name mapping
        llm_names = {
            "reasoning": "DeepSeek R1 70B",
            "non_reasoning": "Llama 3.3 70B"
        }
        
        # Workflow name mapping
        workflow_names = {
            "mas": "MAS",
            "pair": "2AS"  # Fixed: was "2as" but data has "pair"
        }
        
        with open(output_path, 'w') as f:
            f.write(r"\begin{table}[ht]" + "\n")
            f.write(r"  \centering" + "\n")
            f.write(r"  \caption{Overall performance (mean\,$\pm$\,std over 10 runs) of each LLM under the multi-agent system (MAS) and two-agent system (2AS) across temperature settings. Best values in \textbf{bold}.}" + "\n")
            f.write(r"  \label{tab:main-results}" + "\n")
            f.write(r"  \begin{tabular}{llcccccccc}" + "\n")
            f.write(r"    \toprule" + "\n")
            f.write(r"    \textbf{LLM} & \textbf{System} & \textbf{Temp} & \textbf{M1 (\%)$\uparrow$} & \textbf{M2 (\%)$\uparrow$} & \textbf{M3 (\%)$\uparrow$} & \textbf{M4 (\%)$\uparrow$} & \textbf{M5 (\#)$\uparrow$} & \textbf{M6 (s)$\downarrow$} & \textbf{M7 (\# N)$\uparrow$} \\" + "\n")
            f.write(r"    \midrule" + "\n")
            
            # Generate table rows
            for i, llm_type in enumerate(llm_types):
                llm_name = llm_names.get(llm_type, llm_type)
                num_rows = len(workflows) * len(temperatures)
                f.write(f"    \\multirow{{{num_rows}}}{{*}}{{{llm_name}}}\n")
                
                for j, workflow in enumerate(workflows):
                    workflow_name = workflow_names.get(workflow, workflow)
                    f.write(f"      & \\multirow{{{len(temperatures)}}}{{*}}{{{workflow_name}}}\n")
                    
                    for k, temp in enumerate(temperatures):
                        # For continuation rows, we need empty cells for the multirow columns
                        if k == 0:
                            # First row of this workflow group - has both multirow cells
                            f.write(f"        & {temp:.1f}")
                        else:
                            # Continuation row - needs empty cells for both multirow columns
                            f.write(f"    & & {temp:.1f}")
                        
                        # Get values for each metric
                        for metric in ["M1", "M2", "M3", "M4", "M5", "M6", "M7"]:
                            try:
                                # Check if the combination exists in stats
                                if (llm_type, temp, workflow) in stats.index:
                                    if metric == "M5":
                                        # M5 is a count, no standard deviation
                                        count_val = stats.loc[(llm_type, temp, workflow), (metric, "sum")]
                                        formatted_val = f"{int(count_val)}"
                                    else:
                                        # Other metrics have mean and std
                                        mean_val = stats.loc[(llm_type, temp, workflow), (metric, "mean")]
                                        std_val = stats.loc[(llm_type, temp, workflow), (metric, "std")]
                                        # Convert to percent for display for M1-M4
                                        if metric in ["M1", "M2", "M3", "M4"]:
                                            mean_val *= 100
                                            std_val *= 100
                                        formatted_val = format_mean_std(mean_val, std_val)
                                else:
                                    if metric == "M5":
                                        formatted_val = "0"  # No successful runs
                                    else:
                                        formatted_val = r"\tbd\,$\pm$\,\tbd"
                            except Exception as e:
                                print(f"Warning: Could not get {metric} for {llm_type}, {temp}, {workflow}: {e}")
                                if metric == "M5":
                                    formatted_val = "0"
                                else:
                                    formatted_val = r"\tbd\,$\pm$\,\tbd"
                            
                            f.write(f" & {formatted_val}")
                        
                        f.write(" \\\\\n")
                    
                    # Add cmidrule between workflows (except after the last one)
                    if j < len(workflows) - 1:
                        f.write(r"    \cmidrule{2-10}" + "\n")
                
                # Add midrule between LLM types (except after the last one)
                if i < len(llm_types) - 1:
                    f.write(r"    \midrule" + "\n")
            
            f.write(r"  \end{tabular}" + "\n")
            f.write(r"\end{table}" + "\n")
    
    except Exception as e:
        print(f"Error in generate_latex_table: {e}")
        import traceback
        traceback.print_exc()
        raise


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
