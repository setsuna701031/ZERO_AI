from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from typing import Any, Mapping

from core.memory.work_package_memory import WorkPackageMemoryStore
from core.memory.memory_ownership_contract import memory_architecture_summary
from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.work_package_queue import RuntimePackageQueue
from core.tasks.work_package_runtime_intake import build_package_record
from core.reports.engineering_report_contract import attach_engineering_report
from core.goals.goal_lineage_contract import extract_goal_lineage


class RuntimeWorkPackageOperator:
    """Stable operator surface. This module never calls the execution endpoint."""

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        state_dir: str | Path = "workspace/runtime_work_packages",
        queue: RuntimePackageQueue | None = None,
        planner_bridge: WorkPackagePlannerBridge | None = None,
        dispatcher: RuntimeDispatcher | None = None,
        memory_store: WorkPackageMemoryStore | None = None,
        llm_client: Any = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.llm_client = llm_client
        injected_queue_store = getattr(queue, "memory_store", None)
        self.memory_store = (
            memory_store
            or injected_queue_store
            or WorkPackageMemoryStore(self.repo_root / "workspace" / "work_package_memory")
        )
        self.queue = queue or RuntimePackageQueue(
            repo_root=repo_root,
            state_dir=state_dir,
            memory_store=self.memory_store,
        )
        self.queue.memory_store = self.memory_store
        self.planner_bridge = planner_bridge or WorkPackagePlannerBridge(
            workspace_root=str(Path(repo_root) / "workspace"),
            memory_store=self.memory_store,
        )
        self.planner_bridge.memory_store = self.memory_store
        self.dispatcher = dispatcher or RuntimeDispatcher(
            queue=self.queue,
            workspace_root=self.repo_root / "workspace",
            planner_bridge=self.planner_bridge,
            llm_client=llm_client,
        )
        if getattr(self.dispatcher, "planner_bridge", None) is None:
            self.dispatcher.planner_bridge = self.planner_bridge
        configure_llm_client = getattr(self.dispatcher, "configure_llm_client", None)
        if llm_client is not None and callable(configure_llm_client):
            try:
                configure_llm_client(llm_client)
            except (AttributeError, TypeError):
                pass
        elif llm_client is not None and getattr(self.dispatcher, "llm_client", None) is None:
            try:
                self.dispatcher.llm_client = llm_client
            except (AttributeError, TypeError):
                pass

    def submit_package(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        package = build_package_record(payload)
        extract_goal_lineage(package.to_dict(), require_complete=True, reject_conflicts=True)
        record = self.queue.enqueue(package)
        if record.get("planning_status") in {"planned", "failed"}:
            return record
        snapshot = self.planner_bridge.plan_package(record)
        return self.queue.record_planning(str(record["package_id"]), snapshot)

    def intake_package(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = self.submit_package(payload)
        package_id = str(record.get("package_id") or "")
        return {
            "schema": "zero.work_package.intake_result.v1",
            "ok": True,
            "package_id": package_id,
            "status": record.get("status") or "queued",
            "queue_path": str(self.queue.state_dir),
            "record_path": str(self.queue.record_path(package_id)),
            "record": record,
        }

    def plan_package(self, package_id: str) -> dict[str, Any]:
        record = self.queue.status(package_id)
        snapshot = self.planner_bridge.plan_package(record)
        return self.queue.record_planning(package_id, snapshot)

    def package_status(self, package_id: str) -> dict[str, Any]:
        return self.queue.status(package_id)["progress_snapshot"]

    def run_package(self, package_id: str) -> dict[str, Any]:
        return self.dispatcher.dispatch(package_id)

    def resume_session(self, package_id: str) -> dict[str, Any]:
        extract_goal_lineage(
            self.queue.status(package_id), require_complete=True, reject_conflicts=True
        )
        return self.dispatcher.resume(package_id)

    def resume_interrupted_packages(self) -> dict[str, Any]:
        results = []
        for contract in self.queue.list_resumable_sessions():
            results.append(self.resume_session(str(contract.get("package_id") or "")))
        return {
            "ok": True,
            "action": "work_package_sessions_resumed" if results else "nothing_to_resume",
            "resumed_count": len(results),
            "results": results,
        }

    def package_progress(self, package_id: str) -> dict[str, Any]:
        return self.dispatcher.progress(package_id)

    def package_summary(self, package_id: str) -> dict[str, Any]:
        status_fn = getattr(self.queue, "status", None)
        if callable(status_fn):
            record = status_fn(package_id)
            progress = (
                record.get("progress_snapshot")
                if isinstance(record.get("progress_snapshot"), Mapping)
                else self.queue.runtime_progress(package_id)
            )
        else:
            record = {}
            progress = self.queue.runtime_progress(package_id)
        task_graph = progress.get("task_graph_summary")
        last_transition = progress.get("last_transition")
        step_types = (
            list(task_graph.get("step_types") or [])
            if isinstance(task_graph, Mapping)
            else []
        )
        completed_steps = int(progress.get("completed_steps") or 0)
        failed_steps = int(progress.get("failed_steps") or 0)
        remaining_steps = int(progress.get("remaining_steps") or 0)
        if step_types and completed_steps == 0 and failed_steps == 0:
            remaining_steps = len(step_types)
        return {
            "package_id": str(progress.get("package_id") or package_id),
            "lifecycle_state": progress.get("lifecycle_state"),
            "planning_status": progress.get("planning_status"),
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "remaining_steps": remaining_steps,
            "percent": progress.get("percent") or 0,
            "root_cause": progress.get("root_cause"),
            "last_transition_reason": (
                last_transition.get("reason") if isinstance(last_transition, Mapping) else None
            ),
            "memory_status": progress.get("memory_status"),
            "step_types": step_types,
        }

    def package_report(self, package_id: str) -> dict[str, Any]:
        return attach_engineering_report(self.package_summary(package_id), report_type="work_package")

    def run_validation_only(self, package_id: str) -> dict[str, Any]:
        record = self.queue.status(package_id)
        commands = [str(item) for item in record.get("validation_commands") or [] if str(item).strip()]
        before_dirty = self._git_status_lines()
        results: list[dict[str, Any]] = []
        non_mainline_findings: list[dict[str, Any]] = []
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                shell=True,
                capture_output=True,
                text=True,
                check=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            results.append(
                {
                    "command": command,
                    "exit_code": int(completed.returncode),
                    "stdout": stdout,
                    "stderr": stderr,
                    "ok": completed.returncode == 0,
                }
            )
            for stream_name, stream in (("stdout", stdout), ("stderr", stderr)):
                for line in stream.splitlines():
                    lowered = line.lower()
                    if "warning" in lowered or "unexpected" in lowered or "pollution" in lowered:
                        non_mainline_findings.append(
                            {
                                "type": "validation_output_warning",
                                "command": command,
                                "stream": stream_name,
                                "message": line.strip(),
                            }
                        )
        after_dirty = self._git_status_lines()
        new_dirty = [line for line in after_dirty if line not in before_dirty]
        if new_dirty:
            non_mainline_findings.append(
                {
                    "type": "unexpected_dirty_files",
                    "files": new_dirty,
                    "message": "Validation-only command changed repository status.",
                }
            )
        remaining_failures = [
            {
                "command": item["command"],
                "exit_code": item["exit_code"],
                "stderr": item["stderr"],
            }
            for item in results
            if not item["ok"]
        ]
        ok = bool(commands) and not remaining_failures
        criteria = list(record.get("completion_criteria") or [])
        validation_summary = {
            "schema": "zero.work_package.validation_only_report.v1",
            "package_id": package_id,
            "objective": record.get("objective") or record.get("goal"),
            "status": "validation_passed" if ok else "validation_failed",
            "ok": ok,
            "validation_results": copy.deepcopy(results),
            "results": copy.deepcopy(results),
            "remaining_failures": remaining_failures,
            "non_mainline_findings": non_mainline_findings,
            "completion_criteria_status": {
                "criteria": criteria,
                "met": ok and not remaining_failures,
                "unmet": [] if ok else criteria,
            },
            "validation_only": True,
            "repo_mutation_performed_by_zero": False,
        }
        self.queue.update_progress(
            package_id,
            {
                "validation_summary": validation_summary,
                "non_mainline_findings": non_mainline_findings,
                "remaining_failures": remaining_failures,
            },
        )
        return validation_summary

    def _git_status_lines(self) -> list[str]:
        try:
            completed = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, ValueError):
            return []
        if completed.returncode != 0:
            return []
        return [line.rstrip() for line in (completed.stdout or "").splitlines() if line.strip()]

    def pause_package(self, package_id: str) -> dict[str, Any]:
        return self.queue.pause(package_id)

    def resume_package(self, package_id: str) -> dict[str, Any]:
        record = self.queue.status(package_id)
        extract_goal_lineage(record, require_complete=True, reject_conflicts=True)
        if record.get("status") == "running" and record.get("runtime_lifecycle_state") == "executing":
            return self.resume_session(package_id)
        return self.queue.resume(package_id)

    def cancel_package(self, package_id: str) -> dict[str, Any]:
        return self.queue.cancel(package_id)

    def list_packages(self, *, status: str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
        return self.queue.list_packages(status=status, active_only=active_only)

    def list_active_packages(self) -> list[dict[str, Any]]:
        return self.queue.list_active_packages()

    def package_memory(self, package_id: str) -> dict[str, Any] | None:
        return self.memory_store.get_for_package(package_id)

    def memory_status(self) -> dict[str, Any]:
        return memory_architecture_summary()


def submit_package(payload: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).submit_package(payload)


def intake_package(payload: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).intake_package(payload)


def plan_package(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).plan_package(package_id)


def package_status(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).package_status(package_id)


def run_package(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).run_package(package_id)


def run_validation_only(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).run_validation_only(package_id)


def package_progress(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).package_progress(package_id)


def package_summary(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).package_summary(package_id)


def package_report(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).package_report(package_id)


def pause_package(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).pause_package(package_id)


def resume_package(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).resume_package(package_id)


def cancel_package(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).cancel_package(package_id)


def list_packages(**kwargs: Any) -> list[dict[str, Any]]:
    status = kwargs.pop("status", None)
    active_only = bool(kwargs.pop("active_only", False))
    return RuntimeWorkPackageOperator(**kwargs).list_packages(status=status, active_only=active_only)


def package_memory(package_id: str, **kwargs: Any) -> dict[str, Any] | None:
    return RuntimeWorkPackageOperator(**kwargs).package_memory(package_id)


__all__ = [
    "RuntimeWorkPackageOperator",
    "cancel_package",
    "intake_package",
    "list_packages",
    "package_status",
    "package_progress",
    "package_report",
    "package_summary",
    "package_memory",
    "plan_package",
    "pause_package",
    "resume_package",
    "run_package",
    "run_validation_only",
    "submit_package",
]
