#!/usr/bin/env python
from langsmith import Client
import json
import uuid
import csv
from collections import deque
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────
DATASET_ID  = "e80669c8-3e7c-4770-bc7f-bb9da4e9db0c"   # Your Dataset's UUID
OUT_JSON    = "IDETC-25-Extended_full_traces_2025-07-04.json"
OUT_CSV     = "IDETC-25-Extended_summary_2025-07-04.csv"
# ── END CONFIG ────────────────────────────────────────────────────────────

def default_serializer(obj):
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)

def fetch_run_tree(client, run_id):
    """Recursively fetch a run and all its children as a tree."""
    run = client.read_run(run_id=run_id)
    run_dict = run.dict()
    # Fetch children
    children = list(client.list_runs(parent_run_id=run_id))
    run_dict["children"] = [fetch_run_tree(client, child.id) for child in children]
    return run_dict

def flatten_run_tree(run_dict, parent_id=None):
    """Flatten the run tree into a list for CSV summary."""
    flat = []
    this_run = run_dict.copy()
    this_run["parent_id"] = parent_id
    children = this_run.pop("children", [])
    flat.append(this_run)
    for child in children:
        flat.extend(flatten_run_tree(child, parent_id=this_run["id"]))
    return flat

client = Client()

print(f"Getting examples from dataset {DATASET_ID}…")
examples = list(client.list_examples(dataset_id=DATASET_ID))
print(f"→ Found {len(examples)} examples in dataset")

run_ids = set()
for example in examples:
    if example.source_run_id:
        run_ids.add(example.source_run_id)

print(f"→ Found {len(run_ids)} unique runs to fetch recursively")

all_traces = []
all_flat = []
for run_id in run_ids:
    try:
        print(f"  → Fetching full trace for run {run_id}")
        run_tree = fetch_run_tree(client, run_id)
        all_traces.append(run_tree)
        all_flat.extend(flatten_run_tree(run_tree))
    except Exception as e:
        print(f"  ✗ Failed to fetch run {run_id}: {e}")

print(f"→ Successfully fetched {len(all_traces)} full traces")

# Write all traces to JSON
with open(OUT_JSON, "w") as f:
    json.dump(all_traces, f, indent=2, default=default_serializer)
print(f"✅ Wrote full traces to {OUT_JSON}")

# Write summary CSV
if all_flat:
    fieldnames = [
        "id", "parent_id", "name", "status", "start_time", "end_time", "latency", "run_type", "inputs", "outputs", "error", "total_tokens", "prompt_tokens", "completion_tokens", "total_cost", "project_name", "session_id"
    ]
    with open(OUT_CSV, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for run in all_flat:
            row = {k: run.get(k, "") for k in fieldnames}
            # Flatten tokens/cost if nested
            for key in ["inputs", "outputs"]:
                val = row[key]
                if isinstance(val, dict):
                    row[key] = json.dumps(val, default=default_serializer)
            writer.writerow(row)
    print(f"✅ Wrote summary CSV to {OUT_CSV}")
else:
    print("⚠️ No runs to write to CSV.") 