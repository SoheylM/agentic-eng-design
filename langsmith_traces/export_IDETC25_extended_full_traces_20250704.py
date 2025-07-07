#!/usr/bin/env python
from langsmith import Client
import json
import uuid

# ── CONFIG ────────────────────────────────────────────────────────────────
DATASET_ID  = "e80669c8-3e7c-4770-bc7f-bb9da4e9db0c"   # Your Dataset's UUID
OUT_JSON    = "IDETC-25-Extended_full_traces_2025-07-04.json"
# ── END CONFIG ────────────────────────────────────────────────────────────

def default_serializer(obj):
    if isinstance(obj, uuid.UUID):
        return str(obj)
    # Add more custom serialization if needed
    return str(obj)

client = Client()

print(f"Getting examples from dataset {DATASET_ID}…")

# Get all examples from the dataset
examples = list(client.list_examples(dataset_id=DATASET_ID))
print(f"→ Found {len(examples)} examples in dataset")

# Collect all unique run IDs from the examples
run_ids = set()
for example in examples:
    if example.source_run_id:
        run_ids.add(example.source_run_id)

print(f"→ Found {len(run_ids)} unique runs to fetch")

# Fetch all the runs
full_runs = []
for run_id in run_ids:
    try:
        run = client.read_run(run_id=run_id)
        run_dict = run.dict()
        full_runs.append(run_dict)
        print(f"  ✓ Fetched run {run_id}")
    except Exception as e:
        print(f"  ✗ Failed to fetch run {run_id}: {e}")

print(f"→ Successfully fetched {len(full_runs)} runs")

# Write them all out in one big JSON
with open(OUT_JSON, "w") as f:
    json.dump(full_runs, f, indent=2, default=default_serializer)

print(f"✅ Wrote full runs to {OUT_JSON}")
