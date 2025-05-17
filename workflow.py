########### DEPRECATED ###########
# workflow.py
#!/usr/bin/env python3
"""
workflow.py    – Unified experiment runner.

Usage examples
--------------
# 1 run of the MAS (default request)
$ python workflow.py --mode mas

# 5 runs of the 2-Agent baseline, save metrics.jsonl
$ python workflow.py --mode pair --runs 5 --out results_pair.jsonl
"""
import argparse, json, pathlib
from datetime import datetime
from evaluation import collect_metrics          # your helper

from workflows.mas_workflow   import run_once as run_mas
from workflows.pair_workflow  import run_once as run_pair

DEFAULT_REQ = (
    "I want to create a water filtration system that is solar powered. "
    "Please satisfy the Cahier des Charges Rev C."
)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode",  choices=["mas", "pair"], default="mas",
                   help="Which workflow to execute")
    p.add_argument("--runs",  type=int, default=1,
                   help="How many independent seeds to run")
    p.add_argument("--request", type=str, default=DEFAULT_REQ,
                   help="User request string")
    p.add_argument("--out", type=str, default="",
                   help="Optional path to save newline-delimited JSON metrics")
    args = p.parse_args()

    runner = run_mas if args.mode == "mas" else run_pair
    metrics_sink = open(args.out, "w") if args.out else None

    for k in range(args.runs):
        state = runner(args.request, thread_id=str(k))
        metrics = collect_metrics(state, workflow=args.mode, run=k)

        print(f"[{args.mode.upper()} run {k}]  ",
              ", ".join(f"{k}: {v:.3f}" if isinstance(v, float) else f"{k}: {v}"
                        for k, v in metrics.items()))

        if metrics_sink:
            metrics_sink.write(json.dumps(metrics) + "\n")
            metrics_sink.flush()

    if metrics_sink:
        metrics_sink.close()
        print(f"✅  Metrics written to {metrics_sink.name}")


if __name__ == "__main__":
    main()
