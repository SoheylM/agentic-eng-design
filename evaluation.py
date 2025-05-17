########### DEPRECATED ###########
# evaluation.py
import networkx as nx
from typing import List, Dict, Any
from langgraph.types import StateSnapshot

from data_models import State, DesignState


def merge_snapshot_into_state(base_state: State, snapshot_values: dict) -> None:
    """
    Incorporate one LangGraph StateSnapshot.values dict into base_state in-place.
    Lists are extended, simple fields are overwritten or updated.
    """
    # 1) list fields: append
    list_fields = [
        "messages", "supervisor_instructions", "supervisor_current_objectives",
        "proposals", "generation_notes", "reflection_notes", "ranking_notes",
        "evolution_notes", "meta_review_notes", "synthesizer_notes",
        "graph_designer_notes", "proximity_notes", "analyses", "orchestrator_orders"
    ]
    for key in list_fields:
        if key in snapshot_values:
            getattr(base_state, key).extend(snapshot_values[key])

    # 2) overwrite fields
    overwrite_fields = [
        "cahier_des_charges", "design_plan", "supervisor_decision",
        "supervisor_status", "redo_reason", "active_agent", "next_agent",
        "ranking_justification", "evolution_justification", "selected_proposal_index"
    ]
    for key in overwrite_fields:
        if key in snapshot_values:
            setattr(base_state, key, snapshot_values[key])

    # 3) numeric / bool fields: update
    update_fields = [
        "current_step_index", "current_tasks_count", "redo_work", "task_complete",
        "generation_iteration", "reflection_iteration", "ranking_iteration",
        "evolution_iteration", "meta_review_iteration", "synthesizer_iteration",
        "graph_designer_iteration", "max_iterations"
    ]
    for key in update_fields:
        if key in snapshot_values:
            setattr(base_state, key, snapshot_values[key])

    # 4) record design_graph snapshot
    if "design_graph_history" in snapshot_values:
        base_state.design_graph_history.append(snapshot_values["design_graph_history"])


def aggregate_all_snapshots(snapshots: List[StateSnapshot]) -> State:
    """
    Start from an empty State, merge in every snapshot.value, 
    and return the aggregated State.
    """
    agg = State()
    for snap in snapshots:
        merge_snapshot_into_state(agg, snap.values)
    return agg


def evaluate_all_metrics_over_history(
    history: List[DesignState]
) -> List[Dict[str, Any]]:
    """
    For each DesignState in history, build a DiGraph and compute:
      - node counts, edge counts
      - coverage rates, depth, growth, convergence, redundancy, etc.
    Returns a list of per-iteration metric dicts.
    """
    results: List[Dict[str, Any]] = []
    prev_nodes, prev_edges = set(), set()

    for idx, ds in enumerate(history):
        # build DiGraph
        G = nx.DiGraph()
        for nid, node in ds.nodes.items():
            G.add_node(nid, node_type=node.node_type)
            for child in node.children:
                G.add_edge(nid, child)

        node_count = G.number_of_nodes()
        edge_count = G.number_of_edges()

        # 1) node coverage per type
        coverage: Dict[str, int] = {}
        for _, data in G.nodes(data=True):
            t = data["node_type"].lower()
            coverage[t] = coverage.get(t, 0) + 1

        # 2) subsystem coverage
        subf_ids = [n for n,d in G.nodes(data=True) if d["node_type"].lower()=="subfunction"]
        if subf_ids:
            covered = sum(
                any(ds.nodes[ch].node_type.lower()=="subsystem" for ch in ds.nodes[sf].children)
                for sf in subf_ids
            )
            subsystem_coverage = covered / len(subf_ids)
        else:
            subsystem_coverage = 0.0

        # 3) numerical-model attachment rate
        subsys_ids = [n for n,d in G.nodes(data=True) if d["node_type"].lower()=="subsystem"]
        if subsys_ids:
            nm_attached = sum(
                any(ds.nodes[ch].node_type.lower()=="numerical_model" for ch in ds.nodes[sid].children)
                for sid in subsys_ids
            )
            numerical_model_rate = nm_attached / len(subsys_ids)
        else:
            numerical_model_rate = 0.0

        # 4) max depth
        roots = getattr(ds, "root_node_ids", None) or [
            n for n,node in ds.nodes.items() if not node.parents
        ]
        max_depth = 0
        def dfs(u: str, depth: int):
            nonlocal max_depth
            max_depth = max(max_depth, depth)
            for v in ds.nodes[u].children:
                dfs(v, depth+1)
        for r in roots:
            dfs(r, 1)

        # 5) orphan nodes
        orphan_count = sum(
            1 for n,node in ds.nodes.items()
            if not node.parents and not node.children
        )

        # 6) growth rates
        if idx == 0:
            node_growth = edge_growth = 0.0
        else:
            prev_nc, prev_ec = len(prev_nodes), len(prev_edges)
            node_growth = (node_count - prev_nc)/prev_nc if prev_nc else 0.0
            edge_growth = (edge_count - prev_ec)/prev_ec if prev_ec else 0.0

        # 7) convergence (Jaccard)
        cur_nodes = set(ds.nodes.keys())
        cur_edges = {(u,v) for u,node in ds.nodes.items() for v in node.children}
        if idx == 0:
            node_jacc, edge_jacc = 1.0, 1.0
        else:
            node_jacc = len(cur_nodes&prev_nodes)/len(cur_nodes|prev_nodes) if (cur_nodes|prev_nodes) else 1.0
            edge_jacc = len(cur_edges&prev_edges)/len(cur_edges|prev_edges) if (cur_edges|prev_edges) else 1.0
        convergence = (node_jacc + edge_jacc)/2

        # 8) redundancy
        name_map: Dict[Any,List[str]] = {}
        for nid,node in ds.nodes.items():
            key = (node.node_type.lower(), node.payload.get("name",""))
            name_map.setdefault(key,[]).append(nid)
        dup_count = sum(len(lst)-1 for lst in name_map.values() if len(lst)>1)
        redundancy = dup_count/node_count if node_count else 0.0

        # 9) iteration refinement efficiency
        if idx==0:
            it_ref_eff = 0.0
        else:
            new_n = cur_nodes - prev_nodes
            old_n = cur_nodes & prev_nodes
            denom = len(new_n) + len(old_n)
            it_ref_eff = len(old_n)/denom if denom else 0.0

        # 10) loop detection
        loop_flag = 0 if nx.is_directed_acyclic_graph(G) else 1

        # 11) subsystem reuse
        reuse = []
        for sid,node in ds.nodes.items():
            if node.node_type.lower()=="subsystem":
                par_sf = sum(
                    1 for pid in node.parents
                    if ds.nodes[pid].node_type.lower()=="subfunction"
                )
                if par_sf>0:
                    reuse.append(par_sf)
        subsys_reuse = sum(reuse)/len(reuse) if reuse else 0.0

        # 12) complexity = edges/nodes
        complexity = edge_count/node_count if node_count>1 else 0.0

        # assemble
        metrics = {
            "iteration_index": idx,
            "node_coverage_per_type": coverage,
            "subsystem_coverage": subsystem_coverage,
            "numerical_model_attachment_rate": numerical_model_rate,
            "functional_decomposition_depth": max_depth,
            "orphan_nodes_count": orphan_count,
            "node_growth_rate": node_growth,
            "edge_growth_rate": edge_growth,
            "convergence_score": convergence,
            "redundancy_rate": redundancy,
            "iteration_refinement_efficiency": it_ref_eff,
            "loop_detection": loop_flag,
            "subsystem_reuse_rate": subsys_reuse,
            "graph_structural_complexity_score": complexity
        }

        results.append(metrics)
        prev_nodes, prev_edges = cur_nodes, cur_edges

    return results


def collect_metrics(
    state_obj: State,
    workflow: str,
    run: int
) -> Dict[str, Any]:
    """
    Entry point for your CLI runner:
      - aggregate all snapshots
      - evaluate iteration metrics
      - return a flat summary (final iteration) & full history
    """
    # 1) rebuild full state from snapshots
    snapshots = list(state_obj._history)  # or however you fetch StateSnapshot list
    agg_state = aggregate_all_snapshots(snapshots)

    # 2) get history of design graphs
    history = agg_state.design_graph_history
    iter_metrics = evaluate_all_metrics_over_history(history)

    summary: Dict[str, Any] = {
        "workflow": workflow,
        "run": run,
        "iterations": len(iter_metrics)
    }

    if iter_metrics:
        last = iter_metrics[-1]
        # flatten a few key scalars
        summary.update({
            "final_subsystem_coverage":       last["subsystem_coverage"],
            "final_numerical_model_rate":     last["numerical_model_attachment_rate"],
            "final_depth":                    last["functional_decomposition_depth"],
            "final_convergence":              last["convergence_score"],
            "final_redundancy":               last["redundancy_rate"],
            "final_iteration_efficiency":     last["iteration_refinement_efficiency"],
            "final_complexity":               last["graph_structural_complexity_score"]
        })
    else:
        # no history → defaults
        summary.update({
            "final_subsystem_coverage": 0.0,
            "final_numerical_model_rate": 0.0,
            "final_depth": 0,
            "final_convergence": 0.0,
            "final_redundancy": 0.0,
            "final_iteration_efficiency": 0.0,
            "final_complexity": 0.0
        })

    # embed full history if desired
    summary["metrics_history"] = iter_metrics
    return summary
