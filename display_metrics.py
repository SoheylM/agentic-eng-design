#!/usr/bin/env python3
"""
Quick metrics display script for demo purposes.
Shows metrics directly in the terminal without generating files.
"""

import json
import sys
from pathlib import Path
from eval_saved import process_batch, detect_system_type_from_batch

def display_metrics(batch_id: str, base_dir: str = "runs"):
    """
    Display metrics for a batch directly in the terminal.
    """
    base_path = Path(base_dir)
    batch_path = base_path / batch_id
    
    if not batch_path.exists():
        print(f"❌ Batch directory not found: {batch_path}")
        return
    
    # Auto-detect system type
    system_type = detect_system_type_from_batch(batch_path)
    print(f"🔍 System type: {system_type}")
    
    try:
        # Process the batch
        df = process_batch(base_path, batch_id, system_type)
        
        if df.empty:
            print("❌ No data found in batch")
            return
        
        print(f"\n📊 Metrics for Batch: {batch_id}")
        print("=" * 60)
        
        # Display summary statistics
        print(f"Total runs: {len(df)}")
        print(f"Successful runs (M5): {df['M5'].sum()}/{len(df)}")
        print(f"Average completion rate: {df['M5'].mean():.1%}")
        print()
        
        # Display metrics by configuration
        print("📈 Metrics by Configuration:")
        print("-" * 60)
        
        for _, row in df.iterrows():
            config = f"{row['llm_type']} | t={row['temperature']} | {row['workflow']}"
            print(f"\n🔹 {config}")
            print(f"   M1 (JSON Validity): {row['M1']:.1%}")
            print(f"   M2 (Requirements): {row['M2']:.1%}")
            print(f"   M3 (Embodiments): {row['M3']:.1%}")
            print(f"   M4 (Code Compat): {row['M4']:.1%}")
            print(f"   M5 (Completion): {row['M5']:.0%}")
            print(f"   M6 (Time): {row['M6']:.1f}s")
            print(f"   M7 (Nodes): {row['M7']:.0f}")
        
        # Display averages by LLM type
        print(f"\n📊 Averages by LLM Type:")
        print("-" * 60)
        for llm_type in df['llm_type'].unique():
            llm_data = df[df['llm_type'] == llm_type]
            print(f"\n🔹 {llm_type}:")
            print(f"   M1: {llm_data['M1'].mean():.1%} ± {llm_data['M1'].std():.1%}")
            print(f"   M2: {llm_data['M2'].mean():.1%} ± {llm_data['M2'].std():.1%}")
            print(f"   M3: {llm_data['M3'].mean():.1%} ± {llm_data['M3'].std():.1%}")
            print(f"   M4: {llm_data['M4'].mean():.1%} ± {llm_data['M4'].std():.1%}")
            print(f"   M5: {llm_data['M5'].mean():.1%} ± {llm_data['M5'].std():.1%}")
            print(f"   M6: {llm_data['M6'].mean():.1f}s ± {llm_data['M6'].std():.1f}s")
            print(f"   M7: {llm_data['M7'].mean():.1f} ± {llm_data['M7'].std():.1f}")
        
        # Display averages by workflow
        print(f"\n📊 Averages by Workflow:")
        print("-" * 60)
        for workflow in df['workflow'].unique():
            wf_data = df[df['workflow'] == workflow]
            print(f"\n🔹 {workflow}:")
            print(f"   M1: {wf_data['M1'].mean():.1%} ± {wf_data['M1'].std():.1%}")
            print(f"   M2: {wf_data['M2'].mean():.1%} ± {wf_data['M2'].std():.1%}")
            print(f"   M3: {wf_data['M3'].mean():.1%} ± {wf_data['M3'].std():.1%}")
            print(f"   M4: {wf_data['M4'].mean():.1%} ± {wf_data['M4'].std():.1%}")
            print(f"   M5: {wf_data['M5'].mean():.1%} ± {wf_data['M5'].std():.1%}")
            print(f"   M6: {wf_data['M6'].mean():.1f}s ± {wf_data['M6'].std():.1f}s")
            print(f"   M7: {wf_data['M7'].mean():.1f} ± {wf_data['M7'].std():.1f}")
        
        print(f"\n✅ Metrics display complete!")
        
    except Exception as e:
        print(f"❌ Error processing batch: {e}")
        import traceback
        traceback.print_exc()

def main():
    if len(sys.argv) < 2:
        print("Usage: python display_metrics.py <batch_id>")
        print("Example: python display_metrics.py 20250615_185047")
        return
    
    batch_id = sys.argv[1]
    display_metrics(batch_id)

if __name__ == "__main__":
    main()
