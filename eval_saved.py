# eval_saved.py  —  offline quality audit for saved DSG snapshots
# ---------------------------------------------------------------------------
from __future__ import annotations
import argparse, csv, json, ast, re, subprocess, sys, tempfile, textwrap
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timezone as tz
import networkx as nx, sympy as sp

from data_models import DesignState

import json
from itertools import chain
try:
    from radon.complexity import cc_visit_ast        # tiny dependency: pip install radon
except ImportError:
    cc_visit_ast = None
from collections import OrderedDict

# ------------------------------------------------------------------
#  Human-readable metadata for every metric we emit  (code-accurate)
# ------------------------------------------------------------------
_METRIC_INFO = OrderedDict([
    # ------------------------------------------------------------
    #  Requirement-centric
    # ------------------------------------------------------------
    ("req", (
        "Requirement coverage (SR-01 … SR-10)",
        (
            "Regex-based recall of the ten top-level system requirements.\n"
            " 1) For each SR pattern in REQ_PATTS we scan every node payload\n"
            "    (case-insensitive JSON dump).\n"
            " 2) Score = hits / 10.\n"
            "    1.00 → every requirement pattern matched at least once.\n"
            "    0.70 → three of the ten SR patterns never match.\n"
            " Raise by adding the missing requirement keywords/thresholds."
        ))),

    # ------------------------------------------------------------
    #  Graph topology
    # ------------------------------------------------------------
    ("depth", (
        "Average graph depth",
        (
            "Mean longest-path length (edge count) from each root to its furthest\n"
            "leaf.\n"
            " 0      → flat list, no decomposition.\n"
            " 1–3    → typical concept-design hierarchy.\n"
            " >5     → very deep; risk of telephone-pole design."
        ))),

    ("branch", (
        "Average branching factor",
        (
            "Fan-out = outgoing edges per node (mean).\n"
            " ≃1     → linear chain.\n"
            " 2–4    → balanced decomposition.\n"
            " >6     → extremely broad; consider merging functions."
        ))),

    ("density", (
        "Edge density",
        (
            "|E| / |V|  (0 when no edges).\n"
            " 0.05–0.30 is healthy; >0.50 often means spaghetti coupling."
        ))),

    # ------------------------------------------------------------
    #  Design richness / embodiment
    # ------------------------------------------------------------
    ("embody", (
        "Embodiment ratio",
        (
            "Fraction of all nodes whose `embodiment.principle` is not "
            "'undefined'.\n"
            "Indicates how much of the concept space has concrete tech choices."
        ))),

    ("phys_model", (
        "Physics-model coverage",
        (
            "Fraction of *subsystem* nodes that include ≥1 `PhysicsModel`.\n"
            " 0.0 → no predictive capability.\n"
            " 1.0 → every subsystem has code."
        ))),

    ("maturity", (
        "Maturity index",
        (
            "Weighted mean over `node.maturity`:\n"
            "  draft = 0,  reviewed = 0.5,  validated = 1.\n"
            "Tracks progress through design reviews and V&V."
        ))),

    # ------------------------------------------------------------
    #  Analytic documentation
    # ------------------------------------------------------------
    ("sympy", (
        "Equation parse rate",
        (
            "Share of `PhysicsModel.equations` strings that SymPy can parse\n"
            "without error.  Higher value ⇒ better-formatted algebra."
        ))),

    # ------------------------------------------------------------
    #  Code health
    # ------------------------------------------------------------
    ("compile", (
        "Scripts compile",
        (
            "Fraction of extracted *.py files that pass `ast.parse()`.\n"
            "Detects syntax errors and bad indentation."
        ))),

    ("execute", (
        "Scripts execute (--help)",
        (
            "Fraction of scripts that run `python script.py --help` without\n"
            "raising.  Catches missing imports or disallowed I/O."
        ))),

    ("phys_quality", (
        "Physics-quality composite",
        (
            "0–1 normalised average of a 0-90 rubric:\n"
            "  • 10 pts  CLI + JSON I/O contract\n"
            "  • 20 pts  Units (pint, `.to()`, dimensional safety)\n"
            "  • 25 pts  Solver richness (ODE, PDE, FEM, optimisation)\n"
            "  • 15 pts  Verification hooks (asserts, residuals, pytest)\n"
            "  • 20 pts  Physics keyword depth (enthalpy, Reynolds, …)\n"
            "\n"
            "Total maximum = 90 pts ⇒ metric tops out at 0.90.\n"
            "Guide:\n"
            " 0.72–0.90 → production-ready simulation code\n"
            " 0.40–0.71 → partial physics, needs units/tests\n"
            " < 0.40    → stub or empirical placeholders"
        ))),
])




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

# ─────────────────────────────────────────────
#  Physics-fidelity rubric helpers
# ─────────────────────────────────────────────
SOLVER_IMPORTS = {
    "ode":  ("scipy.integrate", "torchdiffeq"),
    "pde":  ("fenics", "dolfin", "fireshape"),
    "optim":("scipy.optimize", "pyomo", "openmdao", "cvxpy"),
    "lin":  ("numpy.linalg",),
}
PHYS_KEYWORDS = (
    "reynolds", "navierstokes", "bernoulli", "poisson",
    "fourier", "enthalpy", "osmotic", "viscosity",
    "young", "stefan-boltzmann", "richardson"
)

def _has_cli(p: Path) -> bool:
    try:
        out = subprocess.check_output([sys.executable, str(p), "--help"],
                                      stderr=subprocess.STDOUT, timeout=5)
        return b"--help" in out or b"usage" in out.lower()
    except Exception:
        return False

def _json_io_ok(p: Path) -> bool:
    try:
        out = subprocess.check_output([sys.executable, str(p)],
                                      stderr=subprocess.STDOUT, timeout=10)
        j = json.loads(out)
        return {"inputs", "outputs"}.issubset(j)
    except Exception:
        return False

def _uses_units(tree: ast.AST, text: str) -> bool:
    return ("unitregistry" in text) or any(
        isinstance(n, ast.Attribute) and n.attr == "to" for n in ast.walk(tree)
    )

def _solver_subscore(tree: ast.AST, text: str) -> int:
    score = 0
    for imps in SOLVER_IMPORTS.values():
        if any(imp in text for imp in imps):
            score += 1
    if re.search(r"solve_ivp|odeint|fdm|fem|mesh", text):
        score += 1
    return min(score, 5)          # 0-5

def _verification_subscore(text: str) -> int:
    if "assert" in text or "pytest" in text:
        return 3                  # full sub-score
    if re.search(r"convergen|residual|richardson", text):
        return 2
    return 0

def _phys_kw_subscore(text: str) -> int:
    return min(sum(k in text for k in PHYS_KEYWORDS), 4)  # 0-4


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

def physics_rubric(p: Path) -> int:
    """
    0-100 score:
      A Interface (10)   – CLI + JSON I/O
      B Units     (20)   – pint / .to() / UnitRegistry
      C Solvers   (25)   – ODE/PDE/FEM/optim imports
      D Checks    (25)   – asserts, residuals, pytest
      E Keywords  (20)   – domain physics vocabulary
    """
    try:
        text = p.read_text().lower()
        tree = ast.parse(text)
    except Exception:
        return 0   # unreadable file

    pts = 0
    # A – interface contract
    if _has_cli(p) and _json_io_ok(p):
        pts += 10
    # B – units / dimensional safety
    if _uses_units(tree, text):
        pts += 20
    # C – solver richness
    pts += 5 * _solver_subscore(tree, text)          # max 25
    # D – verification hooks
    pts += 5 * _verification_subscore(text)          # max 25
    # E – physics keyword depth
    pts += 5 * _phys_kw_subscore(text)               # max 20
    return pts



def _wrap_metrics(raw: Dict[str, float]) -> Dict[str, Dict[str, float | str]]:
    """
    Convert a {name: value} dict into a verbose dict
    {name: {'value': …, 'title': …, 'explain': …}}  using _METRIC_INFO.
    Unknown keys are passed through untouched.
    """
    verbose = OrderedDict()
    for k, v in raw.items():
        title, explain = _METRIC_INFO.get(
            k, (k, "no description available"))
        verbose[k] = {"value": round(v, 3), "title": title, "explain": explain}
    return verbose

# ------------------------------------------------------------------
#  Main evaluator ---------------------------------------------------
# ------------------------------------------------------------------
def evaluate_dsg(dsg: DesignState, tmp: Path) -> Dict[str, Dict[str, float | str]]:
    """
    Return a VERBOSE dict where each metric is annotated with its meaning.
    Example::

        {
          "req":         {"value": 0.9, "title": "Requirement coverage",
                          "explain": "0-1 ⇒ fraction of SR-codes referenced anywhere"},
          "depth":       {"value": 2.3, …},
          …
        }
    """
    scripts     = extract_scripts(dsg, tmp)
    compile_ok  = sum(compiles(p) for p in scripts)
    exec_ok     = sum(execs(p)    for p in scripts)
    phys_pts    = [physics_rubric(p) for p in scripts]
    phys_qual   = sum(phys_pts)/len(phys_pts) if phys_pts else 0   # 0-100

    raw = {
        "req"        : req_coverage(dsg),
        "depth"      : depth_avg(dsg),
        "branch"     : branching_avg(dsg),
        "density"    : edge_density(dsg),
        "embody"     : embodiment_ratio(dsg),
        "phys_model" : physics_model_ratio(dsg),
        "maturity"   : maturity_index(dsg),
        "sympy"      : sympy_rate(dsg),
        "compile"    : compile_ok/len(scripts) if scripts else 0,
        "execute"    : exec_ok /len(scripts) if scripts else 0,
        "phys_quality": phys_qual/100,                         # 0-1
    }
    return _wrap_metrics(raw)


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
    results["timestamp"] = datetime.fromtimestamp(file_path.stat().st_mtime, tz=tz.utc).isoformat()
    
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
