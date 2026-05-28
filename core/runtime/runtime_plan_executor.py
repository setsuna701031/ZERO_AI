from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.governed_engineering_batch import attach_governed_engineering_transaction_batch
from core.runtime.runtime_plan_graph import build_runtime_mutation_plan_graph, serialize_plan_graph, topological_node_order
from core.runtime.runtime_plan_models import RuntimePlanNode
from core.runtime.runtime_plan_verifier import collect_verification_edges, verify_plan_graph_shape, write_plan_graph_journal


def execute_runtime_mutation_plan_graph(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    targets: Any = None,
    force_verification_failure: bool = False,
) -> Dict[str, Any]:
    graph = build_runtime_mutation_plan_graph(
        repo_root=repo_root,
        task_id=task_id,
        goal=goal,
        targets=targets,
        force_verification_failure=force_verification_failure,
    )
    graph_payload = serialize_plan_graph(graph)
    shape_verification = verify_plan_graph_shape(graph_payload)
    verification_edges = collect_verification_edges(graph_payload)
    ordered_nodes = topological_node_order(graph)

    plan_dir = repo_root / "workspace" / "runtime_plan_graphs" / graph.plan_id
    plan_journal_path = plan_dir / "runtime_plan_graph_journal.json"

    execution_records: List[Dict[str, Any]] = []
    batch_result: Dict[str, Any] = {}

    for node in ordered_nodes:
        node_record: Dict[str, Any] = {
            "node_id": node.node_id,
            "node_type": node.node_type,
            "description": node.description,
            "targets": node.targets,
            "started_at": time.time(),
            "finished_at": None,
            "status": "skipped",
            "ok": True,
        }

        if node.node_type == "stage":
            node_record["status"] = "completed"
            node_record["verification"] = {
                "ok": True,
                "checks": list(node.verification),
            }
        elif node.node_type == "mutation_batch":
            intermediate_result: Dict[str, Any] = {}
            intermediate_result = attach_governed_engineering_transaction_batch(
                repo_root=repo_root,
                task=task,
                result=intermediate_result,
                task_id=task_id,
                goal=goal,
                targets=node.targets,
                force_verification_failure=node.force_verification_failure,
            )
            batch_result = intermediate_result.get("governed_engineering_transaction_batch", {})
            node_record["status"] = str(batch_result.get("status") or "unknown")
            node_record["ok"] = bool(batch_result.get("ok"))
            node_record["batch_id"] = batch_result.get("batch_id")
            node_record["journal_path"] = batch_result.get("journal_path")
            node_record["rollback_applied"] = bool((batch_result.get("rollback") or {}).get("rollback_applied"))
            node_record["transaction"] = batch_result
        elif node.node_type == "rollback":
            rollback = batch_result.get("rollback") if isinstance(batch_result, dict) else {}
            node_record["status"] = "available"
            node_record["ok"] = bool(rollback.get("rollback_available", True)) if isinstance(rollback, dict) else True
            node_record["rollback"] = rollback
        else:
            node_record["status"] = "unknown"
            node_record["ok"] = False

        node_record["finished_at"] = time.time()
        execution_records.append(node_record)

        if node.node_type == "mutation_batch" and not bool(node_record.get("ok")):
            # Continue to rollback node because rollback is the explicit failure edge.
            continue

    plan_ok = bool(shape_verification.get("ok")) and bool(batch_result.get("ok"))
    rollback_applied = bool((batch_result.get("rollback") or {}).get("rollback_applied")) if isinstance(batch_result, dict) else False

    plan_record = {
        "ok": plan_ok,
        "schema": "zero.aer.runtime_mutation_plan_graph_execution.v1",
        "plan_id": graph.plan_id,
        "task_id": task_id,
        "goal": goal,
        "status": "committed" if plan_ok else "rolled_back",
        "created_at": graph.created_at,
        "finished_at": time.time(),
        "graph": graph_payload,
        "shape_verification": shape_verification,
        "verification_edges": verification_edges,
        "execution_order": [node.node_id for node in ordered_nodes],
        "execution_records": execution_records,
        "batch_result": batch_result,
        "rollback_applied": rollback_applied,
        "journal_path": str(plan_journal_path),
        "plan_dir": str(plan_dir),
        "execution_authority_endpoint": "step_executor",
        "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
        "boundary": {
            "planner_outputs_plan_graph": True,
            "dependency_ordering_enforced": True,
            "verification_edges_recorded": True,
            "batch_execution_uses_governed_engineering_transaction": True,
            "rollback_strategy_recorded": True,
            "cli_is_not_execution_owner": True,
            "thin_bridge_is_compatibility_layer": True,
            "no_hidden_mutation_shortcut": True,
        },
    }

    write_plan_graph_journal(plan_journal_path, plan_record)

    result["runtime_mutation_plan_graph"] = plan_record
    result["runtime_mutation_plan_graph_schema"] = plan_record["schema"]
    result["runtime_mutation_plan_graph_id"] = plan_record["plan_id"]
    result["runtime_mutation_plan_graph_status"] = plan_record["status"]
    result["runtime_mutation_plan_graph_ok"] = plan_record["ok"]
    result["runtime_mutation_plan_graph_journal_path"] = plan_record["journal_path"]
    result["runtime_mutation_plan_graph_rollback_applied"] = rollback_applied

    task["runtime_mutation_plan_graph"] = plan_record
    task["runtime_mutation_plan_graph_schema"] = plan_record["schema"]
    task["runtime_mutation_plan_graph_id"] = plan_record["plan_id"]
    task["runtime_mutation_plan_graph_status"] = plan_record["status"]
    task["runtime_mutation_plan_graph_ok"] = plan_record["ok"]
    task["runtime_mutation_plan_graph_journal_path"] = plan_record["journal_path"]
    task["runtime_mutation_plan_graph_rollback_applied"] = rollback_applied

    return result
