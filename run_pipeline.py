# run_pipeline.py
"""
Fire-and-forget launcher for MAS or 2-Agent workflows.

• The Meta-Review agent inside every workflow already dumps each Design-State
  Graph (DSG) to:
      runs/<thread_id>/stepXX_metaYY_<timestamp>.json

• This script simply launches the workflow N times and tells you where the
  DSG snapshots were written, so you can feed those folders to `eval_saved.py`.
"""

from __future__ import annotations
import argparse, importlib
from pathlib import Path

from prompts import CAHIER_DES_CHARGES_REV_C


# --------------------------------------------------------------------------- helpers
def default_request() -> str:
    """
    Single-line prompt that embeds the Rev-C Cahier-des-Charges.
    """
    return (
        "I want to create a solar-powered water-filtration system that satisfies "
        "the following Cahier-des-Charges Rev C:\n\n"
        + CAHIER_DES_CHARGES_REV_C
    )


def _run_once(mode: str, request: str, tid: int) -> Path:
    """
    Launch one workflow run and return the folder where DSG snapshots were saved.
    """
    if mode == "mas":
        wf = importlib.import_module("workflows.mas_workflow").run_once
    else:                              # "pair"
        wf = importlib.import_module("workflows.pair_workflow").run_once

    thread_id = f"{mode}-{tid:03d}"
    wf(request, thread_id=thread_id)   # the workflow saves DSGs internally

    outdir = Path("runs") / thread_id
    if outdir.exists():
        print(f"✅ {mode.upper()} run {tid} → {outdir}")
    else:
        print(f"⚠️  expected folder '{outdir}' not found (did Meta-Review run?)")
    return outdir


# --------------------------------------------------------------------------- CLI
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("mas", "pair"),
                    help="Workflow type: multi-agent system (mas) or 2-agent pair")
    ap.add_argument("--runs", type=int, default=1,
                    help="Number of independent runs to launch")
    ap.add_argument("--request", default=default_request(),
                    help="Initial user request (default embeds Rev-C CDC)")
    args = ap.parse_args()

    for i in range(args.runs):
        _run_once(args.mode, args.request, i)
