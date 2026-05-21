"""Canonical runtime execution result contract."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.runtime.runtime_seal import attach_runtime_seal
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


__all__ = ["RuntimeExecutionResult"]


@dataclass(frozen=True)
class RuntimeExecutionResult(Mapping[str, Any]):
    execution_id: str
    execution_start_id: str
    execution_type: str
    status: str
    started_at: str
    finished_at: str
    stdout: str
    stderr: str
    return_code: int
    side_effects: tuple[Any, ...]
    artifacts: tuple[Any, ...]
    verified: bool
    blocked: bool
    rollback_required: bool
    lineage: dict[str, Any]
    replay_id: str | None
    repair_session_id: str | None
    risk_level: str = "LOW"
    risk_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    executed: bool | None = None
    failed: bool | None = None
    rolled_back: bool = False
    recovered: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    impacted_files: tuple[str, ...] = ()
    verification_targets: tuple[str, ...] = ()
    rollback_snapshot: dict[str, Any] = field(default_factory=dict)
    runtime_version: str = RUNTIME_KERNEL_VERSION
    abi_version: str = RUNTIME_ABI_VERSION

    def __post_init__(self) -> None:
        executed = self.executed
        if executed is None:
            executed = (
                self.status
                not in {"blocked", "review_required", "dry_run", "pending", "skipped"}
                and not self.blocked
            )
            object.__setattr__(self, "executed", executed)

        failed = self.failed
        if failed is None:
            failed = self.status in {"failed", "error"} or self.return_code != 0
            object.__setattr__(self, "failed", failed)

        if executed is True and not isinstance(self.verified, bool):
            raise ValueError("runtime_execution_result_requires_verification_truth")

        evidence = dict(self.evidence or {})
        if not evidence:
            evidence = {
                "stdout": self.stdout,
                "stderr": self.stderr,
                "return_code": self.return_code,
                "status": self.status,
                "artifacts": list(self.artifacts),
                "side_effect_count": len(self.side_effects),
            }
            object.__setattr__(self, "evidence", evidence)

        if executed is True and not evidence:
            raise ValueError("runtime_execution_result_requires_evidence")

        rollback_snapshot = dict(self.rollback_snapshot or {})
        if not rollback_snapshot:
            rollback_snapshot = {
                "rollback_required": self.rollback_required,
                "rolled_back": self.rolled_back,
                "rollbackable_effects": [
                    getattr(effect, "effect_id", str(effect))
                    for effect in self.side_effects
                    if bool(getattr(effect, "rollbackable", False))
                ],
            }
            object.__setattr__(self, "rollback_snapshot", rollback_snapshot)

    @classmethod
    def from_legacy_plan_result(
        cls,
        *,
        execution_id: str,
        execution_start_id: str,
        execution_type: str,
        started_at: str,
        finished_at: str,
        legacy_result: Mapping[str, Any],
        side_effects: tuple[Any, ...] = (),
        artifacts: tuple[Any, ...] = (),
        lineage: Mapping[str, Any] | None = None,
        replay_id: str | None = None,
        repair_session_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        risk_level: str = "LOW",
        risk_metadata: Mapping[str, Any] | None = None,
    ) -> "RuntimeExecutionResult":
        success = bool(legacy_result.get("success", False))
        final_verify_result = legacy_result.get("final_verify_result")
        verified = bool(
            isinstance(final_verify_result, Mapping)
            and final_verify_result.get("passed", success)
        )
        blocked = bool(legacy_result.get("blocked", False))
        rollback_required = bool(legacy_result.get("rollback_required", False))
        stdout = str(legacy_result.get("stdout") or legacy_result.get("output") or "")
        stderr = str(legacy_result.get("stderr") or "")
        return_code = 0 if success and not blocked else 1
        result_metadata = dict(metadata or {})
        result_metadata["legacy_result"] = dict(legacy_result)

        return cls(
            execution_id=execution_id,
            execution_start_id=execution_start_id,
            execution_type=execution_type,
            status="succeeded" if success and not blocked else "failed",
            started_at=started_at,
            finished_at=finished_at,
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            side_effects=tuple(side_effects),
            artifacts=tuple(artifacts),
            verified=verified,
            blocked=blocked,
            rollback_required=rollback_required,
            lineage=dict(lineage or {}),
            replay_id=replay_id,
            repair_session_id=repair_session_id,
            risk_level=str(risk_level or "LOW"),
            risk_metadata=dict(risk_metadata or {}),
            metadata=result_metadata,
        )

    @classmethod
    def from_runtime_mapping(
        cls,
        *,
        execution_id: str,
        execution_start_id: str,
        execution_type: str,
        result: Mapping[str, Any],
        started_at: str | None = None,
        finished_at: str | None = None,
        lineage: Mapping[str, Any] | None = None,
        replay_id: str | None = None,
        repair_session_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "RuntimeExecutionResult":
        ok_value = result.get("ok")
        success_value = result.get("success")
        status_text = str(result.get("status") or "").strip().lower()
        blocked = bool(result.get("blocked", False)) or status_text in {
            "blocked",
            "review_required",
            "waiting_review",
        }
        failed = bool(result.get("failed", False))
        if ok_value is not None:
            failed = failed or not bool(ok_value)
        elif success_value is not None:
            failed = failed or not bool(success_value)
        else:
            failed = failed or status_text in {"failed", "error", "cancelled", "canceled"}

        return_code = _return_code_from_mapping(result, failed=failed, blocked=blocked)
        verification_passed = _verification_passed_from_mapping(result, failed=failed, blocked=blocked)
        stdout = _first_text(
            result.get("stdout"),
            result.get("output"),
            result.get("message"),
            result.get("final_answer"),
        )
        stderr = _first_text(
            result.get("stderr"),
            _error_text(result.get("error")),
        )
        evidence = _evidence_from_mapping(result, stdout=stdout, stderr=stderr, return_code=return_code)
        rollback_snapshot = _rollback_snapshot_from_mapping(result)
        impacted_files = tuple(_string_list(result.get("impacted_files") or result.get("changed_files")))
        verification_targets = tuple(_string_list(result.get("verification_targets")))
        metadata_payload = {
            **dict(metadata or {}),
            "legacy_result": dict(result),
            "canonicalized_from_mapping": True,
        }

        final_status = "blocked" if blocked else ("failed" if failed else "succeeded")

        return cls(
            execution_id=execution_id,
            execution_start_id=execution_start_id,
            execution_type=execution_type,
            status=final_status,
            started_at=started_at or _utc_now(),
            finished_at=finished_at or _utc_now(),
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            side_effects=(),
            artifacts=tuple(_string_list(result.get("artifacts"))),
            verified=verification_passed,
            blocked=blocked,
            rollback_required=bool(result.get("rollback_required", False)),
            lineage=dict(lineage or {}),
            replay_id=replay_id,
            repair_session_id=repair_session_id,
            metadata=metadata_payload,
            executed=not blocked,
            failed=failed,
            rolled_back=bool(result.get("rolled_back") or result.get("rollback_applied")),
            recovered=bool(result.get("recovered")),
            evidence=evidence,
            impacted_files=impacted_files,
            verification_targets=verification_targets,
            rollback_snapshot=rollback_snapshot,
        )

    @classmethod
    def from_governed_mutation_result(
        cls,
        result: Any,
        *,
        execution_id: str | None = None,
        execution_start_id: str | None = None,
        execution_type: str = "governed_mutation_runtime",
    ) -> "RuntimeExecutionResult":
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        session_id = str(payload.get("session_id") or "governed-mutation")
        evidence = dict(payload.get("evidence") or {})
        artifacts = tuple(
            str(value)
            for value in dict(payload.get("artifact_paths") or {}).values()
            if str(value).strip()
        )
        return cls(
            execution_id=execution_id or f"runtime_execution:{session_id}",
            execution_start_id=execution_start_id or f"execution_start:{session_id}",
            execution_type=execution_type,
            status=(
                "blocked"
                if payload.get("blocked")
                else ("failed" if payload.get("failed") else "succeeded")
            ),
            started_at=str(evidence.get("created_at") or _utc_now()),
            finished_at=_utc_now(),
            stdout=str(evidence.get("stdout") or ""),
            stderr=str(evidence.get("stderr") or ""),
            return_code=0 if not payload.get("failed") and not payload.get("blocked") else 1,
            side_effects=(),
            artifacts=artifacts,
            verified=bool(payload.get("verified")),
            blocked=bool(payload.get("blocked")),
            rollback_required=bool(payload.get("failed") and not payload.get("rolled_back")),
            lineage={
                "session_id": session_id,
                "source": "governed_mutation_runtime",
            },
            replay_id=f"replay:{session_id}",
            repair_session_id=None,
            metadata={
                "governed_mutation_result": payload,
                "canonical_owner": "core.runtime.governed_mutation_runtime",
            },
            executed=bool(payload.get("executed")),
            failed=bool(payload.get("failed")),
            rolled_back=bool(payload.get("rolled_back")),
            recovered=bool(payload.get("recovered")),
            evidence=evidence,
            impacted_files=tuple(_string_list(payload.get("impacted_files"))),
            verification_targets=tuple(_string_list(payload.get("verification_targets"))),
            rollback_snapshot=dict(payload.get("rollback_snapshot") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "runtime_version": self.runtime_version,
            "abi_version": self.abi_version,
            "artifact_type": "runtime_execution_result",
            "execution_id": self.execution_id,
            "execution_start_id": self.execution_start_id,
            "execution_type": self.execution_type,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "side_effects": list(self.side_effects),
            "artifacts": list(self.artifacts),
            "verified": self.verified,
            "verification_passed": self.verified,
            "blocked": self.blocked,
            "rollback_required": self.rollback_required,
            "lineage": dict(self.lineage),
            "replay_id": self.replay_id,
            "repair_session_id": self.repair_session_id,
            "risk_level": self.risk_level,
            "risk_metadata": dict(self.risk_metadata),
            "metadata": dict(self.metadata),
            "executed": bool(self.executed),
            "failed": bool(self.failed),
            "rolled_back": self.rolled_back,
            "recovered": self.recovered,
            "evidence": dict(self.evidence),
            "impacted_files": list(self.impacted_files),
            "verification_targets": list(self.verification_targets),
            "rollback_snapshot": dict(self.rollback_snapshot),
        }
        return attach_runtime_seal(payload, artifact_type="runtime_execution_result")

    def legacy_result(self) -> dict[str, Any]:
        legacy = self.metadata.get("legacy_result")
        if isinstance(legacy, Mapping):
            return dict(legacy)
        return {}

    def __getitem__(self, key: str) -> Any:
        canonical = self.to_dict()
        if key in canonical:
            return canonical[key]
        legacy = self.legacy_result()
        if key in legacy:
            return legacy[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        yielded = set()
        for key in self.to_dict():
            yielded.add(key)
            yield key
        for key in self.legacy_result():
            if key not in yielded:
                yield key

    def __len__(self) -> int:
        return len(list(iter(self)))

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return ""


def _error_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return _first_text(value.get("message"), value.get("error"), value.get("type"))
    return _first_text(value)


def _return_code_from_mapping(
    result: Mapping[str, Any],
    *,
    failed: bool,
    blocked: bool,
) -> int:
    for key in ("return_code", "returncode", "exit_code"):
        value = result.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 1 if failed or blocked else 0


def _verification_passed_from_mapping(
    result: Mapping[str, Any],
    *,
    failed: bool,
    blocked: bool,
) -> bool:
    for key in ("verification_passed", "verified", "verification_ok"):
        if key in result:
            return bool(result.get(key))
    verification = result.get("verification")
    if isinstance(verification, Mapping):
        for key in ("passed", "ok", "verification_ok"):
            if key in verification:
                return bool(verification.get(key))
    return not failed and not blocked


def _evidence_from_mapping(
    result: Mapping[str, Any],
    *,
    stdout: str,
    stderr: str,
    return_code: int,
) -> dict[str, Any]:
    evidence = result.get("evidence")
    if isinstance(evidence, Mapping) and evidence:
        return dict(evidence)
    return {
        "stdout": stdout,
        "stderr": stderr,
        "return_code": return_code,
        "test_results": result.get("test_results") or result.get("verification"),
        "mutation_summary": result.get("mutation_summary") or result.get("result") or dict(result),
        "execution_traces": result.get("execution_trace") or [],
    }


def _rollback_snapshot_from_mapping(result: Mapping[str, Any]) -> dict[str, Any]:
    value = result.get("rollback_snapshot") or result.get("rollback_metadata")
    if isinstance(value, Mapping):
        return dict(value)
    return {
        "rolled_back": bool(result.get("rolled_back") or result.get("rollback_applied")),
        "rollback_required": bool(result.get("rollback_required", False)),
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []
