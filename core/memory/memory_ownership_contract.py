from __future__ import annotations

import ast
import copy
from pathlib import Path
from typing import Any


MEMORY_OWNERSHIP_SCHEMA = "zero.memory.ownership_contract.v1"
FORBIDDEN_CONTROL_IMPORTS = (
    "core.runtime.runtime_dispatcher",
    "core.runtime.task_runner",
    "core.runtime.work_package_queue",
    "core.tasks.scheduler",
    "core.runtime.step_executor",
)
FORBIDDEN_CONTROL_CALLS = frozenset(
    {"claim", "claim_next", "complete", "dispatch", "dispatch_next", "execute_step", "execute_steps"}
)

MEMORY_MODULES = (
    {
        "name": "task_memory",
        "modules": [
            "core.memory.memory_contract",
            "core.memory.memory_repository",
            "core.memory.memory_query",
            "core.memory.task_memory",
            "core.memory.decision_memory",
            "core.memory.issue_memory",
            "core.memory.engineering_memory",
            "core.memory.memory_engine",
            "core.memory.memory_manager",
            "core.memory.project_memory",
            "core.memory.context_builder",
            "core.memory.reflection_engine",
            "core.memory.reflection_manager",
            "core.memory.step_reflection_engine",
        ],
        "owner": "core.memory",
        "read_path": ["TaskMemory record reads", "legacy TaskRepository reads"],
        "write_path": ["MemoryRepository JSONL", "data/tasks/task_memory.json"],
        "lifecycle_authority": "none; legacy TaskRepository status is deprecated local task metadata",
        "persistent": True,
        "planner_readable": True,
        "runtime_readable": False,
        "writable_paths": ["data/tasks/task_memory.json", "configured MemoryRepository path"],
        "readable_paths": ["configured MemoryRepository path", "data/tasks/task_memory.json"],
        "deprecated_paths": ["core.task_memory", "TaskRepository lifecycle-like status API"],
    },
    {
        "name": "planning_memory",
        "modules": [
            "core.planning.memory_context",
            "core.planning.memory_aware_planner",
            "core.adaptive.adaptive_memory_context",
            "core.adaptive.memory_aware_replanner",
        ],
        "owner": "core.planning",
        "read_path": ["MemoryRepository -> MemoryQuery -> MemoryContextBuilder -> Planner"],
        "write_path": [],
        "lifecycle_authority": "none",
        "persistent": False,
        "planner_readable": True,
        "runtime_readable": False,
        "writable_paths": [],
        "readable_paths": ["MemoryRepository summaries"],
        "deprecated_paths": [],
    },
    {
        "name": "runtime_global_memory",
        "modules": [
            "core.runtime.runtime_memory_engine",
            "core.runtime.runtime_memory_model",
            "core.runtime.runtime_memory_index",
            "core.runtime.runtime_memory_constitution",
            "core.runtime.runtime_stability_memory",
        ],
        "owner": "core.runtime observability",
        "read_path": ["runtime experience/replay/recovery queries"],
        "write_path": ["process-local runtime experience index"],
        "lifecycle_authority": "none",
        "persistent": False,
        "planner_readable": False,
        "runtime_readable": True,
        "writable_paths": ["process-local _MEMORY/_WINDOWS only"],
        "readable_paths": ["process-local runtime experience snapshots"],
        "deprecated_paths": [],
    },
    {
        "name": "engineering_memory",
        "modules": ["core.tasks.engineering_memory_store"],
        "owner": "EngineeringTaskRunner knowledge persistence",
        "read_path": ["EngineeringMemoryStore.load_relevant_memory"],
        "write_path": ["EngineeringMemoryStore.save_record"],
        "lifecycle_authority": "none",
        "persistent": True,
        "planner_readable": True,
        "runtime_readable": False,
        "writable_paths": ["workspace/work_packages/engineering_memory_store.json"],
        "readable_paths": ["workspace/work_packages/engineering_memory_store.json"],
        "deprecated_paths": [],
    },
    {
        "name": "work_package_memory",
        "modules": ["core.memory.work_package_memory"],
        "owner": "RuntimePackageQueue terminal fact commit; WorkPackagePlannerBridge summary read",
        "read_path": ["WorkPackageMemoryStore.query_related -> WorkPackagePlannerBridge"],
        "write_path": ["terminal RuntimePackageQueue transition -> WorkPackageMemoryStore.commit_terminal"],
        "lifecycle_authority": "none; terminal lifecycle is validated before commit",
        "persistent": True,
        "planner_readable": True,
        "runtime_readable": False,
        "writable_paths": ["workspace/work_package_memory/records/*.json"],
        "readable_paths": ["workspace/work_package_memory/records/*.json"],
        "deprecated_paths": [],
    },
)


def memory_architecture_summary() -> dict[str, Any]:
    modules = copy.deepcopy(list(MEMORY_MODULES))
    return {
        "schema": MEMORY_OWNERSHIP_SCHEMA,
        "memory_modules": modules,
        "ownership": {item["name"]: item["owner"] for item in modules},
        "writable_paths": {
            item["name"]: copy.deepcopy(item["writable_paths"]) for item in modules
        },
        "readable_paths": {
            item["name"]: copy.deepcopy(item["readable_paths"]) for item in modules
        },
        "deprecated_paths": sorted(
            {path for item in modules for path in item["deprecated_paths"]}
        ),
        "drift_warnings": [
            "legacy_task_repository_status_is_not_runtime_lifecycle_authority",
            "runtime_global_memory_is_process_local_and_non_persistent",
            "multiple_memory_stores_remain_separate_by_declared_ownership",
            "archived_memory_tool_is_not_a_runtime_control_surface",
        ],
        "contract": {
            "work_package_memory": "terminal engineering facts only",
            "planning_memory": "planning context only",
            "task_memory": "cannot control runtime lifecycle",
            "runtime_global_memory": "cannot change planner decisions",
            "engineering_memory": "cannot bypass queue/dispatcher/scheduler",
            "all_memory": "cannot call execution endpoints",
        },
    }


def audit_memory_control_boundaries(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    violations: list[dict[str, Any]] = []
    audited: list[str] = []
    for item in MEMORY_MODULES:
        for module in item["modules"]:
            path = root / (module.replace(".", "/") + ".py")
            if not path.is_file():
                violations.append({"module": module, "violation": "module_missing"})
                continue
            audited.append(module)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    imported = str(node.module or "")
                    if imported in FORBIDDEN_CONTROL_IMPORTS:
                        violations.append(
                            {"module": module, "violation": f"forbidden_import:{imported}"}
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in FORBIDDEN_CONTROL_IMPORTS:
                            violations.append(
                                {"module": module, "violation": f"forbidden_import:{alias.name}"}
                            )
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in FORBIDDEN_CONTROL_CALLS
                ):
                    violations.append(
                        {"module": module, "violation": f"forbidden_control_call:{node.func.attr}"}
                    )
    return {
        "schema": MEMORY_OWNERSHIP_SCHEMA,
        "ok": not violations,
        "audited_modules": audited,
        "violations": violations,
    }


__all__ = [
    "FORBIDDEN_CONTROL_CALLS",
    "FORBIDDEN_CONTROL_IMPORTS",
    "MEMORY_MODULES",
    "MEMORY_OWNERSHIP_SCHEMA",
    "audit_memory_control_boundaries",
    "memory_architecture_summary",
]
