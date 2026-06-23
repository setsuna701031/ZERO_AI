from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from typing import Any, Mapping

from core.memory.work_package_memory import WorkPackageMemoryStore
from core.memory.memory_ownership_contract import memory_architecture_summary
from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.execution_package_dispatch_bridge import (
    execution_package_to_runtime_dispatch_request,
)
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.work_package_queue import RuntimePackageQueue
from core.tasks.work_package_runtime_intake import build_package_record
from core.tasks.work_package_execution_package import (
    build_execution_package,
    build_proposal_approval,
    proposal_id_for,
    summarize_approval,
    summarize_execution_package,
)
from core.reports.engineering_report_contract import attach_engineering_report
from core.goals.goal_lineage_contract import extract_goal_lineage


EXECUTION_PROPOSAL_SCHEMA = "zero.work_package.execution_proposal.v1"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return copy.deepcopy(value)
    if isinstance(value, tuple):
        return copy.deepcopy(list(value))
    return [copy.deepcopy(value)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _non_mainline_enabled(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value.get("enabled", True))
    if isinstance(value, bool):
        return value
    if value in (None, "", [], {}):
        return True
    return True


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
        proposal = self.propose_package(package_id)
        return {
            "schema": "zero.work_package.intake_result.v1",
            "ok": True,
            "package_id": package_id,
            "status": record.get("status") or "queued",
            "queue_path": str(self.queue.state_dir),
            "record_path": str(self.queue.record_path(package_id)),
            "proposal": proposal,
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
        result = self.package_summary(package_id)
        status_fn = getattr(self.queue, "status", None)
        if callable(status_fn):
            record = status_fn(package_id)
            proposal_summary = record.get("execution_proposal_summary")
            if not isinstance(proposal_summary, Mapping):
                proposal = self.propose_package(package_id)
                proposal_summary = proposal.get("proposal_summary")
            if isinstance(proposal_summary, Mapping):
                result["proposal_summary"] = copy.deepcopy(dict(proposal_summary))
            result["approval_status"] = summarize_approval(
                record.get("proposal_approval")
                if isinstance(record.get("proposal_approval"), Mapping)
                else None
            )
            result["execution_package_summary"] = summarize_execution_package(
                record.get("execution_package")
                if isinstance(record.get("execution_package"), Mapping)
                else None
            )
        return attach_engineering_report(result, report_type="work_package")

    def propose_package(self, package_id: str) -> dict[str, Any]:
        record = self.queue.status(package_id)
        proposal = self._build_execution_proposal(record)
        queue_record = self.queue.record_execution_proposal(package_id, proposal)
        summary = queue_record.get("execution_proposal_summary")
        if isinstance(summary, Mapping):
            proposal["proposal_summary"] = copy.deepcopy(dict(summary))
        return proposal

    def approve_proposal(self, package_id: str) -> dict[str, Any]:
        record = self.queue.status(package_id)
        proposal = (
            copy.deepcopy(dict(record.get("execution_proposal")))
            if isinstance(record.get("execution_proposal"), Mapping)
            else self.propose_package(package_id)
        )
        approval = build_proposal_approval(proposal)
        queue_record = self.queue.record_proposal_approval(package_id, approval)
        return {
            "schema": "zero.work_package.proposal_approval_result.v1",
            "ok": True,
            "package_id": package_id,
            "approval": copy.deepcopy(approval),
            "approval_status": copy.deepcopy(queue_record.get("approval_status") or {}),
            "record_path": str(self.queue.record_path(package_id)),
            "repo_mutation_performed_by_zero": False,
        }

    def execution_package(self, package_id: str) -> dict[str, Any]:
        record = self.queue.status(package_id)
        proposal = record.get("execution_proposal")
        if not isinstance(proposal, Mapping):
            proposal = self.propose_package(package_id)
            record = self.queue.status(package_id)
        approval = record.get("proposal_approval")
        if not isinstance(approval, Mapping) or not approval.get("approved"):
            raise PermissionError("proposal_approval_required")
        if str(approval.get("proposal_id") or "") != proposal_id_for(proposal):
            raise PermissionError("proposal_approval_mismatch")
        execution_package = build_execution_package(
            record=record,
            proposal=proposal,
            approval=approval,
        )
        queue_record = self.queue.record_execution_package(package_id, execution_package)
        return {
            "schema": "zero.work_package.execution_package_result.v1",
            "ok": True,
            "package_id": package_id,
            "execution_package": execution_package,
            "execution_package_summary": copy.deepcopy(
                queue_record.get("execution_package_summary") or {}
            ),
            "record_path": str(self.queue.record_path(package_id)),
            "repo_mutation_performed_by_zero": False,
        }

    def runtime_dispatch_request(self, package_id: str) -> dict[str, Any]:
        record = self.queue.status(package_id)
        execution_package = record.get("execution_package")
        if not isinstance(execution_package, Mapping):
            generated = self.execution_package(package_id)
            execution_package = generated["execution_package"]
            record = self.queue.status(package_id)
        dispatch_request = execution_package_to_runtime_dispatch_request(
            execution_package,
            record=record,
        )
        queue_record = self.queue.record_runtime_dispatch_request(package_id, dispatch_request)
        return {
            "schema": "zero.work_package.runtime_dispatch_request_result.v1",
            "ok": True,
            "package_id": package_id,
            "runtime_dispatch_request": dispatch_request,
            "runtime_dispatch_request_summary": copy.deepcopy(
                queue_record.get("runtime_dispatch_request_summary") or {}
            ),
            "record_path": str(self.queue.record_path(package_id)),
            "repo_mutation_performed_by_zero": False,
        }

    def _build_execution_proposal(self, record: Mapping[str, Any]) -> dict[str, Any]:
        package_id = _text(record.get("package_id"))
        objective = _text(record.get("objective") or record.get("goal") or record.get("title"))
        requirements = _as_list(record.get("requirements"))
        constraints = _as_list(record.get("constraints") or record.get("hard_boundary"))
        validation_commands = [_text(item) for item in _as_list(record.get("validation_commands")) if _text(item)]
        completion_criteria = _as_list(record.get("completion_criteria") or record.get("completion_report_format"))
        proposed_steps = self._proposal_steps(record, requirements=requirements, objective=objective)
        risk_flags = self._proposal_risk_flags(
            requirements=requirements,
            constraints=constraints,
            validation_commands=validation_commands,
            completion_criteria=completion_criteria,
        )
        proposal = {
            "schema": EXECUTION_PROPOSAL_SCHEMA,
            "package_id": package_id,
            "objective": objective,
            "requirements": requirements,
            "constraints": constraints,
            "proposed_steps": proposed_steps,
            "validation_plan": {
                "commands": validation_commands,
                "completion_criteria": completion_criteria,
                "validation_only_supported": True,
            },
            "risk_flags": risk_flags,
            "required_operator_approval": True,
            "non_mainline_reporting_enabled": _non_mainline_enabled(
                record.get("non_mainline_issue_reporting")
            ),
            "proposal_only": True,
            "repo_mutation_performed_by_zero": False,
        }
        proposal["proposal_id"] = proposal_id_for(proposal)
        return proposal

    def _proposal_steps(
        self,
        record: Mapping[str, Any],
        *,
        requirements: list[Any],
        objective: str,
    ) -> list[dict[str, Any]]:
        queue_item = record.get("runtime_queue_item")
        raw_steps = queue_item.get("steps") if isinstance(queue_item, Mapping) else []
        proposed: list[dict[str, Any]] = []
        if isinstance(raw_steps, list) and raw_steps:
            for index, step in enumerate(raw_steps, start=1):
                if not isinstance(step, Mapping):
                    continue
                proposed.append(
                    {
                        "step_id": _text(step.get("id") or step.get("step_id") or f"step-{index}"),
                        "type": _text(step.get("type") or step.get("action") or "work"),
                        "summary": _text(
                            step.get("description")
                            or step.get("summary")
                            or step.get("prompt")
                            or step.get("path")
                            or objective
                        ),
                        "mutation_allowed": False,
                    }
                )
        if proposed:
            return proposed
        for index, requirement in enumerate(requirements or [objective], start=1):
            proposed.append(
                {
                    "step_id": f"requirement-{index}",
                    "type": "proposal_task",
                    "summary": _text(requirement) or objective,
                    "mutation_allowed": False,
                }
            )
        return proposed

    @staticmethod
    def _proposal_risk_flags(
        *,
        requirements: list[Any],
        constraints: list[Any],
        validation_commands: list[str],
        completion_criteria: list[Any],
    ) -> list[str]:
        flags: list[str] = []
        if not requirements:
            flags.append("missing_requirements")
        if not constraints:
            flags.append("missing_constraints")
        if not validation_commands:
            flags.append("missing_validation_commands")
        if not completion_criteria:
            flags.append("missing_completion_criteria")
        return flags

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


def propose_package(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).propose_package(package_id)


def approve_proposal(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).approve_proposal(package_id)


def execution_package(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).execution_package(package_id)


def runtime_dispatch_request(package_id: str, **kwargs: Any) -> dict[str, Any]:
    return RuntimeWorkPackageOperator(**kwargs).runtime_dispatch_request(package_id)


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
    "approve_proposal",
    "cancel_package",
    "execution_package",
    "intake_package",
    "list_packages",
    "package_status",
    "package_progress",
    "package_report",
    "package_summary",
    "package_memory",
    "plan_package",
    "propose_package",
    "pause_package",
    "resume_package",
    "runtime_dispatch_request",
    "run_package",
    "run_validation_only",
    "submit_package",
]
