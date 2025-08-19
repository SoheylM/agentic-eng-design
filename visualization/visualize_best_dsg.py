#!/usr/bin/env python3
"""
Script to visualize the best DSG file found in the runs directory.
"""

import json
import sys
import os
from typing import Dict, Any, List

# Add the current directory to the path so we can import graph_utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from graph_utils import visualize_design_state_func
from data_models import DesignNode, DesignState, Embodiment, PhysicsModel

def load_dsg_from_json(file_path: str) -> DesignState:
    """
    Load a DSG from a JSON file and convert it to our DesignState format.
    """
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    # Create a new DesignState
    design_state = DesignState(nodes={}, edges=data.get('edges', []))
    
    # Convert nodes
    for node_id, node_data in data['nodes'].items():
        # Create Embodiment
        emb_data = node_data.get('embodiment', {})
        embodiment = Embodiment(
            principle=emb_data.get('principle', ''),
            description=emb_data.get('description', ''),
            design_parameters=emb_data.get('design_parameters', {}),
            cost_estimate=emb_data.get('cost_estimate', -1.0),
            mass_estimate=emb_data.get('mass_estimate', -1.0),
            status=emb_data.get('status', 'Unknown')
        )
        
        # Create PhysicsModels
        physics_models = []
        for pm_data in node_data.get('physics_models', []):
            physics_model = PhysicsModel(
                name=pm_data.get('name', ''),
                equations=pm_data.get('equations', ''),
                coding_directives=pm_data.get('coding_directives', ''),
                python_code=pm_data.get('python_code', ''),
                coder_notes=pm_data.get('coder_notes', ''),
                assumptions=pm_data.get('assumptions', []),
                status=pm_data.get('status', 'Unknown')
            )
            physics_models.append(physics_model)
        
        # Create DesignNode
        design_node = DesignNode(
            node_id=node_data.get('node_id', node_id),
            node_kind=node_data.get('node_kind', 'Component'),
            name=node_data.get('name', ''),
            description=node_data.get('description', ''),
            embodiment=embodiment,
            physics_models=physics_models,
            linked_reqs=node_data.get('linked_reqs', []),
            verification_plan=node_data.get('verification_plan', ''),
            maturity=node_data.get('maturity', 'Low'),
            tags=node_data.get('tags', [])
        )
        
        design_state.nodes[node_id] = design_node
    
    return design_state

def main():
    """Main function to load and visualize the best DSG."""
    
    # Path to the best DSG file
    best_dsg_path = "runs/20250616_125436/reasoning_t1.0_mas_run04/DSG_2.json"
    
    print(f"🎯 Loading the best DSG file: {best_dsg_path}")
    print("=" * 60)
    
    try:
        # Load the DSG
        design_state = load_dsg_from_json(best_dsg_path)
        
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
        print(f"❌ Error: Could not find the DSG file at {best_dsg_path}")
        print("Please make sure the file exists and the path is correct.")
    except Exception as e:
        print(f"❌ Error loading or visualizing DSG: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 