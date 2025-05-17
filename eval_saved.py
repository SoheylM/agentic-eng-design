"""
eval_saved.py
Load folders produced by run_pipeline.py and compute quality metrics.

Example:
    python eval_saved.py runs/2025-05-* --csv
"""

from __future__ import annotations
import argparse, csv, json, ast, re, subprocess, sys, tempfile, textwrap
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timezone as tz
import networkx as nx, sympy as sp

from data_models import DesignState

# ---------- regex / constants ------------------------------------------------
REQ_PATTS = {
    "SR-01": r"10\s*l[\/ ]h",
    "SR-02": r"4[- ]?log|99\.99",
    # … add the rest …
}
PHYS_IMPORTS = ("numpy", "scipy", "sympy", "pint", "math")
FENCE_RE     = re.compile(r"```(?:python)?\s+([\s\S]+?)```", re.I)

# ---------- metric helpers ---------------------------------------------------
def _req_coverage(dsg: DesignState) -> float:
    hit = {k: False for k in REQ_PATTS}
    for n in dsg.nodes.values():
        blob = json.dumps(n.model_dump()).lower()
        for k,p in REQ_PATTS.items():
            if re.search(p, blob): hit[k] = True
    return sum(hit.values())/len(hit)


def _depth(dsg: DesignState) -> float:
    G = nx.DiGraph(dsg.edges)
    roots = [n for n in dsg.nodes if not any(e[1]==n for e in dsg.edges)]
    if not roots: return 0.0
    depths = [max(nx.algorithms.dag.dag_longest_path_length(G, r)) for r in roots]
    return sum(depths)/len(depths)


def _branching(dsg: DesignState) -> float:
    G = nx.DiGraph(dsg.edges)
    return sum(G.out_degree(n) for n in G)/G.number_of_nodes() if G else 0


def _maturity(dsg: DesignState) -> float:
    scale = {"draft":0, "reviewed":.5, "validated":1}
    return sum(scale.get(n.maturity,0) for n in dsg.nodes.values())/len(dsg.nodes) if dsg.nodes else 0


def _sympy_rate(dsg: DesignState) -> float:
    eqs=[pm.equations for n in dsg.nodes.values() for pm in n.physics_models]
    ok=sum(1 for e in eqs if _sym_ok(e))
    return ok/len(eqs) if eqs else 0
def _sym_ok(eq:str)->bool:
    try: sp.sympify(eq); return True
    except (sp.SympifyError,TypeError): return False


# ---------- code extraction --------------------------------------------------
def _blocks(txt:str)->List[str]:
    b=FENCE_RE.findall(txt); return b if b else [txt]

def _scripts(dsg:DesignState,tmp:Path)->List[Path]:
    tmp.mkdir(parents=True,exist_ok=True); out=[]
    for i,n in enumerate(dsg.nodes.values()):
        for j,pm in enumerate(n.physics_models):
            for k,code in enumerate(_blocks(pm.python_code)):
                p=tmp/f"n{i}_pm{j}_{k}.py"
                p.write_text(textwrap.dedent(code).strip()); out.append(p)
    return out

def _compile(p:Path)->bool:
    try: ast.parse(p.read_text()); return True
    except SyntaxError: return False
def _exec(p:Path,timeout=10)->bool:
    try:
        res=subprocess.run([sys.executable,str(p),"--help"],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        return res.returncode==0
    except Exception: return False
def _phys(p:Path)->int:
    t=p.read_text().lower();s=0
    if any(f"import {m}" in t for m in PHYS_IMPORTS): s+=1
    if re.search(r"=\s*[^=].*\*\*|np\.",t): s+=1
    if re.search(r"pressure|flow|energy",t): s+=1
    return s


def _eval_folder(folder:Path)->Dict[str,float]:
    snaps=sorted(folder.glob("dsg_*.json"))
    if not snaps: return {"error":"no dsg"}
    hist=[]
    for f in snaps:
        dsg=DesignState(**json.loads(f.read_text()))
        tmp=Path(tempfile.mkdtemp(prefix="eval_"))
        scripts=_scripts(dsg,tmp)
        hist.append({
            "req": _req_coverage(dsg),
            "depth":_depth(dsg),
            "bran": _branching(dsg),
            "mat":  _maturity(dsg),
            "sym":  _sympy_rate(dsg),
            "comp": (sum(_compile(p) for p in scripts)/len(scripts)) if scripts else 0,
            "exec": (sum(_exec(p)    for p in scripts)/len(scripts)) if scripts else 0,
            "phys": (sum(_phys(p)    for p in scripts)/(3*len(scripts))) if scripts else 0,
        })
    first,last=hist[0],hist[-1]
    delta={f"Δ_{k}":round(last[k]-first[k],3) for k in first}
    final={f"final_{k}":round(v,3) for k,v in last.items()}
    return {**final,**delta,"n_iter":len(hist)}

# ---------- CLI --------------------------------------------------------------
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("folders",nargs="+",help="run folders (glob ok)")
    ap.add_argument("--csv",action="store_true")
    args=ap.parse_args()

    rows=[]
    for pat in args.folders:
        for fld in Path().glob(pat):
            res=_eval_folder(fld); res["run"]=fld.name; rows.append(res); print(res)

    if args.csv and rows:
        out=Path(f"eval_{datetime.now(tz.UTC).strftime('%Y%m%dT%H%M%S')}.csv")
        with out.open("w",newline="") as fh:
            w=csv.DictWriter(fh,rows[0].keys()); w.writeheader(); w.writerows(rows)
        print(f"✅ CSV saved → {out}")
