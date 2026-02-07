#!/usr/bin/env python3
"""
Script to visualize the latest DSG from the most recent run in the runs directory.
Usage: python visualization/visualize_uam_dsg.py [run_folder_name]
"""

import json
import sys
from pathlib import Path

# Add the parent directory to the path so we can import graph_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))

from data_models import DesignNode, DesignState, Embodiment, PhysicsModel
from graph_utils import summarize_design_state_func, visualize_design_state_func


def load_dsg_from_json(file_path: str) -> DesignState:
    """
    Load a DSG from a JSON file and convert it to our DesignState format.
    """
    with Path(file_path).open() as f:
        data = json.load(f)

    # Create a new DesignState
    design_state = DesignState(nodes={}, edges=data.get("edges", []))

    # Convert nodes
    for node_id, node_data in data["nodes"].items():
        # Create Embodiment
        emb_data = node_data.get("embodiment", {})
        embodiment = Embodiment(
            principle=emb_data.get("principle", ""),
            description=emb_data.get("description", ""),
            design_parameters=emb_data.get("design_parameters", {}),
            cost_estimate=emb_data.get("cost_estimate", -1.0),
            mass_estimate=emb_data.get("mass_estimate", -1.0),
            status=emb_data.get("status", "Unknown"),
        )

        # Create PhysicsModels
        physics_models = []
        for pm_data in node_data.get("physics_models", []):
            physics_model = PhysicsModel(
                name=pm_data.get("name", ""),
                equations=pm_data.get("equations", ""),
                coding_directives=pm_data.get("coding_directives", ""),
                python_code=pm_data.get("python_code", ""),
                coder_notes=pm_data.get("coder_notes", ""),
                assumptions=pm_data.get("assumptions", []),
                status=pm_data.get("status", "Unknown"),
            )
            physics_models.append(physics_model)

        # Create DesignNode
        design_node = DesignNode(
            node_id=node_data.get("node_id", node_id),
            node_kind=node_data.get("node_kind", "Component"),
            name=node_data.get("name", ""),
            description=node_data.get("description", ""),
            embodiment=embodiment,
            physics_models=physics_models,
            linked_reqs=node_data.get("linked_reqs", []),
            verification_plan=node_data.get("verification_plan", ""),
            maturity=node_data.get("maturity", "Low"),
            tags=node_data.get("tags", []),
        )

        design_state.nodes[node_id] = design_node

    return design_state


def find_latest_run_and_dsg() -> tuple[str, str]:
    """Find the most recent run folder and its latest DSG file."""
    runs_dir = Path("runs")
    if not runs_dir.exists():
        raise FileNotFoundError("No runs directory found")

    # Find all batch directories
    batch_dirs = [d for d in runs_dir.iterdir() if d.is_dir() and d.name != "unnamed_run"]
    if not batch_dirs:
        raise FileNotFoundError("No batch directories found in runs/")

    # Sort by creation time (newest first)
    batch_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    # Look through the most recent batch for any run with DSG files
    latest_batch = batch_dirs[0]
    print(f"🔍 Checking latest batch: {latest_batch.name}")

    # Find all run directories in the latest batch
    run_dirs = [d for d in latest_batch.iterdir() if d.is_dir()]
    if not run_dirs:
        raise FileNotFoundError("No run directories found in latest batch")

    # Sort run directories by creation time (newest first)
    run_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    # Find the first run directory that has DSG files
    for run_dir in run_dirs:
        dsg_files = list(run_dir.glob("*.json"))
        if dsg_files:
            # Sort DSG files and get the latest one
            dsg_files.sort(key=lambda x: x.name)
            latest_dsg = dsg_files[-1].name
            return run_dir.name, latest_dsg

    raise FileNotFoundError("No DSG files found in any run directory in the latest batch")


def main():
    """Main function to load and visualize the latest DSG from the most recent run."""

    # Get run folder name and DSG file from command line or find latest
    if len(sys.argv) > 1:
        run_folder_name = sys.argv[1]
        dsg_file_name = None  # Will find the latest DSG in the specified run
    else:
        try:
            run_folder_name, dsg_file_name = find_latest_run_and_dsg()
            print(f"🔍 Found latest run: {run_folder_name}")
            print(f"📄 Found latest DSG: {dsg_file_name}")
        except FileNotFoundError as e:
            print(f"❌ Error: {e}")
            print("Usage: python visualization/visualize_uam_dsg.py [run_folder_name]")
            return

    # Find the run directory
    runs_dir = Path("runs")
    run_path = None

    # Search through all batch directories
    for batch_dir in runs_dir.iterdir():
        if batch_dir.is_dir() and batch_dir.name != "unnamed_run":
            potential_run = batch_dir / run_folder_name
            if potential_run.exists():
                run_path = potential_run
                break

    if not run_path:
        print(f"❌ Error: Could not find run folder '{run_folder_name}' in any batch directory")
        return

    print(f"🚁 Loading DSG from: {run_path}")
    print("=" * 60)

    # Find DSG files
    if dsg_file_name:
        # Use the specified DSG file
        latest_dsg = run_path / dsg_file_name
        if not latest_dsg.exists():
            print(f"❌ Error: DSG file '{dsg_file_name}' not found in {run_path}")
            return
    else:
        # Find the latest DSG file in the specified run
        dsg_files = list(run_path.glob("*.json"))
        if not dsg_files:
            print(f"❌ Error: No DSG files found in {run_path}")
            return

        # Use the latest DSG file (highest step number)
        dsg_files.sort(key=lambda x: x.name)
        latest_dsg = dsg_files[-1]

    print(f"📄 Using DSG file: {latest_dsg.name}")
    print()

    try:
        # Load the DSG
        design_state = load_dsg_from_json(str(latest_dsg))

        print(f"✅ Successfully loaded DSG with {len(design_state.nodes)} nodes and {len(design_state.edges)} edges")
        print()

        # Print a summary of the nodes
        print("📊 DSG Node Summary:")
        print("-" * 50)
        for node_id, node in design_state.nodes.items():
            print(f"🔹 {node_id}: {node.name} ({node.node_kind})")
            print(f"   Maturity: {node.maturity}")
            print(f"   Physics Models: {len(node.physics_models)}")
            if node.embodiment.cost_estimate > 0:
                print(f"   Cost: ${node.embodiment.cost_estimate:,.0f}")
            if node.embodiment.mass_estimate > 0:
                print(f"   Mass: {node.embodiment.mass_estimate:.1f} kg")
            print()

        # Print edge information
        if design_state.edges:
            print("🔗 System Connections:")
            print("-" * 50)
            for edge in design_state.edges:
                source_name = design_state.nodes[edge[0]].name if edge[0] in design_state.nodes else edge[0]
                target_name = design_state.nodes[edge[1]].name if edge[1] in design_state.nodes else edge[1]
                print(f"   {source_name} → {target_name}")
            print()

        # Calculate total system metrics
        total_cost = sum(
            node.embodiment.cost_estimate for node in design_state.nodes.values() if node.embodiment.cost_estimate > 0
        )
        total_mass = sum(
            node.embodiment.mass_estimate for node in design_state.nodes.values() if node.embodiment.mass_estimate > 0
        )

        print("💰 System Analysis:")
        print("-" * 50)
        if total_cost > 0:
            print(f"   Total System Cost: ${total_cost:,.0f}")
        if total_mass > 0:
            print(f"   Total System Mass: {total_mass:.1f} kg")
        print(f"   Number of Components: {len(design_state.nodes)}")
        print(f"   Number of Connections: {len(design_state.edges)}")
        print()

        # Visualize the design state
        print("🎨 Generating visualization...")
        print("=" * 60)

        result = visualize_design_state_func(design_state)
        print(result)

        # Also provide a detailed summary
        print("\n📋 Detailed DSG Summary:")
        print("=" * 60)

        summary = summarize_design_state_func(design_state)
        print(summary)

    except FileNotFoundError:
        print(f"❌ Error: Could not find the DSG file at {latest_dsg}")
        print("Please make sure the file exists and the path is correct.")
    except Exception as e:
        print(f"❌ Error loading or visualizing DSG: {e!s}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
