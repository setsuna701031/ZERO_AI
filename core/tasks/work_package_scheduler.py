from __future__ import annotations

"""
ZERO Work Package Scheduler v5.1.

This module is a small scheduler facade for operator work packages.

Boundary:
- It schedules work packages, not low-level task steps.
- It delegates actual package execution to core.tasks.work_package_intake.
- It does not mutate source files by itself.
- It stores durable metadata under workspace/work_packages by default.
- It keeps AgentLoop from owning queue/status/resume responsibilities.

v5.1 fix:
- Preserve raw package payload fields such as `edit` when storing scheduler
  records. The validated WorkPackageRequest intentionally normalizes the public
  contract, but execute-mode packages still need their guarded edit payload.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.tasks.work_package_contract import WorkPackageRequest, validate_work_package_request
from core.tasks.work_package_intake import submit_work_package
from core.runtime.runtime_authority_seal import (
    _WORK_PACKAGE_SCHEDULER_ISSUER_TOKEN,
    is_work_package_completion_authority,
    issue_work_package_completion_authority,
)


SCHEMA = "zero.work_package.scheduler.v5_1"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED})
TRUSTED_SCHEDULER_COMPLETION_REASONS = frozenset(
    {
        "controlled_workspace_execution_completed",
    }
)


class WorkPackageSchedulerError(RuntimeError):
    """Raised when the work package scheduler cannot perform an operation."""


def _now() -> float:
    return time.time()


def _safe_package_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise WorkPackageSchedulerError("package_id_required")
    safe = []
    for char in text:
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("_")
    cleaned = "".join(safe).strip("._-")
    if not cleaned:
        raise WorkPackageSchedulerError("package_id_invalid")
    return cleaned[:120]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkPackageSchedulerError(f"invalid_scheduler_record:{path}") from exc
    if not isinstance(data, dict):
        raise WorkPackageSchedulerError(f"scheduler_record_must_be_object:{path}")
    return data


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _owned_artifact_path(repo_root: Path, value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    root = repo_root.resolve()
    path = Path(text)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if root not in (resolved, *resolved.parents):
        return None
    return resolved


def _request_payload_for_storage(payload: Mapping[str, Any] | WorkPackageRequest) -> tuple[WorkPackageRequest, dict[str, Any]]:
    if isinstance(payload, WorkPackageRequest):
        request = payload
        stored_payload = request.to_dict()
        return request, stored_payload

    request = validate_work_package_request(payload)
    stored_payload = dict(payload)
    normalized = request.to_dict()

    # Keep normalized contract fields authoritative, but preserve execution
    # details not represented by WorkPackageRequest, especially execute-mode
    # guarded edit payloads.
    for key, value in normalized.items():
        stored_payload[key] = value

    if "edit" in payload:
        stored_payload["edit"] = payload["edit"]
    if "edits" in payload:
        stored_payload["edits"] = payload["edits"]

    return request, stored_payload


@dataclass(frozen=True)
class WorkPackageScheduleRecord:
    package_id: str
    status: str
    request: dict[str, Any]
    result: dict[str, Any] | None = None
    completion_authority: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "package_id": self.package_id,
            "status": self.status,
            "request": dict(self.request),
            "result": dict(self.result) if isinstance(self.result, dict) else None,
            "completion_authority": dict(self.completion_authority) if isinstance(self.completion_authority, dict) else None,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkPackageScheduleRecord":
        package_id = _safe_package_id(payload.get("package_id"))
        status = str(payload.get("status") or "").strip()
        if status not in {STATUS_QUEUED, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED}:
            raise WorkPackageSchedulerError(f"invalid_work_package_status:{status}")
        request = payload.get("request")
        if not isinstance(request, Mapping):
            raise WorkPackageSchedulerError("scheduler_record_request_missing")
        result = payload.get("result")
        completion_authority = payload.get("completion_authority")
        error = payload.get("error")
        return cls(
            package_id=package_id,
            status=status,
            request=dict(request),
            result=dict(result) if isinstance(result, Mapping) else None,
            completion_authority=dict(completion_authority) if isinstance(completion_authority, Mapping) else None,
            error=str(error) if error else None,
            created_at=float(payload.get("created_at") or _now()),
            updated_at=float(payload.get("updated_at") or _now()),
        )


class WorkPackageScheduler:
    """Durable scheduler for ZERO work packages."""

    def __init__(self, *, repo_root: str | Path, state_dir: str | Path = "workspace/work_packages") -> None:
        self.repo_root = Path(repo_root)
        self.state_dir = self._resolve_state_dir(state_dir)

    def _resolve_state_dir(self, state_dir: str | Path) -> Path:
        candidate = Path(state_dir)
        if not candidate.is_absolute():
            candidate = self.repo_root / candidate
        return candidate

    def _record_path(self, package_id: str) -> Path:
        return self.state_dir / f"{_safe_package_id(package_id)}.json"

    def _completion_authority(self, package_id: str, result: Mapping[str, Any]) -> Any:
        safe_id = _safe_package_id(package_id)
        if not bool(result.get("ok", False)):
            return None
        if str(result.get("package_id") or "") != safe_id:
            return None
        if str(result.get("reason") or "") not in TRUSTED_SCHEDULER_COMPLETION_REASONS:
            return None

        record_path = self._record_path(safe_id)
        if not record_path.is_file():
            return None
        try:
            record = WorkPackageScheduleRecord.from_dict(_read_json(record_path))
        except WorkPackageSchedulerError:
            return None
        if record.package_id != safe_id or record.status != STATUS_RUNNING:
            return None

        request = record.request
        if str(request.get("mode") or "") != "execute" or not bool(request.get("approval", False)):
            return None

        evidence = result.get("evidence")
        if not isinstance(evidence, Mapping):
            return None
        if evidence.get("package_id") != safe_id:
            return None
        if evidence.get("guard") != "workspace_only":
            return None
        if evidence.get("policy_reason") != "controlled_workspace_write_allowed":
            return None
        if evidence.get("approval") is not True:
            return None

        changed_files = result.get("changed_files")
        if not isinstance(changed_files, list) or not changed_files:
            return None

        root = self.repo_root.resolve()
        normalized_changed: list[str] = []
        for item in changed_files:
            changed = str(item or "").strip().replace("\\", "/").lstrip("./")
            if not changed or not changed.startswith("workspace/"):
                return None
            path = (root / changed).resolve()
            if root not in (path, *path.parents) or not path.is_file():
                return None
            normalized_changed.append(changed)

        target_path = str(evidence.get("target_path") or result.get("target_path") or "").replace("\\", "/").lstrip("./")
        evidence_changed = evidence.get("changed_files")
        if isinstance(evidence_changed, list):
            evidence_changed_paths = [str(item or "").replace("\\", "/").lstrip("./") for item in evidence_changed]
            if evidence_changed_paths != normalized_changed:
                return None
        elif target_path and normalized_changed != [target_path]:
            return None

        return issue_work_package_completion_authority(
            _WORK_PACKAGE_SCHEDULER_ISSUER_TOKEN,
            package_id=safe_id,
        )

    def submit(
        self,
        payload: Mapping[str, Any] | WorkPackageRequest,
        *,
        execute: bool = True,
    ) -> dict[str, Any]:
        """Submit a work package."""

        request, request_payload = _request_payload_for_storage(payload)
        package_id = _safe_package_id(request.package_id)

        existing_path = self._record_path(package_id)
        if existing_path.exists():
            existing = WorkPackageScheduleRecord.from_dict(_read_json(existing_path))
            if existing.status == STATUS_RUNNING:
                raise WorkPackageSchedulerError(f"work_package_already_running:{package_id}")

        record = WorkPackageScheduleRecord(
            package_id=package_id,
            status=STATUS_QUEUED,
            request=request_payload,
            result=None,
            completion_authority=None,
            error=None,
            created_at=_now(),
            updated_at=_now(),
        )
        _write_json(self._record_path(package_id), record.to_dict())

        if not execute:
            return record.to_dict()

        return self.run(package_id)

    def run(self, package_id: str, *, completion_authority: Any = None) -> dict[str, Any]:
        """Run a queued work package."""

        safe_id = _safe_package_id(package_id)
        path = self._record_path(safe_id)
        if not path.exists():
            raise WorkPackageSchedulerError(f"work_package_not_found:{safe_id}")

        record = WorkPackageScheduleRecord.from_dict(_read_json(path))
        if record.status in TERMINAL_STATUSES:
            return record.to_dict()
        if record.status == STATUS_RUNNING:
            raise WorkPackageSchedulerError(f"work_package_already_running:{safe_id}")

        running = WorkPackageScheduleRecord(
            package_id=record.package_id,
            status=STATUS_RUNNING,
            request=record.request,
            result=record.result,
            completion_authority=None,
            error=None,
            created_at=record.created_at,
            updated_at=_now(),
        )
        _write_json(path, running.to_dict())

        try:
            result = submit_work_package(running.request, repo_root=self.repo_root)
            if completion_authority is None:
                completion_authority = self._completion_authority(running.package_id, result)
            completion_authorized = is_work_package_completion_authority(
                completion_authority,
                package_id=running.package_id,
            )
            completion_authority_summary = (
                completion_authority.to_dict()
                if completion_authorized and callable(getattr(completion_authority, "to_dict", None))
                else None
            )
            completed = WorkPackageScheduleRecord(
                package_id=running.package_id,
                status=STATUS_COMPLETED if completion_authorized else STATUS_FAILED,
                request=running.request,
                result=dict(result),
                completion_authority=completion_authority_summary,
                error=(
                    None
                    if completion_authorized
                    else "work_package_completion_authority_required"
                    if bool(result.get("ok", False))
                    else str(result.get("error") or result.get("reason") or "work_package_failed")
                ),
                created_at=running.created_at,
                updated_at=_now(),
            )
            _write_json(path, completed.to_dict())
            return completed.to_dict()
        except Exception as exc:
            failed = WorkPackageScheduleRecord(
                package_id=running.package_id,
                status=STATUS_FAILED,
                request=running.request,
                result=None,
                completion_authority=None,
                error=f"{type(exc).__name__}: {exc}",
                created_at=running.created_at,
                updated_at=_now(),
            )
            _write_json(path, failed.to_dict())
            return failed.to_dict()

    def status(self, package_id: str) -> dict[str, Any]:
        """Return the stored package status."""

        safe_id = _safe_package_id(package_id)
        path = self._record_path(safe_id)
        if not path.exists():
            return {
                "ok": False,
                "schema": SCHEMA,
                "package_id": safe_id,
                "status": "not_found",
                "error": "work_package_not_found",
            }
        return WorkPackageScheduleRecord.from_dict(_read_json(path)).to_dict()

    def list(self) -> list[dict[str, Any]]:
        """List stored work package records."""

        if not self.state_dir.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.state_dir.glob("*.json")):
            records.append(WorkPackageScheduleRecord.from_dict(_read_json(path)).to_dict())
        return records

    def resume(self, package_id: str) -> dict[str, Any]:
        """Resume metadata safely."""

        record = self.status(package_id)
        status = str(record.get("status") or "")
        if status == "not_found":
            return record
        if status in TERMINAL_STATUSES:
            resumed = dict(record)
            resumed["resumed"] = True
            resumed["resume_mode"] = "metadata"
            return resumed
        if status == STATUS_QUEUED:
            resumed = self.run(str(record.get("package_id") or package_id))
            resumed["resumed"] = True
            resumed["resume_mode"] = "run_queued"
            return resumed
        if status == STATUS_RUNNING:
            blocked = dict(record)
            blocked["ok"] = False
            blocked["resumed"] = False
            blocked["resume_mode"] = "blocked_running"
            blocked["error"] = "running_package_cannot_be_force_resumed"
            return blocked
        return record


def submit_work_package_to_scheduler(
    payload: Mapping[str, Any] | WorkPackageRequest,
    *,
    repo_root: str | Path,
    state_dir: str | Path = "workspace/work_packages",
    execute: bool = True,
) -> dict[str, Any]:
    return WorkPackageScheduler(repo_root=repo_root, state_dir=state_dir).submit(payload, execute=execute)


__all__ = [
    "SCHEMA",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_QUEUED",
    "STATUS_RUNNING",
    "WorkPackageScheduleRecord",
    "WorkPackageScheduler",
    "WorkPackageSchedulerError",
    "submit_work_package_to_scheduler",
]
