from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.runtime.runtime_execution_result_fields import (
    normalize_runtime_execution_fields,
    resolve_blocked,
    resolve_changed_files,
    resolve_evidence,
    resolve_executed,
    resolve_failed,
    resolve_impacted_files,
    resolve_rollback_snapshot,
    resolve_verification_passed,
)
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


def runtime_execution_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _copy_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _payload_from_any(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)

    if hasattr(value, "to_dict"):
        try:
            converted = value.to_dict()
            if isinstance(converted, dict):
                return copy.deepcopy(converted)
        except Exception:
            pass

    payload: dict[str, Any] = {}
    for key in (
        "ok",
        "success",
        "executed",
        "blocked",
        "failed",
        "verified",
        "verification",
        "verification_passed",
        "changed_files",
        "impacted_files",
        "rollback_metadata",
        "rollback_snapshot",
        "evidence",
        "metadata",
        "mutation_metadata",
        "target_path",
        "target_paths",
        "operations",
        "mutations",
        "message",
        "final_answer",
        "error",
        "error_type",
        "task_id",
        "step_type",
        "step_index",
        "step_count",
        "runtime_mode",
        "status",
        "result",
        "execution_id",
        "execution_start_id",
        "execution_type",
        "started_at",
        "finished_at",
        "stdout",
        "stderr",
        "return_code",
        "side_effects",
        "artifacts",
        "rollback_required",
        "lineage",
        "replay_id",
        "repair_session_id",
        "risk_level",
        "risk_metadata",
    ):
        if hasattr(value, key):
            try:
                payload[key] = copy.deepcopy(getattr(value, key))
            except Exception:
                pass
    return payload


def _error_type_from_payload(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("type") or error.get("error_type") or "")
    if error is not None:
        return str(error)
    return str(payload.get("error_type") or "")


def _merge_metadata(*values: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        if isinstance(value, dict):
            merged.update(copy.deepcopy(value))
    return merged


def _source_metadata(source: dict[str, Any]) -> dict[str, Any]:
    metadata = _merge_metadata(source.get("metadata"))
    for key in (
        "verification",
        "changed_files",
        "impacted_files",
        "rollback_metadata",
        "rollback_snapshot",
        "evidence",
        "mutation_metadata",
        "target_path",
        "target_paths",
        "operations",
        "mutations",
    ):
        if key in source:
            metadata[key] = copy.deepcopy(source.get(key))
    return metadata


def _has_explicit_success_signal(payload: dict[str, Any]) -> bool:
    if any(key in payload for key in ("ok", "executed", "success")):
        return True

    nested = payload.get("result")
    if isinstance(nested, dict) and any(
        key in nested for key in ("ok", "executed", "success", "status")
    ):
        return True

    return bool(str(payload.get("status") or "").strip())


def _has_explicit_failure_signal(payload: dict[str, Any]) -> bool:
    if payload.get("blocked") or payload.get("failed"):
        return True
    if payload.get("error") or payload.get("error_type"):
        return True

    status = str(payload.get("status") or "").strip().lower()
    if status in {"error", "failed", "failure", "blocked", "denied", "rejected", "exception"}:
        return True

    nested = payload.get("result")
    if isinstance(nested, dict):
        if nested.get("blocked") or nested.get("failed"):
            return True
        if nested.get("error") or nested.get("error_type"):
            return True
        nested_status = str(nested.get("status") or "").strip().lower()
        if nested_status in {
            "error",
            "failed",
            "failure",
            "blocked",
            "denied",
            "rejected",
            "exception",
        }:
            return True

    return False


def _normalize_payload_ok(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    if "ok" in normalized:
        return normalized
    if _has_explicit_failure_signal(normalized):
        normalized["ok"] = False
        return normalized
    if _has_explicit_success_signal(normalized):
        normalized["ok"] = bool(resolve_executed(normalized, normalized.get("metadata")))
        return normalized
    normalized["ok"] = True
    return normalized


def _status_from_payload(payload: dict[str, Any], *, ok: bool, blocked: bool) -> str:
    status = str(payload.get("status") or "").strip()
    if status:
        return status
    if blocked:
        return "blocked"
    return "succeeded" if ok else "failed"


def _task_id_from_payload(payload: dict[str, Any], task: dict[str, Any]) -> str:
    return str(
        payload.get("task_id")
        or task.get("task_id")
        or task.get("id")
        or task.get("task_name")
        or ""
    )


def _step_type_from_payload(payload: dict[str, Any], step: dict[str, Any]) -> str:
    return str(payload.get("step_type") or step.get("type") or "")


def _canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = _merge_metadata(payload.get("metadata"), _source_metadata(payload))
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        evidence = metadata.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    normalized = normalize_runtime_execution_fields(payload, metadata=metadata, evidence=evidence)
    normalized["metadata"] = _merge_metadata(metadata, normalized.get("metadata"))
    normalized["executed"] = bool(resolve_executed(normalized, metadata, evidence))
    normalized["blocked"] = bool(resolve_blocked(normalized, metadata, evidence))
    normalized["failed"] = bool(resolve_failed(normalized, metadata, evidence))
    normalized["verification_passed"] = bool(
        resolve_verification_passed(normalized, metadata, evidence)
    )

    changed_files = resolve_changed_files(normalized, metadata, evidence)
    impacted_files = resolve_impacted_files(normalized, metadata, evidence)
    if not changed_files:
        changed_files = list(impacted_files)
    if not impacted_files:
        impacted_files = list(changed_files)
    rollback_snapshot = resolve_rollback_snapshot(normalized, metadata, evidence)

    normalized["changed_files"] = copy.deepcopy(changed_files)
    normalized["impacted_files"] = copy.deepcopy(impacted_files)
    normalized["rollback_metadata"] = copy.deepcopy(rollback_snapshot)
    normalized["rollback_snapshot"] = copy.deepcopy(rollback_snapshot)
    normalized["evidence"] = resolve_evidence(
        {
            **normalized,
            "changed_files": copy.deepcopy(changed_files),
            "impacted_files": copy.deepcopy(impacted_files),
            "rollback_metadata": copy.deepcopy(rollback_snapshot),
            "rollback_snapshot": copy.deepcopy(rollback_snapshot),
        },
        normalized["metadata"],
        evidence,
    )
    return normalized


@dataclass(frozen=True, init=False)
class RuntimeExecutionResult:
    ok: bool
    task_id: str = ""
    step_type: str = ""
    step_index: int | None = None
    step_count: int | None = None
    runtime_mode: str = "execute"
    message: str = ""
    final_answer: str = ""
    error_type: str = ""
    timestamp: str = field(default_factory=runtime_execution_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_id: str = ""
    execution_start_id: str = ""
    execution_type: str = ""
    status: str = ""
    started_at: str = ""
    finished_at: str = ""
    stdout: str = ""
    stderr: str = ""
    return_code: int | None = None
    side_effects: tuple[Any, ...] = ()
    artifacts: tuple[Any, ...] = ()
    verified: bool = False
    blocked: bool = False
    rollback_required: bool = False
    lineage: dict[str, Any] = field(default_factory=dict)
    replay_id: str | None = None
    repair_session_id: str | None = None
    risk_level: str = ""
    risk_metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    plan_result: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        ok: bool | None = None,
        *,
        task_id: str = "",
        step_type: str = "",
        step_index: int | None = None,
        step_count: int | None = None,
        runtime_mode: str = "execute",
        message: str = "",
        final_answer: str = "",
        error_type: str = "",
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
        execution_id: str = "",
        execution_start_id: str = "",
        execution_type: str = "",
        status: str = "",
        started_at: str = "",
        finished_at: str = "",
        stdout: str = "",
        stderr: str = "",
        return_code: int | None = None,
        side_effects: tuple[Any, ...] | list[Any] = (),
        artifacts: tuple[Any, ...] | list[Any] = (),
        verified: bool | None = None,
        blocked: bool | None = None,
        rollback_required: bool = False,
        lineage: dict[str, Any] | None = None,
        replay_id: str | None = None,
        repair_session_id: str | None = None,
        risk_level: str = "",
        risk_metadata: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        plan_result: dict[str, Any] | None = None,
        executed: bool | None = None,
        failed: bool | None = None,
        verification_passed: bool | None = None,
        **extra: Any,
    ) -> None:
        seed = {
            **copy.deepcopy(extra),
            "ok": bool(ok if ok is not None else executed if executed is not None else False),
            "task_id": task_id,
            "step_type": step_type,
            "step_index": step_index,
            "step_count": step_count,
            "runtime_mode": runtime_mode,
            "message": message,
            "final_answer": final_answer,
            "error_type": error_type,
            "metadata": copy.deepcopy(metadata or {}),
            "execution_id": execution_id,
            "execution_start_id": execution_start_id,
            "execution_type": execution_type,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "stdout": stdout,
            "stderr": stderr,
            "return_code": return_code,
            "side_effects": tuple(side_effects or ()),
            "artifacts": tuple(artifacts or ()),
            "verified": bool(verified) if verified is not None else None,
            "blocked": bool(blocked) if blocked is not None else None,
            "failed": bool(failed) if failed is not None else None,
            "rollback_required": bool(rollback_required),
            "lineage": copy.deepcopy(lineage or {}),
            "replay_id": replay_id,
            "repair_session_id": repair_session_id,
            "risk_level": risk_level,
            "risk_metadata": copy.deepcopy(risk_metadata or {}),
            "evidence": copy.deepcopy(evidence or {}),
            "plan_result": copy.deepcopy(plan_result or {}),
            "verification_passed": (
                bool(verification_passed) if verification_passed is not None else None
            ),
        }
        canonical = _canonical_payload(seed)
        canonical["ok"] = bool(ok if ok is not None else canonical.get("ok", False))
        canonical["blocked"] = bool(
            blocked if blocked is not None else canonical.get("blocked", False)
        )
        canonical["failed"] = bool(failed if failed is not None else canonical.get("failed", False))
        canonical["verification_passed"] = bool(
            verification_passed
            if verification_passed is not None
            else canonical.get("verification_passed", False)
        )
        canonical["status"] = _status_from_payload(
            {**seed, **canonical},
            ok=bool(canonical["ok"]),
            blocked=bool(canonical["blocked"]),
        )

        values = {
            "ok": bool(canonical["ok"]),
            "task_id": str(task_id or canonical.get("task_id") or ""),
            "step_type": str(step_type or canonical.get("step_type") or ""),
            "step_index": step_index,
            "step_count": step_count,
            "runtime_mode": str(runtime_mode or canonical.get("runtime_mode") or "execute"),
            "message": str(message or canonical.get("message") or ""),
            "final_answer": str(final_answer or canonical.get("final_answer") or ""),
            "error_type": str(error_type or canonical.get("error_type") or ""),
            "timestamp": str(timestamp or canonical.get("timestamp") or runtime_execution_timestamp()),
            "metadata": _merge_metadata(canonical.get("metadata")),
            "execution_id": str(execution_id or canonical.get("execution_id") or ""),
            "execution_start_id": str(
                execution_start_id or canonical.get("execution_start_id") or ""
            ),
            "execution_type": str(execution_type or canonical.get("execution_type") or step_type or ""),
            "status": str(canonical["status"]),
            "started_at": str(started_at or canonical.get("started_at") or ""),
            "finished_at": str(finished_at or canonical.get("finished_at") or ""),
            "stdout": str(stdout or canonical.get("stdout") or ""),
            "stderr": str(stderr or canonical.get("stderr") or ""),
            "return_code": return_code if return_code is not None else canonical.get("return_code"),
            "side_effects": tuple(side_effects or canonical.get("side_effects") or ()),
            "artifacts": tuple(artifacts or canonical.get("artifacts") or ()),
            "verified": bool(
                verified
                if verified is not None
                else canonical.get("verification_passed", canonical.get("verified", False))
            ),
            "blocked": bool(canonical["blocked"]),
            "rollback_required": bool(
                rollback_required or canonical.get("rollback_required", False)
            ),
            "lineage": _copy_mapping(lineage) if lineage is not None else _copy_mapping(canonical.get("lineage")),
            "replay_id": replay_id if replay_id is not None else canonical.get("replay_id"),
            "repair_session_id": (
                repair_session_id
                if repair_session_id is not None
                else canonical.get("repair_session_id")
            ),
            "risk_level": str(risk_level or canonical.get("risk_level") or ""),
            "risk_metadata": (
                _copy_mapping(risk_metadata)
                if risk_metadata is not None
                else _copy_mapping(canonical.get("risk_metadata"))
            ),
            "evidence": _copy_mapping(canonical.get("evidence")),
            "plan_result": _copy_mapping(plan_result),
        }
        for key, value in values.items():
            object.__setattr__(self, key, value)

    @property
    def success(self) -> bool:
        return bool(self.ok)

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "abi_version": RUNTIME_ABI_VERSION,
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "ok": bool(self.ok),
            "success": bool(self.ok),
            "task_id": str(self.task_id or ""),
            "step_type": str(self.step_type or ""),
            "step_index": self.step_index,
            "step_count": self.step_count,
            "runtime_mode": str(self.runtime_mode or "execute"),
            "message": str(self.message or ""),
            "final_answer": str(self.final_answer or ""),
            "error_type": str(self.error_type or ""),
            "timestamp": str(self.timestamp or ""),
            "metadata": copy.deepcopy(self.metadata),
            "execution_id": str(self.execution_id or ""),
            "execution_start_id": str(self.execution_start_id or ""),
            "execution_type": str(self.execution_type or self.step_type or ""),
            "status": str(self.status or ("succeeded" if self.ok else "failed")),
            "started_at": str(self.started_at or ""),
            "finished_at": str(self.finished_at or ""),
            "stdout": str(self.stdout or ""),
            "stderr": str(self.stderr or ""),
            "return_code": self.return_code,
            "side_effects": copy.deepcopy(self.side_effects),
            "artifacts": copy.deepcopy(self.artifacts),
            "verified": bool(self.verified),
            "blocked": bool(self.blocked),
            "rollback_required": bool(self.rollback_required),
            "lineage": copy.deepcopy(self.lineage),
            "replay_id": self.replay_id,
            "repair_session_id": self.repair_session_id,
            "risk_level": str(self.risk_level or ""),
            "risk_metadata": copy.deepcopy(self.risk_metadata),
            "evidence": copy.deepcopy(self.evidence),
        }
        canonical = _canonical_payload(payload)
        canonical["success"] = bool(canonical.get("ok", False))
        canonical["verified"] = bool(canonical.get("verification_passed", self.verified))
        canonical["status"] = _status_from_payload(
            canonical,
            ok=bool(canonical.get("ok", False)),
            blocked=bool(canonical.get("blocked", False)),
        )
        canonical.update(copy.deepcopy(self.plan_result))
        return canonical

    @classmethod
    def from_runtime_mapping(
        cls,
        mapping: Any = None,
        *,
        execution_result: Any = None,
        payload: Any = None,
        result: Any = None,
        step: dict[str, Any] | None = None,
        task: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> "RuntimeExecutionResult":
        source = mapping
        if source is None:
            source = execution_result
        if source is None:
            source = payload
        if source is None:
            source = result
        if source is None:
            source = kwargs

        raw = _normalize_payload_ok(_payload_from_any(source))
        task_mapping = _safe_mapping(task)
        step_mapping = _safe_mapping(step)
        canonical = build_runtime_execution_result(
            raw,
            task=task_mapping,
            step=step_mapping,
            step_index=raw.get("step_index"),
            step_count=raw.get("step_count"),
        )
        return cls(
            ok=bool(canonical.get("ok", False)),
            task_id=str(canonical.get("task_id") or _task_id_from_payload(raw, task_mapping)),
            step_type=str(canonical.get("step_type") or _step_type_from_payload(raw, step_mapping)),
            step_index=canonical.get("step_index"),
            step_count=canonical.get("step_count"),
            runtime_mode=str(canonical.get("runtime_mode") or "execute"),
            message=str(canonical.get("message") or raw.get("message") or ""),
            final_answer=str(canonical.get("final_answer") or raw.get("final_answer") or ""),
            error_type=str(canonical.get("error_type") or _error_type_from_payload(raw)),
            timestamp=str(canonical.get("timestamp") or runtime_execution_timestamp()),
            metadata=_merge_metadata(canonical.get("metadata"), _source_metadata(raw)),
            execution_id=str(raw.get("execution_id") or ""),
            execution_start_id=str(raw.get("execution_start_id") or ""),
            execution_type=str(raw.get("execution_type") or canonical.get("step_type") or ""),
            status=str(raw.get("status") or ""),
            started_at=str(raw.get("started_at") or ""),
            finished_at=str(raw.get("finished_at") or ""),
            stdout=str(raw.get("stdout") or ""),
            stderr=str(raw.get("stderr") or ""),
            return_code=raw.get("return_code"),
            side_effects=tuple(raw.get("side_effects") or ()),
            artifacts=tuple(raw.get("artifacts") or ()),
            verified=bool(raw.get("verified", canonical.get("verification_passed", False))),
            blocked=bool(canonical.get("blocked", False)),
            rollback_required=bool(raw.get("rollback_required", False)),
            lineage=_copy_mapping(raw.get("lineage")),
            replay_id=raw.get("replay_id"),
            repair_session_id=raw.get("repair_session_id"),
            risk_level=str(raw.get("risk_level") or ""),
            risk_metadata=_copy_mapping(raw.get("risk_metadata")),
            evidence=_copy_mapping(canonical.get("evidence")),
            plan_result=_copy_mapping(raw.get("plan_result")),
        )

    @classmethod
    def from_governed_mutation_result(cls, result: Any, **kwargs: Any) -> "RuntimeExecutionResult":
        source = _normalize_payload_ok(_payload_from_any(result))
        task = _safe_mapping(kwargs.get("task"))
        step = _safe_mapping(kwargs.get("step"))
        built = build_runtime_execution_result(
            source,
            task=task,
            step=step,
            step_index=kwargs.get("step_index", source.get("step_index")),
            step_count=kwargs.get("step_count", source.get("step_count")),
        )
        return cls(
            ok=bool(built.get("ok", False)),
            task_id=str(built.get("task_id") or ""),
            step_type=str(built.get("step_type") or "governed_mutation"),
            step_index=built.get("step_index"),
            step_count=built.get("step_count"),
            runtime_mode=str(built.get("runtime_mode") or "execute"),
            message=str(built.get("message") or ""),
            final_answer=str(built.get("final_answer") or ""),
            error_type=str(built.get("error_type") or ""),
            metadata=_merge_metadata(built.get("metadata"), _source_metadata(source)),
            status=str(source.get("status") or ""),
            verified=bool(source.get("verified", built.get("verification_passed", False))),
            blocked=bool(built.get("blocked", False)),
            evidence=_copy_mapping(built.get("evidence")),
        )

    @classmethod
    def from_legacy_plan_result(
        cls,
        *,
        execution_id: str,
        execution_start_id: str,
        execution_type: str,
        started_at: str,
        finished_at: str,
        legacy_result: dict[str, Any] | None = None,
        side_effects: tuple[Any, ...] | list[Any] = (),
        artifacts: tuple[Any, ...] | list[Any] = (),
        lineage: dict[str, Any] | None = None,
        replay_id: str | None = None,
        repair_session_id: str | None = None,
        risk_level: str = "",
        risk_metadata: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **extra: Any,
    ) -> "RuntimeExecutionResult":
        legacy = _safe_mapping(legacy_result)
        verification = legacy.get("final_verify_result")
        if not isinstance(verification, dict):
            verification = legacy.get("verification")
        payload = {
            **copy.deepcopy(legacy),
            "ok": bool(legacy.get("success", legacy.get("ok", False))),
            "verification": verification if isinstance(verification, dict) else {},
            "metadata": _merge_metadata(metadata, extra),
        }
        canonical = _canonical_payload(payload)
        plan_result = {
            key: copy.deepcopy(legacy[key])
            for key in (
                "needs_correction",
                "rounds",
                "final_round_result",
                "final_verify_result",
                "replan_history",
                "replan_rounds_used",
            )
            if key in legacy
        }
        return cls(
            ok=bool(canonical.get("ok", False)),
            execution_id=execution_id,
            execution_start_id=execution_start_id,
            execution_type=execution_type,
            status="succeeded" if canonical.get("ok", False) else "failed",
            started_at=started_at,
            finished_at=finished_at,
            stdout=str(legacy.get("stdout") or ""),
            stderr=str(legacy.get("stderr") or ""),
            return_code=0 if canonical.get("ok", False) else 1,
            side_effects=tuple(side_effects or ()),
            artifacts=tuple(artifacts or ()),
            verified=bool(canonical.get("verification_passed", False)),
            blocked=bool(canonical.get("blocked", False)),
            rollback_required=bool(legacy.get("rollback_required", False)),
            lineage=copy.deepcopy(lineage or {}),
            replay_id=replay_id,
            repair_session_id=repair_session_id,
            risk_level=risk_level,
            risk_metadata=copy.deepcopy(risk_metadata or {}),
            metadata=_merge_metadata(canonical.get("metadata"), metadata, extra),
            evidence=_copy_mapping(canonical.get("evidence")),
            plan_result=plan_result,
        )


def build_runtime_execution_result(
    payload: Any,
    *,
    task: dict[str, Any] | None = None,
    step: dict[str, Any] | None = None,
    step_index: int | None = None,
    step_count: int | None = None,
) -> dict[str, Any]:
    source = _normalize_payload_ok(_payload_from_any(payload))
    task_mapping = _safe_mapping(task)
    step_mapping = _safe_mapping(step)
    effective_step_index = step_index if step_index is not None else source.get("step_index")
    effective_step_count = step_count if step_count is not None else source.get("step_count")
    metadata = _merge_metadata(
        {
            "classification": source.get("classification"),
            "retry_used": bool(source.get("retry_used", False)),
            "summary": source.get("summary"),
        },
        source.get("metadata"),
        _source_metadata(source),
    )
    base = {
        **copy.deepcopy(source),
        "ok": bool(resolve_executed(source, metadata)),
        "task_id": _task_id_from_payload(source, task_mapping),
        "step_type": _step_type_from_payload(source, step_mapping),
        "step_index": effective_step_index,
        "step_count": effective_step_count,
        "runtime_mode": str(source.get("runtime_mode") or step_mapping.get("runtime_mode") or "execute"),
        "message": str(source.get("message") or ""),
        "final_answer": str(source.get("final_answer") or ""),
        "error_type": _error_type_from_payload(source),
        "timestamp": str(source.get("timestamp") or runtime_execution_timestamp()),
        "metadata": metadata,
    }
    canonical = _canonical_payload(base)
    canonical["ok"] = bool(base["ok"])
    if canonical.get("consistency_status") == "mismatch":
        canonical["ok"] = False
        canonical["executed"] = False
    canonical["success"] = bool(canonical["ok"])
    canonical["status"] = _status_from_payload(
        canonical,
        ok=bool(canonical["ok"]),
        blocked=bool(canonical.get("blocked", False)),
    )
    return canonical


def attach_runtime_execution_result(
    payload: dict[str, Any] | None,
    *,
    task: dict[str, Any] | None = None,
    step: dict[str, Any] | None = None,
    step_index: int | None = None,
    step_count: int | None = None,
) -> dict[str, Any]:
    normalized = payload if isinstance(payload, dict) else {}
    normalized["runtime_execution_result"] = build_runtime_execution_result(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )
    return normalized


# ZERO v7.3.32 - Public runtime output sanitizer
# Keep evidence adapter/hook/boundary implementation internals private.
# Important compatibility split:
# - RuntimeExecutionResult.to_dict() must preserve the canonical "evidence" key
#   for governed mutation gateway contracts.
# - Public nested runtime_execution_result mirrors attached to StepExecutor outputs
#   must not expose evidence internals.
def _zero_v7332_public_internal_keys(*, include_evidence: bool = True) -> set[str]:
    try:
        from core.runtime.runtime_execution_result_fields import (
            public_runtime_output_internal_keys,
        )

        keys = set(public_runtime_output_internal_keys())
    except Exception:
        keys = {
            "evidence",
            "evidence_adapter",
            "evidence_events",
            "boundary",
            "boundary_fingerprint",
            "adapter_fingerprint",
            "hook",
            "hook_fingerprint",
        }
    if not include_evidence:
        keys.discard("evidence")
    return keys


class _PublicRuntimeExecutionResultDict(dict):
    """Public-key-safe dict with legacy indexed evidence access."""

    def __init__(self, *args: Any, legacy_evidence: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._legacy_evidence = copy.deepcopy(legacy_evidence) if legacy_evidence else None

    def __getitem__(self, key: str) -> Any:
        if key == "evidence" and key not in self:
            if self._legacy_evidence is None:
                raise KeyError(key)
            return copy.deepcopy(self._legacy_evidence)
        return super().__getitem__(key)


def sanitize_runtime_execution_result(value: Any, *, drop_evidence: bool = True) -> dict[str, Any]:
    """Return a public RuntimeExecutionResult mapping.

    ``drop_evidence=True`` is used for nested public runtime output mirrors.
    ``drop_evidence=False`` is used by RuntimeExecutionResult.to_dict() to keep
    legacy/canonical gateway evidence payloads such as stdout/stderr.
    """

    if not isinstance(value, dict):
        return {}
    legacy_evidence = value.get("evidence") if drop_evidence else None
    if drop_evidence and not legacy_evidence and isinstance(value.get("metadata"), dict):
        legacy_evidence = {"metadata": copy.deepcopy(value["metadata"])}
    internal_keys = _zero_v7332_public_internal_keys(include_evidence=drop_evidence)
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if key in internal_keys:
            continue
        if key == "metadata" and isinstance(item, dict):
            metadata = sanitize_runtime_public_output(item, drop_evidence=drop_evidence)
            if isinstance(metadata, dict):
                sanitized[key] = metadata
            continue
        sanitized[key] = sanitize_runtime_public_output(item, drop_evidence=drop_evidence)
    if drop_evidence:
        return _PublicRuntimeExecutionResultDict(
            sanitized,
            legacy_evidence=legacy_evidence,
        )
    return sanitized


def sanitize_runtime_execution_result_for_public(payload: Any) -> dict[str, Any]:
    """Return a public-safe nested runtime_execution_result mapping."""

    return sanitize_runtime_execution_result(payload, drop_evidence=True)


def sanitize_runtime_public_output(value: Any, *, drop_evidence: bool = True) -> Any:
    """Recursively remove evidence internals from public runtime output."""

    internal_keys = _zero_v7332_public_internal_keys(include_evidence=drop_evidence)
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key in internal_keys:
                continue
            if key == "runtime_execution_result" and isinstance(item, dict):
                sanitized[key] = sanitize_runtime_execution_result(item, drop_evidence=True)
            elif key == "raw" and isinstance(item, dict):
                # adapter_payload.raw is a compatibility mirror. Keep it public-safe
                # instead of letting it reintroduce evidence internals.
                sanitized[key] = sanitize_runtime_public_output(item, drop_evidence=True)
            else:
                sanitized[key] = sanitize_runtime_public_output(item, drop_evidence=drop_evidence)
        return sanitized
    if isinstance(value, list):
        return [sanitize_runtime_public_output(item, drop_evidence=drop_evidence) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_runtime_public_output(item, drop_evidence=drop_evidence) for item in value)
    if isinstance(value, set):
        return {sanitize_runtime_public_output(item, drop_evidence=drop_evidence) for item in value}
    return copy.deepcopy(value)


_ZERO_V7332_ORIGINAL_RUNTIME_EXECUTION_RESULT_TO_DICT = RuntimeExecutionResult.to_dict


def _zero_v7332_runtime_execution_result_to_dict(self: RuntimeExecutionResult) -> dict[str, Any]:
    return sanitize_runtime_execution_result(
        _ZERO_V7332_ORIGINAL_RUNTIME_EXECUTION_RESULT_TO_DICT(self),
        drop_evidence=False,
    )


RuntimeExecutionResult.to_dict = _zero_v7332_runtime_execution_result_to_dict

_ZERO_V7332_ORIGINAL_BUILD_RUNTIME_EXECUTION_RESULT = build_runtime_execution_result


def build_runtime_execution_result(
    payload: Any,
    *,
    task: dict[str, Any] | None = None,
    step: dict[str, Any] | None = None,
    step_index: int | None = None,
    step_count: int | None = None,
) -> dict[str, Any]:
    return sanitize_runtime_execution_result(
        _ZERO_V7332_ORIGINAL_BUILD_RUNTIME_EXECUTION_RESULT(
            payload,
            task=task,
            step=step,
            step_index=step_index,
            step_count=step_count,
        ),
        drop_evidence=False,
    )


def attach_runtime_execution_result(
    payload: dict[str, Any] | None,
    *,
    task: dict[str, Any] | None = None,
    step: dict[str, Any] | None = None,
    step_index: int | None = None,
    step_count: int | None = None,
) -> dict[str, Any]:
    normalized = payload if isinstance(payload, dict) else {}
    normalized["runtime_execution_result"] = build_runtime_execution_result(
        normalized,
        task=task,
        step=step,
        step_index=step_index,
        step_count=step_count,
    )
    # Compatibility contract: mutate and return the same payload object.
    return normalized
