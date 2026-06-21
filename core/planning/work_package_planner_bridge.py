from __future__ import annotations

import contextlib
import copy
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.memory.work_package_memory import WorkPackageMemoryStore
from core.planning.planner import Planner
from core.planning.planner_contract import validate_step_contracts
from core.tasks.work_package_model import WorkPackage


WORK_PACKAGE_ADAPTIVE_PLAN_SCHEMA = "zero.work_package.adaptive_plan.v1"
WORK_PACKAGE_REPLAN_SCHEMA = "zero.work_package.adaptive_replan.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkPackagePlannerBridge:
    """Translate a passive WorkPackage contract into a runtime-owned task plan."""

    def __init__(
        self,
        *,
        planner: Any = None,
        workspace_root: str = "workspace",
        memory_store: WorkPackageMemoryStore | None = None,
    ) -> None:
        self.planner = planner
        self.workspace_root = workspace_root
        self.memory_store = memory_store or WorkPackageMemoryStore(
            Path(workspace_root) / "work_package_memory"
        )

    def plan_package(self, package: WorkPackage | Mapping[str, Any]) -> dict[str, Any]:
        record = package.to_dict() if isinstance(package, WorkPackage) else copy.deepcopy(dict(package))
        identity = {
            "package_id": str(record.get("package_id") or ""),
            "session_id": str(record.get("session_id") or ""),
            "task_id": str(record.get("task_id") or ""),
        }
        planned_at = _now()
        memory_context_used = self._related_memory_context(record)
        try:
            validation_commands = self._validation_commands(record)
            if validation_commands:
                steps = self._validation_command_steps(
                    identity=identity,
                    commands=validation_commands,
                )
                validation = validate_step_contracts(steps)
                errors = list(validation.get("errors") or [])
                if errors:
                    return self._failed_snapshot(
                        identity,
                        planned_at=planned_at,
                        errors=errors,
                        warnings=list(record.get("warnings") or []),
                        planner_result={"source": "validation_commands_shortcut"},
                        memory_context_used=memory_context_used,
                    )

                return self._planned_snapshot(
                    identity=identity,
                    planned_at=planned_at,
                    warnings=list(record.get("warnings") or []),
                    steps=steps,
                    memory_context_used=memory_context_used,
                    planner_summary={
                        "intent": "validation_commands",
                        "semantic_type": "work_package_validation",
                        "execution_route": "deterministic_command_validation",
                        "step_count": len(steps),
                    },
                    lifecycle_state=str(record.get("lifecycle_state") or "queued"),
                    transition_history=copy.deepcopy(record.get("transition_history") or []),
                    last_transition=copy.deepcopy(record.get("last_transition")),
                )

            planner_result = self._invoke_planner(record, memory_context_used=memory_context_used)
            steps = copy.deepcopy(
                planner_result.get("steps") if isinstance(planner_result.get("steps"), list) else []
            )
            steps = self._apply_readonly_contract(record, steps)
            validation = validate_step_contracts(steps)
            errors = list(validation.get("errors") or [])
            if planner_result.get("error"):
                errors.append(str(planner_result["error"]))
            if not steps:
                errors.append("planner_produced_no_executable_steps")
            if errors:
                return self._failed_snapshot(
                    identity,
                    planned_at=planned_at,
                    errors=errors,
                    warnings=list(record.get("warnings") or []),
                    planner_result=planner_result,
                    memory_context_used=memory_context_used,
                )

            return self._planned_snapshot(
                identity=identity,
                planned_at=planned_at,
                warnings=list(record.get("warnings") or []),
                steps=steps,
                memory_context_used=memory_context_used,
                planner_summary={
                    "intent": planner_result.get("intent"),
                    "semantic_type": (planner_result.get("meta") or {}).get("semantic_type"),
                    "execution_route": (planner_result.get("meta") or {}).get("execution_route"),
                    "step_count": len(steps),
                },
                lifecycle_state=str(record.get("lifecycle_state") or "queued"),
                transition_history=copy.deepcopy(record.get("transition_history") or []),
                last_transition=copy.deepcopy(record.get("last_transition")),
            )
        except Exception as exc:
            return self._failed_snapshot(
                identity,
                planned_at=planned_at,
                errors=[f"work_package_planning_failed:{type(exc).__name__}:{exc}"],
                warnings=list(record.get("warnings") or []),
                planner_result={},
                memory_context_used=memory_context_used,
            )

    def replan_package(
        self,
        package: Mapping[str, Any],
        replan_request: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = copy.deepcopy(dict(package))
        request = copy.deepcopy(dict(replan_request))
        record["replan_request"] = request
        record["failure_type"] = str(request.get("root_cause") or "")
        record["root_cause"] = str(request.get("root_cause") or record.get("root_cause") or "")
        metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
        record["metadata"] = {
            **copy.deepcopy(dict(metadata)),
            "adaptive_replan": True,
            "replan_request_id": request.get("request_id"),
        }
        snapshot = self.plan_package(record)
        snapshot["schema"] = WORK_PACKAGE_REPLAN_SCHEMA
        snapshot["replan_request"] = request
        snapshot["preserves_previous_evidence"] = True
        snapshot["append_only_steps"] = True
        return snapshot

    def _related_memory_context(self, package: Mapping[str, Any]) -> list[dict[str, Any]]:
        objective = " ".join(
            str(value or "")
            for value in (
                package.get("title"),
                package.get("goal"),
                package.get("description"),
                " ".join(str(item) for item in package.get("requirements") or []),
            )
        )
        related = self.memory_store.query_related(
            objective=objective,
            target_files=tuple(str(item) for item in package.get("target_files") or []),
            failure_type=str(package.get("failure_type") or package.get("root_cause") or ""),
            limit=5,
        )
        package_id = str(package.get("package_id") or "")
        return [item for item in related if str(item.get("package_id") or "") != package_id]

    def _invoke_planner(
        self,
        package: Mapping[str, Any],
        *,
        memory_context_used: list[dict[str, Any]],
    ) -> dict[str, Any]:
        planner = self.planner
        if planner is None:
            with contextlib.redirect_stdout(io.StringIO()):
                planner = Planner(workspace_root=self.workspace_root)
        context = {
            "user_input": self._planner_request(package),
            "task_type": "work_package",
            "semantic_type": "multi_step_task",
            "work_package": copy.deepcopy(dict(package)),
            "package_id": package.get("package_id"),
            "session_id": package.get("session_id"),
            "task_id": package.get("task_id"),
            "memory_context": {
                "schema": "zero.work_package.planning_memory_context.v1",
                "related_work_packages": copy.deepcopy(memory_context_used),
            },
        }
        method = getattr(planner, "plan", None)
        if not callable(method):
            raise TypeError("work_package_planner_missing_plan_method")
        try:
            result = method(context=context, user_input=context["user_input"])
        except TypeError:
            result = method(copy.deepcopy(context))
        if not isinstance(result, Mapping):
            raise TypeError("work_package_planner_result_must_be_mapping")
        return copy.deepcopy(dict(result))

    @staticmethod
    def _apply_readonly_contract(package: Mapping[str, Any], steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        metadata = package.get("metadata") if isinstance(package.get("metadata"), Mapping) else {}
        if not bool(metadata.get("force_read_file_only")):
            return steps

        target_files = [str(item).strip() for item in package.get("target_files") or [] if str(item).strip()]
        return [
            {
                "id": f"readonly_read_file_{index}",
                "type": "read_file",
                "path": path,
                "planner_contract_version": "planner_step_contract.v2",
                "legacy_plan_contract": False,
            }
            for index, path in enumerate(target_files, start=1)
        ]

    @staticmethod
    def _validation_commands(package: Mapping[str, Any]) -> list[str]:
        return [
            str(item).strip()
            for item in package.get("validation_commands") or []
            if str(item).strip()
        ]

    def _validation_command_steps(
        self,
        *,
        identity: Mapping[str, str],
        commands: list[str],
    ) -> list[dict[str, Any]]:
        task_id = str(identity.get("task_id") or identity.get("package_id") or "work_package")
        command_cwd = self._validation_command_cwd()
        return [
            {
                "id": f"{task_id}_validation_{index}",
                "type": "command",
                "command": command,
                "command_cwd": command_cwd,
                "cwd": command_cwd,
                "planner_contract_version": "planner_step_contract.v2",
                "legacy_plan_contract": False,
                "step_purpose": "work_package_validation_command",
            }
            for index, command in enumerate(commands, start=1)
        ]

    def _validation_command_cwd(self) -> str:
        workspace = Path(self.workspace_root)
        try:
            resolved = workspace.resolve()
        except Exception:
            resolved = workspace

        if resolved.name == "workspace":
            return str(resolved.parent)
        return str(resolved)

    def _planned_snapshot(
        self,
        *,
        identity: Mapping[str, str],
        planned_at: str,
        warnings: list[str],
        steps: list[dict[str, Any]],
        memory_context_used: list[dict[str, Any]],
        planner_summary: Mapping[str, Any],
        lifecycle_state: str,
        transition_history: list[dict[str, Any]],
        last_transition: Any,
    ) -> dict[str, Any]:
        graph = self._task_graph(str(identity.get("task_id") or ""), steps)
        return {
            "schema": WORK_PACKAGE_ADAPTIVE_PLAN_SCHEMA,
            **copy.deepcopy(dict(identity)),
            "planning_status": "planned",
            "planned_at": planned_at,
            "warnings": list(warnings),
            "errors": [],
            "memory_context_used": copy.deepcopy(memory_context_used),
            "planner_summary": copy.deepcopy(dict(planner_summary)),
            "task_graph": graph,
            "task_graph_summary": {
                "node_count": len(graph["nodes"]),
                "edge_count": len(graph["edges"]),
                "root_task_id": identity.get("task_id"),
                "step_types": [str(step.get("type") or "") for step in steps],
            },
            "executable_steps": copy.deepcopy(steps),
            "runtime_queue_item": {
                **copy.deepcopy(dict(identity)),
                "status": "queued",
                "lifecycle_state": lifecycle_state,
                "transition_history": copy.deepcopy(transition_history),
                "last_transition": copy.deepcopy(last_transition),
                "steps": copy.deepcopy(steps),
                "current_step_index": 0,
                "results": [],
                "runtime_owner": "RuntimeDispatcher",
                "taskrunner_required": True,
                "step_executor_endpoint_only": True,
                "direct_execution": False,
                "memory_context_used": copy.deepcopy(memory_context_used),
            },
        }

    @staticmethod
    def _planner_request(package: Mapping[str, Any]) -> str:
        requirements = "; ".join(str(item) for item in package.get("requirements") or [])
        targets = ", ".join(str(item) for item in package.get("target_files") or [])
        boundaries = "; ".join(str(item) for item in package.get("hard_boundary") or [])
        validations = "; ".join(str(item) for item in package.get("validation_commands") or [])
        return (
            "Create a multi-step task plan for this engineering work package. "
            f"Goal: {package.get('goal')}. Description: {package.get('description')}. "
            f"Requirements: {requirements}. Target files: {targets}. "
            f"Hard boundaries: {boundaries}. Validation commands: {validations}."
        )

    @staticmethod
    def _task_graph(task_id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        previous = ""
        for index, step in enumerate(steps, start=1):
            node_id = str(step.get("id") or f"{task_id}:step:{index}")
            nodes.append(
                {
                    "node_id": node_id,
                    "task_id": task_id,
                    "step_index": index - 1,
                    "step_type": str(step.get("type") or ""),
                    "depends_on": [previous] if previous else [],
                }
            )
            if previous:
                edges.append({"from": previous, "to": node_id})
            previous = node_id
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _failed_snapshot(
        identity: Mapping[str, str],
        *,
        planned_at: str,
        errors: list[str],
        warnings: list[str],
        planner_result: Mapping[str, Any],
        memory_context_used: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema": WORK_PACKAGE_ADAPTIVE_PLAN_SCHEMA,
            **copy.deepcopy(dict(identity)),
            "planning_status": "failed",
            "planned_at": planned_at,
            "warnings": list(warnings),
            "errors": list(errors),
            "memory_context_used": copy.deepcopy(memory_context_used),
            "planner_summary": {"step_count": 0},
            "task_graph": {"nodes": [], "edges": []},
            "task_graph_summary": {
                "node_count": 0,
                "edge_count": 0,
                "root_task_id": identity.get("task_id"),
                "step_types": [],
            },
            "executable_steps": [],
            "runtime_queue_item": None,
            "planner_result": copy.deepcopy(dict(planner_result)),
        }


__all__ = ["WORK_PACKAGE_ADAPTIVE_PLAN_SCHEMA", "WORK_PACKAGE_REPLAN_SCHEMA", "WorkPackagePlannerBridge"]
