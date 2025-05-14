# graph_designer.py  ─────────────────────────────────────────────────────────
import uuid
from typing import Literal, List

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command

from data_models  import (
    State, DesignState,
    NodeOp, EdgeOp,
    DesignNode,
)
from graph_utils  import (
    add_node_func,
    delete_node_func,
    update_node_func,
    add_edges_to_state,         # already defined in graph_utils
    visualize_design_state_func,
    summarize_design_state_func,
)
from utils        import remove_think_tags
from llm_models   import base_model_reasoning


# ────────────────────────────────────────────────────────────────────────────
def graph_designer_node(state: State) -> Command[Literal["supervisor"]]:
    """
    Applies NodeOp / EdgeOp lists produced by the Synthesizer.
    After updating the in-memory DesignGraph it:
      • runs a quick LLM “sanity check”,
      • appends the snapshot to design_graph_history,
      • hands control back to the supervisor.
    """

    print("\n📐 [DEBUG] Graph-Designer node invoked.")

    # 0. Sanity-check that we actually have something to do
    if not state.pending_node_ops and not state.pending_edge_ops:
        print("⚠️  [DEBUG] No pending NodeOps / EdgeOps – nothing to apply.")
        return Command(
            update={"graph_designer_notes": ["No graph modifications supplied."]},
            goto="supervisor",
        )

    # Pick last batches pushed by Synthesizer
    node_ops: List[NodeOp] = state.pending_node_ops[-1] if state.pending_node_ops else []
    edge_ops: List[EdgeOp] = state.pending_edge_ops[-1] if state.pending_edge_ops else []

    # Work on a *mutable* copy of the latest DesignGraph snapshot
    graph = state.design_graph_history[-1] if state.design_graph_history else DesignState()

    # ───────────────────────────────────────────────────────────── NodeOps
    node_results: List[str] = []
    for op in node_ops:
        try:
            if op.op == "add":
                res = add_node_func(graph, op)               # new helper works on NodeOp
            elif op.op == "delete":
                res = delete_node_func(graph, op.node_id)
            elif op.op == "update":
                res = update_node_func(graph, op)
            else:
                res = f"❌ Unknown NodeOp '{op.op}'."
            node_results.append(res)
            print(f"✅ [DEBUG] {res}")
        except Exception as exc:
            err = f"❌ NodeOp error ({op.op}): {exc}"
            node_results.append(err)
            print(err)

    # ───────────────────────────────────────────────────────────── EdgeOps
    edge_results: List[str] = []
    for eop in edge_ops:
        try:
            if eop.op == "add":
                if eop.src in graph.nodes and eop.dst in graph.nodes:
                    add_edges_to_state(graph, [(eop.src, eop.dst)])
                    graph.edges.append((eop.src, eop.dst))
                    res = f"✅ Edge added {eop.src} → {eop.dst}"
                else:
                    res = f"❌ Edge add failed – unknown node(s) {eop.src}/{eop.dst}"
            elif eop.op == "delete":
                if (eop.src, eop.dst) in graph.edges:
                    graph.edges.remove((eop.src, eop.dst))
                    # also scrub in/out lists
                    graph.nodes[eop.src].edges_out.remove(eop.dst)
                    graph.nodes[eop.dst].edges_in.remove(eop.src)
                    res = f"✅ Edge removed {eop.src} → {eop.dst}"
                else:
                    res = f"⚠️  Edge {eop.src} → {eop.dst} not present."
            else:
                res = f"❌ Unknown EdgeOp '{eop.op}'."
            edge_results.append(res)
            print(f"✅ [DEBUG] {res}")
        except Exception as exc:
            err = f"❌ EdgeOp error ({eop.op} {eop.src}->{eop.dst}): {exc}"
            edge_results.append(err)
            print(err)

    # ───────────────────────────────────────────────────────────── Validation (LLM quick-check)
    validation_prompt = f"""
### Design-Graph validation request

• NodeOp results
{node_results}

• EdgeOp results
{edge_results}

• Current graph summary
{summarize_design_state_func(graph)}

Please return JSON with keys:
  {{ "ok": true/false, "issues": [ ... ] }}
"""
    val_msg = base_model_reasoning.invoke(
        [
            SystemMessage(content="You are an expert systems-engineering auditor."),
            HumanMessage(content=validation_prompt),
        ]
    ).content

    print("🔍 [DEBUG] Graph validation response:")
    print(remove_think_tags(val_msg))

    # ───────────────────────────────────────────────────────────── Visualisation (optional)
    visualize_design_state_func(graph)

    # ───────────────────────────────────────────────────────────── Persist + hand back
    return Command(
        update={
            "graph_designer_notes": [val_msg],
            "design_graph_history": [graph],   # snapshot appended
        },
        goto="supervisor",
    )
