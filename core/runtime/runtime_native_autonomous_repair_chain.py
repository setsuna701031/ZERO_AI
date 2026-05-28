from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPAIR_STATUS_CREATED = "created"
REPAIR_STATUS_FAILED_VERIFICATION = "failed_verification"
REPAIR_STATUS_CLASSIFIED = "classified"
REPAIR_STATUS_REPAIR_PLANNED = "repair_planned"
REPAIR_STATUS_REPAIRED = "repaired"
REPAIR_STATUS_VERIFIED = "verified"
REPAIR_STATUS_FINALIZED = "finalized"
REPAIR_STATUS_RETRY_LIMIT_REACHED = "retry_limit_reached"

FAILURE_CLASS_SYNTAX = "syntax"
FAILURE_CLASS_TEST = "test"
FAILURE_CLASS_CONTENT = "content"
FAILURE_CLASS_UNKNOWN = "unknown"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_repair_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class RuntimeRepairAttempt:
    attempt_id: str
    attempt_index: int
    status: str
    failure_class: str = FAILURE_CLASS_UNKNOWN
    failure: dict[str, Any] = field(default_factory=dict)
    mutation_ref: dict[str, Any] = field(default_factory=dict)
    pytest_plan: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    repair_plan: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "attempt_index": self.attempt_index,
            "status": self.status,
            "failure_class": self.failure_class,
            "failure": copy.deepcopy(self.failure),
            "mutation_ref": copy.deepcopy(self.mutation_ref),
            "pytest_plan": copy.deepcopy(self.pytest_plan),
            "verification": copy.deepcopy(self.verification),
            "repair_plan": copy.deepcopy(self.repair_plan),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeRepairAttempt":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            attempt_id=str(data.get("attempt_id") or ""),
            attempt_index=int(data.get("attempt_index") or 0),
            status=str(data.get("status") or REPAIR_STATUS_CREATED),
            failure_class=str(data.get("failure_class") or FAILURE_CLASS_UNKNOWN),
            failure=_copy_dict(data.get("failure")),
            mutation_ref=_copy_dict(data.get("mutation_ref")),
            pytest_plan=_copy_dict(data.get("pytest_plan")),
            verification=_copy_dict(data.get("verification")),
            repair_plan=_copy_dict(data.get("repair_plan")),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeAutonomousRepairRecord:
    repair_chain_id: str
    goal: str
    workspace_root: str
    status: str = REPAIR_STATUS_CREATED
    attempts: list[RuntimeRepairAttempt] = field(default_factory=list)
    final_mutation: dict[str, Any] = field(default_factory=dict)
    final_pytest_plan: dict[str, Any] = field(default_factory=dict)
    final_result: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 2
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repair_chain_id": self.repair_chain_id,
            "goal": self.goal,
            "workspace_root": self.workspace_root,
            "status": self.status,
            "attempts": [item.to_dict() for item in self.attempts],
            "final_mutation": copy.deepcopy(self.final_mutation),
            "final_pytest_plan": copy.deepcopy(self.final_pytest_plan),
            "final_result": copy.deepcopy(self.final_result),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeAutonomousRepairRecord":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            repair_chain_id=str(data.get("repair_chain_id") or ""),
            goal=str(data.get("goal") or ""),
            workspace_root=str(data.get("workspace_root") or "."),
            status=str(data.get("status") or REPAIR_STATUS_CREATED),
            attempts=[RuntimeRepairAttempt.from_dict(x) for x in data.get("attempts") or [] if isinstance(x, dict)],
            final_mutation=_copy_dict(data.get("final_mutation")),
            final_pytest_plan=_copy_dict(data.get("final_pytest_plan")),
            final_result=_copy_dict(data.get("final_result")),
            retry_count=int(data.get("retry_count") or 0),
            max_retries=int(data.get("max_retries") or 2),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


class RuntimeNativeAutonomousRepairChainRejected(RuntimeError):
    pass


PlanFn = Callable[[str, dict[str, Any]], dict[str, Any]]
VerifyFn = Callable[[Any], dict[str, Any]]
RepairPlanFn = Callable[[RuntimeAutonomousRepairRecord, RuntimeRepairAttempt], dict[str, Any]]


class RuntimeNativeAutonomousRepairChain:
    """
    Runtime-native autonomous repair chain.

    Flow:
      initial mutation
        -> verification failure
        -> classify failure
        -> generate repair mutation
        -> re-run verification / targeted pytest plan
        -> repeat until success or retry limit
    """

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        storage_path: str | Path | None = None,
        mutation_loop: Any,
        pytest_planner: Any = None,
        patch_pipeline: Any = None,
        engineering_session: Any = None,
    ) -> None:
        if mutation_loop is None:
            raise RuntimeNativeAutonomousRepairChainRejected("mutation_loop_required")
        self.workspace_root = Path(workspace_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.workspace_root / "workspace" / "runtime_native_autonomous_repair_chain.json"
        self.mutation_loop = mutation_loop
        self.pytest_planner = pytest_planner
        self.patch_pipeline = patch_pipeline
        self.engineering_session = engineering_session
        self._records: dict[str, RuntimeAutonomousRepairRecord] = {}
        self._order: list[str] = []
        self.load()

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = ".", **kwargs: Any) -> "RuntimeNativeAutonomousRepairChain":
        return cls(workspace_root=workspace_root, **kwargs)

    def run_repair_chain(
        self,
        *,
        goal: str,
        initial_plan_fn: PlanFn,
        verify_fn: VerifyFn,
        repair_plan_fn: RepairPlanFn,
        max_retries: int = 2,
        repair_chain_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeAutonomousRepairRecord:
        record = self.create_chain(
            goal=goal,
            max_retries=max_retries,
            repair_chain_id=repair_chain_id,
            metadata=metadata,
        )

        current_plan_fn = initial_plan_fn
        last_mutation = {}
        last_pytest_plan = {}
        last_verification = {}
        final_status = REPAIR_STATUS_RETRY_LIMIT_REACHED

        for attempt_index in range(0, max_retries + 1):
            mutation = self.mutation_loop.run_mutation(
                goal=goal if attempt_index == 0 else f"{goal} repair attempt {attempt_index}",
                plan_fn=current_plan_fn,
                verify_fn=verify_fn,
                max_retries=0,
                metadata={
                    "repair_chain_id": record.repair_chain_id,
                    "attempt_index": attempt_index,
                },
            )
            mutation_payload = mutation.to_dict() if hasattr(mutation, "to_dict") else copy.deepcopy(mutation)
            last_mutation = mutation_payload

            verification = self._latest_verification(mutation_payload)
            last_verification = verification
            failure_class = self.classify_failure(verification)

            pytest_plan = self._plan_pytest(mutation_payload)
            last_pytest_plan = pytest_plan

            if mutation_payload.get("status") == "finalized" and mutation_payload.get("final_result", {}).get("ok") is True:
                attempt = self._make_attempt(
                    record=record,
                    attempt_index=attempt_index,
                    status=REPAIR_STATUS_VERIFIED,
                    failure_class=failure_class,
                    failure={},
                    mutation_ref=mutation_payload,
                    pytest_plan=pytest_plan,
                    verification=verification,
                    repair_plan={},
                )
                record = self._append_attempt(record, attempt)
                final_status = REPAIR_STATUS_FINALIZED
                break

            failure = {
                "failure_class": failure_class,
                "verification": verification,
                "mutation_status": mutation_payload.get("status"),
                "final_result": mutation_payload.get("final_result", {}),
            }

            attempt = self._make_attempt(
                record=record,
                attempt_index=attempt_index,
                status=REPAIR_STATUS_FAILED_VERIFICATION,
                failure_class=failure_class,
                failure=failure,
                mutation_ref=mutation_payload,
                pytest_plan=pytest_plan,
                verification=verification,
                repair_plan={},
            )
            record = self._append_attempt(record, attempt)

            if attempt_index >= max_retries:
                final_status = REPAIR_STATUS_RETRY_LIMIT_REACHED
                break

            repair_plan = repair_plan_fn(record, attempt)
            if not isinstance(repair_plan, dict):
                raise RuntimeNativeAutonomousRepairChainRejected("repair_plan_must_be_dict")

            planned_attempt = RuntimeRepairAttempt.from_dict(
                {
                    **attempt.to_dict(),
                    "status": REPAIR_STATUS_REPAIR_PLANNED,
                    "repair_plan": copy.deepcopy(repair_plan),
                }
            )
            record = self._replace_last_attempt(record, planned_attempt)

            current_plan_fn = self._repair_plan_to_plan_fn(repair_plan)

        result_ok = final_status == REPAIR_STATUS_FINALIZED
        updated = self._replace_record(
            record,
            status=final_status,
            retry_count=max(0, len(record.attempts) - 1),
            final_mutation=last_mutation,
            final_pytest_plan=last_pytest_plan,
            final_result={
                "ok": result_ok,
                "status": final_status,
                "repair_chain_id": record.repair_chain_id,
                "attempts": len(record.attempts),
                "last_verification": last_verification,
            },
        )
        return updated

    def create_chain(
        self,
        *,
        goal: str,
        max_retries: int = 2,
        repair_chain_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeAutonomousRepairRecord:
        goal = self._validate_text("goal", goal)
        if repair_chain_id is None:
            repair_chain_id = "runtime-repair-chain-" + stable_repair_fingerprint(
                {
                    "goal": goal,
                    "workspace_root": str(self.workspace_root),
                    "sequence": len(self._order) + 1,
                }
            )[:16]
        repair_chain_id = self._validate_text("repair_chain_id", repair_chain_id)
        if repair_chain_id in self._records:
            raise RuntimeNativeAutonomousRepairChainRejected(f"repair chain already exists: {repair_chain_id!r}")

        record = RuntimeAutonomousRepairRecord(
            repair_chain_id=repair_chain_id,
            goal=goal,
            workspace_root=str(self.workspace_root),
            max_retries=max(0, int(max_retries)),
            metadata=_copy_dict(metadata),
        )
        self._records[repair_chain_id] = record
        self._order.append(repair_chain_id)
        self.save()
        return copy.deepcopy(record)

    def classify_failure(self, verification: dict[str, Any]) -> str:
        text = " ".join(
            [
                str(verification.get("stdout") or ""),
                str(verification.get("stderr") or ""),
                str(verification.get("command") or ""),
            ]
        ).lower()

        if "syntaxerror" in text or "indentationerror" in text:
            return FAILURE_CLASS_SYNTAX
        if "assert" in text or "failed" in text or "pytest" in text:
            return FAILURE_CLASS_TEST
        if "content" in text or "not found" in text or "mismatch" in text:
            return FAILURE_CLASS_CONTENT
        return FAILURE_CLASS_UNKNOWN

    def get_chain(self, repair_chain_id: str) -> RuntimeAutonomousRepairRecord:
        repair_chain_id = self._validate_text("repair_chain_id", repair_chain_id)
        record = self._records.get(repair_chain_id)
        if record is None:
            raise RuntimeNativeAutonomousRepairChainRejected(f"repair chain does not exist: {repair_chain_id!r}")
        return copy.deepcopy(record)

    def list_chains(self) -> list[RuntimeAutonomousRepairRecord]:
        return [copy.deepcopy(self._records[item]) for item in self._order if item in self._records]

    def health(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self._records.values():
            counts[record.status] = counts.get(record.status, 0) + 1
        return {
            "ok": True,
            "runtime_phase": "runtime_native_autonomous_repair_chain_health",
            "chains": len(self._records),
            "counts": counts,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_autonomous_repair_chain",
            "records": [self._records[item].to_dict() for item in self._order if item in self._records],
        }

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return
        self._records = {}
        self._order = []
        for item in payload.get("records") or []:
            if isinstance(item, dict):
                record = RuntimeAutonomousRepairRecord.from_dict(item)
                if record.repair_chain_id:
                    self._records[record.repair_chain_id] = record
                    self._order.append(record.repair_chain_id)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _latest_verification(self, mutation_payload: dict[str, Any]) -> dict[str, Any]:
        verifications = mutation_payload.get("verifications") or []
        if verifications:
            return copy.deepcopy(verifications[-1])
        return _copy_dict(mutation_payload.get("final_result", {}).get("verification"))

    def _plan_pytest(self, mutation_payload: dict[str, Any]) -> dict[str, Any]:
        if self.pytest_planner is None:
            return {}
        try:
            plan = self.pytest_planner.plan_for_mutation_record(mutation_payload)
            return plan.to_dict() if hasattr(plan, "to_dict") else copy.deepcopy(plan)
        except Exception as exc:
            return {
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }

    def _repair_plan_to_plan_fn(self, repair_plan: dict[str, Any]) -> PlanFn:
        def _plan(goal: str, context: dict[str, Any]) -> dict[str, Any]:
            return copy.deepcopy(repair_plan)

        return _plan

    def _make_attempt(
        self,
        *,
        record: RuntimeAutonomousRepairRecord,
        attempt_index: int,
        status: str,
        failure_class: str,
        failure: dict[str, Any],
        mutation_ref: dict[str, Any],
        pytest_plan: dict[str, Any],
        verification: dict[str, Any],
        repair_plan: dict[str, Any],
    ) -> RuntimeRepairAttempt:
        return RuntimeRepairAttempt(
            attempt_id="runtime-repair-attempt-" + stable_repair_fingerprint(
                {
                    "repair_chain_id": record.repair_chain_id,
                    "attempt_index": attempt_index,
                    "status": status,
                    "mutation": mutation_ref.get("mutation_id", ""),
                }
            )[:16],
            attempt_index=attempt_index,
            status=status,
            failure_class=failure_class,
            failure=_copy_dict(failure),
            mutation_ref=_copy_dict(mutation_ref),
            pytest_plan=_copy_dict(pytest_plan),
            verification=_copy_dict(verification),
            repair_plan=_copy_dict(repair_plan),
        )

    def _append_attempt(
        self,
        record: RuntimeAutonomousRepairRecord,
        attempt: RuntimeRepairAttempt,
    ) -> RuntimeAutonomousRepairRecord:
        return self._replace_record(
            record,
            status=attempt.status,
            attempts=[item.to_dict() for item in record.attempts] + [attempt.to_dict()],
        )

    def _replace_last_attempt(
        self,
        record: RuntimeAutonomousRepairRecord,
        attempt: RuntimeRepairAttempt,
    ) -> RuntimeAutonomousRepairRecord:
        attempts = [item.to_dict() for item in record.attempts]
        if not attempts:
            attempts.append(attempt.to_dict())
        else:
            attempts[-1] = attempt.to_dict()
        return self._replace_record(
            record,
            status=attempt.status,
            attempts=attempts,
        )

    def _replace_record(self, record: RuntimeAutonomousRepairRecord, **updates: Any) -> RuntimeAutonomousRepairRecord:
        latest = self._records.get(record.repair_chain_id, record)
        payload = latest.to_dict()
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimeAutonomousRepairRecord.from_dict(payload)
        self._records[updated.repair_chain_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeNativeAutonomousRepairChainRejected(f"{field_name}_required")
        return text


# ZERO v2.0 - Runtime Loop Integration helpers
# ------------------------------------------------------------
# These helpers keep the autonomous repair chain reusable while giving
# Scheduler / StepExecutor / AgentLoop one stable runtime envelope to carry.

def _zero_v2_repair_record_runtime_envelope(record: RuntimeAutonomousRepairRecord) -> dict[str, Any]:
    payload = record.to_dict() if hasattr(record, "to_dict") else copy.deepcopy(record)
    final_result = payload.get("final_result") if isinstance(payload, dict) else {}
    if not isinstance(final_result, dict):
        final_result = {}
    attempts = payload.get("attempts") if isinstance(payload, dict) else []
    return {
        "ok": bool(final_result.get("ok", False)),
        "runtime_phase": "autonomous_repair_chaining_v2",
        "status": str(payload.get("status") or "unknown"),
        "repair_chain_id": str(payload.get("repair_chain_id") or ""),
        "attempt_count": len(attempts) if isinstance(attempts, list) else 0,
        "retry_count": int(payload.get("retry_count") or 0),
        "max_retries": int(payload.get("max_retries") or 0),
        "final_result": copy.deepcopy(final_result),
        "record": copy.deepcopy(payload),
        "audit_trace": _zero_v2_repair_record_audit_trace(payload),
    }


def _zero_v2_repair_record_audit_trace(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    trace: list[dict[str, Any]] = []
    for item in payload.get("attempts") or []:
        if not isinstance(item, dict):
            continue
        trace.append(
            {
                "type": "autonomous_repair_attempt",
                "attempt_index": item.get("attempt_index"),
                "attempt_id": item.get("attempt_id"),
                "status": item.get("status"),
                "failure_class": item.get("failure_class"),
                "verification_ok": bool((item.get("verification") or {}).get("ok", False)) if isinstance(item.get("verification"), dict) else False,
                "has_repair_plan": bool(item.get("repair_plan")),
                "created_at": item.get("created_at"),
            }
        )
    trace.append(
        {
            "type": "autonomous_repair_finalize",
            "status": payload.get("status"),
            "repair_chain_id": payload.get("repair_chain_id"),
            "retry_count": payload.get("retry_count"),
            "updated_at": payload.get("updated_at"),
        }
    )
    return trace


def _zero_v2_runtime_record_to_execution_result(self: RuntimeNativeAutonomousRepairChain, record: RuntimeAutonomousRepairRecord) -> dict[str, Any]:
    return _zero_v2_repair_record_runtime_envelope(record)


RuntimeNativeAutonomousRepairChain.to_runtime_execution_result = _zero_v2_runtime_record_to_execution_result
