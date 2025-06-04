#!/usr/bin/env python
"""eval_metrics.py – quality audit for Design‑State Graph (DSG)

Implements the current metric suite *M1 … M6*:

M1 – **DSG parse rate**             (snapshot‑level → folder mean)
M2 – **Requirement coverage**       (SR‑01 … SR‑10 regex recall)
M3 – **Embodiment availability**    (non‑undefined `embodiment.principle`)
M4 – **Executable physics models**  (script compiles **and** `--help` runs)
M5 – **Run completion ratio**       (1 if final snapshot sets
        `workflow_complete=True`, else 0)
M6 – **Wall‑time to completion [s]** (first‑to‑last snapshot mtime delta)

The script processes *run folders* that contain one or more JSON snapshots.
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
from typing import Dict, List

import networkx as nx  # already part of the stack
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

# ──────────────────────────────────────────────
#  Folder‑level aggregation
# ──────────────────────────────────────────────

def evaluate_folder(folder: Path) -> Dict[str, float]:
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
        # M5 – completion flag from *final* snapshot
        "M5": per[-1]["_complete"],
    }

    # M6 – wall‑time (first→last) in seconds (UTC)
    t0 = datetime.fromtimestamp(snaps[0].stat().st_mtime, tz=tz.utc)
    t1 = datetime.fromtimestamp(snaps[-1].stat().st_mtime, tz=tz.utc)
    agg["M6"] = (t1 - t0).total_seconds()
    return agg

# ──────────────────────────────────────────────
#  CLI entry‑point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, csv

    ap = argparse.ArgumentParser(description="Evaluate run folders on metrics M1–M6.")
    ap.add_argument("paths", nargs="+", help="Run folder(s) to evaluate")
    ap.add_argument("--csv", action="store_true", help="Write aggregate CSV")
    args = ap.parse_args()

    rows: List[Dict[str, float]] = []
    for p in args.paths:
        f = Path(p)
        if not f.is_dir():
            print(f"⚠️  '{p}' is not a directory – skipped")
            continue
        res = evaluate_folder(f)
        rows.append(res)
        print(f"\n► Results for run '{res['run']}':")
        for k, v in res.items():
            print(f"  {k:<10}: {v}")

    if args.csv and rows:
        out = Path(f"eval_runs_{datetime.now(tz.utc).strftime('%Y%m%dT%H%M%SZ')}.csv")
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, rows[0].keys())
            w.writeheader(); w.writerows(rows)
        print(f"\n✅ CSV written → {out}")
