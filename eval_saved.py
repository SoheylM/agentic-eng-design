# eval_saved.py  —  offline quality audit for saved DSG snapshots
# ---------------------------------------------------------------------------
from __future__ import annotations
import argparse, csv, json, ast, re, subprocess, sys, tempfile, textwrap
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timezone as tz
import networkx as nx, sympy as sp

from data_models import DesignState

# ---------- regex / constants ----------------------------------------------
# ---------------------------------------
# Regex patterns for SR-01 … SR-10
# ---------------------------------------
REQ_PATTS: dict[str, str] = {
    # SR-01  ─ potable-water throughput ≥ 10 L/h
    "SR-01": r"10\s*l[\/ ]h",

    # SR-02  ─ ≥ 4-log (99.99 %) pathogen removal
    "SR-02": r"(4[- ]?log|99\.99\s*%)",

    # SR-03  ─ performance guaranteed at ≥ 300 W / m² (AM1.5)
    "SR-03": r"300\s*w\s*/\s*m(?:\^?2|²)",

    # SR-04  ─ average electrical power < 50 W
    "SR-04": r"50\s*w\b",

    # SR-05  ─ autonomous ≥ 6 hours with no sunlight
    "SR-05": r"6\s*h(?:ours?)?",

    # SR-06  ─ operating range −10 °C … 50 °C
    "SR-06": r"-?10\s*°?\s*c.*50\s*°?\s*c",

    # SR-07  ─ dry-mass limits < 20 kg (household) or < 80 kg (community)
    "SR-07": r"(?:20|80)\s*kg",

    # SR-08  ─ ≥ 60 % recyclable content
    "SR-08": r"60\s*%.*recycl",

    # SR-09  ─ ≤ 3 start/stop actions AND < 2 s status display
    "SR-09": r"start\/stop.*3.*action|<\s*2\s*s",

    # SR-10  ─ cost limits ≤ \$500 or ≤ \$5 000
    "SR-10": r"(?:500|5,?000)\s*\$",
}

PHYS_IMPORTS = ("numpy", "scipy", "sympy", "pint", "math")
FENCE_RE     = re.compile(r"```(?:python)?\s+([\s\S]+?)```", re.I)

# ---------- requirement coverage -------------------------------------------
def req_coverage(dsg: DesignState) -> float:
    hit = {k: False for k in REQ_PATTS}
    for n in dsg.nodes.values():
        blob = json.dumps(n.model_dump()).lower()
        for k, patt in REQ_PATTS.items():
            if re.search(patt, blob):
                hit[k] = True
    return sum(hit.values()) / len(hit)

# ---------- graph-shape -----------------------------------------------------
def depth_avg(dsg: DesignState) -> float:
    G = nx.DiGraph(dsg.edges)
    roots = [n for n in dsg.nodes if not any(e[1] == n for e in dsg.edges)]
    if not roots:
        return 0.0
    depths = []
    for r in roots:
        try:
            depths.append(nx.algorithms.dag.dag_longest_path_length(G, r))
        except nx.NetworkXUnfeasible:         # cycle present
            depths.append(0)
    return sum(depths) / len(depths)

def branching_avg(dsg: DesignState) -> float:
    G = nx.DiGraph(dsg.edges)
    return sum(dict(G.out_degree()).values()) / G.number_of_nodes() if G else 0

def edge_density(dsg: DesignState) -> float:
    v = len(dsg.nodes)
    return len(dsg.edges) / v if v else 0

# ---------- design richness --------------------------------------------------
def embodiment_ratio(dsg: DesignState) -> float:
    ok = [n for n in dsg.nodes.values()
          if n.embodiment and n.embodiment.principle != "undefined"]
    return len(ok) / len(dsg.nodes) if dsg.nodes else 0

def physics_model_ratio(dsg: DesignState) -> float:
    subsys = [n for n in dsg.nodes.values() if n.node_kind.lower() == "subsystem"]
    ok     = [n for n in subsys if n.physics_models]
    return len(ok) / len(subsys) if subsys else 0

def maturity_index(dsg: DesignState) -> float:
    scale = {"draft": 0, "reviewed": .5, "validated": 1}
    return (sum(scale.get(n.maturity, 0) for n in dsg.nodes.values())
            / len(dsg.nodes)) if dsg.nodes else 0

# ---------- sympy parse rate -------------------------------------------------
def _sym_ok(eq: str) -> bool:
    try: sp.sympify(eq); return True
    except (sp.SympifyError, TypeError): return False

def sympy_rate(dsg: DesignState) -> float:
    eqs = [pm.equations for n in dsg.nodes.values() for pm in n.physics_models]
    return sum(_sym_ok(e) for e in eqs) / len(eqs) if eqs else 0

# ---------- code extraction --------------------------------------------------
def _fenced_blocks(txt: str) -> List[str]:
    blk = FENCE_RE.findall(txt)
    return blk if blk else [txt]

def extract_scripts(dsg: DesignState, out: Path) -> List[Path]:
    out.mkdir(parents=True, exist_ok=True)
    files: List[Path] = []
    for i, n in enumerate(dsg.nodes.values()):
        for j, pm in enumerate(n.physics_models):
            for k, code in enumerate(_fenced_blocks(pm.python_code)):
                p = out / f"n{i}_pm{j}_{k}.py"
                p.write_text(textwrap.dedent(code).strip())
                files.append(p)
    return files

def compiles(p: Path) -> bool:
    try: ast.parse(p.read_text()); return True
    except SyntaxError: return False

def execs(p: Path, timeout=10) -> bool:
    try:
        r = subprocess.run([sys.executable, str(p), "--help"],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False

def phys_score(p: Path) -> int:
    t = p.read_text().lower(); s = 0
    if any(f"import {m}" in t for m in PHYS_IMPORTS): s += 1
    if re.search(r"=\s*[^=].*\*\*|np\.", t):         s += 1
    if re.search(r"pressure|flow|energy", t):        s += 1
    return s    # 0-3

# ---------- per-snapshot evaluation -----------------------------------------
def evaluate_dsg(dsg: DesignState, tmp: Path) -> Dict[str, float]:
    scripts = extract_scripts(dsg, tmp)
    compile_ok = sum(compiles(p) for p in scripts)
    exec_ok    = sum(execs(p)    for p in scripts)
    phys       = sum(phys_score(p) for p in scripts)

    return {
        "req" : req_coverage(dsg),
        "depth": depth_avg(dsg),
        "branch": branching_avg(dsg),
        "density": edge_density(dsg),
        "embody": embodiment_ratio(dsg),
        "phys_model": physics_model_ratio(dsg),
        "maturity": maturity_index(dsg),
        "sympy": sympy_rate(dsg),
        "compile": compile_ok / len(scripts) if scripts else 0,
        "execute": exec_ok    / len(scripts) if scripts else 0,
        "phys_code": phys / (3 * len(scripts)) if scripts else 0,
    }

# ---------- evaluate a run folder -------------------------------------------
def evaluate_folder(folder: Path) -> Dict[str, float]:
    snaps = sorted(folder.glob("dsg_*.json")) or sorted(folder.glob("*.json"))
    snaps = [p for p in snaps if "dsg" in p.name]   # avoid manifest.json
    if not snaps:
        return {"error": "no_dsg_files"}

    history: List[Dict[str, float]] = []
    for fp in snaps:
        dsg = DesignState(**json.loads(fp.read_text()))
        tmp = Path(tempfile.mkdtemp(prefix="eval_"))
        history.append(evaluate_dsg(dsg, tmp))

    first, last = history[0], history[-1]
    delta = {f"Δ_{k}": round(last[k] - first[k], 3) for k in first}
    final = {f"final_{k}": round(v, 3) for k, v in last.items()}
    final["n_iter"] = len(history)

    # optional: write per-iteration CSV for later plotting
    hist_path = folder / "metrics_history.csv"
    with hist_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, history[0].keys())
        w.writeheader(); w.writerows(history)

    return {**final, **delta}

def evaluate_single_file(file_path: Path) -> Dict[str, float]:
    """Evaluate a single DesignState JSON file."""
    if not file_path.exists():
        return {"error": "file_not_found"}
    
    dsg = DesignState(**json.loads(file_path.read_text()))
    tmp = Path(tempfile.mkdtemp(prefix="eval_"))
    results = evaluate_dsg(dsg, tmp)
    
    # Add file information
    results["file"] = file_path.name
    results["timestamp"] = datetime.fromtimestamp(file_path.stat().st_mtime, tz=tz.UTC).isoformat()
    
    return results

# ---------- CLI --------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="run folders or individual JSON files")
    ap.add_argument("--csv", action="store_true", help="save aggregate CSV")
    args = ap.parse_args()

    rows: List[Dict[str, float]] = []
    for pat in args.paths:
        path = Path(pat)
        if path.is_file() and path.suffix == '.json':
            # Single file analysis
            res = evaluate_single_file(path)
            rows.append(res)
            print(f"\nResults for {path.name}:")
            print(json.dumps(res, indent=2))
        elif path.is_dir():
            # Folder analysis
            res = evaluate_folder(path)
            res["run"] = path.name
            rows.append(res)
            print(f"\nResults for folder {path.name}:")
            print(json.dumps(res, indent=2))

    if args.csv and rows:
        out = Path(f"eval_{datetime.now(tz.UTC).strftime('%Y%m%dT%H%M%SZ')}.csv")
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        print(f"\n✅ aggregate CSV saved → {out}")
