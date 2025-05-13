# run_pipeline.py – fully‑automated MAS vs 2AS benchmark runner
# -----------------------------------------------------------------------------
#  – Launches the chosen workflows N times
#  – Extracts Design‑State Graphs, generated scripts & token logs
#  – Computes reproducible metrics → CSV + pretty Markdown table
# -----------------------------------------------------------------------------
#  Metrics collected per run  (all zero‑to‑one unless noted)
#   • req_coverage   – SR‑01 … SR‑10 textual hit‑rate in graph nodes
#   • func_depth     – avg. depth of functional decomposition branch
#   • script_compile – % scripts that pass `ast.parse`
#   • script_exec    – % scripts that *run* (python ⟨file⟩ --smoketest)
#   • physics_score  – heuristic physics fidelity (NumPy/SciPy + eq signs)
#   • tokens         – total prompt+completion tokens (if LangSmith logs) **
# -----------------------------------------------------------------------------
# Usage examples
#   python run_pipeline.py                  # 1 MAS + 1 2AS run → table only
#   python run_pipeline.py --runs 5 --csv   # writes metrics_YYYYMMDD.csv
# -----------------------------------------------------------------------------

import argparse, csv, json, tempfile, ast, re, subprocess, sys, time, shlex
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple

from workflows.mas_workflow  import run_once as run_mas
from workflows.pair_workflow import run_once as run_pair

from prompts import CAHIER_DES_CHARGES_REV_C


# ---------- 1.  Configurable patterns --------------------------------------------------
REQ_REGEX: Dict[str, str] = {
    "SR-01": r"10\s*l[\/]h|10\s*lit(e|re)s",
    "SR-02": r"4[- ]?log|99\.99",
    "SR-03": r"300\s*w\/m\^?2",
    "SR-04": r"50\s*w",
    "SR-05": r"6\s*h(ours)?",
    "SR-06": r"-?10\s*°?c.*50\s*°?c",
    "SR-07": r"20\s*kg|80\s*kg",
    "SR-08": r"60%.*recycl",
    "SR-09": r"start\/stop.*3.*action|<\s*2\s*s",
    "SR-10": r"500\s*\$|5,?000\s*\$",
}

PHYSICS_IMPORTS = ("numpy", "scipy", "sympy", "pint", "math")
CODE_BLOCK_RE = re.compile(r"```(?:python)?\s+([\s\S]*?)```", re.IGNORECASE)


# ---------- 2.  Helpers ----------------------------------------------------------------

def get_final_graph(state) -> Dict[str, Any]:
    if not state.design_graph_history:
        return {"nodes": [], "edges": []}
    g = state.design_graph_history[-1]
    return json.loads(g.model_dump_json()) if hasattr(g, "model_dump_json") else g


def requirement_coverage(graph: Dict[str, Any]) -> float:
    covered = {k: False for k in REQ_REGEX}
    for node in graph.get("nodes", []):
        blob = json.dumps(node).lower()
        for rid, patt in REQ_REGEX.items():
            if re.search(patt, blob):
                covered[rid] = True
    return sum(covered.values()) / len(covered)


def functional_depth(graph: Dict[str, Any]) -> float:
    parents = {n["node_id"]: set() for n in graph.get("nodes", [])}
    for e in graph.get("edges", []):
        parents[e[1]].add(e[0])
    depths = {}
    def _d(n):
        if n in depths: return depths[n]
        depths[n] = 0 if not parents[n] else 1 + max(_d(p) for p in parents[n])
        return depths[n]
    leaves = [n["node_id"] for n in graph.get("nodes", []) if n["node_type"] in ("function","subfunction") and not any(e[0]==n["node_id"] for e in graph.get("edges", []))]
    return sum(_d(l) for l in leaves)/len(leaves) if leaves else 0.0

# --- script utils ----------------------------------------------------------------------


def extract_scripts(graph: Dict[str, Any], out_dir: Path) -> List[Path]:
    """Return list of *.py files extracted from every code‑type node.

    • Accepts Markdown payloads with fenced blocks, e.g.
        ```python
        import numpy as np
        ...
        ```
      If multiple code fences exist, each is dumped separately.
    • If no fence is present we treat the *entire* payload as Python.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for idx, node in enumerate(graph.get("nodes", [])):
        #if node.get("node_type") != "code":
        #    continue

        payload = node.get("payload", "")
        blocks = CODE_BLOCK_RE.findall(payload)
        if not blocks:
            blocks = [payload]  # fallback – assume whole payload is code

        for b_idx, code in enumerate(blocks):
            # strip leading whitespace to avoid indentation errors
            code = code.lstrip("\n").rstrip()
            p = out_dir / f"node{idx}_part{b_idx}.py"
            p.write_text(code)
            paths.append(p)

    return paths



def compile_ok(path: Path) -> bool:
    try:
        ast.parse(path.read_text())
        return True
    except SyntaxError:
        return False


def exec_ok(path: Path, timeout=10) -> bool:
    """Run the script in a subprocess with --help smoke‑test."""
    try:
        cmd = [sys.executable, str(path), "--help"]
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return out.returncode == 0
    except Exception:
        return False


def physics_heuristic(path: Path) -> int:
    txt = path.read_text().lower()
    score = 0
    if any(f"import {pkg}" in txt for pkg in PHYSICS_IMPORTS):
        score += 1
    # rough equation cue: equality containing ** or mathematical ops
    if re.search(r"[=].*\*\*|np\.", txt):
        score += 1
    if re.search(r"def .*_balance|pressure|flow|energy", txt):
        score += 1
    return score  # 0‑3

# ---------- 3.  Token extraction (optional) --------------------------------------------

def token_count(state) -> int:
    return getattr(state, "total_tokens", 0) if hasattr(state, "total_tokens") else 0

# ---------- 4.  Single experiment ------------------------------------------------------

def evaluate_state(state, mode, tid) -> Dict[str, Any]:
    graph = get_final_graph(state)
    tmp   = Path(tempfile.mkdtemp(prefix="scripts_"))
    scripts = extract_scripts(graph, tmp)

    compile_pass = sum(compile_ok(p) for p in scripts)
    exec_pass    = sum(exec_ok(p)    for p in scripts)
    phys_score   = sum(physics_heuristic(p) for p in scripts)
    max_phys     = 3 * len(scripts)

    return {
        "mode": mode,
        "thread": tid,
        "req_coverage": round(requirement_coverage(graph), 3),
        "func_depth":   round(functional_depth(graph), 3),
        "script_compile": round(compile_pass/len(scripts), 3) if scripts else 0,
        "script_exec":    round(exec_pass/len(scripts), 3) if scripts else 0,
        "physics_score":  round(phys_score/max_phys, 3) if scripts else 0,
        "tokens": token_count(state),
    }


# ---------- 5.  Runner -----------------------------------------------------------------

def single_run(mode: str, request: str, idx: int):
    state = run_mas(request, str(idx)) if mode == "mas" else run_pair(request, str(idx))
    return evaluate_state(state, mode, idx)


# ---------- 6.  CLI --------------------------------------------------------------------

def get_default_request():
    return f"I want to create a solar powered water filtration system satisfying the Cahier des Charges Rev C: {CAHIER_DES_CHARGES_REV_C}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--request", default=get_default_request())
    ap.add_argument("--csv", action="store_true", help="write csv file")
    args = ap.parse_args()

    rows: List[Dict[str, Any]] = []
    for r in range(args.runs):
        for m in ("mas", "pair"):
            res = single_run(m, args.request, r)
            rows.append(res)
            print(res)

    if args.csv:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(f"metrics_{ts}.csv")
        with path.open("w", newline="") as fh:
            csv.DictWriter(fh, rows[0].keys()).writeheader(); csv.DictWriter(fh, rows[0].keys()).writerows(rows)
        print(f"✅ CSV saved → {path}")

    # Pretty Markdown for quick copy‑paste
    hdr = " | ".join(rows[0].keys())
    print("\n\n### Aggregate Metrics\n")
    print("| " + hdr + " |")
    print("| " + " | ".join(["---"]*len(rows[0])) + " |")
    for r in rows:
        print("| " + " | ".join(str(v) for v in r.values()) + " |")

if __name__ == "__main__":
    main()
