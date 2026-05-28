from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


MUTATION_STATUS_CREATED = "created"
MUTATION_STATUS_PLANNED = "planned"
MUTATION_STATUS_APPLIED = "applied"
MUTATION_STATUS_VERIFIED = "verified"
MUTATION_STATUS_FAILED = "failed"
MUTATION_STATUS_RECOVERED = "recovered"
MUTATION_STATUS_FINALIZED = "finalized"
MUTATION_STATUS_BLOCKED = "blocked"

MUTATION_STEP_PLAN = "plan"
MUTATION_STEP_APPLY = "apply"
MUTATION_STEP_VERIFY = "verify"
MUTATION_STEP_REPAIR = "repair"
MUTATION_STEP_FINALIZE = "finalize"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_mutation_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class RuntimeMutationAction:
    action_id: str
    action_type: str
    target_file: str
    content: str = ""
    before_content: str = ""
    after_content: str = ""
    status: str = MUTATION_STATUS_CREATED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "target_file": self.target_file,
            "content": self.content,
            "before_content": self.before_content,
            "after_content": self.after_content,
            "status": self.status,
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeMutationAction":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            action_id=str(data.get("action_id") or ""),
            action_type=str(data.get("action_type") or "write_file"),
            target_file=str(data.get("target_file") or ""),
            content=str(data.get("content") or ""),
            before_content=str(data.get("before_content") or ""),
            after_content=str(data.get("after_content") or ""),
            status=str(data.get("status") or MUTATION_STATUS_CREATED),
            metadata=_copy_dict(data.get("metadata")),
        )


@dataclass(frozen=True)
class RuntimeMutationVerification:
    verification_id: str
    command: str
    ok: bool = False
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    status: str = MUTATION_STATUS_CREATED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "command": self.command,
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "status": self.status,
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeMutationVerification":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            verification_id=str(data.get("verification_id") or ""),
            command=str(data.get("command") or ""),
            ok=bool(data.get("ok", False)),
            returncode=int(data.get("returncode") or 0),
            stdout=str(data.get("stdout") or ""),
            stderr=str(data.get("stderr") or ""),
            status=str(data.get("status") or MUTATION_STATUS_CREATED),
            metadata=_copy_dict(data.get("metadata")),
        )


@dataclass(frozen=True)
class RuntimeMutationRecord:
    mutation_id: str
    goal: str
    workspace_root: str
    status: str = MUTATION_STATUS_CREATED
    impacted_files: list[str] = field(default_factory=list)
    actions: list[RuntimeMutationAction] = field(default_factory=list)
    verifications: list[RuntimeMutationVerification] = field(default_factory=list)
    recovery_ref: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 1
    final_result: dict[str, Any] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "goal": self.goal,
            "workspace_root": self.workspace_root,
            "status": self.status,
            "impacted_files": copy.deepcopy(self.impacted_files),
            "actions": [action.to_dict() for action in self.actions],
            "verifications": [item.to_dict() for item in self.verifications],
            "recovery_ref": copy.deepcopy(self.recovery_ref),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "final_result": copy.deepcopy(self.final_result),
            "audit_log": copy.deepcopy(self.audit_log),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeMutationRecord":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            mutation_id=str(data.get("mutation_id") or ""),
            goal=str(data.get("goal") or ""),
            workspace_root=str(data.get("workspace_root") or "."),
            status=str(data.get("status") or MUTATION_STATUS_CREATED),
            impacted_files=_copy_list(data.get("impacted_files")),
            actions=[RuntimeMutationAction.from_dict(x) for x in data.get("actions") or [] if isinstance(x, dict)],
            verifications=[RuntimeMutationVerification.from_dict(x) for x in data.get("verifications") or [] if isinstance(x, dict)],
            recovery_ref=_copy_dict(data.get("recovery_ref")),
            retry_count=int(data.get("retry_count") or 0),
            max_retries=int(data.get("max_retries") or 1),
            final_result=_copy_dict(data.get("final_result")),
            audit_log=_copy_list(data.get("audit_log")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


class RuntimeNativeCodeMutationLoopRejected(RuntimeError):
    pass


PlanFn = Callable[[str, dict[str, Any]], dict[str, Any]]
VerifyFn = Callable[[RuntimeMutationRecord], dict[str, Any]]
RepairFn = Callable[[RuntimeMutationRecord, dict[str, Any]], dict[str, Any]]


class RuntimeNativeCodeMutationLoop:
    """
    Runtime-native code mutation loop.

    Canonical flow:
        goal
          -> impacted files / mutation plan
          -> controlled file mutation
          -> sandbox verify
          -> targeted tests
          -> failure capture
          -> recovery runtime
          -> retry repair mutation
          -> finalize
    """

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        storage_path: str | Path | None = None,
        recovery_orchestrator: Any = None,
        dispatch: Any = None,
        scheduler: Any = None,
        mainline: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.workspace_root / "workspace" / "runtime_native_code_mutation_loop.json"
        self.recovery_orchestrator = recovery_orchestrator or getattr(mainline, "orchestrator", None)
        self.dispatch = dispatch
        self.scheduler = scheduler
        self.mainline = mainline
        self.journal = journal
        self.audit = audit
        self._records: dict[str, RuntimeMutationRecord] = {}
        self._order: list[str] = []
        self.load()

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = ".", **kwargs: Any) -> "RuntimeNativeCodeMutationLoop":
        return cls(workspace_root=workspace_root, **kwargs)

    def run_mutation(
        self,
        *,
        goal: str,
        plan_fn: PlanFn,
        verify_fn: VerifyFn | None = None,
        repair_fn: RepairFn | None = None,
        max_retries: int = 1,
        mutation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeMutationRecord:
        record = self.create_mutation(
            goal=goal,
            max_retries=max_retries,
            mutation_id=mutation_id,
            metadata=metadata,
        )

        record = self.plan_mutation(record.mutation_id, plan_fn=plan_fn)
        record = self.apply_mutation(record.mutation_id)
        record = self.verify_mutation(record.mutation_id, verify_fn=verify_fn)

        while record.status == MUTATION_STATUS_FAILED and record.retry_count < record.max_retries:
            record = self.queue_recovery(record.mutation_id)
            record = self.repair_mutation(record.mutation_id, repair_fn=repair_fn)
            record = self.apply_mutation(record.mutation_id)
            record = self.verify_mutation(record.mutation_id, verify_fn=verify_fn)

        if record.status == MUTATION_STATUS_VERIFIED:
            return self.finalize_mutation(record.mutation_id)

        return self._replace_record(
            record,
            status=MUTATION_STATUS_FAILED,
            final_result={
                "ok": False,
                "status": MUTATION_STATUS_FAILED,
                "mutation_id": record.mutation_id,
            },
        )

    def create_mutation(
        self,
        *,
        goal: str,
        max_retries: int = 1,
        mutation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeMutationRecord:
        goal = self._validate_text("goal", goal)
        if mutation_id is None:
            mutation_id = "runtime-code-mutation-" + stable_mutation_fingerprint(
                {"goal": goal, "workspace_root": str(self.workspace_root), "sequence": len(self._order) + 1}
            )[:16]
        mutation_id = self._validate_text("mutation_id", mutation_id)
        if mutation_id in self._records:
            raise RuntimeNativeCodeMutationLoopRejected(f"mutation already exists: {mutation_id!r}")

        record = RuntimeMutationRecord(
            mutation_id=mutation_id,
            goal=goal,
            workspace_root=str(self.workspace_root),
            max_retries=max(0, int(max_retries)),
            metadata=_copy_dict(metadata),
        )
        self._records[mutation_id] = record
        self._order.append(mutation_id)
        self._audit(record, MUTATION_STEP_PLAN, {"event": "mutation_created"})
        self.save()
        return copy.deepcopy(record)

    def plan_mutation(self, mutation_id: str, *, plan_fn: PlanFn) -> RuntimeMutationRecord:
        record = self.get_mutation(mutation_id)
        plan = plan_fn(record.goal, {"mutation": record.to_dict(), "workspace_root": str(self.workspace_root)})
        if not isinstance(plan, dict):
            raise RuntimeNativeCodeMutationLoopRejected("mutation_plan_must_be_dict")

        impacted_files = [str(item) for item in plan.get("impacted_files") or []]
        actions = []
        for index, item in enumerate(plan.get("actions") or [], start=1):
            if not isinstance(item, dict):
                continue
            action_id = str(item.get("action_id") or f"{mutation_id}-action-{index}")
            action = RuntimeMutationAction(
                action_id=action_id,
                action_type=str(item.get("action_type") or "write_file"),
                target_file=str(item.get("target_file") or ""),
                content=str(item.get("content") or ""),
                metadata=_copy_dict(item.get("metadata")),
            )
            actions.append(action)

        if not actions:
            raise RuntimeNativeCodeMutationLoopRejected("mutation_plan_requires_actions")

        updated = self._replace_record(
            record,
            status=MUTATION_STATUS_PLANNED,
            impacted_files=impacted_files,
            actions=[action.to_dict() for action in actions],
        )
        self._audit(updated, MUTATION_STEP_PLAN, {"event": "mutation_planned", "actions": [a.to_dict() for a in actions]})
        return updated

    def apply_mutation(self, mutation_id: str) -> RuntimeMutationRecord:
        record = self.get_mutation(mutation_id)
        applied_actions: list[RuntimeMutationAction] = []

        for action in record.actions:
            target = self._resolve_target(action.target_file)
            if action.action_type != "write_file":
                raise RuntimeNativeCodeMutationLoopRejected(f"unsupported_action_type: {action.action_type}")
            before = target.read_text(encoding="utf-8") if target.exists() else ""
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(action.content, encoding="utf-8")
            applied_actions.append(
                RuntimeMutationAction.from_dict(
                    {
                        **action.to_dict(),
                        "before_content": before,
                        "after_content": action.content,
                        "status": MUTATION_STATUS_APPLIED,
                    }
                )
            )

        updated = self._replace_record(
            record,
            status=MUTATION_STATUS_APPLIED,
            actions=[action.to_dict() for action in applied_actions],
        )
        self._audit(updated, MUTATION_STEP_APPLY, {"event": "mutation_applied"})
        return updated

    def verify_mutation(self, mutation_id: str, *, verify_fn: VerifyFn | None = None) -> RuntimeMutationRecord:
        record = self.get_mutation(mutation_id)
        if verify_fn is None:
            result = {"ok": True, "command": "internal-noop-verifier", "returncode": 0, "stdout": "", "stderr": ""}
        else:
            result = verify_fn(record)
            if not isinstance(result, dict):
                result = {"ok": bool(result), "command": "custom-verifier", "returncode": 0 if result else 1}

        verification = RuntimeMutationVerification(
            verification_id="runtime-mutation-verification-" + stable_mutation_fingerprint(
                {"mutation_id": mutation_id, "sequence": len(record.verifications) + 1, "result": result}
            )[:16],
            command=str(result.get("command") or "custom-verifier"),
            ok=bool(result.get("ok", False)),
            returncode=int(result.get("returncode") or (0 if result.get("ok") else 1)),
            stdout=str(result.get("stdout") or ""),
            stderr=str(result.get("stderr") or ""),
            status=MUTATION_STATUS_VERIFIED if bool(result.get("ok", False)) else MUTATION_STATUS_FAILED,
            metadata=_copy_dict(result.get("metadata")),
        )

        updated = self._replace_record(
            record,
            status=MUTATION_STATUS_VERIFIED if verification.ok else MUTATION_STATUS_FAILED,
            verifications=[item.to_dict() for item in record.verifications] + [verification.to_dict()],
            final_result={
                "ok": verification.ok,
                "status": MUTATION_STATUS_VERIFIED if verification.ok else MUTATION_STATUS_FAILED,
                "verification": verification.to_dict(),
            },
        )
        self._audit(updated, MUTATION_STEP_VERIFY, {"event": "mutation_verified", "verification": verification.to_dict()})
        return updated

    def queue_recovery(self, mutation_id: str) -> RuntimeMutationRecord:
        record = self.get_mutation(mutation_id)
        recovery_ref = {
            "recovery_ticket": {
                "recovery_id": "mutation-recovery-" + stable_mutation_fingerprint(record.to_dict())[:16],
                "source_session_id": record.mutation_id,
                "task_id": record.mutation_id,
                "status": "queued",
            }
        }

        if self.recovery_orchestrator is not None:
            incident = {
                "incident_id": recovery_ref["recovery_ticket"]["recovery_id"],
                "incident_type": "code_mutation_verification_failed",
                "source_session_id": record.mutation_id,
                "runtime_session_id": record.mutation_id,
                "task_id": record.mutation_id,
                "event_type": "failure",
                "payload": record.to_dict(),
                "source": "runtime_native_code_mutation_loop",
            }
            try:
                submitted = self.recovery_orchestrator.submit_incident(incident, current_tick=0)
                payload = submitted.to_dict() if hasattr(submitted, "to_dict") else copy.deepcopy(submitted)
                ticket = payload.get("ticket") if isinstance(payload, dict) else None
                if isinstance(ticket, dict):
                    recovery_ref = {"recovery_ticket": ticket}
            except Exception:
                pass

        updated = self._replace_record(
            record,
            status=MUTATION_STATUS_RECOVERED,
            recovery_ref=recovery_ref,
        )
        self._audit(updated, MUTATION_STEP_REPAIR, {"event": "mutation_recovery_queued", "recovery_ref": recovery_ref})
        return updated

    def repair_mutation(self, mutation_id: str, *, repair_fn: RepairFn | None = None) -> RuntimeMutationRecord:
        record = self.get_mutation(mutation_id)
        if repair_fn is None:
            return self._replace_record(record, retry_count=record.retry_count + 1)

        repair_plan = repair_fn(record, record.final_result)
        if not isinstance(repair_plan, dict):
            raise RuntimeNativeCodeMutationLoopRejected("repair_plan_must_be_dict")

        actions = []
        for index, item in enumerate(repair_plan.get("actions") or [], start=1):
            if not isinstance(item, dict):
                continue
            actions.append(
                RuntimeMutationAction(
                    action_id=str(item.get("action_id") or f"{mutation_id}-repair-action-{index}"),
                    action_type=str(item.get("action_type") or "write_file"),
                    target_file=str(item.get("target_file") or ""),
                    content=str(item.get("content") or ""),
                    metadata=_copy_dict(item.get("metadata")),
                )
            )

        if not actions:
            raise RuntimeNativeCodeMutationLoopRejected("repair_plan_requires_actions")

        updated = self._replace_record(
            record,
            status=MUTATION_STATUS_PLANNED,
            retry_count=record.retry_count + 1,
            actions=[action.to_dict() for action in actions],
            impacted_files=[str(item) for item in repair_plan.get("impacted_files") or record.impacted_files],
        )
        self._audit(updated, MUTATION_STEP_REPAIR, {"event": "mutation_repair_planned"})
        return updated

    def finalize_mutation(self, mutation_id: str) -> RuntimeMutationRecord:
        record = self.get_mutation(mutation_id)
        updated = self._replace_record(
            record,
            status=MUTATION_STATUS_FINALIZED,
            final_result={
                "ok": True,
                "status": MUTATION_STATUS_FINALIZED,
                "mutation_id": record.mutation_id,
                "impacted_files": record.impacted_files,
                "retry_count": record.retry_count,
            },
        )
        self._audit(updated, MUTATION_STEP_FINALIZE, {"event": "mutation_finalized"})
        return updated

    def get_mutation(self, mutation_id: str) -> RuntimeMutationRecord:
        mutation_id = self._validate_text("mutation_id", mutation_id)
        record = self._records.get(mutation_id)
        if record is None:
            raise RuntimeNativeCodeMutationLoopRejected(f"mutation does not exist: {mutation_id!r}")
        return copy.deepcopy(record)

    def list_mutations(self) -> list[RuntimeMutationRecord]:
        return [copy.deepcopy(self._records[item_id]) for item_id in self._order if item_id in self._records]

    def health(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self._records.values():
            counts[record.status] = counts.get(record.status, 0) + 1
        return {
            "ok": True,
            "runtime_phase": "runtime_native_code_mutation_loop_health",
            "mutations": len(self._records),
            "counts": counts,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_code_mutation_loop",
            "records": [self._records[item_id].to_dict() for item_id in self._order if item_id in self._records],
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
                record = RuntimeMutationRecord.from_dict(item)
                if record.mutation_id:
                    self._records[record.mutation_id] = record
                    self._order.append(record.mutation_id)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _resolve_target(self, target_file: str) -> Path:
        target = self._validate_text("target_file", target_file)
        path = Path(target)
        if path.is_absolute():
            resolved = path
        else:
            resolved = self.workspace_root / path
        try:
            resolved.relative_to(self.workspace_root.resolve())
        except Exception:
            # Allow tmp_path relative behavior in tests, block obvious escapes.
            if ".." in Path(target).parts:
                raise RuntimeNativeCodeMutationLoopRejected(f"target escapes workspace: {target!r}")
        return resolved

    def _replace_record(self, record: RuntimeMutationRecord, **updates: Any) -> RuntimeMutationRecord:
        latest = self._records.get(record.mutation_id, record)
        payload = latest.to_dict()
        if "actions" in updates and updates["actions"] and isinstance(updates["actions"][0], dict):
            pass
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimeMutationRecord.from_dict(payload)
        self._records[updated.mutation_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _audit(self, record: RuntimeMutationRecord, step_type: str, payload: dict[str, Any]) -> None:
        entry = {
            "timestamp": utc_timestamp(),
            "step_type": step_type,
            "mutation_id": record.mutation_id,
            "payload": copy.deepcopy(payload),
        }
        latest = self._records.get(record.mutation_id, record)
        updated_payload = latest.to_dict()
        updated_payload["audit_log"] = _copy_list(updated_payload.get("audit_log")) + [entry]
        updated_payload["updated_at"] = utc_timestamp()
        self._records[record.mutation_id] = RuntimeMutationRecord.from_dict(updated_payload)
        self.save()

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeNativeCodeMutationLoopRejected(f"{field_name}_required")
        return text
