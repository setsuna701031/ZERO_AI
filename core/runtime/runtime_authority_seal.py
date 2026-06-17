from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_RUNTIME_DISPATCHER_ISSUER_TOKEN = object()
_TASK_RUNNER_ISSUER_TOKEN = object()
_WORK_PACKAGE_SCHEDULER_ISSUER_TOKEN = object()
_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN = object()


@dataclass(frozen=True)
class RuntimeExecutionCapability:
    task_id: str
    session_id: str
    package_id: str
    step_id: str = ""
    delegated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "zero.runtime_execution_capability.summary.v1",
            "task_id": self.task_id,
            "session_id": self.session_id,
            "package_id": self.package_id,
            "step_id": self.step_id,
            "delegated": self.delegated,
            "authoritative": False,
        }

    def __deepcopy__(self, memo: dict[int, Any]) -> "RuntimeExecutionCapability":
        return self


@dataclass(frozen=True)
class TaskCompletionAuthority:
    task_id: str
    package_id: str
    session_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "zero.task_completion_authority.summary.v1",
            "task_id": self.task_id,
            "package_id": self.package_id,
            "session_id": self.session_id,
            "authoritative": False,
        }

    def __deepcopy__(self, memo: dict[int, Any]) -> "TaskCompletionAuthority":
        return self


@dataclass(frozen=True)
class WorkPackageCompletionAuthority:
    package_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "zero.work_package_completion_authority.summary.v1",
            "package_id": self.package_id,
            "authoritative": False,
        }

    def __deepcopy__(self, memo: dict[int, Any]) -> "WorkPackageCompletionAuthority":
        return self


@dataclass(frozen=True)
class TerminalExecutionEvidence:
    task_id: str
    package_id: str
    session_id: str
    step_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "zero.terminal_execution_evidence.summary.v1",
            "task_id": self.task_id,
            "package_id": self.package_id,
            "session_id": self.session_id,
            "step_id": self.step_id,
            "authoritative": False,
        }

    def __deepcopy__(self, memo: dict[int, Any]) -> "TerminalExecutionEvidence":
        return self


def _build_authority_boundary():
    dispatch_capabilities: dict[int, RuntimeExecutionCapability] = {}
    delegated_capabilities: dict[int, RuntimeExecutionCapability] = {}
    task_completions: dict[int, TaskCompletionAuthority] = {}
    terminal_evidence: dict[int, TerminalExecutionEvidence] = {}
    package_completions: dict[int, WorkPackageCompletionAuthority] = {}
    evidence_authorities: dict[int, Any] = {}

    def issue_dispatch_execution_capability(
        token: Any,
        *,
        task_id: str,
        session_id: str,
        package_id: str,
    ) -> RuntimeExecutionCapability:
        if token is not _RUNTIME_DISPATCHER_ISSUER_TOKEN:
            raise PermissionError("runtime_dispatcher_authority_required")
        capability = RuntimeExecutionCapability(
            task_id=str(task_id),
            session_id=str(session_id),
            package_id=str(package_id),
        )
        dispatch_capabilities[id(capability)] = capability
        return capability

    def delegate_taskrunner_execution_capability(
        token: Any,
        capability: Any,
        *,
        task_id: str,
        step_id: str,
    ) -> RuntimeExecutionCapability:
        if token is not _TASK_RUNNER_ISSUER_TOKEN:
            raise PermissionError("taskrunner_authority_required")
        if not is_dispatch_execution_capability(capability, task_id=task_id):
            raise PermissionError("runtime_dispatcher_live_capability_required")
        dispatch = capability
        delegated = RuntimeExecutionCapability(
            task_id=str(task_id),
            session_id=dispatch.session_id,
            package_id=dispatch.package_id,
            step_id=str(step_id),
            delegated=True,
        )
        delegated_capabilities[id(delegated)] = delegated
        return delegated

    def issue_terminal_execution_evidence(
        token: Any,
        capability: Any,
        *,
        task_id: str,
        package_id: str,
        session_id: str,
        step_id: str,
    ) -> TerminalExecutionEvidence:
        if token is not _TASK_RUNNER_ISSUER_TOKEN:
            raise PermissionError("taskrunner_authority_required")
        if not is_taskrunner_execution_capability(
            capability,
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
            step_id=step_id,
        ):
            raise PermissionError("terminal_execution_lineage_required")
        evidence = TerminalExecutionEvidence(
            task_id=str(task_id),
            package_id=str(package_id),
            session_id=str(session_id),
            step_id=str(step_id),
        )
        terminal_evidence[id(evidence)] = evidence
        return evidence

    def issue_task_completion_authority(
        token: Any,
        *,
        task_id: str,
        package_id: str,
        session_id: str,
        evidence: Any,
    ) -> TaskCompletionAuthority:
        if token is not _TASK_RUNNER_ISSUER_TOKEN:
            raise PermissionError("taskrunner_authority_required")
        if not is_terminal_execution_evidence(
            evidence,
            task_id=task_id,
            package_id=package_id,
            session_id=session_id,
        ):
            raise PermissionError("terminal_execution_evidence_required")
        authority = TaskCompletionAuthority(
            task_id=str(task_id),
            package_id=str(package_id),
            session_id=str(session_id),
        )
        task_completions[id(authority)] = authority
        return authority

    def issue_work_package_completion_authority(
        token: Any,
        *,
        package_id: str,
    ) -> WorkPackageCompletionAuthority:
        if token not in {
            _RUNTIME_DISPATCHER_ISSUER_TOKEN,
            _WORK_PACKAGE_SCHEDULER_ISSUER_TOKEN,
        }:
            raise PermissionError("work_package_completion_owner_required")
        authority = WorkPackageCompletionAuthority(package_id=str(package_id))
        package_completions[id(authority)] = authority
        return authority

    def register_runtime_evidence_authority(token: Any, authority: Any) -> None:
        if token is not _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN:
            raise PermissionError("governed_runtime_evidence_owner_required")
        evidence_authorities[id(authority)] = authority

    def is_dispatch_execution_capability(value: Any, *, task_id: str | None = None) -> bool:
        return bool(
            isinstance(value, RuntimeExecutionCapability)
            and dispatch_capabilities.get(id(value)) is value
            and not value.delegated
            and (task_id is None or value.task_id == str(task_id))
        )

    def is_taskrunner_execution_capability(
        value: Any,
        *,
        task_id: str | None = None,
        step_id: str | None = None,
        package_id: str | None = None,
        session_id: str | None = None,
    ) -> bool:
        return bool(
            isinstance(value, RuntimeExecutionCapability)
            and delegated_capabilities.get(id(value)) is value
            and value.delegated
            and (task_id is None or value.task_id == str(task_id))
            and (not value.step_id or step_id is None or value.step_id == str(step_id))
            and (package_id is None or value.package_id == str(package_id))
            and (session_id is None or value.session_id == str(session_id))
        )

    def is_terminal_execution_evidence(
        value: Any,
        *,
        task_id: str | None = None,
        package_id: str | None = None,
        session_id: str | None = None,
    ) -> bool:
        return bool(
            isinstance(value, TerminalExecutionEvidence)
            and terminal_evidence.get(id(value)) is value
            and (task_id is None or value.task_id == str(task_id))
            and (package_id is None or value.package_id == str(package_id))
            and (session_id is None or value.session_id == str(session_id))
        )

    def is_task_completion_authority(
        value: Any,
        *,
        task_id: str | None = None,
        package_id: str | None = None,
        session_id: str | None = None,
    ) -> bool:
        return bool(
            isinstance(value, TaskCompletionAuthority)
            and task_completions.get(id(value)) is value
            and (task_id is None or value.task_id == str(task_id))
            and (package_id is None or value.package_id == str(package_id))
            and (session_id is None or value.session_id == str(session_id))
        )

    def is_work_package_completion_authority(value: Any, *, package_id: str | None = None) -> bool:
        return bool(
            isinstance(value, WorkPackageCompletionAuthority)
            and package_completions.get(id(value)) is value
            and (package_id is None or value.package_id == str(package_id))
        )

    def is_runtime_evidence_authority(value: Any) -> bool:
        return evidence_authorities.get(id(value)) is value

    return (
        issue_dispatch_execution_capability,
        delegate_taskrunner_execution_capability,
        issue_terminal_execution_evidence,
        issue_task_completion_authority,
        issue_work_package_completion_authority,
        register_runtime_evidence_authority,
        is_dispatch_execution_capability,
        is_taskrunner_execution_capability,
        is_terminal_execution_evidence,
        is_task_completion_authority,
        is_work_package_completion_authority,
        is_runtime_evidence_authority,
    )


(
    issue_dispatch_execution_capability,
    delegate_taskrunner_execution_capability,
    issue_terminal_execution_evidence,
    issue_task_completion_authority,
    issue_work_package_completion_authority,
    register_runtime_evidence_authority,
    is_dispatch_execution_capability,
    is_taskrunner_execution_capability,
    is_terminal_execution_evidence,
    is_task_completion_authority,
    is_work_package_completion_authority,
    is_runtime_evidence_authority,
) = _build_authority_boundary()
del _build_authority_boundary


__all__ = [
    "RuntimeExecutionCapability",
    "TaskCompletionAuthority",
    "TerminalExecutionEvidence",
    "WorkPackageCompletionAuthority",
    "is_dispatch_execution_capability",
    "is_runtime_evidence_authority",
    "is_task_completion_authority",
    "is_taskrunner_execution_capability",
    "is_terminal_execution_evidence",
    "is_work_package_completion_authority",
]
