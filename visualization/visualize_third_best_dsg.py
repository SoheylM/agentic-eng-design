#!/usr/bin/env python3
"""
Script to visualize the third best DSG file found in the runs directory.
"""

import json
import sys
from pathlib import Path

# Add the current directory to the path so we can import graph_utils
sys.path.append(str(Path(__file__).resolve().parent))

from data_models import DesignNode, DesignState, Embodiment, PhysicsModel
from graph_utils import visualize_design_state_func


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


def main():
    """Main function to load and visualize the third best DSG."""

    # Path to the third best DSG file
    third_best_dsg_path = "runs/20250615_185047/reasoning_t0.5_pair_run00/DSG_7.json"

    print(f"🥉 Loading the THIRD BEST DSG file: {third_best_dsg_path}")
    print("=" * 60)

    try:
        # Load the DSG
        design_state = load_dsg_from_json(third_best_dsg_path)

        print(f"✅ Successfully loaded DSG with {len(design_state.nodes)} nodes and {len(design_state.edges)} edges")
        print()

        # Print a summary of the nodes
        print("📊 DSG Node Summary:")
        print("-" * 40)
        for node_id, node in design_state.nodes.items():
            print(f"🔹 {node_id}: {node.name} ({node.node_kind})")
            print(f"   Maturity: {node.maturity}")
            print(f"   Physics Models: {len(node.physics_models)}")
            print(f"   Cost: ${node.embodiment.cost_estimate}")
            print(f"   Mass: {node.embodiment.mass_estimate} kg")
            print()

        # Print edge information
        if design_state.edges:
            print("🔗 DSG Connections:")
            print("-" * 40)
            for edge in design_state.edges:
                source_name = design_state.nodes[edge[0]].name if edge[0] in design_state.nodes else edge[0]
                target_name = design_state.nodes[edge[1]].name if edge[1] in design_state.nodes else edge[1]
                print(f"   {source_name} → {target_name}")
            print()

        # Calculate total system cost
        total_cost = sum(node.embodiment.cost_estimate for node in design_state.nodes.values())
        total_mass = sum(node.embodiment.mass_estimate for node in design_state.nodes.values())

        print("💰 System Cost Analysis:")
        print("-" * 40)
        print(f"   Total System Cost: ${total_cost}")
        print(f"   Total System Mass: {total_mass} kg")
        print()

        # Visualize the design state
        print("🎨 Generating visualization...")
        print("=" * 60)

        result = visualize_design_state_func(design_state)
        print(result)

        # Also provide a detailed summary
        print("\n📋 Detailed DSG Summary:")
        print("=" * 60)

        from graph_utils import summarize_design_state_func

        summary = summarize_design_state_func(design_state)
        print(summary)

    except FileNotFoundError:
        print(f"❌ Error: Could not find the DSG file at {third_best_dsg_path}")
        print("Please make sure the file exists and the path is correct.")
    except Exception as e:
        print(f"❌ Error loading or visualizing DSG: {e!s}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
