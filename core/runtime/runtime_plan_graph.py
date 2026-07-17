from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.runtime_plan_models import RuntimePlanEdge, RuntimePlanGraph, RuntimePlanNode


def _plan_id(task_id: str) -> str:
    seed = f"{task_id}:{time.time()}".encode("utf-8", errors="replace")
    return "runtime_plan_" + hashlib.sha1(seed).hexdigest()[:16]


def _normalize_targets(targets: Any) -> List[str]:
    if isinstance(targets, list):
        return [str(item).strip() for item in targets if str(item).strip()]
    if isinstance(targets, str):
        return [item.strip() for item in targets.split(",") if item.strip()]
    return []


def _ensure_default_targets(repo_root: Path) -> List[str]:
    shared = repo_root / "workspace" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    targets = [
        shared / "runtime_plan_target_a.py",
        shared / "runtime_plan_target_b.py",
    ]
    for index, target in enumerate(targets, start=1):
        if not target.exists():
            target.write_text(f'print("runtime plan target {index}")\n', encoding="utf-8")
    return [
        "workspace/shared/runtime_plan_target_a.py",
        "workspace/shared/runtime_plan_target_b.py",
    ]


def build_runtime_mutation_plan_graph(
    *,
    repo_root: Path,
    task_id: str,
    goal: str,
    targets: Any = None,
    force_verification_failure: bool = False,
) -> RuntimePlanGraph:
    normalized_targets = _normalize_targets(targets)
    if not normalized_targets:
        normalized_targets = _ensure_default_targets(repo_root)

    plan_id = _plan_id(task_id)
    stage_node = RuntimePlanNode(
        node_id="stage_targets",
        node_type="stage",
        targets=normalized_targets,
        description="Stage target files and enforce allowed roots before mutation.",
        verification=["allowed_roots", "target_snapshot"],
    )
    mutation_node = RuntimePlanNode(
        node_id="execute_mutation_batch",
        node_type="mutation_batch",
        targets=normalized_targets,
        description="Execute governed engineering mutation batch through StepExecutor authority.",
        depends_on=["stage_targets"],
        verification=["py_compile_or_exists", "batch_verification"],
        force_verification_failure=force_verification_failure,
    )
    rollback_node = RuntimePlanNode(
        node_id="rollback_strategy",
        node_type="rollback",
        targets=normalized_targets,
        description="Rollback all touched files if any write or verification edge fails.",
        depends_on=["execute_mutation_batch"],
        verification=["rollback_available", "rollback_journal"],
    )

    return RuntimePlanGraph(
        plan_id=plan_id,
        task_id=task_id,
        goal=goal,
        nodes=[stage_node, mutation_node, rollback_node],
        edges=[
            RuntimePlanEdge(from_node="stage_targets", to_node="execute_mutation_batch"),
            RuntimePlanEdge(from_node="execute_mutation_batch", to_node="rollback_strategy", edge_type="failure_edge"),
        ],
        created_at=time.time(),
    )


def topological_node_order(graph: RuntimePlanGraph) -> List[RuntimePlanNode]:
    nodes = {node.node_id: node for node in graph.nodes}
    ordered: List[RuntimePlanNode] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise ValueError(f"cycle detected at {node_id}")
        visiting.add(node_id)
        node = nodes[node_id]
        for dep in node.depends_on:
            if dep in nodes:
                visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)
        ordered.append(node)

    for node in graph.nodes:
        visit(node.node_id)

    return ordered


def serialize_plan_graph(graph: RuntimePlanGraph) -> Dict[str, Any]:
    return graph.to_dict()
