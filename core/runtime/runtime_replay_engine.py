from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
import hashlib
import json
from typing import Any, Callable

from core.runtime.runtime_execution_session import (
    RuntimeExecutionSession,
    RuntimeExecutionSessionManager,
)
from core.runtime.runtime_status import status_from_replay_state
from core.runtime.runtime_status_transition import (
    is_runtime_status_regression,
    runtime_status_transition_payload,
)


REPLAY_CONSTITUTION_CANONICAL = "canonical"
REPLAY_CONSTITUTION_REVIEW_REQUIRED = "review_required"
REPLAY_CONSTITUTION_BLOCK_RECOMMENDED = "block_recommended"


@dataclass(frozen=True)
class RuntimeReplayRecord:
    replay_id: str
    source_session_id: str
    lifecycle_id: str
    phase: str
    source: str
    payload: Any
    metadata: Any
    original_sequence: int
    replay_sequence: int
    canonical_status: str = "replaying"
    transition_allowed: bool = True
    transition_regression: bool = False
    transition_reason: str = ""
    transition_trigger: str = ""
    transition_source: str = ""
    transition_evidence: dict[str, Any] = field(default_factory=dict)
    enforcement_readiness: str = ""
    enforcement_classification: str = ""
    enforcement_reason: str = ""
    safe_to_enforce: bool = False
    review_required: bool = False
    block_recommended: bool = False
    source_runtime_state_ref: dict[str, Any] = field(default_factory=dict)
    constitutional_continuity: dict[str, Any] = field(default_factory=dict)
    continuity_verified: bool = True
    continuity_break: str = ""
    replay_constitution_status: str = REPLAY_CONSTITUTION_CANONICAL
    enforcement_visibility: bool = True
    enforcement_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeReplayIntegrityRecord:
    original_execution_id: str
    replay_execution_id: str
    original_result_hash: str
    replay_result_hash: str
    integrity_verified: bool
    mismatch_reason: str | None = None


@dataclass(frozen=True)
class RuntimeReplaySession:
    replay_id: str
    source_session_id: str | None
    replay_group: str | None
    records: list[RuntimeReplayRecord]
    sequence: int
    payload: Any
    metadata: Any
    verified: bool
    integrity_records: list[RuntimeReplayIntegrityRecord] = field(default_factory=list)
    canonical_status: str = "replayed"
    transition_allowed: bool = True
    transition_regression: bool = False
    transition_reason: str = ""
    transition_trigger: str = ""
    transition_source: str = ""
    transition_evidence: dict[str, Any] = field(default_factory=dict)
    enforcement_readiness: str = ""
    enforcement_classification: str = ""
    enforcement_reason: str = ""
    safe_to_enforce: bool = False
    review_required: bool = False
    block_recommended: bool = False
    parent_replay_lineage: list[str] = field(default_factory=list)
    source_runtime_state_refs: list[dict[str, Any]] = field(default_factory=list)
    constitutional_continuity: dict[str, Any] = field(default_factory=dict)
    continuity_verified: bool = True
    continuity_break: str = ""
    replay_constitution_status: str = REPLAY_CONSTITUTION_CANONICAL
    enforcement_visibility: bool = True
    enforcement_snapshot: dict[str, Any] = field(default_factory=dict)


class RuntimeReplayRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


def replay_constitution_summary(
    *,
    replay_id: str,
    parent_replay_lineage: list[str] | None = None,
    source_runtime_state_refs: list[dict[str, Any]] | None = None,
    transition: dict[str, Any] | None = None,
    transition_evidence: dict[str, Any] | None = None,
    enforcement_snapshot: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize replay constitutional continuity without enforcing it."""

    lineage = [str(item) for item in (parent_replay_lineage or []) if str(item or "").strip()]
    refs = [
        copy.deepcopy(item)
        for item in (source_runtime_state_refs or [])
        if isinstance(item, dict)
    ]
    transition_payload = copy.deepcopy(transition) if isinstance(transition, dict) else {}
    evidence = (
        copy.deepcopy(transition_evidence)
        if isinstance(transition_evidence, dict)
        else copy.deepcopy(transition_payload.get("transition_evidence"))
        if isinstance(transition_payload.get("transition_evidence"), dict)
        else {}
    )
    snapshot = (
        copy.deepcopy(enforcement_snapshot)
        if isinstance(enforcement_snapshot, dict)
        else copy.deepcopy(transition_payload.get("enforcement_decision"))
        if isinstance(transition_payload.get("enforcement_decision"), dict)
        else {}
    )
    meta = copy.deepcopy(metadata) if isinstance(metadata, dict) else {}

    review_reasons: list[str] = []
    block_reasons: list[str] = []
    if not evidence:
        review_reasons.append("missing_replay_evidence")
    if not refs:
        review_reasons.append("missing_source_runtime_refs")
    if bool(meta.get("parent_lineage_required")) and not lineage:
        review_reasons.append("missing_parent_lineage")
    if replay_id and replay_id in lineage:
        block_reasons.append("replay_loop")
    if len(lineage) != len(set(lineage)):
        block_reasons.append("replay_lineage_corruption")
    if bool(meta.get("replay_lineage_corrupted") or meta.get("lineage_corruption")):
        block_reasons.append("replay_lineage_corruption")
    if bool(transition_payload.get("regression")) and not bool(transition_payload.get("allowed")):
        review_reasons.append("replay_graph_discontinuity")

    from_status = str(transition_payload.get("from_status") or "")
    to_status = str(transition_payload.get("to_status") or "")
    if from_status == "sealed" and to_status not in {"", "sealed"}:
        block_reasons.append("sealed_active_replay_resurrection")
    if from_status == "replayed" and to_status == "queued":
        block_reasons.append("replayed_queued_reset_loop")
    if is_runtime_status_regression(from_status, to_status) and (
        from_status in {"sealed", "replayed"} or to_status == "queued"
    ):
        block_reasons.append("replay_regression")

    status = REPLAY_CONSTITUTION_CANONICAL
    if block_reasons:
        status = REPLAY_CONSTITUTION_BLOCK_RECOMMENDED
    elif review_reasons:
        status = REPLAY_CONSTITUTION_REVIEW_REQUIRED

    continuity_breaks = _sorted_unique([*review_reasons, *block_reasons])
    return {
        "constitutional_continuity": {
            "kind": "runtime_replay_constitution",
            "replay_id": str(replay_id or ""),
            "parent_replay_lineage": list(lineage),
            "source_runtime_state_refs": refs,
            "transition_legal": bool(transition_payload.get("allowed", True)),
            "transition_regression": bool(transition_payload.get("regression", False)),
            "evidence_lineage": copy.deepcopy(evidence),
            "evidence_complete": bool(evidence),
            "enforcement_visibility": bool(snapshot),
            "enforcement_snapshot": copy.deepcopy(snapshot),
            "classification": status,
        },
        "continuity_verified": status == REPLAY_CONSTITUTION_CANONICAL,
        "continuity_break": ",".join(continuity_breaks),
        "replay_constitution_status": status,
        "enforcement_visibility": bool(snapshot),
        "enforcement_snapshot": snapshot,
        "legality": status,
        "evidence_complete": bool(evidence),
        "constitutional_classification": status,
        "review_required": status == REPLAY_CONSTITUTION_REVIEW_REQUIRED,
        "block_recommended": status == REPLAY_CONSTITUTION_BLOCK_RECOMMENDED,
    }


class RuntimeReplayEngine:
    def __init__(
        self,
        session_manager: RuntimeExecutionSessionManager | None = None,
    ) -> None:
        self.session_manager = (
            session_manager
            if session_manager is not None
            else RuntimeExecutionSessionManager()
        )
        self._replays: dict[str, RuntimeReplaySession] = {}
        self._sequence = 0

    def replay_session(
        self,
        replay_id: str,
        source_session_id: str,
        payload: Any = None,
        metadata: Any = None,
        handler: Callable[[RuntimeReplayRecord], None] | None = None,
    ) -> RuntimeReplaySession:
        replay_id = self._validate_replay_id(replay_id)
        self._reject_duplicate_replay_id(replay_id)

        session = self._get_source_session(source_session_id)
        records = self._build_records(replay_id, [session])
        return self._store_replay(
            replay_id=replay_id,
            source_session_id=session.session_id,
            replay_group=session.replay_group,
            records=records,
            payload=payload,
            metadata=metadata,
            handler=handler,
        )

    def replay_group(
        self,
        replay_id: str,
        replay_group: str,
        payload: Any = None,
        metadata: Any = None,
        handler: Callable[[RuntimeReplayRecord], None] | None = None,
    ) -> RuntimeReplaySession:
        replay_id = self._validate_replay_id(replay_id)
        self._reject_duplicate_replay_id(replay_id)

        sessions = self._get_group_sessions(replay_group)
        records = self._build_records(replay_id, sessions)
        return self._store_replay(
            replay_id=replay_id,
            source_session_id=None,
            replay_group=replay_group,
            records=records,
            payload=payload,
            metadata=metadata,
            handler=handler,
        )

    def get_replay(self, replay_id: str) -> RuntimeReplaySession | None:
        replay = self._replays.get(replay_id)
        if replay is None:
            return None

        return self._copy_replay(replay)

    def get_replays(self) -> list[RuntimeReplaySession]:
        return [
            self._copy_replay(replay)
            for replay in self._replays.values()
        ]

    def record_execution_result_integrity(
        self,
        *,
        original_execution_id: str,
        replay_execution_id: str,
        original_result: Any,
        replay_result: Any,
    ) -> RuntimeReplayIntegrityRecord:
        original_hash = self._hash_result(original_result)
        replay_hash = self._hash_result(replay_result)
        verified = original_hash == replay_hash
        return RuntimeReplayIntegrityRecord(
            original_execution_id=str(original_execution_id),
            replay_execution_id=str(replay_execution_id),
            original_result_hash=original_hash,
            replay_result_hash=replay_hash,
            integrity_verified=verified,
            mismatch_reason=None if verified else "result_hash_mismatch",
        )

    def attach_integrity_record(
        self,
        replay_id: str,
        integrity_record: RuntimeReplayIntegrityRecord,
    ) -> RuntimeReplaySession:
        replay = self._replays.get(replay_id)
        if replay is None:
            raise RuntimeReplayRejected(
                "runtime replay target does not exist: "
                f"{replay_id!r}"
            )

        transition = runtime_status_transition_payload(
            replay.canonical_status,
            status_from_replay_state(
                "replayed" if replay.verified and integrity_record.integrity_verified else "failed"
            ),
            source="runtime_replay_engine",
        )
        constitution = replay_constitution_summary(
            replay_id=replay.replay_id,
            parent_replay_lineage=replay.parent_replay_lineage,
            source_runtime_state_refs=replay.source_runtime_state_refs,
            transition=transition,
            metadata=replay.metadata if isinstance(replay.metadata, dict) else None,
        )
        updated = replace(
            replay,
            integrity_records=[
                *replay.integrity_records,
                integrity_record,
            ],
            verified=replay.verified and integrity_record.integrity_verified,
            canonical_status=transition["to_status"],
            transition_allowed=transition["allowed"],
            transition_regression=transition["regression"],
            transition_reason=transition["transition_reason"],
            transition_trigger=transition["transition_trigger"],
            transition_source=transition["transition_source"],
            transition_evidence=transition["transition_evidence"],
            enforcement_readiness=transition["enforcement_readiness"],
            enforcement_classification=transition["enforcement_classification"],
            enforcement_reason=transition["enforcement_reason"],
            safe_to_enforce=transition["safe_to_enforce"],
            review_required=transition["review_required"] or constitution["review_required"],
            block_recommended=transition["block_recommended"] or constitution["block_recommended"],
            constitutional_continuity=constitution["constitutional_continuity"],
            continuity_verified=constitution["continuity_verified"],
            continuity_break=constitution["continuity_break"],
            replay_constitution_status=constitution["replay_constitution_status"],
            enforcement_visibility=constitution["enforcement_visibility"],
            enforcement_snapshot=constitution["enforcement_snapshot"],
        )
        self._replays[replay_id] = updated
        return self._copy_replay(updated)

    def clear(self) -> None:
        self._replays.clear()
        self._sequence = 0

    def _store_replay(
        self,
        replay_id: str,
        source_session_id: str | None,
        replay_group: str | None,
        records: list[RuntimeReplayRecord],
        payload: Any,
        metadata: Any,
        handler: Callable[[RuntimeReplayRecord], None] | None,
    ) -> RuntimeReplaySession:
        if handler is not None:
            for record in records:
                try:
                    handler(record)
                except Exception as exc:
                    raise RuntimeReplayRejected(
                        "runtime replay handler failed",
                        original_exception=exc,
                    ) from exc

        self._sequence += 1
        transition = runtime_status_transition_payload(
            "replaying",
            "replayed",
            source="runtime_replay_engine",
        )
        source_refs = _source_runtime_state_refs(records)
        parent_lineage = _parent_replay_lineage(records)
        constitution = replay_constitution_summary(
            replay_id=replay_id,
            parent_replay_lineage=parent_lineage,
            source_runtime_state_refs=source_refs,
            transition=transition,
            metadata=metadata if isinstance(metadata, dict) else None,
        )
        replay = RuntimeReplaySession(
            replay_id=replay_id,
            source_session_id=source_session_id,
            replay_group=replay_group,
            records=list(records),
            sequence=self._sequence,
            payload=payload,
            metadata=metadata,
            verified=True,
            integrity_records=[],
            canonical_status=status_from_replay_state("replayed"),
            transition_allowed=transition["allowed"],
            transition_regression=transition["regression"],
            transition_reason=transition["transition_reason"],
            transition_trigger=transition["transition_trigger"],
            transition_source=transition["transition_source"],
            transition_evidence=transition["transition_evidence"],
            enforcement_readiness=transition["enforcement_readiness"],
            enforcement_classification=transition["enforcement_classification"],
            enforcement_reason=transition["enforcement_reason"],
            safe_to_enforce=transition["safe_to_enforce"],
            review_required=transition["review_required"] or constitution["review_required"],
            block_recommended=transition["block_recommended"] or constitution["block_recommended"],
            parent_replay_lineage=parent_lineage,
            source_runtime_state_refs=source_refs,
            constitutional_continuity=constitution["constitutional_continuity"],
            continuity_verified=constitution["continuity_verified"],
            continuity_break=constitution["continuity_break"],
            replay_constitution_status=constitution["replay_constitution_status"],
            enforcement_visibility=constitution["enforcement_visibility"],
            enforcement_snapshot=constitution["enforcement_snapshot"],
        )
        self._replays[replay_id] = replay
        return self._copy_replay(replay)

    def _build_records(
        self,
        replay_id: str,
        sessions: list[RuntimeExecutionSession],
    ) -> list[RuntimeReplayRecord]:
        replay_records = []
        replay_sequence = 0

        for session in sorted(sessions, key=lambda item: item.sequence):
            for lifecycle_record in sorted(
                session.lifecycle_records,
                key=lambda item: item.sequence,
            ):
                replay_sequence += 1
                previous_phase = "unknown"
                if replay_records:
                    previous_phase = replay_records[-1].canonical_status
                transition = runtime_status_transition_payload(
                    previous_phase,
                    status_from_replay_state(lifecycle_record.phase),
                    source="runtime_replay_engine",
                )
                source_ref = {
                    "source_session_id": session.session_id,
                    "parent_session_id": session.parent_session_id,
                    "lifecycle_id": lifecycle_record.lifecycle_id,
                    "original_sequence": lifecycle_record.sequence,
                    "replay_sequence": replay_sequence,
                    "canonical_status": transition["to_status"],
                }
                constitution = replay_constitution_summary(
                    replay_id=replay_id,
                    parent_replay_lineage=_session_parent_lineage(session),
                    source_runtime_state_refs=[source_ref],
                    transition=transition,
                    metadata=session.metadata if isinstance(session.metadata, dict) else None,
                )
                replay_records.append(
                    RuntimeReplayRecord(
                        replay_id=replay_id,
                        source_session_id=session.session_id,
                        lifecycle_id=lifecycle_record.lifecycle_id,
                        phase=lifecycle_record.phase,
                        source=lifecycle_record.source,
                        payload=lifecycle_record.payload,
                        metadata=lifecycle_record.metadata,
                        original_sequence=lifecycle_record.sequence,
                        replay_sequence=replay_sequence,
                        canonical_status=transition["to_status"],
                        transition_allowed=transition["allowed"],
                        transition_regression=transition["regression"],
                        transition_reason=transition["transition_reason"],
                        transition_trigger=transition["transition_trigger"],
                        transition_source=transition["transition_source"],
                        transition_evidence=transition["transition_evidence"],
                        enforcement_readiness=transition["enforcement_readiness"],
                        enforcement_classification=transition["enforcement_classification"],
                        enforcement_reason=transition["enforcement_reason"],
                        safe_to_enforce=transition["safe_to_enforce"],
                        review_required=transition["review_required"] or constitution["review_required"],
                        block_recommended=transition["block_recommended"] or constitution["block_recommended"],
                        source_runtime_state_ref=source_ref,
                        constitutional_continuity=constitution["constitutional_continuity"],
                        continuity_verified=constitution["continuity_verified"],
                        continuity_break=constitution["continuity_break"],
                        replay_constitution_status=constitution["replay_constitution_status"],
                        enforcement_visibility=constitution["enforcement_visibility"],
                        enforcement_snapshot=constitution["enforcement_snapshot"],
                    )
                )

        return replay_records

    def _get_source_session(self, source_session_id: str) -> RuntimeExecutionSession:
        try:
            session = self.session_manager.get_session(source_session_id)
        except Exception as exc:
            raise RuntimeReplayRejected(
                "runtime replay source session lookup failed",
                original_exception=exc,
            ) from exc

        if session is None:
            raise RuntimeReplayRejected(
                "runtime replay source session does not exist: "
                f"{source_session_id!r}"
            )

        return session

    def _get_group_sessions(self, replay_group: str) -> list[RuntimeExecutionSession]:
        try:
            sessions = self.session_manager.get_sessions(replay_group=replay_group)
        except Exception as exc:
            raise RuntimeReplayRejected(
                "runtime replay group lookup failed",
                original_exception=exc,
            ) from exc

        if not sessions:
            raise RuntimeReplayRejected(
                "runtime replay group has no sessions: "
                f"{replay_group!r}"
            )

        return sessions

    def _validate_replay_id(self, replay_id: str) -> str:
        if not str(replay_id or "").strip():
            raise RuntimeReplayRejected("runtime replay_id is required")

        return replay_id

    def _reject_duplicate_replay_id(self, replay_id: str) -> None:
        if replay_id in self._replays:
            raise RuntimeReplayRejected(
                f"runtime replay already exists: {replay_id!r}"
            )

    def _copy_replay(self, replay: RuntimeReplaySession) -> RuntimeReplaySession:
        return replace(
            replay,
            records=list(replay.records),
            integrity_records=list(replay.integrity_records),
            parent_replay_lineage=list(replay.parent_replay_lineage),
            source_runtime_state_refs=[copy.deepcopy(item) for item in replay.source_runtime_state_refs],
            constitutional_continuity=copy.deepcopy(replay.constitutional_continuity),
            enforcement_snapshot=copy.deepcopy(replay.enforcement_snapshot),
        )

    def _hash_result(self, result: Any) -> str:
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        payload = json.dumps(
            result,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _session_parent_lineage(session: RuntimeExecutionSession) -> list[str]:
    lineage = []
    if session.parent_session_id:
        lineage.append(str(session.parent_session_id))
    return lineage


def _parent_replay_lineage(records: list[RuntimeReplayRecord]) -> list[str]:
    lineage = []
    for record in records:
        parent = record.source_runtime_state_ref.get("parent_session_id")
        if parent:
            lineage.append(str(parent))
    return _sorted_unique(lineage)


def _source_runtime_state_refs(records: list[RuntimeReplayRecord]) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for record in records:
        ref = copy.deepcopy(record.source_runtime_state_ref)
        key = (
            ref.get("source_session_id"),
            ref.get("lifecycle_id"),
            ref.get("original_sequence"),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _sorted_unique(values: list[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value or "").strip()})


# ============================================================
# AER Workflow Runtime Session replay bridge v1
# ============================================================
def build_replayable_workflow_runtime_session(
    *,
    task: dict[str, Any] | None = None,
    runtime_state: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    source_session_id: str = "",
) -> dict[str, Any]:
    """Return the canonical replayable workflow session envelope.

    This is a read-only replay bridge: it summarizes the runtime execution log
    into the planner -> execution -> verify -> repair -> rollback/retry ->
    replayable session shape without executing recovery or mutation actions.
    """
    try:
        from core.runtime.workflow_runtime_session import build_workflow_runtime_session
    except Exception as exc:  # pragma: no cover - compatibility guard
        return {
            "ok": False,
            "error": "workflow_runtime_session_unavailable",
            "message": str(exc),
        }

    state = copy.deepcopy(runtime_state if isinstance(runtime_state, dict) else {})
    source_id = str(source_session_id or state.get("source_session_id") or "").strip()
    if not source_id:
        existing = state.get("workflow_runtime_session")
        if isinstance(existing, dict):
            source_id = str(existing.get("session_id") or "").strip()
    replay_continuation = copy.deepcopy(state.get("replay_continuation")) if isinstance(state.get("replay_continuation"), dict) else {}
    existing = state.get("workflow_runtime_session")
    if isinstance(existing, dict):
        lineage = existing.get("lineage") if isinstance(existing.get("lineage"), dict) else {}
        if not replay_continuation and isinstance(lineage.get("replay_continuation"), dict):
            replay_continuation = copy.deepcopy(lineage.get("replay_continuation"))
        source_branch_id = str(replay_continuation.get("source_branch_id") or lineage.get("current_branch_id") or "").strip()
        if source_branch_id:
            replay_continuation["source_branch_id"] = source_branch_id
        replay_graph = workflow_replay_graph_summary(lineage=lineage, replay_continuation=replay_continuation)
        replay_continuation = copy.deepcopy(replay_graph["replay_continuation"])
    else:
        lineage = {}
    if source_id:
        replay_continuation["source_session_id"] = source_id
        replay_continuation["continued_by"] = "runtime_replay_engine"
        continued_branch_id = str(
            state.get("current_branch_id")
            or replay_continuation.get("continued_branch_id")
            or replay_continuation.get("source_branch_id")
            or ""
        ).strip()
        if continued_branch_id:
            replay_continuation["continued_branch_id"] = continued_branch_id
        state["source_session_id"] = source_id
        state["replay_continuation"] = replay_continuation

    session = build_workflow_runtime_session(
        task=task if isinstance(task, dict) else {},
        state=state,
        result=result if isinstance(result, dict) else None,
    )
    return {
        "ok": True,
        "workflow_runtime_session": session,
        "replayable": bool(session.get("replayable")),
        "session_id": session.get("session_id"),
        "workflow_id": session.get("workflow_id"),
        "source_session_id": source_id,
        "replay_continuation": copy.deepcopy(session.get("lineage", {}).get("replay_continuation", {})),
        "continuity_summary": copy.deepcopy(session.get("continuity_summary", {})),
        "status": session.get("status"),
    }


def workflow_replay_graph_summary(
    *,
    lineage: dict[str, Any] | None = None,
    replay_continuation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize deterministic workflow graph replay references without side effects."""

    source_lineage = lineage if isinstance(lineage, dict) else {}
    replay = copy.deepcopy(replay_continuation if isinstance(replay_continuation, dict) else {})
    mutation_graph = source_lineage.get("mutation_transaction_graph") if isinstance(source_lineage.get("mutation_transaction_graph"), dict) else {}
    rollback_graph = source_lineage.get("rollback_graph") if isinstance(source_lineage.get("rollback_graph"), dict) else {}
    governance_graph = source_lineage.get("governance_state_graph") if isinstance(source_lineage.get("governance_state_graph"), dict) else {}
    actor_graph = source_lineage.get("actor_worker_graph") if isinstance(source_lineage.get("actor_worker_graph"), dict) else {}
    consensus_graph = source_lineage.get("federated_consensus_graph") if isinstance(source_lineage.get("federated_consensus_graph"), dict) else {}
    self_healing_graph = source_lineage.get("self_healing_governance_graph") if isinstance(source_lineage.get("self_healing_governance_graph"), dict) else {}
    preservation_graph = source_lineage.get("constitutional_preservation_graph") if isinstance(source_lineage.get("constitutional_preservation_graph"), dict) else {}

    mutation_ids = [
        str(item.get("mutation_transaction_id") or "").strip()
        for item in (mutation_graph.get("mutations") if isinstance(mutation_graph.get("mutations"), list) else [])
        if isinstance(item, dict) and str(item.get("mutation_transaction_id") or "").strip()
    ]
    rollback_ids = [
        str(item.get("rollback_id") or "").strip()
        for item in (rollback_graph.get("rollbacks") if isinstance(rollback_graph.get("rollbacks"), list) else [])
        if isinstance(item, dict) and str(item.get("rollback_id") or "").strip()
    ]

    if mutation_ids and not isinstance(replay.get("mutation_transaction_ids"), list):
        replay["mutation_transaction_ids"] = mutation_ids[-20:]
    if rollback_ids and not isinstance(replay.get("rollback_ids"), list):
        replay["rollback_ids"] = rollback_ids[-20:]

    governance_ids = []
    for key, field in (
        ("policy_decision_id", "policy_decisions"),
        ("authority_id", "authority"),
        ("review_id", "reviews"),
        ("approval_id", "approvals"),
        ("governance_resume_id", "resumes"),
        ("enforcement_id", "constitution_enforcements"),
    ):
        for item in governance_graph.get(field) if isinstance(governance_graph.get(field), list) else []:
            value = str(item.get(key) or "").strip() if isinstance(item, dict) else ""
            if value:
                governance_ids.append(value)
    if governance_ids and not isinstance(replay.get("governance_record_ids"), list):
        replay["governance_record_ids"] = governance_ids[-20:]

    worker_ids = [
        str(item.get("worker_id") or "").strip()
        for item in (actor_graph.get("workers") if isinstance(actor_graph.get("workers"), list) else [])
        if isinstance(item, dict) and str(item.get("worker_id") or "").strip()
    ]
    execution_ids = [
        str(item.get("distributed_execution_id") or "").strip()
        for item in (actor_graph.get("distributed_executions") if isinstance(actor_graph.get("distributed_executions"), list) else [])
        if isinstance(item, dict) and str(item.get("distributed_execution_id") or "").strip()
    ]
    if worker_ids and not isinstance(replay.get("worker_ids"), list):
        replay["worker_ids"] = worker_ids[-20:]
    if execution_ids and not isinstance(replay.get("distributed_execution_ids"), list):
        replay["distributed_execution_ids"] = execution_ids[-20:]

    consensus_ids = [
        str(item.get("consensus_id") or "").strip()
        for item in (consensus_graph.get("consensus") if isinstance(consensus_graph.get("consensus"), list) else [])
        if isinstance(item, dict) and str(item.get("consensus_id") or "").strip()
    ]
    if consensus_ids and not isinstance(replay.get("consensus_ids"), list):
        replay["consensus_ids"] = consensus_ids[-20:]

    self_healing_recovery_ids = [
        str(item.get("self_healing_recovery_id") or "").strip()
        for item in (self_healing_graph.get("recoveries") if isinstance(self_healing_graph.get("recoveries"), list) else [])
        if isinstance(item, dict) and str(item.get("self_healing_recovery_id") or "").strip()
    ]
    if self_healing_recovery_ids and not isinstance(replay.get("self_healing_recovery_ids"), list):
        replay["self_healing_recovery_ids"] = self_healing_recovery_ids[-20:]

    preservation_ids = [
        str(item.get("preservation_id") or "").strip()
        for item in (preservation_graph.get("preservations") if isinstance(preservation_graph.get("preservations"), list) else [])
        if isinstance(item, dict) and str(item.get("preservation_id") or "").strip()
    ]
    if preservation_ids and not isinstance(replay.get("preservation_ids"), list):
        replay["preservation_ids"] = preservation_ids[-20:]

    return {
        "schema": "zero.workflow_runtime_session.replay_graph_summary.v1",
        "ok": True,
        "replay_continuation": replay,
        "mutation_transaction_ids": copy.deepcopy(replay.get("mutation_transaction_ids") if isinstance(replay.get("mutation_transaction_ids"), list) else []),
        "rollback_ids": copy.deepcopy(replay.get("rollback_ids") if isinstance(replay.get("rollback_ids"), list) else []),
        "governance_record_ids": copy.deepcopy(replay.get("governance_record_ids") if isinstance(replay.get("governance_record_ids"), list) else []),
        "worker_ids": copy.deepcopy(replay.get("worker_ids") if isinstance(replay.get("worker_ids"), list) else []),
        "distributed_execution_ids": copy.deepcopy(replay.get("distributed_execution_ids") if isinstance(replay.get("distributed_execution_ids"), list) else []),
        "consensus_ids": copy.deepcopy(replay.get("consensus_ids") if isinstance(replay.get("consensus_ids"), list) else []),
        "self_healing_recovery_ids": copy.deepcopy(replay.get("self_healing_recovery_ids") if isinstance(replay.get("self_healing_recovery_ids"), list) else []),
        "preservation_ids": copy.deepcopy(replay.get("preservation_ids") if isinstance(replay.get("preservation_ids"), list) else []),
    }
