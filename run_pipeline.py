# run_pipeline.py  – experiment runner + metrics
# ---------------------------------------------------------------------------
#  ▸ Launch MAS & 2AS workflows N times
#  ▸ Save final Design-State Graph, scripts, and deterministic metrics
# ---------------------------------------------------------------------------
import argparse, csv, json, re, subprocess, sys, tempfile, ast, time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import networkx as nx
import sympy

from workflows.mas_workflow  import run_once as run_mas
from workflows.pair_workflow import run_once as run_pair
from prompts import CAHIER_DES_CHARGES_REV_C

from data_models import DesignState, PhysicsModel, DesignNode

# ────────────────────────────────────────────────────────────────────────────
#  Regex blue-prints for requirement coverage
# ────────────────────────────────────────────────────────────────────────────
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

PHYS_IMPORTS  = ("numpy", "scipy", "sympy", "pint", "math")
SOLVER_KEYW   = ("integrate", "ode", "solve", "root", "linalg")
CODE_BLOCK_RE = re.compile(r"```(?:python)?\s+([\s\S]*?)```", re.IGNORECASE)


# ────────────────────────────────────────────────────────────────────────────
#  Helpers – graph-level metrics
# ────────────────────────────────────────────────────────────────────────────
def to_nx(graph: DesignState) -> nx.DiGraph:
    G = nx.DiGraph()
    for nid, n in graph.nodes.items():
        G.add_node(nid, kind=n.node_kind, maturity=n.maturity)
    for src, dst in graph.edges:
        G.add_edge(src, dst)
    return G


def requirement_coverage(graph: DesignState) -> float:
    covered = {k: False for k in REQ_REGEX}
    blob    = json.dumps(graph.model_dump()).lower()
    for rid, patt in REQ_REGEX.items():
        if re.search(patt, blob):
            covered[rid] = True
    return sum(covered.values()) / len(covered)


def trace_depth(graph: DesignState) -> float:
    G = to_nx(graph)
    req_ids  = [n for n,d in G.nodes(data=True) if d["kind"] == "requirement"]
    phys_ids = [nid for nid, nd in graph.nodes.items() if nd.physics_models]
    if not req_ids or not phys_ids:
        return 0.0
    depths = []
    for r in req_ids:
        try:
            d = min(nx.shortest_path_length(G, r, p) for p in phys_ids)
            depths.append(d)
        except nx.NetworkXNoPath:
            depths.append(len(graph.nodes))
    return sum(depths)/len(depths)


def avg_branching(graph: DesignState) -> float:
    G = to_nx(graph)
    degs = [G.out_degree(n) for n in G.nodes if G.out_degree(n)]
    return sum(degs)/len(degs) if degs else 0.0


def design_maturity(graph: DesignState) -> float:
    mature = sum(1 for n in graph.nodes.values() if n.maturity in ("reviewed", "validated"))
    return mature/len(graph.nodes) if graph.nodes else 0.0


def embody_ratio(graph: DesignState) -> float:
    filled = sum(n.embodiment.principle != "undefined" for n in graph.nodes.values())
    return filled/len(graph.nodes) if graph.nodes else 0.0


def cost_filled(graph: DesignState) -> float:
    ok = sum(n.embodiment.cost_estimate >= 0 for n in graph.nodes.values())
    return ok/len(graph.nodes) if graph.nodes else 0.0


def sympy_parse_rate(graph: DesignState) -> float:
    eqs = [pm.equations for n in graph.nodes.values() for pm in n.physics_models]
    if not eqs:
        return 0.0
    ok = 0
    for e in eqs:
        try:
            sympy.sympify(e)
            ok += 1
        except Exception:
            pass
    return ok/len(eqs)


# ────────────────────────────────────────────────────────────────────────────
#  Helpers – code extraction & evaluation
# ────────────────────────────────────────────────────────────────────────────
def extract_scripts(graph: DesignState, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for idx, node in enumerate(graph.nodes.values()):
        for pm_idx, pm in enumerate(node.physics_models):
            blocks = CODE_BLOCK_RE.findall(pm.python_code) or [pm.python_code]
            for b_idx, code in enumerate(blocks):
                code = code.lstrip("\n").rstrip()
                p    = out_dir / f"node{idx}_pm{pm_idx}_part{b_idx}.py"
                p.write_text(code)
                paths.append(p)
    return paths


def compile_ok(path: Path) -> bool:
    try:
        ast.parse(path.read_text())
        return True
    except SyntaxError:
        return False


def exec_ok(path: Path, timeout: int = 10) -> bool:
    try:
        cmd = [sys.executable, str(path), "--help"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=timeout)
        return res.returncode == 0
    except Exception:
        return False


def physics_fidelity(path: Path) -> float:
    txt = path.read_text().lower()
    pts = 0
    if any(f"import {pkg}" in txt for pkg in PHYS_IMPORTS):
        pts += 1
    if re.search(r"[\=].*\*\*|np\.(sin|cos|log)", txt):
        pts += 1
    if any(kw in txt for kw in SOLVER_KEYW):
        pts += 1
    return pts/3


def pylint_score(path: Path) -> float:
    try:
        out = subprocess.run(["pylint", "--score", "y", str(path)],
                             capture_output=True, text=True, timeout=20)
        m = re.search(r"rated at ([\d\.]+)/10", out.stdout)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


def cyclomatic_mean(path: Path) -> float:
    try:
        from radon.complexity import cc_visit
        scores = [c.complexity for c in cc_visit(path.read_text())]
        return (sum(scores)/len(scores))/10 if scores else 0.0
    except Exception:
        return 0.0


# ────────────────────────────────────────────────────────────────────────────
#  Single-run evaluation
# ────────────────────────────────────────────────────────────────────────────
def eval_state(state, mode: str, tid: int) -> Dict[str, Any]:
    if not state.design_graph_history:
        return {"error": "no graph produced"}

    dsg: DesignState = state.design_graph_history[-1]
    tmp_dir          = Path(tempfile.mkdtemp(prefix="dsg_scripts_"))
    scripts          = extract_scripts(dsg, tmp_dir)

    # ----- code metrics
    comp_pass = sum(compile_ok(p) for p in scripts)
    exec_pass = sum(exec_ok(p)    for p in scripts)
    phys_fid  = sum(physics_fidelity(p) for p in scripts)

    lint      = [pylint_score(p)     for p in scripts]
    cyclo     = [cyclomatic_mean(p)  for p in scripts]

    # ----- aggregate
    return {
        "mode":                  mode,
        "thread":                tid,
        # requirement / traceability
        "req_coverage":          round(requirement_coverage(dsg), 3),
        "trace_depth":           round(trace_depth(dsg), 3),
        # graph structure
        "avg_branching":         round(avg_branching(dsg), 3),
        "design_maturity":       round(design_maturity(dsg), 3),
        "embody_ratio":          round(embody_ratio(dsg), 3),
        "cost_filled":           round(cost_filled(dsg), 3),
        # equations
        "sympy_parse_rate":      round(sympy_parse_rate(dsg), 3),
        # code quality
        "script_compile":        round(comp_pass/len(scripts), 3) if scripts else 0,
        "script_exec":           round(exec_pass/len(scripts), 3) if scripts else 0,
        "physics_fidelity":      round(phys_fid/len(scripts), 3)  if scripts else 0,
        "lint_score":            round(sum(lint)/len(lint)/10, 3) if lint else 0,
        "cyclomatic_mean":       round(sum(cyclo)/len(cyclo), 3)  if cyclo else 0,
        # resources (placeholder - fill later)
        "tokens_prompt":         getattr(state, "tokens_prompt", 0),
        "tokens_completion":     getattr(state, "tokens_completion", 0),
        "wall_clock_s":          round(getattr(state, "wall_clock", 0), 2),
    }


# ────────────────────────────────────────────────────────────────────────────
#  Runner helpers
# ────────────────────────────────────────────────────────────────────────────
def single_run(mode: str, request: str, idx: int):
    tic   = time.time()
    state = run_mas(request, str(idx)) if mode == "mas" else run_pair(request, str(idx))
    toc   = time.time()
    # persist timing
    state.wall_clock = toc - tic
    return eval_state(state, mode, idx)


def default_request() -> str:
    return ("I want to create a solar powered water filtration system that "
            "satisfies this Cahier-des-Charges: "
            + CAHIER_DES_CHARGES_REV_C)


# ────────────────────────────────────────────────────────────────────────────
#  Command-line entry
# ────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--request", default=default_request())
    ap.add_argument("--csv", action="store_true")
    args = ap.parse_args()

    rows: List[Dict[str, Any]] = []
    for r in range(args.runs):
        for m in ("mas", "pair"):
            res = single_run(m, args.request, r)
            rows.append(res)
            print(res)

    # optional CSV
    if args.csv:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = Path(f"metrics_{ts}.csv")
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, rows[0].keys())
            w.writeheader(); w.writerows(rows)
        print(f"✅ CSV saved → {path}")

    # quick Markdown table
    hdr = " | ".join(rows[0].keys())
    print("\n\n### Aggregate Metrics\n")
    print("| " + hdr + " |")
    print("| " + " | ".join(["---"]*len(rows[0])) + " |")
    for r in rows:
        print("| " + " | ".join(str(v) for v in r.values()) + " |")


if __name__ == "__main__":
    main()
