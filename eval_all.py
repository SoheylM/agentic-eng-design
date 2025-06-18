import os
from pathlib import Path
import pandas as pd
from eval_saved import process_batch, generate_report

base_dir = Path("runs")
output_dir = Path("experiment_results")
all_dfs = []

for folder in base_dir.iterdir():
    if folder.is_dir() and folder.name != "unnamed_run":
        batch_id = folder.name
        try:
            df = process_batch(base_dir, batch_id)
            df["batch_id"] = batch_id  # Optionally track source
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