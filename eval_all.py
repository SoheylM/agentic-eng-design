from pathlib import Path

import pandas as pd

from eval_saved import detect_system_type_from_batch, generate_report, process_batch

base_dir = Path("runs")
output_dir = Path("experiment_results")
all_dfs = []

for folder in base_dir.iterdir():
    if folder.is_dir() and folder.name != "unnamed_run":
        batch_id = folder.name
        try:
            # Auto-detect system type for each batch
            system_type = detect_system_type_from_batch(folder)
            print(f"🔍 Processing {batch_id} with system type: {system_type}")

            df = process_batch(base_dir, batch_id, system_type)
            df["batch_id"] = batch_id  # Optionally track source
            df["system_type"] = system_type  # Track system type
            all_dfs.append(df)
        except Exception as e:
            print(f"Skipping {batch_id}: {e}")

if all_dfs:
    df_all = pd.concat(all_dfs, ignore_index=True)
    # Save consolidated metrics and plots
    generate_report(df_all, output_dir, "ALL")
    print("✅ Consolidated evaluation complete.")
    print(f"  Results → {output_dir}")
else:
    print("No valid experiment folders found.")
