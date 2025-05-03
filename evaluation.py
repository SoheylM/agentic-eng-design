from data_models import State, DesignState
from typing import List

def merge_snapshot_into_state(base_state: State, snapshot_values: dict) -> None:
    """
    Merges a single snapshot's .values dict into base_state in-place, 
    respecting operator.add vs. overwrite semantics.
    """
    # 1) Append list fields
    for key in [
        "messages", "supervisor_instructions", "supervisor_current_objectives",
        "proposals", "generation_notes", "reflection_notes", "ranking_notes",
        "evolution_notes", "meta_review_notes", "synthesizer_notes",
        "graph_designer_notes", "proximity_notes", "analyses", "orchestrator_orders"
    ]:
        if key in snapshot_values:
            getattr(base_state, key).extend(snapshot_values[key])

    # 2) Overwrite certain keys
    overwrite_keys = [
        "cahier_des_charges", "design_plan", "supervisor_decision",
        "supervisor_status", "redo_reason", "active_agent", "next_agent",
        "ranking_justification", "evolution_justification", "selected_proposal_index"
    ]
    for key in overwrite_keys:
        if key in snapshot_values:
            setattr(base_state, key, snapshot_values[key])

    # 3) Update numeric and boolean fields
    for key in [
        "current_step_index", "current_tasks_count", "redo_work", "task_complete",
        "generation_iteration", "reflection_iteration", "ranking_iteration",
        "evolution_iteration", "meta_review_iteration", "synthesizer_iteration",
        "graph_designer_iteration", "max_iterations"
    ]:
        if key in snapshot_values:
            setattr(base_state, key, snapshot_values[key])

    # 4) Save the design_graph in design_graph_history
    if "design_graph_history" in snapshot_values:
        base_state.design_graph_history.append(snapshot_values["design_graph_history"])

from langgraph.types import StateSnapshot

def aggregate_all_snapshots(snapshot_list: List[StateSnapshot]) -> State:
    aggregated = State()  # start empty
    for snap in snapshot_list:
        merge_snapshot_into_state(aggregated, snap.values)
    return aggregated

import networkx as nx
from typing import List, Dict, Any

def evaluate_all_metrics_over_history(
    design_graph_history: List[DesignState]
) -> List[Dict[str, Any]]:
    """
    Computes the full set of metrics for each iteration in the design_graph_history.
    Returns a list of dicts, each dict containing the metrics for that iteration.
    """

    results = []

    # We'll track node_id sets and edge sets across iterations to compute
    # growth rates, convergence, redundancy, etc.
    prev_node_ids = set()
    prev_edge_set = set()

    for i, ds in enumerate(design_graph_history):
        print("design_graph_history",design_graph_history)
        # Convert to a NetworkX DiGraph
        G = nx.DiGraph()
        for node_id, node_obj in ds.nodes.items():
            G.add_node(node_id, node_type=node_obj.node_type)
            for ch in node_obj.children:
                G.add_edge(node_id, ch)

        node_count = G.number_of_nodes()
        edge_count = G.number_of_edges()

        # 1) Node Coverage per Category
        node_type_counts = {}
        for n_id, data in G.nodes(data=True):
            ntype = data.get('node_type', 'unknown').lower()
            node_type_counts[ntype] = node_type_counts.get(ntype, 0) + 1

        # 2) Subsystem Coverage (%)
        #    subfunctions with subsystem child / total subfunctions
        subfunctions = []
        for n_id, data in G.nodes(data=True):
            if data['node_type'].lower() == 'subfunction':
                subfunctions.append(n_id)
        if len(subfunctions) > 0:
            subf_with_subsys = 0
            for sf in subfunctions:
                child_ids = ds.nodes[sf].children
                # Check if any child is "subsystem"
                has_subsys = any(
                    ds.nodes[ch].node_type.lower() == "subsystem"
                    for ch in child_ids if ch in ds.nodes
                )
                if has_subsys:
                    subf_with_subsys += 1
            subsystem_coverage = subf_with_subsys / len(subfunctions)
        else:
            subsystem_coverage = 0.0

        # 3) Numerical Model Attachment Rate
        #    (subsystems with at least one numerical_model child) / total subsystems
        subsystems = []
        for n_id, data in G.nodes(data=True):
            if data['node_type'].lower() == 'subsystem':
                subsystems.append(n_id)
        if len(subsystems) > 0:
            subs_with_model = 0
            for sid in subsystems:
                child_ids = ds.nodes[sid].children
                # if any child is "numerical_model"
                has_model = any(
                    ds.nodes[ch].node_type.lower() == "numerical_model"
                    for ch in child_ids if ch in ds.nodes
                )
                if has_model:
                    subs_with_model += 1
            numerical_model_rate = subs_with_model / len(subsystems)
        else:
            numerical_model_rate = 0.0

        # 4) Functional Decomposition Depth
        #    max distance from any root node
        # if no root_node_ids, define them as nodes with no parents
        if ds.root_node_ids:
            roots = ds.root_node_ids
        else:
            # fallback
            roots = []
            for nid, nobj in ds.nodes.items():
                if len(nobj.parents) == 0:
                    roots.append(nid)

        max_depth = 0
        def dfs_depth(node_id, depth):
            nonlocal max_depth
            max_depth = max(max_depth, depth)
            for ch in ds.nodes[node_id].children:
                dfs_depth(ch, depth + 1)
        for r in roots:
            dfs_depth(r, 1)

        # 5) Orphan Nodes Count
        orphan_count = 0
        for nid, nobj in ds.nodes.items():
            if len(nobj.parents) == 0 and len(nobj.children) == 0:
                orphan_count += 1

        # 6) Node Growth Rate, Edge Growth Rate
        #    (node_count - prev_node_count)/prev_node_count, etc.
        if i == 0:
            node_growth_rate = 0.0
            edge_growth_rate = 0.0
        else:
            prev_nc = len(design_graph_history[i-1].nodes)
            prev_ec = 0
            for pid, pnode in design_graph_history[i-1].nodes.items():
                for c in pnode.children:
                    prev_ec += 1
            if prev_nc > 0:
                node_growth_rate = (node_count - prev_nc) / prev_nc
            else:
                node_growth_rate = 0.0
            if prev_ec > 0:
                edge_growth_rate = (edge_count - prev_ec) / prev_ec
            else:
                edge_growth_rate = 0.0

        # 7) Convergence Score => Jaccard of node sets, edge sets
        current_node_ids = set(ds.nodes.keys())
        current_edge_set = set()
        for nid, nobj in ds.nodes.items():
            for ch in nobj.children:
                current_edge_set.add((nid, ch))

        if i == 0:
            node_jaccard = 1.0
            edge_jaccard = 1.0
        else:
            inter_nodes = len(current_node_ids.intersection(prev_node_ids))
            union_nodes = len(current_node_ids.union(prev_node_ids))
            node_jaccard = inter_nodes / union_nodes if union_nodes > 0 else 1.0

            inter_edges = len(current_edge_set.intersection(prev_edge_set))
            union_edges = len(current_edge_set.union(prev_edge_set))
            edge_jaccard = inter_edges / union_edges if union_edges > 0 else 1.0

        convergence_score = (node_jaccard + edge_jaccard) / 2.0

        # 8) Redundancy Rate => # of duplicate nodes / node_count
        #    We'll define "duplicates" if same node_type & same 'payload.name' 
        #    (requires domain logic). We'll do a naive approach:
        name_map = {}
        for nid, nobj in ds.nodes.items():
            node_name = nobj.payload.get('name', '???')
            key = (nobj.node_type.lower(), node_name)
            name_map.setdefault(key, []).append(nid)
        duplicates_count = sum(len(lst) - 1 for lst in name_map.values() if len(lst) > 1)
        redundancy_rate = (duplicates_count / node_count) if node_count > 0 else 0.0

        # 9) Iteration Refinement Efficiency => 
        #    ratio of "updated nodes" vs. (updated + new). We'll do a naive approach
        if i == 0:
            iteration_ref_eff = 0.0
        else:
            new_nodes = current_node_ids - prev_node_ids
            old_nodes = current_node_ids.intersection(prev_node_ids)
            denom = len(new_nodes) + len(old_nodes)
            iteration_ref_eff = (len(old_nodes) / denom) if denom > 0 else 0.0

        # 10) Loop Detection => DAG check
        is_dag = nx.is_directed_acyclic_graph(G)
        loop_detection = 0 if is_dag else 1

        # 11) Subsystem Reuse Rate => 
        #     average # of subfunctions that share the same subsystem
        subs_reuse_list = []
        for sid in ds.nodes:
            if ds.nodes[sid].node_type.lower() == "subsystem":
                # how many parent subfunctions?
                par_subf_count = 0
                for par_id in ds.nodes[sid].parents:
                    if ds.nodes[par_id].node_type.lower() == "subfunction":
                        par_subf_count += 1
                if par_subf_count > 0:
                    subs_reuse_list.append(par_subf_count)
        if len(subs_reuse_list) > 0:
            subsystem_reuse_rate = sum(subs_reuse_list)/len(subs_reuse_list)
        else:
            subsystem_reuse_rate = 0.0

        # 12) Graph Structural Complexity Score => edges/nodes
        if node_count <= 1:
            graph_complexity_score = 0.0
        else:
            graph_complexity_score = edge_count / node_count

        # The last three are AI Agent Contribution metrics:
        # 13) Proposal Integration Rate => 
        #    If you want to track proposals at iteration i, you can store them in parallel, or skip.
        #    We'll define 0.0 for now:
        proposal_integration_rate = 0.0

        # 14) Correction Rate per Agent => 
        correction_rate_per_agent = 0.0

        # 15) Supervisor Override Rate =>
        supervisor_override_rate = 0.0

        # Collect iteration i metrics
        iteration_metrics = {
            "iteration_index": i,
            "node_coverage_per_category": node_type_counts,  # a dict
            "subsystem_coverage": subsystem_coverage,
            "numerical_model_attachment_rate": numerical_model_rate,
            "functional_decomposition_depth": max_depth,
            "orphan_nodes_count": orphan_count,
            "node_growth_rate": node_growth_rate,
            "edge_growth_rate": edge_growth_rate,
            "convergence_score": convergence_score,
            "redundancy_rate": redundancy_rate,
            "iteration_refinement_efficiency": iteration_ref_eff,
            "loop_detection": loop_detection,
            "subsystem_reuse_rate": subsystem_reuse_rate,
            "graph_structural_complexity_score": graph_complexity_score,
            "proposal_integration_rate": proposal_integration_rate,
            "correction_rate_per_agent": correction_rate_per_agent,
            "supervisor_override_rate": supervisor_override_rate
        }

        results.append(iteration_metrics)

        # update "prev" sets
        prev_node_ids = current_node_ids
        prev_edge_set = current_edge_set

    return results

def run_advanced_evaluation_all_scalars(state_obj: State):
    """
    Aggregates all design_graph snapshots from state_obj.design_graph_history,
    computes the metrics for each iteration, and prints them out.
    """
    # The design_graph_history was appended in the merge function
    history = state_obj.design_graph_history
    if not history:
        print("No design graph snapshots found. Nothing to evaluate.")
        return

    # Evaluate
    results = evaluate_all_metrics_over_history(history)

    # Print or store
    for r in results:
        print(f"\nIteration {r['iteration_index']} metrics:")
        for k, v in r.items():
            if k != 'iteration_index':
                print(f"  {k}: {v}")

def run_advanced_evaluation(state_obj: State) -> List[Dict[str, Any]]:
    history = state_obj.design_graph_history
    if not history:
        print("No design graph snapshots found. Nothing to evaluate.")
        return []
    results = evaluate_all_metrics_over_history(history)
    return results

"""
all_snapshots = list(app.get_state_history(config))
final_aggregated_state = aggregate_all_snapshots(all_snapshots)

# Now run the evaluation
run_advanced_evaluation(final_aggregated_state)
"""

import matplotlib.pyplot as plt
import pandas as pd

def plot_metric_over_iterations(df: pd.DataFrame, metric_key: str, ylabel: str, title: str, save_path: str = None):
    """
    Plots a single metric over iterations.
    
    Args:
        df: DataFrame containing metric results with an 'iteration_index' column.
        metric_key: Column name for the metric to plot.
        ylabel: Label for the y-axis.
        title: Title of the plot.
        save_path: Optional file path to save the plot as a PDF.
    """
    plt.figure(figsize=(3.5, 2.5))
    plt.plot(df['iteration_index'], df[metric_key], marker='o', linestyle='-', color='b')
    plt.xlabel("Iteration", fontsize=8)
    plt.ylabel(ylabel, fontsize=8)
    #plt.title(title, fontsize=10)
    plt.xticks(fontsize=6)
    plt.yticks(fontsize=6)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"Saved {title} to {save_path}")
    else:
        plt.show()


def plot_all_metrics(df: pd.DataFrame):
    """
    Generates and saves plots for key metrics.
    Adjust or remove metrics as needed.
    """
    # Node Growth Rate (expected to increase initially and then stabilize)
    plot_metric_over_iterations(
        df, 
        metric_key="node_growth_rate", 
        ylabel="Node Growth Rate", 
        title="Node Growth Rate", 
        save_path="node_growth_rate.pdf"
    )
    
    # Edge Growth Rate (expected to increase)
    plot_metric_over_iterations(
        df, 
        metric_key="edge_growth_rate", 
        ylabel="Edge Growth Rate", 
        title="Edge Growth Rate", 
        save_path="edge_growth_rate.pdf"
    )
    
    # Convergence Score (Jaccard similarity; expected to increase as design stabilizes)
    plot_metric_over_iterations(
        df, 
        metric_key="convergence_score", 
        ylabel="Convergence Score", 
        title="Convergence Score", 
        save_path="convergence_score.pdf"
    )
    
    # Redundancy Rate (expected to decrease)
    plot_metric_over_iterations(
        df, 
        metric_key="redundancy_rate", 
        ylabel="Redundancy Rate", 
        title="Redundancy Rate", 
        save_path="redundancy_rate.pdf"
    )
    
    # Graph Structural Complexity (Edges/Nodes; controlled increase)
    plot_metric_over_iterations(
        df, 
        metric_key="graph_structural_complexity_score", 
        ylabel="Complexity Score", 
        title="Graph Structural Complexity", 
        save_path="graph_complexity.pdf"
    )
    
    # Subsystem Coverage (%)
    plot_metric_over_iterations(
        df, 
        metric_key="subsystem_coverage", 
        ylabel="Subsystem Coverage (%)", 
        title="Subsystem Coverage", 
        save_path="subsystem_coverage.pdf"
    )
    
    # Numerical Model Attachment Rate (%)
    plot_metric_over_iterations(
        df, 
        metric_key="numerical_model_attachment_rate", 
        ylabel="Model Attachment Rate (%)", 
        title="Numerical Model Attachment Rate", 
        save_path="numerical_model_attachment_rate.pdf"
    )
    
    # Functional Decomposition Depth
    plot_metric_over_iterations(
        df, 
        metric_key="functional_decomposition_depth", 
        ylabel="Max Depth", 
        title="Functional Decomposition Depth", 
        save_path="functional_decomposition_depth.pdf"
    )
    
    # Orphan Nodes Count (expected to decrease)
    plot_metric_over_iterations(
        df, 
        metric_key="orphan_nodes_count", 
        ylabel="Orphan Nodes", 
        title="Orphan Nodes Count", 
        save_path="orphan_nodes_count.pdf"
    )
    
    # Loop Detection: we could plot a binary indicator (0 for acyclic, 1 for cycle detected)
    plot_metric_over_iterations(
        df, 
        metric_key="loop_detection", 
        ylabel="Loop Detection", 
        title="Loop Detection", 
        save_path="loop_detection.pdf"
    )
    
    # Subsystem Reuse Rate (expected to increase)
    plot_metric_over_iterations(
        df, 
        metric_key="subsystem_reuse_rate", 
        ylabel="Subsystem Reuse Rate", 
        title="Subsystem Reuse Rate", 
        save_path="subsystem_reuse_rate.pdf"
    )

"""
# After aggregating the state snapshots and computing the metrics:
metrics_results = evaluate_all_metrics_over_history(final_aggregated_state.design_graph_history)
df_metrics = pd.DataFrame(metrics_results)
# In case some metrics are dictionaries, you might need to flatten them or extract summary values.
# For example, for orphan_nodes_count, convert list length:
if "orphan_nodes_count" not in df_metrics.columns and "orphan_nodes" in df_metrics.columns:
    df_metrics["orphan_nodes_count"] = df_metrics["orphan_nodes"].apply(len)

# Now, generate the plots:
plot_all_metrics(df_metrics)
"""