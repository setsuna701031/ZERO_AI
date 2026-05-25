from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


WORKFLOW_SESSION_SCHEMA = "zero.workflow_runtime_session.v1"
WORKFLOW_SESSION_PHASES = (
    "planner",
    "execution",
    "verify",
    "repair",
    "rollback_retry",
    "replayable_session",
)
TERMINAL_STATUSES = {"finished", "done", "success", "completed", "failed", "error", "cancelled", "canceled", "timeout"}
VERIFY_STEP_TYPES = {"verify", "verify_file", "verify_python_syntax", "python_syntax_check", "verify_unified_diff", "verify_patch"}
REPAIR_STEP_TYPES = {"governed_repair_mutation", "code_chain_repair", "autonomous_code_repair", "repair", "repair_plan"}
ROLLBACK_STEP_TYPES = {"rollback", "restore", "retry", "apply_patch", "apply_unified_diff"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
        return copy.deepcopy(value)
    except Exception:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v) for v in value]
        return str(value)


def stable_hash(value: Any) -> str:
    payload = json.dumps(_json_safe(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _sorted_unique(values: Iterable[Any]) -> List[str]:
    """Return deterministic unique non-empty strings for continuity summaries.

    This helper is intentionally local and side-effect free.  Several
    continuity validators append duplicate break reasons while walking the
    graph; keeping the result sorted makes test output and persisted summaries
    stable across runs.
    """
    normalized: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = safe_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return sorted(normalized)


def task_id_from(task: Any, state: Any = None) -> str:
    for source in (task, state):
        if isinstance(source, dict):
            for key in ("task_id", "id", "task_name", "name"):
                value = safe_text(source.get(key))
                if value:
                    return value
    return "workflow_task"


def step_type_from(step: Any, result: Any = None) -> str:
    for source in (step, result, result.get("step") if isinstance(result, dict) else None):
        if isinstance(source, dict):
            value = safe_text(source.get("type") or source.get("action") or source.get("step_type")).lower()
            if value:
                return value
    return "unknown"


def infer_phase(step: Any = None, result: Any = None, action: str = "") -> str:
    step_type = step_type_from(step, result)
    action_text = safe_text(action or (result.get("action") if isinstance(result, dict) else "")).lower()
    combined = " ".join([step_type, action_text])
    if step_type in VERIFY_STEP_TYPES or "verify" in combined or "validation" in combined:
        return "verify"
    if step_type in REPAIR_STEP_TYPES or "repair" in combined:
        return "repair"
    if step_type in ROLLBACK_STEP_TYPES or "rollback" in combined or "retry" in combined:
        return "rollback_retry"
    if "planner" in combined or "plan" in combined or "replan" in combined:
        return "planner"
    return "execution"


@dataclass(frozen=True)
class WorkflowRuntimeEvent:
    event_id: str
    workflow_id: str
    session_id: str
    phase: str
    event_type: str
    status: str
    tick: int = 0
    step_index: int = 0
    step_type: str = ""
    ok: bool = True
    message: str = ""
    payload_hash: str = ""
    payload: Any = field(default_factory=dict)
    lineage: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowRuntimeSession:
    schema: str
    session_id: str
    workflow_id: str
    task_id: str
    status: str
    phases: Dict[str, Dict[str, Any]]
    events: List[WorkflowRuntimeEvent]
    replayable: bool
    result_hash: str
    lineage: Dict[str, Any]
    continuity_summary: Dict[str, Any]
    dictionary_contract: Dict[str, Any]
    created_at: str
    updated_at: str
    summary: str = ""
    replay_source: str = "runtime_state.execution_log"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["events"] = [event.to_dict() for event in self.events]
        return data


class WorkflowRuntimeSessionManager:
    """Builds the AER planner -> execution -> verify -> repair -> rollback/retry -> replay session envelope.

    This manager is intentionally read-only with respect to execution authority.
    It records and summarizes runtime state that TaskRunner / StepExecutor already
    produced; it does not execute commands, write repo files, or bypass policy.
    """

    schema = WORKFLOW_SESSION_SCHEMA

    def workflow_id_for(self, task: Dict[str, Any], state: Dict[str, Any] | None = None) -> str:
        existing = (state or {}).get("workflow_runtime_session") if isinstance(state, dict) else None
        if isinstance(existing, dict):
            value = safe_text(existing.get("workflow_id"))
            if value:
                return value
        value = safe_text(
            (state or {}).get("workflow_id") if isinstance(state, dict) else ""
        ) or safe_text(task.get("workflow_id") if isinstance(task, dict) else "")
        if value:
            return value
        return "wfw_" + stable_hash({"task_id": task_id_from(task, state)})[:16]

    def session_id_for(self, task: Dict[str, Any], state: Dict[str, Any] | None = None) -> str:
        existing = (state or {}).get("workflow_runtime_session") if isinstance(state, dict) else None
        if isinstance(existing, dict):
            value = safe_text(existing.get("session_id"))
            if value:
                return value
        value = safe_text(
            (state or {}).get("workflow_session_id") if isinstance(state, dict) else ""
        ) or safe_text(task.get("workflow_session_id") if isinstance(task, dict) else "")
        if value:
            return value
        task_id = task_id_from(task, state)
        seed = {
            "task_id": task_id,
            "created_at": (state or {}).get("created_at") if isinstance(state, dict) else "",
            "workflow_id": self.workflow_id_for(task, state),
        }
        return "wfs_" + stable_hash(seed)[:16]

    def initial_state(self, *, task: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        existing = state.get("workflow_runtime_session") if isinstance(state, dict) else None
        if isinstance(existing, dict) and existing.get("schema") == self.schema:
            return copy.deepcopy(existing)
        session = self.build_session(task=task, state=state)
        return session.to_dict()

    def start_from_intent(
        self,
        *,
        intent: Dict[str, Any],
        task: Dict[str, Any] | None = None,
        state: Dict[str, Any] | None = None,
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        resolved_task = copy.deepcopy(task if isinstance(task, dict) else {})
        resolved_state = copy.deepcopy(state if isinstance(state, dict) else {})
        if isinstance(intent, dict):
            for key in ("task_id", "id", "goal", "name"):
                if key in intent and key not in resolved_task:
                    resolved_task[key] = copy.deepcopy(intent[key])
        return self.append_workflow_record(
            task=resolved_task,
            state=resolved_state,
            phase="planner",
            event_type="intent",
            record=intent if isinstance(intent, dict) else {"intent": intent},
            current_tick=current_tick,
            ok=True,
        )

    def attach_plan_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        plan: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="planner",
            event_type="plan",
            record=plan,
            current_tick=current_tick,
            ok=bool(plan.get("ok", True)) if isinstance(plan, dict) else True,
        )

    def attach_execution_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Dict[str, Any],
        result: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        return self.append_step_result(
            task=task,
            state=state,
            step=step,
            step_result=result,
            current_tick=current_tick,
        )

    def attach_verify_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        verify_step: Dict[str, Any],
        verify_result: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        result = copy.deepcopy(verify_result if isinstance(verify_result, dict) else {})
        result.setdefault("verification_classification", self.classify_verify_result(result))
        return self.append_step_result(
            task=task,
            state=state,
            step=verify_step,
            step_result=result,
            current_tick=current_tick,
        )

    def attach_repair_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        repair_step: Dict[str, Any],
        repair_result: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        return self.append_step_result(
            task=task,
            state=state,
            step=repair_step,
            step_result=repair_result,
            current_tick=current_tick,
        )

    def attach_retry_continuation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        retry_record: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = copy.deepcopy(retry_record if isinstance(retry_record, dict) else {})
        step = record.get("step") if isinstance(record.get("step"), dict) else {"type": "retry"}
        result = record.get("result") if isinstance(record.get("result"), dict) else record
        result = copy.deepcopy(result)
        result.setdefault("action", "retry")
        result.setdefault("ok", True)
        return self.append_step_result(
            task=task,
            state=state,
            step=step,
            step_result=result,
            current_tick=current_tick,
        )

    def create_checkpoint(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        label: str = "",
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        checkpoint = self.build_checkpoint_record(
            task=task,
            state=state,
            session=session,
            label=label,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="checkpoint",
            record=checkpoint,
            current_tick=current_tick,
            ok=True,
        )

    def build_checkpoint_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        session: Dict[str, Any],
        label: str = "",
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        events = session.get("events") if isinstance(session, dict) and isinstance(session.get("events"), list) else []
        workflow_id = safe_text(session.get("workflow_id")) or self.workflow_id_for(task, state)
        session_id = safe_text(session.get("session_id")) or self.session_id_for(task, state)
        event_ids = [
            safe_text(event.get("event_id"))
            for event in events
            if isinstance(event, dict) and safe_text(event.get("event_id"))
        ]
        repair_ancestry = {}
        lineage = session.get("lineage") if isinstance(session.get("lineage"), dict) else {}
        repair_items = lineage.get("repair_ancestry") if isinstance(lineage.get("repair_ancestry"), list) else []
        if repair_items and isinstance(repair_items[-1], dict):
            repair_ancestry = copy.deepcopy(repair_items[-1])
        checkpoint_seed = {
            "workflow_id": workflow_id,
            "session_id": session_id,
            "event_ids": event_ids,
            "current_tick": current_tick,
            "label": label,
        }
        return {
            "schema": "zero.workflow_runtime_session.checkpoint.v1",
            "checkpoint_id": "wfcp_" + stable_hash(checkpoint_seed)[:16],
            "workflow_id": workflow_id,
            "session_id": session_id,
            "task_id": task_id_from(task, state),
            "label": safe_text(label),
            "event_count": len(event_ids),
            "event_ids": event_ids,
            "state_hash": stable_hash(
                {
                    "task_id": task_id_from(task, state),
                    "status": state.get("status") if isinstance(state, dict) else "",
                    "steps": state.get("steps") if isinstance(state, dict) else [],
                    "repair_context": state.get("repair_context") if isinstance(state, dict) else {},
                }
            ),
            "result_hash": safe_text(session.get("result_hash")),
            "repair_ancestry": repair_ancestry,
            "created_at": utc_now(),
        }

    def restore_from_checkpoint(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        checkpoint: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        checkpoint_record = copy.deepcopy(checkpoint if isinstance(checkpoint, dict) else {})
        restore_record = {
            "schema": "zero.workflow_runtime_session.restore.v1",
            "checkpoint_id": safe_text(checkpoint_record.get("checkpoint_id")),
            "source_checkpoint_id": safe_text(checkpoint_record.get("checkpoint_id")),
            "source_workflow_id": safe_text(checkpoint_record.get("workflow_id")),
            "source_session_id": safe_text(checkpoint_record.get("session_id")),
            "workflow_id": self.workflow_id_for(task, state),
            "session_id": self.session_id_for(task, state),
            "event_count": safe_int(checkpoint_record.get("event_count"), 0),
            "checkpoint_event_ids": copy.deepcopy(checkpoint_record.get("event_ids") if isinstance(checkpoint_record.get("event_ids"), list) else []),
            "repair_ancestry": copy.deepcopy(checkpoint_record.get("repair_ancestry") if isinstance(checkpoint_record.get("repair_ancestry"), dict) else {}),
            "restored_at": utc_now(),
        }
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="restore",
            record=restore_record,
            current_tick=current_tick,
            ok=True,
        )

    def attach_resume_continue_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        resume_record: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = copy.deepcopy(resume_record if isinstance(resume_record, dict) else {})
        step = record.get("step") if isinstance(record.get("step"), dict) else {"type": "retry"}
        result = record.get("result") if isinstance(record.get("result"), dict) else record
        result = copy.deepcopy(result)
        result.setdefault("ok", True)
        result.setdefault("action", "resume_continue")
        return self.append_step_result(
            task=task,
            state=state,
            step=step,
            step_result=result,
            current_tick=current_tick,
        )

    def persist_execution_cursor(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        cursor: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        cursor_record = self.build_execution_cursor_record(
            task=task,
            state=state,
            cursor=cursor,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="execution_cursor",
            record=cursor_record,
            current_tick=current_tick,
            ok=True,
        )

    def build_execution_cursor_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        cursor: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        events = session.get("events") if isinstance(session.get("events"), list) else []
        checkpoint_id = self._latest_checkpoint_id(self._events_from_any(events))
        restore_event_id = self._latest_event_id(self._events_from_any(events), event_type="restore")
        step_index = safe_int(cursor.get("step_index") if isinstance(cursor, dict) else state.get("current_step_index"), 0)
        cursor_seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "step_index": step_index,
            "current_tick": current_tick,
            "checkpoint_id": checkpoint_id,
            "restore_event_id": restore_event_id,
        }
        return {
            "schema": "zero.workflow_runtime_session.execution_cursor.v1",
            "cursor_id": "wfcur_" + stable_hash(cursor_seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "step_index": step_index,
            "step_id": safe_text(cursor.get("step_id") if isinstance(cursor, dict) else ""),
            "phase": safe_text(cursor.get("phase") if isinstance(cursor, dict) else "") or "execution",
            "checkpoint_id": safe_text(cursor.get("checkpoint_id") if isinstance(cursor, dict) else "") or checkpoint_id,
            "restore_event_id": safe_text(cursor.get("restore_event_id") if isinstance(cursor, dict) else "") or restore_event_id,
            "parent_event_id": self._latest_event_id(self._events_from_any(events), event_type="restore") or (safe_text(events[-1].get("event_id")) if events and isinstance(events[-1], dict) else ""),
            "created_at": utc_now(),
        }

    def append_execution_memory(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        memory: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        memory_record = self.build_execution_memory_record(
            task=task,
            state=state,
            memory=memory,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="execution_memory",
            record=memory_record,
            current_tick=current_tick,
            ok=True,
        )

    def build_execution_memory_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        memory: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        cursor = self._latest_lineage_item(session, "execution_cursors")
        memory_payload = copy.deepcopy(memory if isinstance(memory, dict) else {})
        memory_seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "cursor_id": cursor.get("cursor_id") if isinstance(cursor, dict) else "",
            "memory": memory_payload,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.execution_memory.v1",
            "memory_id": "wfmem_" + stable_hash(memory_seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "cursor_id": safe_text(cursor.get("cursor_id") if isinstance(cursor, dict) else ""),
            "checkpoint_id": safe_text(cursor.get("checkpoint_id") if isinstance(cursor, dict) else ""),
            "entry_type": safe_text(memory_payload.get("entry_type")) or "execution_memory",
            "payload": _json_safe(memory_payload.get("payload") if "payload" in memory_payload else memory_payload),
            "payload_hash": stable_hash(memory_payload),
            "created_at": utc_now(),
        }

    def create_recovery_resume_point(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        resume_point: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        resume_record = self.build_recovery_resume_point_record(
            task=task,
            state=state,
            resume_point=resume_point,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="recovery_resume_point",
            record=resume_record,
            current_tick=current_tick,
            ok=True,
        )

    def build_recovery_resume_point_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        resume_point: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        cursor = self._latest_lineage_item(session, "execution_cursors")
        memory = self._latest_lineage_item(session, "execution_memory")
        recovery_seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "cursor_id": cursor.get("cursor_id") if isinstance(cursor, dict) else "",
            "memory_id": memory.get("memory_id") if isinstance(memory, dict) else "",
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.recovery_resume_point.v1",
            "recovery_resume_id": "wfrr_" + stable_hash(recovery_seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "cursor_id": safe_text(resume_point.get("cursor_id") if isinstance(resume_point, dict) else "") or safe_text(cursor.get("cursor_id") if isinstance(cursor, dict) else ""),
            "memory_id": safe_text(resume_point.get("memory_id") if isinstance(resume_point, dict) else "") or safe_text(memory.get("memory_id") if isinstance(memory, dict) else ""),
            "checkpoint_id": safe_text(resume_point.get("checkpoint_id") if isinstance(resume_point, dict) else "") or safe_text(cursor.get("checkpoint_id") if isinstance(cursor, dict) else ""),
            "restore_event_id": safe_text(resume_point.get("restore_event_id") if isinstance(resume_point, dict) else "") or safe_text(cursor.get("restore_event_id") if isinstance(cursor, dict) else ""),
            "step_index": safe_int(resume_point.get("step_index") if isinstance(resume_point, dict) else cursor.get("step_index") if isinstance(cursor, dict) else 0, 0),
            "reason": safe_text(resume_point.get("reason") if isinstance(resume_point, dict) else ""),
            "created_at": utc_now(),
        }

    def resume_from_recovery_point(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        recovery_resume_point: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        point = copy.deepcopy(recovery_resume_point if isinstance(recovery_resume_point, dict) else {})
        record = {
            "schema": "zero.workflow_runtime_session.recovery_resume.v1",
            "recovery_resume_id": safe_text(point.get("recovery_resume_id")),
            "cursor_id": safe_text(point.get("cursor_id")),
            "memory_id": safe_text(point.get("memory_id")),
            "checkpoint_id": safe_text(point.get("checkpoint_id")),
            "restore_event_id": safe_text(point.get("restore_event_id")),
            "workflow_id": self.workflow_id_for(task, state),
            "session_id": self.session_id_for(task, state),
            "source_workflow_id": safe_text(point.get("workflow_id")),
            "source_session_id": safe_text(point.get("session_id")),
            "step_index": safe_int(point.get("step_index"), 0),
            "resumed_at": utc_now(),
        }
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="recovery_resume",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def create_execution_graph_node(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        node: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_execution_graph_node_record(
            task=task,
            state=state,
            node=node,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase=safe_text(record.get("phase")) or "execution",
            event_type="execution_graph_node",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_execution_graph_node_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        node: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(node if isinstance(node, dict) else {})
        branch_id = safe_text(payload.get("branch_id")) or self._current_branch_id(session, state)
        phase = safe_text(payload.get("phase")) or "execution"
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "branch_id": branch_id,
            "step_index": safe_int(payload.get("step_index"), 0),
            "label": safe_text(payload.get("label") or payload.get("step_id")),
            "current_tick": current_tick,
        }
        node_id = safe_text(payload.get("node_id")) or "wfgn_" + stable_hash(seed)[:16]
        return {
            "schema": "zero.workflow_runtime_session.execution_graph_node.v1",
            "node_id": node_id,
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "branch_id": branch_id,
            "parent_node_id": safe_text(payload.get("parent_node_id")),
            "step_index": safe_int(payload.get("step_index"), 0),
            "phase": phase if phase in WORKFLOW_SESSION_PHASES else "execution",
            "node_type": safe_text(payload.get("node_type")) or "execution",
            "label": safe_text(payload.get("label") or payload.get("step_id")),
            "payload": _json_safe(payload.get("payload") if "payload" in payload else {}),
            "payload_hash": stable_hash(payload),
            "created_at": utc_now(),
        }

    def connect_graph_edge(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        edge: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_graph_edge_record(task=task, state=state, edge=edge, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="execution",
            event_type="graph_edge",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_graph_edge_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        edge: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(edge if isinstance(edge, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "from_node_id": safe_text(payload.get("from_node_id")),
            "to_node_id": safe_text(payload.get("to_node_id")),
            "edge_type": safe_text(payload.get("edge_type")) or "continuation",
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.graph_edge.v1",
            "edge_id": safe_text(payload.get("edge_id")) or "wfge_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "from_node_id": safe_text(payload.get("from_node_id")),
            "to_node_id": safe_text(payload.get("to_node_id")),
            "edge_type": safe_text(payload.get("edge_type")) or "continuation",
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "created_at": utc_now(),
        }

    def create_branch_fork(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        branch: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_branch_fork_record(task=task, state=state, branch=branch, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="execution",
            event_type="branch_fork",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_branch_fork_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        branch: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(branch if isinstance(branch, dict) else {})
        parent_branch_id = safe_text(payload.get("parent_branch_id")) or self._current_branch_id(session, state)
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "parent_branch_id": parent_branch_id,
            "fork_node_id": safe_text(payload.get("fork_node_id")),
            "name": safe_text(payload.get("name")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.branch_fork.v1",
            "branch_id": safe_text(payload.get("branch_id")) or "wfbr_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "parent_branch_id": parent_branch_id,
            "fork_node_id": safe_text(payload.get("fork_node_id")),
            "name": safe_text(payload.get("name")),
            "created_at": utc_now(),
        }

    def create_join_merge(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        join: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_join_merge_record(task=task, state=state, join=join, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="execution",
            event_type="join_merge",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_join_merge_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        join: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(join if isinstance(join, dict) else {})
        source_branch_ids = [
            safe_text(item)
            for item in (payload.get("source_branch_ids") if isinstance(payload.get("source_branch_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "source_branch_ids": source_branch_ids,
            "target_branch_id": safe_text(payload.get("target_branch_id")),
            "join_node_id": safe_text(payload.get("join_node_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.join_merge.v1",
            "join_id": safe_text(payload.get("join_id")) or "wfj_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "source_branch_ids": source_branch_ids,
            "target_branch_id": safe_text(payload.get("target_branch_id")) or self._current_branch_id(session, state),
            "join_node_id": safe_text(payload.get("join_node_id")),
            "strategy": safe_text(payload.get("strategy")) or "merge",
            "created_at": utc_now(),
        }

    def attach_recovery_dependency(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        dependency: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_recovery_dependency_record(
            task=task,
            state=state,
            dependency=dependency,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="recovery_dependency",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_recovery_dependency_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        dependency: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(dependency if isinstance(dependency, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "source_node_id": safe_text(payload.get("source_node_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "dependency_type": safe_text(payload.get("dependency_type")) or "recovery",
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.recovery_dependency.v1",
            "recovery_dependency_id": safe_text(payload.get("recovery_dependency_id")) or "wfrd_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "source_node_id": safe_text(payload.get("source_node_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "dependency_type": safe_text(payload.get("dependency_type")) or "recovery",
            "required": bool(payload.get("required", True)),
            "created_at": utc_now(),
        }

    def attach_mutation_transaction(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        mutation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_mutation_transaction_record(
            task=task,
            state=state,
            mutation=mutation,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="execution",
            event_type="mutation_transaction",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_mutation_transaction_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        mutation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(mutation if isinstance(mutation, dict) else {})
        branch_id = safe_text(payload.get("branch_id")) or self._current_branch_id(session, state)
        mutation_payload = _json_safe(payload.get("payload") if "payload" in payload else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "node_id": safe_text(payload.get("node_id")),
            "branch_id": branch_id,
            "mutation": mutation_payload,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.mutation_transaction.v1",
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")) or "wfmt_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "node_id": safe_text(payload.get("node_id")),
            "branch_id": branch_id,
            "mutation_type": safe_text(payload.get("mutation_type")) or "mutation",
            "payload": mutation_payload,
            "payload_hash": stable_hash(payload),
            "created_at": utc_now(),
        }

    def attach_mutation_verify_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        verify: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_mutation_verify_record(task=task, state=state, verify=verify, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="verify",
            event_type="mutation_verify",
            record=record,
            current_tick=current_tick,
            ok=bool(record.get("ok", False)),
        )

    def build_mutation_verify_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        verify: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(verify if isinstance(verify, dict) else {})
        mutation_id = safe_text(payload.get("mutation_transaction_id"))
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "mutation_transaction_id": mutation_id,
            "verify_node_id": safe_text(payload.get("verify_node_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.mutation_verify.v1",
            "mutation_verify_id": safe_text(payload.get("mutation_verify_id")) or "wfmv_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "mutation_transaction_id": mutation_id,
            "verify_node_id": safe_text(payload.get("verify_node_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "ok": bool(payload.get("ok", False)),
            "failure_classification": safe_text(payload.get("failure_classification")),
            "payload": _json_safe(payload.get("payload") if "payload" in payload else {}),
            "payload_hash": stable_hash(payload),
            "created_at": utc_now(),
        }

    def attach_rollback_graph_node(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        rollback: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_rollback_graph_record(task=task, state=state, rollback=rollback, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="rollback_retry",
            event_type="rollback_graph_node",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_rollback_graph_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        rollback: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(rollback if isinstance(rollback, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "mutation_verify_id": safe_text(payload.get("mutation_verify_id")),
            "rollback_node_id": safe_text(payload.get("rollback_node_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.rollback_graph_node.v1",
            "rollback_id": safe_text(payload.get("rollback_id")) or "wfrb_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "rollback_node_id": safe_text(payload.get("rollback_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "mutation_verify_id": safe_text(payload.get("mutation_verify_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "retry_node_id": safe_text(payload.get("retry_node_id")),
            "reason": safe_text(payload.get("reason")),
            "created_at": utc_now(),
        }

    def attach_branch_conflict_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        conflict: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_branch_conflict_record(task=task, state=state, conflict=conflict, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="execution",
            event_type="branch_conflict",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_branch_conflict_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        conflict: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(conflict if isinstance(conflict, dict) else {})
        source_branch_ids = [
            safe_text(item)
            for item in (payload.get("source_branch_ids") if isinstance(payload.get("source_branch_ids"), list) else [])
            if safe_text(item)
        ]
        mutation_ids = [
            safe_text(item)
            for item in (payload.get("mutation_transaction_ids") if isinstance(payload.get("mutation_transaction_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "source_branch_ids": source_branch_ids,
            "target_branch_id": safe_text(payload.get("target_branch_id")),
            "mutation_transaction_ids": mutation_ids,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.branch_conflict.v1",
            "conflict_id": safe_text(payload.get("conflict_id")) or "wfcf_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "source_branch_ids": source_branch_ids,
            "target_branch_id": safe_text(payload.get("target_branch_id")) or self._current_branch_id(session, state),
            "conflict_node_id": safe_text(payload.get("conflict_node_id")),
            "mutation_transaction_ids": mutation_ids,
            "reason": safe_text(payload.get("reason")),
            "created_at": utc_now(),
        }

    def attach_graph_reconciliation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        reconciliation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_graph_reconciliation_record(
            task=task,
            state=state,
            reconciliation=reconciliation,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="rollback_retry",
            event_type="graph_reconciliation",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_graph_reconciliation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        reconciliation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(reconciliation if isinstance(reconciliation, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "conflict_id": safe_text(payload.get("conflict_id")),
            "rollback_id": safe_text(payload.get("rollback_id")),
            "retry_node_id": safe_text(payload.get("retry_node_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.graph_reconciliation.v1",
            "reconciliation_id": safe_text(payload.get("reconciliation_id")) or "wfrc_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "conflict_id": safe_text(payload.get("conflict_id")),
            "rollback_id": safe_text(payload.get("rollback_id")),
            "retry_node_id": safe_text(payload.get("retry_node_id")),
            "source_branch_ids": [
                safe_text(item)
                for item in (payload.get("source_branch_ids") if isinstance(payload.get("source_branch_ids"), list) else [])
                if safe_text(item)
            ],
            "target_branch_id": safe_text(payload.get("target_branch_id")) or self._current_branch_id(session, state),
            "strategy": safe_text(payload.get("strategy")) or "rollback_retry_reconcile",
            "created_at": utc_now(),
        }

    def attach_policy_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        decision: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_policy_decision_record(task=task, state=state, decision=decision, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="policy_decision",
            record=record,
            current_tick=current_tick,
            ok=bool(record.get("allowed", False)),
        )

    def build_policy_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        decision: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(decision if isinstance(decision, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "decision": safe_text(payload.get("decision")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.policy_decision.v1",
            "policy_decision_id": safe_text(payload.get("policy_decision_id")) or "wfpol_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "policy_id": safe_text(payload.get("policy_id")),
            "decision": safe_text(payload.get("decision")) or ("allow" if payload.get("allowed", False) else "review_required"),
            "allowed": bool(payload.get("allowed", False)),
            "reason": safe_text(payload.get("reason")),
            "created_at": utc_now(),
        }

    def attach_authority_continuity_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        authority: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_authority_continuity_record(task=task, state=state, authority=authority, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="authority_continuity",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_authority_continuity_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        authority: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(authority if isinstance(authority, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "owner": safe_text(payload.get("execution_owner")),
            "source": safe_text(payload.get("authority_source")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.authority_continuity.v1",
            "authority_id": safe_text(payload.get("authority_id")) or "wfauth_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(payload.get("workflow_id")) or safe_text(session.get("workflow_id")),
            "session_id": safe_text(payload.get("session_id")) or safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "execution_owner": safe_text(payload.get("execution_owner")) or "TaskRunner",
            "authority_source": safe_text(payload.get("authority_source")) or "workflow_runtime_session",
            "allowed": bool(payload.get("allowed", True)),
            "created_at": utc_now(),
        }

    def attach_review_required_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        review: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_review_required_record(task=task, state=state, review=review, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="review_required",
            record=record,
            current_tick=current_tick,
            ok=False,
        )

    def build_review_required_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        review: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(review if isinstance(review, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "policy_decision_id": safe_text(payload.get("policy_decision_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.review_required.v1",
            "review_id": safe_text(payload.get("review_id")) or "wfrev_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "policy_decision_id": safe_text(payload.get("policy_decision_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "transition": "blocked",
            "reason": safe_text(payload.get("reason")),
            "created_at": utc_now(),
        }

    def attach_approval_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        approval: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_approval_record(task=task, state=state, approval=approval, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="approval",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_approval_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        approval: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(approval if isinstance(approval, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "review_id": safe_text(payload.get("review_id")),
            "approver": safe_text(payload.get("approver")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.approval.v1",
            "approval_id": safe_text(payload.get("approval_id")) or "wfapp_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "review_id": safe_text(payload.get("review_id")),
            "policy_decision_id": safe_text(payload.get("policy_decision_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "approver": safe_text(payload.get("approver")) or "governance",
            "approved": bool(payload.get("approved", True)),
            "created_at": utc_now(),
        }

    def attach_governance_resume_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        resume: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_governance_resume_record(task=task, state=state, resume=resume, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="rollback_retry",
            event_type="governance_resume",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_governance_resume_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        resume: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(resume if isinstance(resume, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "approval_id": safe_text(payload.get("approval_id")),
            "resumed_node_id": safe_text(payload.get("resumed_node_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.governance_resume.v1",
            "governance_resume_id": safe_text(payload.get("governance_resume_id")) or "wfgres_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "approval_id": safe_text(payload.get("approval_id")),
            "review_id": safe_text(payload.get("review_id")),
            "resumed_node_id": safe_text(payload.get("resumed_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "transition": "resumed",
            "created_at": utc_now(),
        }

    def attach_constitution_enforcement_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        enforcement: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_constitution_enforcement_record(
            task=task,
            state=state,
            enforcement=enforcement,
            current_tick=current_tick,
        )
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="constitution_enforcement",
            record=record,
            current_tick=current_tick,
            ok=bool(record.get("enforced", True)),
        )

    def build_constitution_enforcement_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        enforcement: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(enforcement if isinstance(enforcement, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "rule_id": safe_text(payload.get("rule_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.constitution_enforcement.v1",
            "enforcement_id": safe_text(payload.get("enforcement_id")) or "wfce_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "mutation_transaction_id": safe_text(payload.get("mutation_transaction_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "rule_id": safe_text(payload.get("rule_id")) or "execution_constitution",
            "enforced": bool(payload.get("enforced", True)),
            "created_at": utc_now(),
        }

    def attach_actor_worker_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        worker: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_actor_worker_record(task=task, state=state, worker=worker, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="actor_worker",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_actor_worker_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        worker: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(worker if isinstance(worker, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "worker_id": safe_text(payload.get("worker_id")),
            "actor_id": safe_text(payload.get("actor_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.actor_worker.v1",
            "worker_id": safe_text(payload.get("worker_id")) or "wfwrk_" + stable_hash(seed)[:16],
            "actor_id": safe_text(payload.get("actor_id")) or safe_text(payload.get("worker_id")),
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "worker_type": safe_text(payload.get("worker_type")) or "runtime_worker",
            "authority_scope": safe_text(payload.get("authority_scope")) or "execution",
            "created_at": utc_now(),
        }

    def attach_worker_federation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        federation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_worker_federation_record(task=task, state=state, federation=federation, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="worker_federation",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_worker_federation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        federation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(federation if isinstance(federation, dict) else {})
        worker_ids = [
            safe_text(item)
            for item in (payload.get("worker_ids") if isinstance(payload.get("worker_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "worker_ids": worker_ids,
            "coordinator_worker_id": safe_text(payload.get("coordinator_worker_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.worker_federation.v1",
            "federation_id": safe_text(payload.get("federation_id")) or "wffed_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "worker_ids": worker_ids,
            "coordinator_worker_id": safe_text(payload.get("coordinator_worker_id")),
            "created_at": utc_now(),
        }

    def attach_distributed_execution_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        execution: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_distributed_execution_record(task=task, state=state, execution=execution, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="execution",
            event_type="distributed_execution",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_distributed_execution_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        execution: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(execution if isinstance(execution, dict) else {})
        parent_worker_ids = [
            safe_text(item)
            for item in (payload.get("parent_worker_ids") if isinstance(payload.get("parent_worker_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "worker_id": safe_text(payload.get("worker_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.distributed_execution.v1",
            "distributed_execution_id": safe_text(payload.get("distributed_execution_id")) or "wfdx_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "worker_id": safe_text(payload.get("worker_id")),
            "parent_worker_ids": parent_worker_ids,
            "federation_id": safe_text(payload.get("federation_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "branch_id": safe_text(payload.get("branch_id")) or self._current_branch_id(session, state),
            "created_at": utc_now(),
        }

    def attach_distributed_recovery_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        recovery: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_distributed_recovery_record(task=task, state=state, recovery=recovery, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="distributed_recovery",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_distributed_recovery_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        recovery: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(recovery if isinstance(recovery, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "source_execution_id": safe_text(payload.get("source_execution_id")),
            "recovery_worker_id": safe_text(payload.get("recovery_worker_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.distributed_recovery.v1",
            "distributed_recovery_id": safe_text(payload.get("distributed_recovery_id")) or "wfdr_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "source_execution_id": safe_text(payload.get("source_execution_id")),
            "recovery_worker_id": safe_text(payload.get("recovery_worker_id")),
            "recovery_node_id": safe_text(payload.get("recovery_node_id")),
            "created_at": utc_now(),
        }

    def attach_federated_authority_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        authority: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_federated_authority_record(task=task, state=state, authority=authority, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="federated_authority",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_federated_authority_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        authority: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(authority if isinstance(authority, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "worker_id": safe_text(payload.get("worker_id")),
            "authority_id": safe_text(payload.get("authority_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.federated_authority.v1",
            "federated_authority_id": safe_text(payload.get("federated_authority_id")) or "wffauth_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(payload.get("workflow_id")) or safe_text(session.get("workflow_id")),
            "session_id": safe_text(payload.get("session_id")) or safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "worker_id": safe_text(payload.get("worker_id")),
            "authority_id": safe_text(payload.get("authority_id")),
            "federation_id": safe_text(payload.get("federation_id")),
            "allowed": bool(payload.get("allowed", True)),
            "created_at": utc_now(),
        }

    def attach_distributed_governance_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        governance: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_distributed_governance_record(task=task, state=state, governance=governance, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="distributed_governance",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_distributed_governance_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        governance: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(governance if isinstance(governance, dict) else {})
        governance_record_ids = [
            safe_text(item)
            for item in (payload.get("governance_record_ids") if isinstance(payload.get("governance_record_ids"), list) else [])
            if safe_text(item)
        ]
        worker_ids = [
            safe_text(item)
            for item in (payload.get("worker_ids") if isinstance(payload.get("worker_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "worker_ids": worker_ids,
            "governance_record_ids": governance_record_ids,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.distributed_governance.v1",
            "distributed_governance_id": safe_text(payload.get("distributed_governance_id")) or "wfdg_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "worker_ids": worker_ids,
            "governance_record_ids": governance_record_ids,
            "federation_id": safe_text(payload.get("federation_id")),
            "created_at": utc_now(),
        }

    def attach_worker_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        decision: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_worker_decision_record(task=task, state=state, decision=decision, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="execution",
            event_type="worker_decision",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_worker_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        decision: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(decision if isinstance(decision, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "worker_id": safe_text(payload.get("worker_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "decision": safe_text(payload.get("decision")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.worker_decision.v1",
            "worker_decision_id": safe_text(payload.get("worker_decision_id")) or safe_text(payload.get("decision_id")) or "wfwd_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "worker_id": safe_text(payload.get("worker_id")),
            "federation_id": safe_text(payload.get("federation_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "decision": safe_text(payload.get("decision")),
            "decision_value": _json_safe(payload.get("decision_value", payload.get("decision"))),
            "created_at": utc_now(),
        }

    def attach_arbitration_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        arbitration: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_arbitration_decision_record(task=task, state=state, arbitration=arbitration, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="arbitration_decision",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_arbitration_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        arbitration: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(arbitration if isinstance(arbitration, dict) else {})
        conflicting_decision_ids = [
            safe_text(item)
            for item in (payload.get("conflicting_decision_ids") if isinstance(payload.get("conflicting_decision_ids"), list) else [])
            if safe_text(item)
        ]
        worker_ids = [
            safe_text(item)
            for item in (payload.get("worker_ids") if isinstance(payload.get("worker_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "conflicting_decision_ids": conflicting_decision_ids,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.arbitration_decision.v1",
            "arbitration_id": safe_text(payload.get("arbitration_id")) or "wfarb_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "conflicting_decision_ids": conflicting_decision_ids,
            "worker_ids": worker_ids,
            "federation_id": safe_text(payload.get("federation_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "decision": safe_text(payload.get("decision")),
            "created_at": utc_now(),
        }

    def attach_authority_quorum_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        quorum: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_authority_quorum_record(task=task, state=state, quorum=quorum, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="authority_quorum",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_authority_quorum_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        quorum: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(quorum if isinstance(quorum, dict) else {})
        authority_worker_ids = [
            safe_text(item)
            for item in (payload.get("authority_worker_ids") if isinstance(payload.get("authority_worker_ids"), list) else payload.get("worker_ids") if isinstance(payload.get("worker_ids"), list) else [])
            if safe_text(item)
        ]
        threshold = safe_int(payload.get("threshold"), len(authority_worker_ids))
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "authority_worker_ids": authority_worker_ids,
            "threshold": threshold,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.authority_quorum.v1",
            "quorum_id": safe_text(payload.get("quorum_id")) or "wfqrm_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "authority_worker_ids": authority_worker_ids,
            "federation_id": safe_text(payload.get("federation_id")),
            "threshold": threshold,
            "created_at": utc_now(),
        }

    def attach_consensus_vote_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        vote: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_consensus_vote_record(task=task, state=state, vote=vote, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="consensus_vote",
            record=record,
            current_tick=current_tick,
            ok=bool(record.get("accepted", True)),
        )

    def build_consensus_vote_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        vote: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(vote if isinstance(vote, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "quorum_id": safe_text(payload.get("quorum_id")),
            "worker_id": safe_text(payload.get("worker_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.consensus_vote.v1",
            "vote_id": safe_text(payload.get("vote_id")) or "wfvote_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "quorum_id": safe_text(payload.get("quorum_id")),
            "worker_id": safe_text(payload.get("worker_id")),
            "federation_id": safe_text(payload.get("federation_id")),
            "vote": safe_text(payload.get("vote")) or safe_text(payload.get("decision")),
            "accepted": bool(payload.get("accepted", True)),
            "created_at": utc_now(),
        }

    def attach_federated_consensus_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        consensus: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_federated_consensus_record(task=task, state=state, consensus=consensus, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="federated_consensus",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_federated_consensus_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        consensus: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(consensus if isinstance(consensus, dict) else {})
        vote_ids = [
            safe_text(item)
            for item in (payload.get("vote_ids") if isinstance(payload.get("vote_ids"), list) else [])
            if safe_text(item)
        ]
        required_vote_ids = [
            safe_text(item)
            for item in (payload.get("required_vote_ids") if isinstance(payload.get("required_vote_ids"), list) else vote_ids)
            if safe_text(item)
        ]
        worker_ids = [
            safe_text(item)
            for item in (payload.get("worker_ids") if isinstance(payload.get("worker_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "arbitration_id": safe_text(payload.get("arbitration_id")),
            "required_vote_ids": required_vote_ids,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.federated_consensus.v1",
            "consensus_id": safe_text(payload.get("consensus_id")) or "wfcon_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "arbitration_id": safe_text(payload.get("arbitration_id")),
            "quorum_id": safe_text(payload.get("quorum_id")),
            "vote_ids": vote_ids,
            "required_vote_ids": required_vote_ids,
            "worker_ids": worker_ids,
            "federation_id": safe_text(payload.get("federation_id")),
            "decision": safe_text(payload.get("decision")),
            "created_at": utc_now(),
        }

    def attach_replay_reconciliation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        reconciliation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_replay_reconciliation_record(task=task, state=state, reconciliation=reconciliation, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="replay_reconciliation",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_replay_reconciliation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        reconciliation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(reconciliation if isinstance(reconciliation, dict) else {})
        consensus_id = safe_text(payload.get("consensus_id"))
        consensus_hash = safe_text(payload.get("consensus_lineage_hash"))
        if consensus_id and not consensus_hash:
            for item in session.get("lineage", {}).get("federated_consensus_graph", {}).get("consensus", []):
                if isinstance(item, dict) and safe_text(item.get("consensus_id")) == consensus_id:
                    consensus_hash = stable_hash(item)
                    break
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "consensus_id": consensus_id,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.replay_reconciliation.v1",
            "replay_reconciliation_id": safe_text(payload.get("replay_reconciliation_id")) or "wfrrec_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "consensus_id": consensus_id,
            "consensus_lineage_hash": consensus_hash,
            "arbitration_id": safe_text(payload.get("arbitration_id")),
            "vote_ids": copy.deepcopy(payload.get("vote_ids") if isinstance(payload.get("vote_ids"), list) else []),
            "created_at": utc_now(),
        }

    def attach_federated_governance_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        governance: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_federated_governance_decision_record(task=task, state=state, governance=governance, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="federated_governance_decision",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_federated_governance_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        governance: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(governance if isinstance(governance, dict) else {})
        worker_ids = [
            safe_text(item)
            for item in (payload.get("worker_ids") if isinstance(payload.get("worker_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "consensus_id": safe_text(payload.get("consensus_id")),
            "worker_ids": worker_ids,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.federated_governance_decision.v1",
            "governance_decision_id": safe_text(payload.get("governance_decision_id")) or "wfgovd_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "consensus_id": safe_text(payload.get("consensus_id")),
            "arbitration_id": safe_text(payload.get("arbitration_id")),
            "worker_ids": worker_ids,
            "federation_id": safe_text(payload.get("federation_id")),
            "decision": safe_text(payload.get("decision")),
            "created_at": utc_now(),
        }

    def attach_runtime_self_observability_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        observability: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_runtime_self_observability_record(task=task, state=state, observability=observability, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="runtime_self_observability",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_runtime_self_observability_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        observability: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(observability if isinstance(observability, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "signal": safe_text(payload.get("signal")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.runtime_self_observability.v1",
            "observability_id": safe_text(payload.get("observability_id")) or "wfobs_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "signal": safe_text(payload.get("signal")),
            "severity": safe_text(payload.get("severity")) or "info",
            "payload_hash": safe_text(payload.get("payload_hash")) or stable_hash(payload.get("payload", {})),
            "created_at": utc_now(),
        }

    def attach_constitutional_audit_lineage_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        audit: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_constitutional_audit_lineage_record(task=task, state=state, audit=audit, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="constitutional_audit_lineage",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_constitutional_audit_lineage_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        audit: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(audit if isinstance(audit, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "observability_id": safe_text(payload.get("observability_id")),
            "rule_id": safe_text(payload.get("rule_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.constitutional_audit_lineage.v1",
            "audit_id": safe_text(payload.get("audit_id")) or "wfaud_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "observability_id": safe_text(payload.get("observability_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "rule_id": safe_text(payload.get("rule_id")) or "runtime_constitution",
            "finding": safe_text(payload.get("finding")),
            "created_at": utc_now(),
        }

    def attach_self_diagnosis_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        diagnosis: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_self_diagnosis_record(task=task, state=state, diagnosis=diagnosis, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="self_diagnosis",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_self_diagnosis_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        diagnosis: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(diagnosis if isinstance(diagnosis, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "audit_id": safe_text(payload.get("audit_id")),
            "observability_id": safe_text(payload.get("observability_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.self_diagnosis.v1",
            "diagnosis_id": safe_text(payload.get("diagnosis_id")) or "wfdiag_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "audit_id": safe_text(payload.get("audit_id")),
            "observability_id": safe_text(payload.get("observability_id")),
            "target_node_id": safe_text(payload.get("target_node_id")),
            "diagnosis": safe_text(payload.get("diagnosis")),
            "created_at": utc_now(),
        }

    def attach_self_repair_governance_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        repair: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_self_repair_governance_record(task=task, state=state, repair=repair, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="self_repair_governance",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_self_repair_governance_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        repair: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(repair if isinstance(repair, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "diagnosis_id": safe_text(payload.get("diagnosis_id")),
            "authority_id": safe_text(payload.get("authority_id")),
            "approval_id": safe_text(payload.get("approval_id")),
            "consensus_id": safe_text(payload.get("consensus_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.self_repair_governance.v1",
            "self_repair_id": safe_text(payload.get("self_repair_id")) or "wfsrg_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "diagnosis_id": safe_text(payload.get("diagnosis_id")),
            "audit_id": safe_text(payload.get("audit_id")),
            "observability_id": safe_text(payload.get("observability_id")),
            "authority_id": safe_text(payload.get("authority_id")),
            "approval_id": safe_text(payload.get("approval_id")),
            "consensus_id": safe_text(payload.get("consensus_id")),
            "repair_action": safe_text(payload.get("repair_action")) or "governed_self_repair",
            "created_at": utc_now(),
        }

    def attach_self_healing_replay_recovery_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        recovery: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_self_healing_replay_recovery_record(task=task, state=state, recovery=recovery, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="self_healing_replay_recovery",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_self_healing_replay_recovery_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        recovery: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(recovery if isinstance(recovery, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "self_repair_id": safe_text(payload.get("self_repair_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.self_healing_replay_recovery.v1",
            "self_healing_recovery_id": safe_text(payload.get("self_healing_recovery_id")) or "wfshr_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "self_repair_id": safe_text(payload.get("self_repair_id")),
            "diagnosis_id": safe_text(payload.get("diagnosis_id")),
            "replay_reconciliation_id": safe_text(payload.get("replay_reconciliation_id")),
            "recovery_action": safe_text(payload.get("recovery_action")) or "self_healing_replay_recovery",
            "created_at": utc_now(),
        }

    def attach_adaptive_governance_stabilization_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        stabilization: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_adaptive_governance_stabilization_record(task=task, state=state, stabilization=stabilization, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="adaptive_governance_stabilization",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_adaptive_governance_stabilization_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        stabilization: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(stabilization if isinstance(stabilization, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "self_healing_recovery_id": safe_text(payload.get("self_healing_recovery_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.adaptive_governance_stabilization.v1",
            "stabilization_id": safe_text(payload.get("stabilization_id")) or "wfags_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "self_healing_recovery_id": safe_text(payload.get("self_healing_recovery_id")),
            "self_repair_id": safe_text(payload.get("self_repair_id")),
            "stabilization": safe_text(payload.get("stabilization")) or "adaptive_governance_stabilized",
            "created_at": utc_now(),
        }

    def attach_constitutional_preservation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        preservation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_constitutional_preservation_record(task=task, state=state, preservation=preservation, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="constitutional_preservation",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_constitutional_preservation_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        preservation: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(preservation if isinstance(preservation, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "constitution_node_id": safe_text(payload.get("constitution_node_id") or payload.get("target_node_id")),
            "governance_record_id": safe_text(payload.get("governance_record_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.constitutional_preservation.v1",
            "preservation_id": safe_text(payload.get("preservation_id")) or "wfcpr_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "constitution_node_id": safe_text(payload.get("constitution_node_id") or payload.get("target_node_id")),
            "governance_record_id": safe_text(payload.get("governance_record_id")),
            "enforcement_id": safe_text(payload.get("enforcement_id")),
            "policy_decision_id": safe_text(payload.get("policy_decision_id")),
            "preservation_scope": safe_text(payload.get("preservation_scope")) or "runtime_constitution",
            "created_at": utc_now(),
        }

    def attach_self_preservation_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        decision: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_self_preservation_decision_record(task=task, state=state, decision=decision, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="self_preservation_decision",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_self_preservation_decision_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        decision: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(decision if isinstance(decision, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "observability_id": safe_text(payload.get("observability_id")),
            "authority_id": safe_text(payload.get("authority_id")),
            "policy_decision_id": safe_text(payload.get("policy_decision_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.self_preservation_decision.v1",
            "self_preservation_decision_id": safe_text(payload.get("self_preservation_decision_id")) or "wfspd_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "preservation_id": safe_text(payload.get("preservation_id")),
            "observability_id": safe_text(payload.get("observability_id")),
            "policy_decision_id": safe_text(payload.get("policy_decision_id")),
            "authority_id": safe_text(payload.get("authority_id")),
            "decision": safe_text(payload.get("decision")) or "preserve",
            "created_at": utc_now(),
        }

    def attach_catastrophic_failure_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        failure: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_catastrophic_failure_record(task=task, state=state, failure=failure, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="catastrophic_failure",
            record=record,
            current_tick=current_tick,
            ok=False,
        )

    def build_catastrophic_failure_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        failure: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(failure if isinstance(failure, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "failure_node_id": safe_text(payload.get("failure_node_id") or payload.get("target_node_id")),
            "governance_record_id": safe_text(payload.get("governance_record_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.catastrophic_failure.v1",
            "catastrophic_failure_id": safe_text(payload.get("catastrophic_failure_id")) or "wfcf_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "failure_node_id": safe_text(payload.get("failure_node_id") or payload.get("target_node_id")),
            "governance_record_id": safe_text(payload.get("governance_record_id")),
            "failure_classification": safe_text(payload.get("failure_classification")) or "catastrophic_runtime_failure",
            "created_at": utc_now(),
        }

    def attach_catastrophic_recovery_lineage_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        recovery: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_catastrophic_recovery_lineage_record(task=task, state=state, recovery=recovery, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="catastrophic_recovery_lineage",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_catastrophic_recovery_lineage_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        recovery: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(recovery if isinstance(recovery, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "catastrophic_failure_id": safe_text(payload.get("catastrophic_failure_id")),
            "rollback_id": safe_text(payload.get("rollback_id")),
            "recovery_dependency_id": safe_text(payload.get("recovery_dependency_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.catastrophic_recovery_lineage.v1",
            "catastrophic_recovery_id": safe_text(payload.get("catastrophic_recovery_id")) or "wfcr_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "catastrophic_failure_id": safe_text(payload.get("catastrophic_failure_id")),
            "rollback_id": safe_text(payload.get("rollback_id")),
            "recovery_dependency_id": safe_text(payload.get("recovery_dependency_id")),
            "recovery_node_id": safe_text(payload.get("recovery_node_id")),
            "created_at": utc_now(),
        }

    def attach_constitutional_rollback_arbitration_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        arbitration: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_constitutional_rollback_arbitration_record(task=task, state=state, arbitration=arbitration, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="constitutional_rollback_arbitration",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_constitutional_rollback_arbitration_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        arbitration: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(arbitration if isinstance(arbitration, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "consensus_id": safe_text(payload.get("consensus_id")),
            "quorum_id": safe_text(payload.get("quorum_id")),
            "failed_change_id": safe_text(payload.get("failed_constitutional_change_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.constitutional_rollback_arbitration.v1",
            "constitutional_rollback_arbitration_id": safe_text(payload.get("constitutional_rollback_arbitration_id")) or "wfcra_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "consensus_id": safe_text(payload.get("consensus_id")),
            "quorum_id": safe_text(payload.get("quorum_id")),
            "failed_constitutional_change_id": safe_text(payload.get("failed_constitutional_change_id")),
            "rollback_id": safe_text(payload.get("rollback_id")),
            "decision": safe_text(payload.get("decision")) or "rollback",
            "created_at": utc_now(),
        }

    def attach_adaptive_constitutional_stabilization_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        stabilization: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_adaptive_constitutional_stabilization_record(task=task, state=state, stabilization=stabilization, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="adaptive_constitutional_stabilization",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_adaptive_constitutional_stabilization_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        stabilization: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(stabilization if isinstance(stabilization, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "catastrophic_recovery_id": safe_text(payload.get("catastrophic_recovery_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.adaptive_constitutional_stabilization.v1",
            "constitutional_stabilization_id": safe_text(payload.get("constitutional_stabilization_id")) or "wfacst_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "catastrophic_recovery_id": safe_text(payload.get("catastrophic_recovery_id")),
            "preservation_id": safe_text(payload.get("preservation_id")),
            "stabilization": safe_text(payload.get("stabilization")) or "constitutional_stabilized",
            "created_at": utc_now(),
        }

    def attach_survivability_continuity_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        survivability: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_survivability_continuity_record(task=task, state=state, survivability=survivability, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="survivability_continuity",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_survivability_continuity_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        survivability: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(survivability if isinstance(survivability, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "preservation_id": safe_text(payload.get("preservation_id")),
            "catastrophic_recovery_id": safe_text(payload.get("catastrophic_recovery_id")),
            "constitutional_stabilization_id": safe_text(payload.get("constitutional_stabilization_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.survivability_continuity.v1",
            "survivability_id": safe_text(payload.get("survivability_id")) or "wfsurv_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "preservation_id": safe_text(payload.get("preservation_id")),
            "catastrophic_recovery_id": safe_text(payload.get("catastrophic_recovery_id")),
            "constitutional_stabilization_id": safe_text(payload.get("constitutional_stabilization_id")),
            "status": safe_text(payload.get("status")) or "survivable",
            "created_at": utc_now(),
        }

    def attach_autonomous_constitutional_evolution_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        evolution: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_autonomous_constitutional_evolution_record(task=task, state=state, evolution=evolution, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="autonomous_constitutional_evolution",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_autonomous_constitutional_evolution_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        evolution: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(evolution if isinstance(evolution, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "policy_decision_id": safe_text(payload.get("policy_decision_id")),
            "preservation_id": safe_text(payload.get("preservation_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.autonomous_constitutional_evolution.v1",
            "evolution_id": safe_text(payload.get("evolution_id")) or "wface_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "policy_decision_id": safe_text(payload.get("policy_decision_id")),
            "preservation_id": safe_text(payload.get("preservation_id")),
            "constitution_node_id": safe_text(payload.get("constitution_node_id")),
            "proposal": safe_text(payload.get("proposal")) or "autonomous_constitutional_evolution",
            "created_at": utc_now(),
        }

    def attach_constitutional_fork_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        fork: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_constitutional_fork_record(task=task, state=state, fork=fork, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="constitutional_fork",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_constitutional_fork_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        fork: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(fork if isinstance(fork, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "evolution_id": safe_text(payload.get("evolution_id")),
            "branch_id": safe_text(payload.get("branch_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.constitutional_fork.v1",
            "constitutional_fork_id": safe_text(payload.get("constitutional_fork_id")) or "wfcfk_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "evolution_id": safe_text(payload.get("evolution_id")),
            "preservation_id": safe_text(payload.get("preservation_id")),
            "constitution_node_id": safe_text(payload.get("constitution_node_id")),
            "branch_id": safe_text(payload.get("branch_id")),
            "parent_branch_id": safe_text(payload.get("parent_branch_id")),
            "fork_node_id": safe_text(payload.get("fork_node_id")),
            "created_at": utc_now(),
        }

    def attach_constitutional_merge_arbitration_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        arbitration: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_constitutional_merge_arbitration_record(task=task, state=state, arbitration=arbitration, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="constitutional_merge_arbitration",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_constitutional_merge_arbitration_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        arbitration: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(arbitration if isinstance(arbitration, dict) else {})
        source_branch_ids = [
            safe_text(item)
            for item in (payload.get("source_branch_ids") if isinstance(payload.get("source_branch_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "source_branch_ids": source_branch_ids,
            "consensus_id": safe_text(payload.get("consensus_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.constitutional_merge_arbitration.v1",
            "merge_arbitration_id": safe_text(payload.get("merge_arbitration_id")) or "wfcma_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "source_branch_ids": source_branch_ids,
            "target_branch_id": safe_text(payload.get("target_branch_id")),
            "quorum_id": safe_text(payload.get("quorum_id")),
            "consensus_id": safe_text(payload.get("consensus_id")),
            "decision": safe_text(payload.get("decision")) or "merge",
            "created_at": utc_now(),
        }

    def attach_constitutional_merge_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        merge: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_constitutional_merge_record(task=task, state=state, merge=merge, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="constitutional_merge",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_constitutional_merge_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        merge: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(merge if isinstance(merge, dict) else {})
        source_branch_ids = [
            safe_text(item)
            for item in (payload.get("source_branch_ids") if isinstance(payload.get("source_branch_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "merge_arbitration_id": safe_text(payload.get("merge_arbitration_id")),
            "source_branch_ids": source_branch_ids,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.constitutional_merge.v1",
            "constitutional_merge_id": safe_text(payload.get("constitutional_merge_id")) or "wfcmg_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "merge_arbitration_id": safe_text(payload.get("merge_arbitration_id")),
            "source_branch_ids": source_branch_ids,
            "target_branch_id": safe_text(payload.get("target_branch_id")),
            "merged_preservation_id": safe_text(payload.get("merged_preservation_id")),
            "created_at": utc_now(),
        }

    def attach_survivability_federation_continuity_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        survivability: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_survivability_federation_continuity_record(task=task, state=state, survivability=survivability, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="survivability_federation_continuity",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_survivability_federation_continuity_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        survivability: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(survivability if isinstance(survivability, dict) else {})
        worker_ids = [
            safe_text(item)
            for item in (payload.get("worker_ids") if isinstance(payload.get("worker_ids"), list) else [])
            if safe_text(item)
        ]
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "constitutional_merge_id": safe_text(payload.get("constitutional_merge_id")),
            "federation_id": safe_text(payload.get("federation_id")),
            "worker_ids": worker_ids,
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.survivability_federation_continuity.v1",
            "survivability_federation_id": safe_text(payload.get("survivability_federation_id")) or "wfsfed_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "constitutional_merge_id": safe_text(payload.get("constitutional_merge_id")),
            "federation_id": safe_text(payload.get("federation_id")),
            "worker_ids": worker_ids,
            "status": safe_text(payload.get("status")) or "federated_survivability_continuous",
            "created_at": utc_now(),
        }

    def attach_autonomous_governance_stabilization_loop_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        loop: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        record = self.build_autonomous_governance_stabilization_loop_record(task=task, state=state, loop=loop, current_tick=current_tick)
        return self.append_workflow_record(
            task=task,
            state=state,
            phase="replayable_session",
            event_type="autonomous_governance_stabilization_loop",
            record=record,
            current_tick=current_tick,
            ok=True,
        )

    def build_autonomous_governance_stabilization_loop_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        loop: Dict[str, Any],
        current_tick: int = 0,
    ) -> Dict[str, Any]:
        session = self.initial_state(task=task, state=state)
        payload = copy.deepcopy(loop if isinstance(loop, dict) else {})
        seed = {
            "workflow_id": session.get("workflow_id"),
            "session_id": session.get("session_id"),
            "constitutional_merge_id": safe_text(payload.get("constitutional_merge_id")),
            "catastrophic_recovery_id": safe_text(payload.get("catastrophic_recovery_id")),
            "constitutional_stabilization_id": safe_text(payload.get("constitutional_stabilization_id")),
            "current_tick": current_tick,
        }
        return {
            "schema": "zero.workflow_runtime_session.autonomous_governance_stabilization_loop.v1",
            "stabilization_loop_id": safe_text(payload.get("stabilization_loop_id")) or "wfagsl_" + stable_hash(seed)[:16],
            "workflow_id": safe_text(session.get("workflow_id")),
            "session_id": safe_text(session.get("session_id")),
            "task_id": task_id_from(task, state),
            "constitutional_merge_id": safe_text(payload.get("constitutional_merge_id")),
            "catastrophic_recovery_id": safe_text(payload.get("catastrophic_recovery_id")),
            "constitutional_stabilization_id": safe_text(payload.get("constitutional_stabilization_id")),
            "loop_status": safe_text(payload.get("loop_status")) or "stabilized",
            "created_at": utc_now(),
        }

    def append_workflow_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        phase: str,
        event_type: str,
        record: Dict[str, Any],
        current_tick: int = 0,
        ok: bool = True,
    ) -> Dict[str, Any]:
        session_dict = self.initial_state(task=task, state=state)
        events = self._events_from_any(session_dict.get("events", []))
        event = self.event_from_workflow_record(
            task=task,
            state=state,
            phase=phase,
            event_type=event_type,
            record=record,
            current_tick=current_tick,
            ok=ok,
        )
        existing_ids = {item.event_id for item in events}
        existing_keys = {self._event_dedupe_key(item) for item in events}
        if event.event_id not in existing_ids and self._event_dedupe_key(event) not in existing_keys:
            events.append(event)
        return self.build_session(task=task, state=state, events=events).to_dict()

    def event_from_workflow_record(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        phase: str,
        event_type: str,
        record: Dict[str, Any],
        current_tick: int,
        ok: bool = True,
    ) -> WorkflowRuntimeEvent:
        workflow_id = self.workflow_id_for(task, state)
        session_id = self.session_id_for(task, state)
        resolved_phase = phase if phase in WORKFLOW_SESSION_PHASES else infer_phase(result=record, action=event_type)
        status = "completed" if ok else "failed"
        step_index = safe_int(record.get("step_index") if isinstance(record, dict) else 0, 0)
        step = record.get("step") if isinstance(record, dict) and isinstance(record.get("step"), dict) else {"type": event_type}
        result = record.get("result") if isinstance(record, dict) and isinstance(record.get("result"), dict) else record
        result = copy.deepcopy(result if isinstance(result, dict) else {"value": result})
        result.setdefault("ok", ok)
        result.setdefault("step_index", step_index)
        result.setdefault("action", event_type)
        lineage = self._event_lineage(
            workflow_id=workflow_id,
            session_id=session_id,
            task=task,
            state=state,
            step=step,
            step_result=result,
            phase=resolved_phase,
            step_index=step_index,
        )
        payload = {
            "task_id": task_id_from(task, state),
            "record": _json_safe(record if isinstance(record, dict) else {}),
            "step": _json_safe(step),
            "result": _json_safe(result),
            "lineage": copy.deepcopy(lineage),
        }
        payload_hash = stable_hash(payload)
        event_id = "wfse_" + stable_hash(
            {
                "session": session_id,
                "tick": current_tick,
                "event_type": event_type,
                "phase": resolved_phase,
                "payload_hash": payload_hash,
            }
        )[:16]
        lineage["event_id"] = event_id
        return WorkflowRuntimeEvent(
            event_id=event_id,
            workflow_id=workflow_id,
            session_id=session_id,
            phase=resolved_phase,
            event_type=event_type,
            status=status,
            tick=safe_int(current_tick, 0),
            step_index=step_index,
            step_type=step_type_from(step, result),
            ok=ok,
            message=safe_text(result.get("message") or result.get("summary") or event_type)[:500],
            payload_hash=payload_hash,
            payload=payload,
            lineage=lineage,
        )

    def classify_verify_result(self, verify_result: Dict[str, Any]) -> Dict[str, Any]:
        result = verify_result if isinstance(verify_result, dict) else {}
        ok = bool(result.get("ok", False))
        error = result.get("error")
        text = " ".join(
            str(value or "")
            for value in (
                result.get("message"),
                error.get("message") if isinstance(error, dict) else error,
                result.get("stderr"),
                result.get("stdout"),
                result.get("final_answer"),
            )
        ).lower()
        if ok:
            classification = "verify_passed"
            repair_required = False
        elif "syntaxerror" in text or "invalid syntax" in text or "py_compile" in text:
            classification = "python_syntax_error"
            repair_required = True
        elif "assert" in text or "expected" in text or "mismatch" in text:
            classification = "verification_mismatch"
            repair_required = True
        else:
            classification = "verification_failed"
            repair_required = True
        return {
            "schema": "zero.workflow_runtime_session.verify_classification.v1",
            "ok": ok,
            "classification": classification,
            "repair_required": repair_required,
        }

    def event_from_step_result(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Dict[str, Any] | None,
        step_result: Dict[str, Any],
        current_tick: int,
    ) -> WorkflowRuntimeEvent:
        workflow_id = self.workflow_id_for(task, state)
        session_id = self.session_id_for(task, state)
        phase = infer_phase(step, step_result)
        step_index = safe_int(step_result.get("step_index", state.get("current_step_index", 0)) if isinstance(step_result, dict) else 0, 0)
        step_type = step_type_from(step, step_result)
        ok = bool(step_result.get("ok", False)) if isinstance(step_result, dict) else False
        status = "completed" if ok else "failed"
        message = safe_text(
            step_result.get("message")
            or step_result.get("final_answer")
            or (step_result.get("error", {}).get("message") if isinstance(step_result.get("error"), dict) else step_result.get("error"))
            if isinstance(step_result, dict)
            else ""
        )
        payload = {
            "task_id": task_id_from(task, state),
            "step": _json_safe(step or {}),
            "result": _json_safe(step_result),
        }
        lineage = self._event_lineage(
            workflow_id=workflow_id,
            session_id=session_id,
            task=task,
            state=state,
            step=step,
            step_result=step_result,
            phase=phase,
            step_index=step_index,
        )
        payload["lineage"] = copy.deepcopy(lineage)
        payload_hash = stable_hash(payload)
        event_id = "wfse_" + stable_hash({"session": session_id, "tick": current_tick, "step_index": step_index, "payload_hash": payload_hash})[:16]
        lineage["event_id"] = event_id
        return WorkflowRuntimeEvent(
            event_id=event_id,
            workflow_id=workflow_id,
            session_id=session_id,
            phase=phase,
            event_type="step_result",
            status=status,
            tick=safe_int(current_tick, 0),
            step_index=step_index,
            step_type=step_type,
            ok=ok,
            message=message[:500],
            payload_hash=payload_hash,
            payload=payload,
            lineage=lineage,
        )

    def append_step_result(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Dict[str, Any] | None,
        step_result: Dict[str, Any],
        current_tick: int,
    ) -> Dict[str, Any]:
        session_dict = self.initial_state(task=task, state=state)
        events = self._events_from_any(session_dict.get("events", []))
        event = self.event_from_step_result(task=task, state=state, step=step, step_result=step_result, current_tick=current_tick)
        existing_ids = {item.event_id for item in events}
        existing_keys = {self._event_dedupe_key(item) for item in events}
        if event.event_id not in existing_ids and self._event_dedupe_key(event) not in existing_keys:
            events.append(event)
        rebuilt = self.build_session(task=task, state=state, events=events)
        return rebuilt.to_dict()

    def build_session(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        events: Iterable[WorkflowRuntimeEvent] | None = None,
        result: Dict[str, Any] | None = None,
    ) -> WorkflowRuntimeSession:
        now = utc_now()
        task_id = task_id_from(task, state)
        session_id = self.session_id_for(task, state)
        workflow_id = self.workflow_id_for(task, state)
        resolved_events = list(events) if events is not None else self._events_from_state(task=task, state=state)
        phases = self._phase_summary(state=state, events=resolved_events)
        status = self._session_status(state=state, result=result, phases=phases)
        replayable = self._is_replayable(state=state, events=resolved_events)
        lineage = self._session_lineage(
            workflow_id=workflow_id,
            session_id=session_id,
            task=task,
            state=state,
            events=resolved_events,
            result=result,
        )
        continuity_summary = self.continuity_summary(
            {
                "schema": self.schema,
                "session_id": session_id,
                "workflow_id": workflow_id,
                "lineage": lineage,
                "events": [event.to_dict() for event in resolved_events],
            }
        )
        result_hash = stable_hash({
            "task_id": task_id,
            "workflow_id": workflow_id,
            "session_id": session_id,
            "status": status,
            "phases": phases,
            "events": [event.to_dict() for event in resolved_events],
            "lineage": lineage,
            "continuity_summary": continuity_summary,
            "last_result": (result or state).get("last_step_result") if isinstance((result or state), dict) else None,
        })
        summary = self._summary(status=status, phases=phases, replayable=replayable)
        created_at = safe_text((state.get("workflow_runtime_session") or {}).get("created_at")) if isinstance(state.get("workflow_runtime_session"), dict) else now
        return WorkflowRuntimeSession(
            schema=self.schema,
            session_id=session_id,
            workflow_id=workflow_id,
            task_id=task_id,
            status=status,
            phases=phases,
            events=resolved_events[-200:],
            replayable=replayable,
            result_hash=result_hash,
            lineage=lineage,
            continuity_summary=continuity_summary,
            dictionary_contract=self._dictionary_contract(),
            created_at=created_at or now,
            updated_at=now,
            summary=summary,
        )

    def finalize_public_result(self, *, task: Dict[str, Any], state: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        session = self.build_session(task=task, state=state, result=result).to_dict()
        public_result = copy.deepcopy(result)
        public_result["workflow_runtime_session"] = session
        public_result["aer_workflow_runtime"] = {
            "schema": self.schema,
            "session_id": session.get("session_id"),
            "workflow_id": session.get("workflow_id"),
            "status": session.get("status"),
            "replayable": bool(session.get("replayable")),
            "summary": session.get("summary", ""),
            "phases": copy.deepcopy(session.get("phases", {})),
            "lineage": copy.deepcopy(session.get("lineage", {})),
            "continuity_summary": copy.deepcopy(session.get("continuity_summary", {})),
        }
        runtime_state = public_result.get("runtime_state")
        if isinstance(runtime_state, dict):
            runtime_state["workflow_runtime_session"] = copy.deepcopy(session)
        return public_result

    def _events_from_any(self, value: Any) -> List[WorkflowRuntimeEvent]:
        events: List[WorkflowRuntimeEvent] = []
        if not isinstance(value, list):
            return events
        for item in value:
            if isinstance(item, WorkflowRuntimeEvent):
                events.append(item)
            elif isinstance(item, dict):
                try:
                    defaults = {
                        "workflow_id": item.get("workflow_id") or "",
                        "session_id": item.get("session_id") or "",
                        "lineage": item.get("lineage") if isinstance(item.get("lineage"), dict) else {},
                    }
                    payload = {
                        k: item.get(k, defaults.get(k))
                        for k in WorkflowRuntimeEvent.__dataclass_fields__.keys()
                    }
                    events.append(WorkflowRuntimeEvent(**payload))
                except Exception:
                    continue
        return events

    def _events_from_state(self, *, task: Dict[str, Any], state: Dict[str, Any]) -> List[WorkflowRuntimeEvent]:
        existing = state.get("workflow_runtime_session") if isinstance(state, dict) else None
        if isinstance(existing, dict):
            events = self._events_from_any(existing.get("events", []))
            if events:
                return events
        events: List[WorkflowRuntimeEvent] = []
        execution_log = state.get("execution_log") if isinstance(state, dict) else []
        if isinstance(execution_log, list):
            temp_state = copy.deepcopy(state) if isinstance(state, dict) else {}
            temp_state["workflow_runtime_session"] = {
                "schema": self.schema,
                "session_id": self.session_id_for(task, state),
                "workflow_id": self.workflow_id_for(task, state),
                "events": [],
            }
            for record in execution_log[-200:]:
                if not isinstance(record, dict):
                    continue
                step = record.get("step") if isinstance(record.get("step"), dict) else None
                step_result = record.get("result") if isinstance(record.get("result"), dict) else {}
                tick = safe_int(record.get("tick"), safe_int(step_result.get("tick") if isinstance(step_result, dict) else 0, 0))
                event = self.event_from_step_result(task=task, state=temp_state, step=step, step_result=step_result, current_tick=tick)
                events.append(event)
                temp_state["workflow_runtime_session"]["events"] = [item.to_dict() for item in events]
        return events

    def _event_lineage(
        self,
        *,
        workflow_id: str,
        session_id: str,
        task: Dict[str, Any],
        state: Dict[str, Any],
        step: Dict[str, Any] | None,
        step_result: Dict[str, Any],
        phase: str,
        step_index: int,
    ) -> Dict[str, Any]:
        existing = state.get("workflow_runtime_session") if isinstance(state, dict) else {}
        events = self._events_from_any(existing.get("events", []) if isinstance(existing, dict) else [])
        parent_event = events[-1] if events else None
        failed_parent = self._latest_failed_event(events, preferred_phase="verify" if phase == "repair" else "")
        source_session_id = self._source_session_id(task=task, state=state, result=step_result)
        parent_session_id = self._parent_session_id(task=task, state=state, result=step_result)
        lineage = {
            "schema": "zero.workflow_runtime_event.lineage.v1",
            "workflow_id": workflow_id,
            "session_id": session_id,
            "source_session_id": source_session_id,
            "parent_session_id": parent_session_id,
            "parent_event_id": parent_event.event_id if parent_event else "",
            "parent_phase": parent_event.phase if parent_event else "",
            "parent_status": parent_event.status if parent_event else "",
            "step_index": int(step_index),
            "phase": phase,
        }
        action = safe_text(step_result.get("action") if isinstance(step_result, dict) else "").lower()
        if action == "checkpoint":
            lineage["checkpoint"] = {
                "checkpoint_id": safe_text(step_result.get("checkpoint_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "event_count": safe_int(step_result.get("event_count"), 0),
                "event_ids": copy.deepcopy(step_result.get("event_ids") if isinstance(step_result.get("event_ids"), list) else []),
            }
        if action == "restore":
            lineage["restore"] = {
                "source_checkpoint_id": safe_text(step_result.get("source_checkpoint_id") or step_result.get("checkpoint_id")),
                "source_workflow_id": safe_text(step_result.get("source_workflow_id")),
                "source_session_id": safe_text(step_result.get("source_session_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "checkpoint_event_ids": copy.deepcopy(step_result.get("checkpoint_event_ids") if isinstance(step_result.get("checkpoint_event_ids"), list) else []),
            }
        if action in {"resume", "resume_continue", "continue"}:
            lineage["resume_continue"] = {
                "workflow_id": workflow_id,
                "session_id": session_id,
                "parent_event_id": parent_event.event_id if parent_event else "",
                "restore_event_id": self._latest_event_id(events, event_type="restore"),
                "checkpoint_id": self._latest_checkpoint_id(events),
            }
        if action == "execution_cursor":
            lineage["execution_cursor"] = {
                "cursor_id": safe_text(step_result.get("cursor_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "checkpoint_id": safe_text(step_result.get("checkpoint_id")),
                "restore_event_id": safe_text(step_result.get("restore_event_id")),
                "parent_event_id": safe_text(step_result.get("parent_event_id")) or (parent_event.event_id if parent_event else ""),
                "step_index": safe_int(step_result.get("step_index"), 0),
            }
        if action == "execution_memory":
            lineage["execution_memory"] = {
                "memory_id": safe_text(step_result.get("memory_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "cursor_id": safe_text(step_result.get("cursor_id")),
                "checkpoint_id": safe_text(step_result.get("checkpoint_id")),
                "payload_hash": safe_text(step_result.get("payload_hash")),
            }
        if action == "recovery_resume_point":
            lineage["recovery_resume_point"] = {
                "recovery_resume_id": safe_text(step_result.get("recovery_resume_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "cursor_id": safe_text(step_result.get("cursor_id")),
                "memory_id": safe_text(step_result.get("memory_id")),
                "checkpoint_id": safe_text(step_result.get("checkpoint_id")),
                "restore_event_id": safe_text(step_result.get("restore_event_id")),
                "step_index": safe_int(step_result.get("step_index"), 0),
            }
        if action == "recovery_resume":
            lineage["recovery_resume"] = {
                "recovery_resume_id": safe_text(step_result.get("recovery_resume_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "source_workflow_id": safe_text(step_result.get("source_workflow_id")),
                "source_session_id": safe_text(step_result.get("source_session_id")),
                "cursor_id": safe_text(step_result.get("cursor_id")),
                "memory_id": safe_text(step_result.get("memory_id")),
                "checkpoint_id": safe_text(step_result.get("checkpoint_id")),
                "restore_event_id": safe_text(step_result.get("restore_event_id")),
                "step_index": safe_int(step_result.get("step_index"), 0),
            }
        if action == "execution_graph_node":
            lineage["execution_graph_node"] = {
                "node_id": safe_text(step_result.get("node_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "branch_id": safe_text(step_result.get("branch_id")),
                "parent_node_id": safe_text(step_result.get("parent_node_id")),
                "phase": safe_text(step_result.get("phase")) or phase,
                "step_index": safe_int(step_result.get("step_index"), 0),
            }
        if action == "graph_edge":
            lineage["graph_edge"] = {
                "edge_id": safe_text(step_result.get("edge_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "from_node_id": safe_text(step_result.get("from_node_id")),
                "to_node_id": safe_text(step_result.get("to_node_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "edge_type": safe_text(step_result.get("edge_type")) or "continuation",
            }
        if action == "branch_fork":
            lineage["branch_fork"] = {
                "branch_id": safe_text(step_result.get("branch_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "parent_branch_id": safe_text(step_result.get("parent_branch_id")),
                "fork_node_id": safe_text(step_result.get("fork_node_id")),
                "name": safe_text(step_result.get("name")),
            }
        if action == "join_merge":
            lineage["join_merge"] = {
                "join_id": safe_text(step_result.get("join_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "source_branch_ids": copy.deepcopy(step_result.get("source_branch_ids") if isinstance(step_result.get("source_branch_ids"), list) else []),
                "target_branch_id": safe_text(step_result.get("target_branch_id")),
                "join_node_id": safe_text(step_result.get("join_node_id")),
                "strategy": safe_text(step_result.get("strategy")) or "merge",
            }
        if action == "recovery_dependency":
            lineage["recovery_dependency"] = {
                "recovery_dependency_id": safe_text(step_result.get("recovery_dependency_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "source_node_id": safe_text(step_result.get("source_node_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "dependency_type": safe_text(step_result.get("dependency_type")) or "recovery",
                "required": bool(step_result.get("required", True)),
            }
        if action == "mutation_transaction":
            lineage["mutation_transaction"] = {
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "node_id": safe_text(step_result.get("node_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "mutation_type": safe_text(step_result.get("mutation_type")) or "mutation",
                "payload_hash": safe_text(step_result.get("payload_hash")),
            }
        if action == "mutation_verify":
            lineage["mutation_verify"] = {
                "mutation_verify_id": safe_text(step_result.get("mutation_verify_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "verify_node_id": safe_text(step_result.get("verify_node_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "ok": bool(step_result.get("ok", False)),
                "failure_classification": safe_text(step_result.get("failure_classification")),
            }
        if action == "rollback_graph_node":
            lineage["rollback_graph_node"] = {
                "rollback_id": safe_text(step_result.get("rollback_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "rollback_node_id": safe_text(step_result.get("rollback_node_id")),
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "mutation_verify_id": safe_text(step_result.get("mutation_verify_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "retry_node_id": safe_text(step_result.get("retry_node_id")),
            }
        if action == "branch_conflict":
            lineage["branch_conflict"] = {
                "conflict_id": safe_text(step_result.get("conflict_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "source_branch_ids": copy.deepcopy(step_result.get("source_branch_ids") if isinstance(step_result.get("source_branch_ids"), list) else []),
                "target_branch_id": safe_text(step_result.get("target_branch_id")),
                "conflict_node_id": safe_text(step_result.get("conflict_node_id")),
                "mutation_transaction_ids": copy.deepcopy(step_result.get("mutation_transaction_ids") if isinstance(step_result.get("mutation_transaction_ids"), list) else []),
            }
        if action == "graph_reconciliation":
            lineage["graph_reconciliation"] = {
                "reconciliation_id": safe_text(step_result.get("reconciliation_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "conflict_id": safe_text(step_result.get("conflict_id")),
                "rollback_id": safe_text(step_result.get("rollback_id")),
                "retry_node_id": safe_text(step_result.get("retry_node_id")),
                "source_branch_ids": copy.deepcopy(step_result.get("source_branch_ids") if isinstance(step_result.get("source_branch_ids"), list) else []),
                "target_branch_id": safe_text(step_result.get("target_branch_id")),
                "strategy": safe_text(step_result.get("strategy")) or "rollback_retry_reconcile",
            }
        if action == "policy_decision":
            lineage["policy_decision"] = {
                "policy_decision_id": safe_text(step_result.get("policy_decision_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "policy_id": safe_text(step_result.get("policy_id")),
                "decision": safe_text(step_result.get("decision")),
                "allowed": bool(step_result.get("allowed", False)),
            }
        if action == "authority_continuity":
            lineage["authority_continuity"] = {
                "authority_id": safe_text(step_result.get("authority_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")),
                "session_id": safe_text(step_result.get("session_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "execution_owner": safe_text(step_result.get("execution_owner")),
                "authority_source": safe_text(step_result.get("authority_source")),
                "allowed": bool(step_result.get("allowed", True)),
            }
        if action == "review_required":
            lineage["review_required"] = {
                "review_id": safe_text(step_result.get("review_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "policy_decision_id": safe_text(step_result.get("policy_decision_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "transition": "blocked",
            }
        if action == "approval":
            lineage["approval"] = {
                "approval_id": safe_text(step_result.get("approval_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "review_id": safe_text(step_result.get("review_id")),
                "policy_decision_id": safe_text(step_result.get("policy_decision_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "approved": bool(step_result.get("approved", True)),
            }
        if action == "governance_resume":
            lineage["governance_resume"] = {
                "governance_resume_id": safe_text(step_result.get("governance_resume_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "approval_id": safe_text(step_result.get("approval_id")),
                "review_id": safe_text(step_result.get("review_id")),
                "resumed_node_id": safe_text(step_result.get("resumed_node_id")),
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "transition": "resumed",
            }
        if action == "constitution_enforcement":
            lineage["constitution_enforcement"] = {
                "enforcement_id": safe_text(step_result.get("enforcement_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "mutation_transaction_id": safe_text(step_result.get("mutation_transaction_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "rule_id": safe_text(step_result.get("rule_id")),
                "enforced": bool(step_result.get("enforced", True)),
            }
        if action == "actor_worker":
            lineage["actor_worker"] = {
                "worker_id": safe_text(step_result.get("worker_id")),
                "actor_id": safe_text(step_result.get("actor_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "worker_type": safe_text(step_result.get("worker_type")),
                "authority_scope": safe_text(step_result.get("authority_scope")),
            }
        if action == "worker_federation":
            lineage["worker_federation"] = {
                "federation_id": safe_text(step_result.get("federation_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "worker_ids": copy.deepcopy(step_result.get("worker_ids") if isinstance(step_result.get("worker_ids"), list) else []),
                "coordinator_worker_id": safe_text(step_result.get("coordinator_worker_id")),
            }
        if action == "distributed_execution":
            lineage["distributed_execution"] = {
                "distributed_execution_id": safe_text(step_result.get("distributed_execution_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "worker_id": safe_text(step_result.get("worker_id")),
                "parent_worker_ids": copy.deepcopy(step_result.get("parent_worker_ids") if isinstance(step_result.get("parent_worker_ids"), list) else []),
                "federation_id": safe_text(step_result.get("federation_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
            }
        if action == "distributed_recovery":
            lineage["distributed_recovery"] = {
                "distributed_recovery_id": safe_text(step_result.get("distributed_recovery_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "source_execution_id": safe_text(step_result.get("source_execution_id")),
                "recovery_worker_id": safe_text(step_result.get("recovery_worker_id")),
                "recovery_node_id": safe_text(step_result.get("recovery_node_id")),
            }
        if action == "federated_authority":
            lineage["federated_authority"] = {
                "federated_authority_id": safe_text(step_result.get("federated_authority_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")),
                "session_id": safe_text(step_result.get("session_id")),
                "worker_id": safe_text(step_result.get("worker_id")),
                "authority_id": safe_text(step_result.get("authority_id")),
                "federation_id": safe_text(step_result.get("federation_id")),
                "allowed": bool(step_result.get("allowed", True)),
            }
        if action == "distributed_governance":
            lineage["distributed_governance"] = {
                "distributed_governance_id": safe_text(step_result.get("distributed_governance_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "worker_ids": copy.deepcopy(step_result.get("worker_ids") if isinstance(step_result.get("worker_ids"), list) else []),
                "governance_record_ids": copy.deepcopy(step_result.get("governance_record_ids") if isinstance(step_result.get("governance_record_ids"), list) else []),
                "federation_id": safe_text(step_result.get("federation_id")),
            }
        if action == "worker_decision":
            lineage["worker_decision"] = {
                "worker_decision_id": safe_text(step_result.get("worker_decision_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "worker_id": safe_text(step_result.get("worker_id")),
                "federation_id": safe_text(step_result.get("federation_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "decision": safe_text(step_result.get("decision")),
                "decision_value": _json_safe(step_result.get("decision_value")),
            }
        if action == "arbitration_decision":
            lineage["arbitration_decision"] = {
                "arbitration_id": safe_text(step_result.get("arbitration_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "conflicting_decision_ids": copy.deepcopy(step_result.get("conflicting_decision_ids") if isinstance(step_result.get("conflicting_decision_ids"), list) else []),
                "worker_ids": copy.deepcopy(step_result.get("worker_ids") if isinstance(step_result.get("worker_ids"), list) else []),
                "federation_id": safe_text(step_result.get("federation_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "decision": safe_text(step_result.get("decision")),
            }
        if action == "authority_quorum":
            lineage["authority_quorum"] = {
                "quorum_id": safe_text(step_result.get("quorum_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "authority_worker_ids": copy.deepcopy(step_result.get("authority_worker_ids") if isinstance(step_result.get("authority_worker_ids"), list) else []),
                "federation_id": safe_text(step_result.get("federation_id")),
                "threshold": safe_int(step_result.get("threshold"), 0),
            }
        if action == "consensus_vote":
            lineage["consensus_vote"] = {
                "vote_id": safe_text(step_result.get("vote_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "quorum_id": safe_text(step_result.get("quorum_id")),
                "worker_id": safe_text(step_result.get("worker_id")),
                "federation_id": safe_text(step_result.get("federation_id")),
                "vote": safe_text(step_result.get("vote")),
                "accepted": bool(step_result.get("accepted", True)),
            }
        if action == "federated_consensus":
            lineage["federated_consensus"] = {
                "consensus_id": safe_text(step_result.get("consensus_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "arbitration_id": safe_text(step_result.get("arbitration_id")),
                "quorum_id": safe_text(step_result.get("quorum_id")),
                "vote_ids": copy.deepcopy(step_result.get("vote_ids") if isinstance(step_result.get("vote_ids"), list) else []),
                "required_vote_ids": copy.deepcopy(step_result.get("required_vote_ids") if isinstance(step_result.get("required_vote_ids"), list) else []),
                "worker_ids": copy.deepcopy(step_result.get("worker_ids") if isinstance(step_result.get("worker_ids"), list) else []),
                "federation_id": safe_text(step_result.get("federation_id")),
                "decision": safe_text(step_result.get("decision")),
            }
        if action == "replay_reconciliation":
            lineage["replay_reconciliation"] = {
                "replay_reconciliation_id": safe_text(step_result.get("replay_reconciliation_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "consensus_id": safe_text(step_result.get("consensus_id")),
                "consensus_lineage_hash": safe_text(step_result.get("consensus_lineage_hash")),
                "arbitration_id": safe_text(step_result.get("arbitration_id")),
                "vote_ids": copy.deepcopy(step_result.get("vote_ids") if isinstance(step_result.get("vote_ids"), list) else []),
            }
        if action == "federated_governance_decision":
            lineage["federated_governance_decision"] = {
                "governance_decision_id": safe_text(step_result.get("governance_decision_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "consensus_id": safe_text(step_result.get("consensus_id")),
                "arbitration_id": safe_text(step_result.get("arbitration_id")),
                "worker_ids": copy.deepcopy(step_result.get("worker_ids") if isinstance(step_result.get("worker_ids"), list) else []),
                "federation_id": safe_text(step_result.get("federation_id")),
                "decision": safe_text(step_result.get("decision")),
            }
        if action == "runtime_self_observability":
            lineage["runtime_self_observability"] = {
                "observability_id": safe_text(step_result.get("observability_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "signal": safe_text(step_result.get("signal")),
                "severity": safe_text(step_result.get("severity")),
                "payload_hash": safe_text(step_result.get("payload_hash")),
            }
        if action == "constitutional_audit_lineage":
            lineage["constitutional_audit_lineage"] = {
                "audit_id": safe_text(step_result.get("audit_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "observability_id": safe_text(step_result.get("observability_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "rule_id": safe_text(step_result.get("rule_id")),
                "finding": safe_text(step_result.get("finding")),
            }
        if action == "self_diagnosis":
            lineage["self_diagnosis"] = {
                "diagnosis_id": safe_text(step_result.get("diagnosis_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "audit_id": safe_text(step_result.get("audit_id")),
                "observability_id": safe_text(step_result.get("observability_id")),
                "target_node_id": safe_text(step_result.get("target_node_id")),
                "diagnosis": safe_text(step_result.get("diagnosis")),
            }
        if action == "self_repair_governance":
            lineage["self_repair_governance"] = {
                "self_repair_id": safe_text(step_result.get("self_repair_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "diagnosis_id": safe_text(step_result.get("diagnosis_id")),
                "audit_id": safe_text(step_result.get("audit_id")),
                "observability_id": safe_text(step_result.get("observability_id")),
                "authority_id": safe_text(step_result.get("authority_id")),
                "approval_id": safe_text(step_result.get("approval_id")),
                "consensus_id": safe_text(step_result.get("consensus_id")),
                "repair_action": safe_text(step_result.get("repair_action")),
            }
        if action == "self_healing_replay_recovery":
            lineage["self_healing_replay_recovery"] = {
                "self_healing_recovery_id": safe_text(step_result.get("self_healing_recovery_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "self_repair_id": safe_text(step_result.get("self_repair_id")),
                "diagnosis_id": safe_text(step_result.get("diagnosis_id")),
                "replay_reconciliation_id": safe_text(step_result.get("replay_reconciliation_id")),
                "recovery_action": safe_text(step_result.get("recovery_action")),
            }
        if action == "adaptive_governance_stabilization":
            lineage["adaptive_governance_stabilization"] = {
                "stabilization_id": safe_text(step_result.get("stabilization_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "self_healing_recovery_id": safe_text(step_result.get("self_healing_recovery_id")),
                "self_repair_id": safe_text(step_result.get("self_repair_id")),
                "stabilization": safe_text(step_result.get("stabilization")),
            }
        if action == "constitutional_preservation":
            lineage["constitutional_preservation"] = {
                "preservation_id": safe_text(step_result.get("preservation_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "constitution_node_id": safe_text(step_result.get("constitution_node_id")),
                "governance_record_id": safe_text(step_result.get("governance_record_id")),
                "enforcement_id": safe_text(step_result.get("enforcement_id")),
                "policy_decision_id": safe_text(step_result.get("policy_decision_id")),
                "preservation_scope": safe_text(step_result.get("preservation_scope")),
            }
        if action == "self_preservation_decision":
            lineage["self_preservation_decision"] = {
                "self_preservation_decision_id": safe_text(step_result.get("self_preservation_decision_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "preservation_id": safe_text(step_result.get("preservation_id")),
                "observability_id": safe_text(step_result.get("observability_id")),
                "policy_decision_id": safe_text(step_result.get("policy_decision_id")),
                "authority_id": safe_text(step_result.get("authority_id")),
                "decision": safe_text(step_result.get("decision")),
            }
        if action == "catastrophic_failure":
            lineage["catastrophic_failure"] = {
                "catastrophic_failure_id": safe_text(step_result.get("catastrophic_failure_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "failure_node_id": safe_text(step_result.get("failure_node_id")),
                "governance_record_id": safe_text(step_result.get("governance_record_id")),
                "failure_classification": safe_text(step_result.get("failure_classification")),
            }
        if action == "catastrophic_recovery_lineage":
            lineage["catastrophic_recovery_lineage"] = {
                "catastrophic_recovery_id": safe_text(step_result.get("catastrophic_recovery_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "catastrophic_failure_id": safe_text(step_result.get("catastrophic_failure_id")),
                "rollback_id": safe_text(step_result.get("rollback_id")),
                "recovery_dependency_id": safe_text(step_result.get("recovery_dependency_id")),
                "recovery_node_id": safe_text(step_result.get("recovery_node_id")),
            }
        if action == "constitutional_rollback_arbitration":
            lineage["constitutional_rollback_arbitration"] = {
                "constitutional_rollback_arbitration_id": safe_text(step_result.get("constitutional_rollback_arbitration_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "consensus_id": safe_text(step_result.get("consensus_id")),
                "quorum_id": safe_text(step_result.get("quorum_id")),
                "failed_constitutional_change_id": safe_text(step_result.get("failed_constitutional_change_id")),
                "rollback_id": safe_text(step_result.get("rollback_id")),
                "decision": safe_text(step_result.get("decision")),
            }
        if action == "adaptive_constitutional_stabilization":
            lineage["adaptive_constitutional_stabilization"] = {
                "constitutional_stabilization_id": safe_text(step_result.get("constitutional_stabilization_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "catastrophic_recovery_id": safe_text(step_result.get("catastrophic_recovery_id")),
                "preservation_id": safe_text(step_result.get("preservation_id")),
                "stabilization": safe_text(step_result.get("stabilization")),
            }
        if action == "survivability_continuity":
            lineage["survivability_continuity"] = {
                "survivability_id": safe_text(step_result.get("survivability_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "preservation_id": safe_text(step_result.get("preservation_id")),
                "catastrophic_recovery_id": safe_text(step_result.get("catastrophic_recovery_id")),
                "constitutional_stabilization_id": safe_text(step_result.get("constitutional_stabilization_id")),
                "status": safe_text(step_result.get("status")),
            }
        if action == "autonomous_constitutional_evolution":
            lineage["autonomous_constitutional_evolution"] = {
                "evolution_id": safe_text(step_result.get("evolution_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "policy_decision_id": safe_text(step_result.get("policy_decision_id")),
                "preservation_id": safe_text(step_result.get("preservation_id")),
                "constitution_node_id": safe_text(step_result.get("constitution_node_id")),
                "proposal": safe_text(step_result.get("proposal")),
            }
        if action == "constitutional_fork":
            lineage["constitutional_fork"] = {
                "constitutional_fork_id": safe_text(step_result.get("constitutional_fork_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "evolution_id": safe_text(step_result.get("evolution_id")),
                "preservation_id": safe_text(step_result.get("preservation_id")),
                "constitution_node_id": safe_text(step_result.get("constitution_node_id")),
                "branch_id": safe_text(step_result.get("branch_id")),
                "parent_branch_id": safe_text(step_result.get("parent_branch_id")),
                "fork_node_id": safe_text(step_result.get("fork_node_id")),
            }
        if action == "constitutional_merge_arbitration":
            lineage["constitutional_merge_arbitration"] = {
                "merge_arbitration_id": safe_text(step_result.get("merge_arbitration_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "source_branch_ids": copy.deepcopy(step_result.get("source_branch_ids") if isinstance(step_result.get("source_branch_ids"), list) else []),
                "target_branch_id": safe_text(step_result.get("target_branch_id")),
                "quorum_id": safe_text(step_result.get("quorum_id")),
                "consensus_id": safe_text(step_result.get("consensus_id")),
                "decision": safe_text(step_result.get("decision")),
            }
        if action == "constitutional_merge":
            lineage["constitutional_merge"] = {
                "constitutional_merge_id": safe_text(step_result.get("constitutional_merge_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "merge_arbitration_id": safe_text(step_result.get("merge_arbitration_id")),
                "source_branch_ids": copy.deepcopy(step_result.get("source_branch_ids") if isinstance(step_result.get("source_branch_ids"), list) else []),
                "target_branch_id": safe_text(step_result.get("target_branch_id")),
                "merged_preservation_id": safe_text(step_result.get("merged_preservation_id")),
            }
        if action == "survivability_federation_continuity":
            lineage["survivability_federation_continuity"] = {
                "survivability_federation_id": safe_text(step_result.get("survivability_federation_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "constitutional_merge_id": safe_text(step_result.get("constitutional_merge_id")),
                "federation_id": safe_text(step_result.get("federation_id")),
                "worker_ids": copy.deepcopy(step_result.get("worker_ids") if isinstance(step_result.get("worker_ids"), list) else []),
                "status": safe_text(step_result.get("status")),
            }
        if action == "autonomous_governance_stabilization_loop":
            lineage["autonomous_governance_stabilization_loop"] = {
                "stabilization_loop_id": safe_text(step_result.get("stabilization_loop_id")),
                "workflow_id": safe_text(step_result.get("workflow_id")) or workflow_id,
                "session_id": safe_text(step_result.get("session_id")) or session_id,
                "constitutional_merge_id": safe_text(step_result.get("constitutional_merge_id")),
                "catastrophic_recovery_id": safe_text(step_result.get("catastrophic_recovery_id")),
                "constitutional_stabilization_id": safe_text(step_result.get("constitutional_stabilization_id")),
                "loop_status": safe_text(step_result.get("loop_status")),
            }
        if phase == "repair":
            lineage["repair_ancestry"] = self._repair_ancestry(
                state=state,
                step=step,
                step_result=step_result,
                failed_parent=failed_parent,
            )
        if phase == "rollback_retry":
            lineage["retry_chain"] = self._retry_chain(
                state=state,
                step=step,
                step_result=step_result,
                parent_event=parent_event,
                events=events,
            )
        if source_session_id:
            replay_input = self._replay_continuation_input(task=task, state=state, result=step_result)
            lineage["replay_continuation"] = {
                "source_session_id": source_session_id,
                "continued_session_id": session_id,
                "workflow_id": workflow_id,
                "source_branch_id": safe_text(replay_input.get("source_branch_id")),
                "continued_branch_id": safe_text(replay_input.get("continued_branch_id")),
                "mutation_transaction_ids": copy.deepcopy(replay_input.get("mutation_transaction_ids") if isinstance(replay_input.get("mutation_transaction_ids"), list) else []),
                "rollback_ids": copy.deepcopy(replay_input.get("rollback_ids") if isinstance(replay_input.get("rollback_ids"), list) else []),
                "governance_record_ids": copy.deepcopy(replay_input.get("governance_record_ids") if isinstance(replay_input.get("governance_record_ids"), list) else []),
                "worker_ids": copy.deepcopy(replay_input.get("worker_ids") if isinstance(replay_input.get("worker_ids"), list) else []),
                "distributed_execution_ids": copy.deepcopy(replay_input.get("distributed_execution_ids") if isinstance(replay_input.get("distributed_execution_ids"), list) else []),
                "consensus_ids": copy.deepcopy(replay_input.get("consensus_ids") if isinstance(replay_input.get("consensus_ids"), list) else []),
                "self_healing_recovery_ids": copy.deepcopy(replay_input.get("self_healing_recovery_ids") if isinstance(replay_input.get("self_healing_recovery_ids"), list) else []),
                "preservation_ids": copy.deepcopy(replay_input.get("preservation_ids") if isinstance(replay_input.get("preservation_ids"), list) else []),
                "evolution_ids": copy.deepcopy(replay_input.get("evolution_ids") if isinstance(replay_input.get("evolution_ids"), list) else []),
            }
        return lineage

    def _session_lineage(
        self,
        *,
        workflow_id: str,
        session_id: str,
        task: Dict[str, Any],
        state: Dict[str, Any],
        events: List[WorkflowRuntimeEvent],
        result: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        source_session_id = self._source_session_id(task=task, state=state, result=result)
        parent_session_id = self._parent_session_id(task=task, state=state, result=result)
        event_ids_by_phase: Dict[str, List[str]] = {phase: [] for phase in WORKFLOW_SESSION_PHASES}
        for event in events:
            event_ids_by_phase.setdefault(event.phase, []).append(event.event_id)
        retry_events = [
            copy.deepcopy(event.lineage.get("retry_chain"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("retry_chain"), dict)
        ]
        repair_events = [
            copy.deepcopy(event.lineage.get("repair_ancestry"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("repair_ancestry"), dict)
        ]
        checkpoint_events = [
            copy.deepcopy(event.lineage.get("checkpoint"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("checkpoint"), dict)
        ]
        restore_events = [
            copy.deepcopy(event.lineage.get("restore"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("restore"), dict)
        ]
        resume_events = [
            copy.deepcopy(event.lineage.get("resume_continue"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("resume_continue"), dict)
        ]
        cursor_events = [
            copy.deepcopy(event.lineage.get("execution_cursor"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("execution_cursor"), dict)
        ]
        memory_events = [
            copy.deepcopy(event.lineage.get("execution_memory"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("execution_memory"), dict)
        ]
        recovery_points = [
            copy.deepcopy(event.lineage.get("recovery_resume_point"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("recovery_resume_point"), dict)
        ]
        recovery_resumes = [
            copy.deepcopy(event.lineage.get("recovery_resume"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("recovery_resume"), dict)
        ]
        graph_nodes = [
            copy.deepcopy(event.lineage.get("execution_graph_node"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("execution_graph_node"), dict)
        ]
        graph_edges = [
            copy.deepcopy(event.lineage.get("graph_edge"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("graph_edge"), dict)
        ]
        branch_forks = [
            copy.deepcopy(event.lineage.get("branch_fork"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("branch_fork"), dict)
        ]
        join_merges = [
            copy.deepcopy(event.lineage.get("join_merge"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("join_merge"), dict)
        ]
        recovery_dependencies = [
            copy.deepcopy(event.lineage.get("recovery_dependency"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("recovery_dependency"), dict)
        ]
        mutation_transactions = [
            copy.deepcopy(event.lineage.get("mutation_transaction"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("mutation_transaction"), dict)
        ]
        mutation_verifies = [
            copy.deepcopy(event.lineage.get("mutation_verify"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("mutation_verify"), dict)
        ]
        rollback_nodes = [
            copy.deepcopy(event.lineage.get("rollback_graph_node"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("rollback_graph_node"), dict)
        ]
        branch_conflicts = [
            copy.deepcopy(event.lineage.get("branch_conflict"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("branch_conflict"), dict)
        ]
        graph_reconciliations = [
            copy.deepcopy(event.lineage.get("graph_reconciliation"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("graph_reconciliation"), dict)
        ]
        policy_decisions = [
            copy.deepcopy(event.lineage.get("policy_decision"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("policy_decision"), dict)
        ]
        authority_records = [
            copy.deepcopy(event.lineage.get("authority_continuity"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("authority_continuity"), dict)
        ]
        review_records = [
            copy.deepcopy(event.lineage.get("review_required"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("review_required"), dict)
        ]
        approval_records = [
            copy.deepcopy(event.lineage.get("approval"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("approval"), dict)
        ]
        governance_resumes = [
            copy.deepcopy(event.lineage.get("governance_resume"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("governance_resume"), dict)
        ]
        constitution_enforcements = [
            copy.deepcopy(event.lineage.get("constitution_enforcement"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("constitution_enforcement"), dict)
        ]
        actor_workers = [
            copy.deepcopy(event.lineage.get("actor_worker"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("actor_worker"), dict)
        ]
        worker_federations = [
            copy.deepcopy(event.lineage.get("worker_federation"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("worker_federation"), dict)
        ]
        distributed_executions = [
            copy.deepcopy(event.lineage.get("distributed_execution"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("distributed_execution"), dict)
        ]
        distributed_recoveries = [
            copy.deepcopy(event.lineage.get("distributed_recovery"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("distributed_recovery"), dict)
        ]
        federated_authorities = [
            copy.deepcopy(event.lineage.get("federated_authority"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("federated_authority"), dict)
        ]
        distributed_governance = [
            copy.deepcopy(event.lineage.get("distributed_governance"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("distributed_governance"), dict)
        ]
        worker_decisions = [
            copy.deepcopy(event.lineage.get("worker_decision"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("worker_decision"), dict)
        ]
        arbitration_decisions = [
            copy.deepcopy(event.lineage.get("arbitration_decision"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("arbitration_decision"), dict)
        ]
        authority_quorums = [
            copy.deepcopy(event.lineage.get("authority_quorum"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("authority_quorum"), dict)
        ]
        consensus_votes = [
            copy.deepcopy(event.lineage.get("consensus_vote"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("consensus_vote"), dict)
        ]
        federated_consensus = [
            copy.deepcopy(event.lineage.get("federated_consensus"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("federated_consensus"), dict)
        ]
        replay_reconciliations = [
            copy.deepcopy(event.lineage.get("replay_reconciliation"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("replay_reconciliation"), dict)
        ]
        federated_governance_decisions = [
            copy.deepcopy(event.lineage.get("federated_governance_decision"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("federated_governance_decision"), dict)
        ]
        self_observability_records = [
            copy.deepcopy(event.lineage.get("runtime_self_observability"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("runtime_self_observability"), dict)
        ]
        constitutional_audits = [
            copy.deepcopy(event.lineage.get("constitutional_audit_lineage"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("constitutional_audit_lineage"), dict)
        ]
        self_diagnoses = [
            copy.deepcopy(event.lineage.get("self_diagnosis"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("self_diagnosis"), dict)
        ]
        self_repair_governance = [
            copy.deepcopy(event.lineage.get("self_repair_governance"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("self_repair_governance"), dict)
        ]
        self_healing_recoveries = [
            copy.deepcopy(event.lineage.get("self_healing_replay_recovery"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("self_healing_replay_recovery"), dict)
        ]
        adaptive_stabilizations = [
            copy.deepcopy(event.lineage.get("adaptive_governance_stabilization"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("adaptive_governance_stabilization"), dict)
        ]
        constitutional_preservations = [
            copy.deepcopy(event.lineage.get("constitutional_preservation"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("constitutional_preservation"), dict)
        ]
        self_preservation_decisions = [
            copy.deepcopy(event.lineage.get("self_preservation_decision"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("self_preservation_decision"), dict)
        ]
        catastrophic_failures = [
            copy.deepcopy(event.lineage.get("catastrophic_failure"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("catastrophic_failure"), dict)
        ]
        catastrophic_recoveries = [
            copy.deepcopy(event.lineage.get("catastrophic_recovery_lineage"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("catastrophic_recovery_lineage"), dict)
        ]
        constitutional_rollback_arbitrations = [
            copy.deepcopy(event.lineage.get("constitutional_rollback_arbitration"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("constitutional_rollback_arbitration"), dict)
        ]
        adaptive_constitutional_stabilizations = [
            copy.deepcopy(event.lineage.get("adaptive_constitutional_stabilization"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("adaptive_constitutional_stabilization"), dict)
        ]
        survivability_records = [
            copy.deepcopy(event.lineage.get("survivability_continuity"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("survivability_continuity"), dict)
        ]
        constitutional_evolutions = [
            copy.deepcopy(event.lineage.get("autonomous_constitutional_evolution"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("autonomous_constitutional_evolution"), dict)
        ]
        constitutional_forks = [
            copy.deepcopy(event.lineage.get("constitutional_fork"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("constitutional_fork"), dict)
        ]
        constitutional_merge_arbitrations = [
            copy.deepcopy(event.lineage.get("constitutional_merge_arbitration"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("constitutional_merge_arbitration"), dict)
        ]
        constitutional_merges = [
            copy.deepcopy(event.lineage.get("constitutional_merge"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("constitutional_merge"), dict)
        ]
        survivability_federations = [
            copy.deepcopy(event.lineage.get("survivability_federation_continuity"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("survivability_federation_continuity"), dict)
        ]
        governance_stabilization_loops = [
            copy.deepcopy(event.lineage.get("autonomous_governance_stabilization_loop"))
            for event in events
            if isinstance(event.lineage, dict) and isinstance(event.lineage.get("autonomous_governance_stabilization_loop"), dict)
        ]
        current_branch_id = self._current_branch_id_from_records(graph_nodes, branch_forks, state)
        lineage = {
            "schema": "zero.workflow_runtime_session.lineage.v1",
            "workflow_id": workflow_id,
            "session_id": session_id,
            "task_id": task_id_from(task, state),
            "source_session_id": source_session_id,
            "parent_session_id": parent_session_id,
            "root_session_id": parent_session_id or source_session_id or session_id,
            "current_branch_id": current_branch_id,
            "event_ids_by_phase": event_ids_by_phase,
            "repair_ancestry": repair_events[-20:],
            "retry_chain": retry_events[-20:],
            "checkpoints": checkpoint_events[-20:],
            "restores": restore_events[-20:],
            "resume_continuations": resume_events[-20:],
            "execution_cursors": cursor_events[-20:],
            "execution_memory": memory_events[-20:],
            "recovery_resume_points": recovery_points[-20:],
            "recovery_resumes": recovery_resumes[-20:],
            "execution_graph": {
                "schema": "zero.workflow_runtime_session.execution_graph.v1",
                "nodes": graph_nodes[-200:],
                "edges": graph_edges[-200:],
                "branches": branch_forks[-100:],
                "joins": join_merges[-100:],
            },
            "recovery_dependency_graph": {
                "schema": "zero.workflow_runtime_session.recovery_dependency_graph.v1",
                "dependencies": recovery_dependencies[-200:],
            },
            "mutation_transaction_graph": {
                "schema": "zero.workflow_runtime_session.mutation_transaction_graph.v1",
                "mutations": mutation_transactions[-200:],
                "verifies": mutation_verifies[-200:],
                "conflicts": branch_conflicts[-100:],
                "reconciliations": graph_reconciliations[-100:],
            },
            "rollback_graph": {
                "schema": "zero.workflow_runtime_session.rollback_graph.v1",
                "rollbacks": rollback_nodes[-200:],
            },
            "governance_state_graph": {
                "schema": "zero.workflow_runtime_session.governance_state_graph.v1",
                "policy_decisions": policy_decisions[-200:],
                "authority": authority_records[-200:],
                "reviews": review_records[-100:],
                "approvals": approval_records[-100:],
                "resumes": governance_resumes[-100:],
                "constitution_enforcements": constitution_enforcements[-200:],
            },
            "actor_worker_graph": {
                "schema": "zero.workflow_runtime_session.actor_worker_graph.v1",
                "workers": actor_workers[-200:],
                "federations": worker_federations[-100:],
                "distributed_executions": distributed_executions[-200:],
                "distributed_recoveries": distributed_recoveries[-100:],
                "federated_authority": federated_authorities[-100:],
                "distributed_governance": distributed_governance[-100:],
                "worker_decisions": worker_decisions[-200:],
            },
            "federated_consensus_graph": {
                "schema": "zero.workflow_runtime_session.federated_consensus_graph.v1",
                "arbitrations": arbitration_decisions[-100:],
                "quorums": authority_quorums[-100:],
                "votes": consensus_votes[-200:],
                "consensus": federated_consensus[-100:],
                "replay_reconciliations": replay_reconciliations[-100:],
                "governance_decisions": federated_governance_decisions[-100:],
            },
            "self_healing_governance_graph": {
                "schema": "zero.workflow_runtime_session.self_healing_governance_graph.v1",
                "observability": self_observability_records[-100:],
                "audits": constitutional_audits[-100:],
                "diagnoses": self_diagnoses[-100:],
                "self_repairs": self_repair_governance[-100:],
                "recoveries": self_healing_recoveries[-100:],
                "stabilizations": adaptive_stabilizations[-100:],
            },
            "constitutional_preservation_graph": {
                "schema": "zero.workflow_runtime_session.constitutional_preservation_graph.v1",
                "preservations": constitutional_preservations[-100:],
                "self_preservation_decisions": self_preservation_decisions[-100:],
                "catastrophic_failures": catastrophic_failures[-100:],
                "catastrophic_recoveries": catastrophic_recoveries[-100:],
                "rollback_arbitrations": constitutional_rollback_arbitrations[-100:],
                "stabilizations": adaptive_constitutional_stabilizations[-100:],
                "survivability": survivability_records[-100:],
            },
            "constitutional_evolution_graph": {
                "schema": "zero.workflow_runtime_session.constitutional_evolution_graph.v1",
                "evolutions": constitutional_evolutions[-100:],
                "forks": constitutional_forks[-100:],
                "merge_arbitrations": constitutional_merge_arbitrations[-100:],
                "merges": constitutional_merges[-100:],
                "survivability_federations": survivability_federations[-100:],
                "stabilization_loops": governance_stabilization_loops[-100:],
            },
        }
        if source_session_id:
            replay_input = self._replay_continuation_input(task=task, state=state, result=result)
            replay_mutation_ids = [
                safe_text(item)
                for item in (replay_input.get("mutation_transaction_ids") if isinstance(replay_input.get("mutation_transaction_ids"), list) else [])
                if safe_text(item)
            ]
            if not replay_mutation_ids:
                replay_mutation_ids = [
                    safe_text(item.get("mutation_transaction_id"))
                    for item in mutation_transactions[-20:]
                    if isinstance(item, dict) and safe_text(item.get("mutation_transaction_id"))
                ]
            replay_governance_ids = [
                safe_text(item)
                for item in (replay_input.get("governance_record_ids") if isinstance(replay_input.get("governance_record_ids"), list) else [])
                if safe_text(item)
            ]
            if not replay_governance_ids:
                replay_governance_ids = self._governance_record_ids(
                    policy_decisions=policy_decisions,
                    authority_records=authority_records,
                    review_records=review_records,
                    approval_records=approval_records,
                    governance_resumes=governance_resumes,
                    constitution_enforcements=constitution_enforcements,
                )[-20:]
            replay_worker_ids = [
                safe_text(item)
                for item in (replay_input.get("worker_ids") if isinstance(replay_input.get("worker_ids"), list) else [])
                if safe_text(item)
            ]
            if not replay_worker_ids:
                replay_worker_ids = [
                    safe_text(item.get("worker_id"))
                    for item in actor_workers[-20:]
                    if isinstance(item, dict) and safe_text(item.get("worker_id"))
                ]
            replay_execution_ids = [
                safe_text(item)
                for item in (replay_input.get("distributed_execution_ids") if isinstance(replay_input.get("distributed_execution_ids"), list) else [])
                if safe_text(item)
            ]
            if not replay_execution_ids:
                replay_execution_ids = [
                    safe_text(item.get("distributed_execution_id"))
                    for item in distributed_executions[-20:]
                    if isinstance(item, dict) and safe_text(item.get("distributed_execution_id"))
                ]
            replay_consensus_ids = [
                safe_text(item)
                for item in (replay_input.get("consensus_ids") if isinstance(replay_input.get("consensus_ids"), list) else [])
                if safe_text(item)
            ]
            if not replay_consensus_ids:
                replay_consensus_ids = [
                    safe_text(item.get("consensus_id"))
                    for item in federated_consensus[-20:]
                    if isinstance(item, dict) and safe_text(item.get("consensus_id"))
                ]
            replay_self_healing_recovery_ids = [
                safe_text(item)
                for item in (replay_input.get("self_healing_recovery_ids") if isinstance(replay_input.get("self_healing_recovery_ids"), list) else [])
                if safe_text(item)
            ]
            if not replay_self_healing_recovery_ids:
                replay_self_healing_recovery_ids = [
                    safe_text(item.get("self_healing_recovery_id"))
                    for item in self_healing_recoveries[-20:]
                    if isinstance(item, dict) and safe_text(item.get("self_healing_recovery_id"))
                ]
            replay_preservation_ids = [
                safe_text(item)
                for item in (replay_input.get("preservation_ids") if isinstance(replay_input.get("preservation_ids"), list) else [])
                if safe_text(item)
            ]
            if not replay_preservation_ids:
                replay_preservation_ids = [
                    safe_text(item.get("preservation_id"))
                    for item in constitutional_preservations[-20:]
                    if isinstance(item, dict) and safe_text(item.get("preservation_id"))
                ]
            replay_evolution_ids = [
                safe_text(item)
                for item in (replay_input.get("evolution_ids") if isinstance(replay_input.get("evolution_ids"), list) else [])
                if safe_text(item)
            ]
            if not replay_evolution_ids:
                replay_evolution_ids = [
                    safe_text(item.get("evolution_id"))
                    for item in constitutional_evolutions[-20:]
                    if isinstance(item, dict) and safe_text(item.get("evolution_id"))
                ]
            lineage["replay_continuation"] = {
                "source_session_id": source_session_id,
                "continued_session_id": session_id,
                "workflow_id": workflow_id,
                "event_count": len(events),
                "recovery_resume_id": safe_text(recovery_resumes[-1].get("recovery_resume_id")) if recovery_resumes else "",
                "cursor_id": safe_text(recovery_resumes[-1].get("cursor_id")) if recovery_resumes else "",
                "source_branch_id": safe_text(replay_input.get("source_branch_id")),
                "continued_branch_id": safe_text(replay_input.get("continued_branch_id")) or current_branch_id,
                "mutation_transaction_ids": replay_mutation_ids,
                "rollback_ids": [
                    safe_text(item)
                    for item in (replay_input.get("rollback_ids") if isinstance(replay_input.get("rollback_ids"), list) else [])
                    if safe_text(item)
                ],
                "governance_record_ids": replay_governance_ids,
                "worker_ids": replay_worker_ids,
                "distributed_execution_ids": replay_execution_ids,
                "consensus_ids": replay_consensus_ids,
                "self_healing_recovery_ids": replay_self_healing_recovery_ids,
                "preservation_ids": replay_preservation_ids,
                "evolution_ids": replay_evolution_ids,
            }
        return lineage

    def _repair_ancestry(
        self,
        *,
        state: Dict[str, Any],
        step: Dict[str, Any] | None,
        step_result: Dict[str, Any],
        failed_parent: WorkflowRuntimeEvent | None,
    ) -> Dict[str, Any]:
        repair_context = state.get("repair_context") if isinstance(state, dict) else {}
        if not isinstance(repair_context, dict):
            repair_context = {}
        embedded = step.get("repair_ancestry") if isinstance(step, dict) and isinstance(step.get("repair_ancestry"), dict) else {}
        result_embedded = step_result.get("repair_ancestry") if isinstance(step_result, dict) and isinstance(step_result.get("repair_ancestry"), dict) else {}
        failed_step = (
            embedded.get("parent_failed_step")
            or embedded.get("failed_step")
            or result_embedded.get("parent_failed_step")
            or repair_context.get("original_failed_step")
            or repair_context.get("failed_step")
        )
        failed_result = (
            embedded.get("parent_failed_result")
            or embedded.get("failed_result")
            or result_embedded.get("parent_failed_result")
            or repair_context.get("original_failed_result")
            or repair_context.get("failed_result")
        )
        if failed_parent is not None:
            parent_payload = failed_parent.payload if isinstance(failed_parent.payload, dict) else {}
            failed_step = failed_step or parent_payload.get("step")
            failed_result = failed_result or parent_payload.get("result")
        parent_failed_step_ref = (
            embedded.get("parent_failed_step_ref")
            or result_embedded.get("parent_failed_step_ref")
            or self._reference_for_payload("failed_step", failed_step)
        )
        parent_failed_result_ref = (
            embedded.get("parent_failed_result_ref")
            or result_embedded.get("parent_failed_result_ref")
            or self._reference_for_payload("failed_result", failed_result)
        )
        return {
            "schema": "zero.workflow_runtime_session.repair_ancestry.v1",
            "parent_event_id": failed_parent.event_id if failed_parent is not None else "",
            "parent_failed_step_ref": copy.deepcopy(parent_failed_step_ref),
            "parent_failed_result_ref": copy.deepcopy(parent_failed_result_ref),
            "parent_failed_step": _json_safe(failed_step or {}),
            "parent_failed_result": _json_safe(failed_result or {}),
        }

    def _retry_chain(
        self,
        *,
        state: Dict[str, Any],
        step: Dict[str, Any] | None,
        step_result: Dict[str, Any],
        parent_event: WorkflowRuntimeEvent | None,
        events: List[WorkflowRuntimeEvent] | None = None,
    ) -> Dict[str, Any]:
        repair_context = state.get("repair_context") if isinstance(state, dict) else {}
        if not isinstance(repair_context, dict):
            repair_context = {}
        strategy = repair_context.get("strategy") if isinstance(repair_context.get("strategy"), dict) else {}
        retry_count = safe_int(
            step_result.get("retry_count")
            or strategy.get("retry_count")
            or state.get("retry_count") if isinstance(state, dict) else 0,
            0,
        )
        chain_seed = {
            "session_id": self.session_id_for({}, state),
            "parent_event_id": parent_event.event_id if parent_event else "",
            "step": step,
        }
        repair_ancestry = {}
        for event in reversed(events or []):
            if event.phase != "repair" or not isinstance(event.lineage, dict):
                continue
            candidate = event.lineage.get("repair_ancestry")
            if isinstance(candidate, dict):
                repair_ancestry = copy.deepcopy(candidate)
                break
        return {
            "schema": "zero.workflow_runtime_session.retry_chain.v1",
            "retry_chain_id": "wfr_" + stable_hash(chain_seed)[:16],
            "retry_attempt": retry_count,
            "parent_event_id": parent_event.event_id if parent_event else "",
            "repair_ancestry": repair_ancestry,
            "action": safe_text(step_result.get("action") if isinstance(step_result, dict) else ""),
        }

    def _latest_failed_event(
        self,
        events: List[WorkflowRuntimeEvent],
        *,
        preferred_phase: str = "",
    ) -> WorkflowRuntimeEvent | None:
        if preferred_phase:
            for event in reversed(events):
                if event.phase == preferred_phase and not event.ok:
                    return event
        for event in reversed(events):
            if not event.ok:
                return event
        return None

    def _latest_event_id(
        self,
        events: List[WorkflowRuntimeEvent],
        *,
        event_type: str,
    ) -> str:
        for event in reversed(events):
            if event.event_type == event_type:
                return event.event_id
        return ""

    def _latest_checkpoint_id(self, events: List[WorkflowRuntimeEvent]) -> str:
        for event in reversed(events):
            if not isinstance(event.lineage, dict):
                continue
            checkpoint = event.lineage.get("checkpoint")
            if isinstance(checkpoint, dict):
                value = safe_text(checkpoint.get("checkpoint_id"))
                if value:
                    return value
        return ""

    def _latest_lineage_item(self, session: Dict[str, Any], key: str) -> Dict[str, Any]:
        lineage = session.get("lineage") if isinstance(session, dict) and isinstance(session.get("lineage"), dict) else {}
        items = lineage.get(key)
        if isinstance(items, list) and items and isinstance(items[-1], dict):
            return copy.deepcopy(items[-1])
        return {}

    def _current_branch_id(self, session: Dict[str, Any], state: Dict[str, Any]) -> str:
        lineage = session.get("lineage") if isinstance(session, dict) and isinstance(session.get("lineage"), dict) else {}
        value = safe_text(state.get("current_branch_id") if isinstance(state, dict) else "")
        if value:
            return value
        value = safe_text(lineage.get("current_branch_id"))
        if value:
            return value
        graph = lineage.get("execution_graph") if isinstance(lineage.get("execution_graph"), dict) else {}
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        for node in reversed(nodes):
            if isinstance(node, dict) and safe_text(node.get("branch_id")):
                return safe_text(node.get("branch_id"))
        branches = graph.get("branches") if isinstance(graph.get("branches"), list) else []
        for branch in reversed(branches):
            if isinstance(branch, dict) and safe_text(branch.get("branch_id")):
                return safe_text(branch.get("branch_id"))
        return "main"

    def _current_branch_id_from_records(
        self,
        nodes: List[Dict[str, Any]],
        branches: List[Dict[str, Any]],
        state: Dict[str, Any],
    ) -> str:
        value = safe_text(state.get("current_branch_id") if isinstance(state, dict) else "")
        if value:
            return value
        for node in reversed(nodes):
            if isinstance(node, dict) and safe_text(node.get("branch_id")):
                return safe_text(node.get("branch_id"))
        for branch in reversed(branches):
            if isinstance(branch, dict) and safe_text(branch.get("branch_id")):
                return safe_text(branch.get("branch_id"))
        return ""

    def _replay_continuation_input(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        result: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        for source in (result, state, task):
            if not isinstance(source, dict):
                continue
            replay = source.get("replay_continuation")
            if isinstance(replay, dict):
                return copy.deepcopy(replay)
        return {}

    def _branches_related(
        self,
        source_branch_id: str,
        target_branch_id: str,
        branch_parent: Dict[str, str],
        joins: List[Dict[str, Any]],
    ) -> bool:
        source = safe_text(source_branch_id)
        target = safe_text(target_branch_id)
        if not source or not target:
            return False
        if source == target:
            return True
        if source in self._branch_ancestors(target, branch_parent):
            return True
        if target in self._branch_ancestors(source, branch_parent):
            return True
        for join in joins:
            join_target = safe_text(join.get("target_branch_id"))
            join_sources = {
                safe_text(item)
                for item in (join.get("source_branch_ids") if isinstance(join.get("source_branch_ids"), list) else [])
                if safe_text(item)
            }
            if target == join_target and source in join_sources:
                return True
            if source == join_target and target in join_sources:
                return True
            if source in join_sources and target in join_sources:
                return True
        return False

    def _branch_ancestors(self, branch_id: str, branch_parent: Dict[str, str]) -> set[str]:
        ancestors: set[str] = set()
        current = safe_text(branch_id)
        while current and current in branch_parent:
            parent = safe_text(branch_parent.get(current))
            if not parent or parent in ancestors:
                break
            ancestors.add(parent)
            current = parent
        return ancestors

    def _governance_record_ids(
        self,
        *,
        policy_decisions: List[Dict[str, Any]],
        authority_records: List[Dict[str, Any]],
        review_records: List[Dict[str, Any]],
        approval_records: List[Dict[str, Any]],
        governance_resumes: List[Dict[str, Any]],
        constitution_enforcements: List[Dict[str, Any]],
    ) -> List[str]:
        ids: List[str] = []
        for key, records in (
            ("policy_decision_id", policy_decisions),
            ("authority_id", authority_records),
            ("review_id", review_records),
            ("approval_id", approval_records),
            ("governance_resume_id", governance_resumes),
            ("enforcement_id", constitution_enforcements),
        ):
            for record in records:
                value = safe_text(record.get(key)) if isinstance(record, dict) else ""
                if value:
                    ids.append(value)
        return ids

    def _source_session_id(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        result: Dict[str, Any] | None,
    ) -> str:
        for source in (result, state, task):
            if not isinstance(source, dict):
                continue
            value = safe_text(source.get("source_session_id"))
            if value:
                return value
            replay = source.get("replay_continuation")
            if isinstance(replay, dict):
                value = safe_text(replay.get("source_session_id"))
                if value:
                    return value
        existing = state.get("workflow_runtime_session") if isinstance(state, dict) else {}
        if isinstance(existing, dict):
            lineage = existing.get("lineage") if isinstance(existing.get("lineage"), dict) else {}
            return safe_text(lineage.get("source_session_id"))
        return ""

    def _parent_session_id(
        self,
        *,
        task: Dict[str, Any],
        state: Dict[str, Any],
        result: Dict[str, Any] | None,
    ) -> str:
        for source in (result, state, task):
            if isinstance(source, dict):
                value = safe_text(source.get("parent_session_id"))
                if value:
                    return value
        return ""

    def _reference_for_payload(self, kind: str, payload: Any) -> Dict[str, Any]:
        if not payload:
            return {}
        return {
            "kind": kind,
            "hash": stable_hash(payload),
        }

    def _event_dedupe_key(self, event: WorkflowRuntimeEvent) -> tuple[Any, ...]:
        payload = event.payload if isinstance(event.payload, dict) else {}
        return (
            event.phase,
            event.tick,
            event.step_index,
            stable_hash(
                {
                    "step": payload.get("step"),
                    "result": payload.get("result"),
                }
            ),
        )

    def _dictionary_contract(self) -> Dict[str, Any]:
        return {
            "schema": "zero.workflow_runtime_session.dictionary_contract.v1",
            "required_session_keys": [
                "schema",
                "session_id",
                "workflow_id",
                "task_id",
                "status",
                "phases",
                "events",
                "lineage",
                "continuity_summary",
            ],
            "required_event_keys": [
                "event_id",
                "workflow_id",
                "session_id",
                "phase",
                "status",
                "payload_hash",
                "lineage",
            ],
            "persistence_ready": True,
        }

    def continuity_summary(self, session: Dict[str, Any]) -> Dict[str, Any]:
        session_id = safe_text(session.get("session_id"))
        workflow_id = safe_text(session.get("workflow_id"))
        lineage = session.get("lineage") if isinstance(session.get("lineage"), dict) else {}
        events = session.get("events") if isinstance(session.get("events"), list) else []
        breaks: List[str] = []

        if not session_id:
            breaks.append("missing_session_id")
        if not workflow_id:
            breaks.append("missing_workflow_id")

        event_ids = set()
        checkpoint_ids = set()
        cursor_ids = set()
        memory_ids = set()
        recovery_resume_ids = set()
        graph_node_ids = set()
        branch_ids = {"main"}
        graph_edges: List[Dict[str, Any]] = []
        branch_forks: List[Dict[str, Any]] = []
        join_merges: List[Dict[str, Any]] = []
        recovery_dependencies: List[Dict[str, Any]] = []
        mutation_transactions: List[Dict[str, Any]] = []
        mutation_verifies: List[Dict[str, Any]] = []
        rollback_nodes: List[Dict[str, Any]] = []
        branch_conflicts: List[Dict[str, Any]] = []
        graph_reconciliations: List[Dict[str, Any]] = []
        policy_decisions: List[Dict[str, Any]] = []
        authority_records: List[Dict[str, Any]] = []
        review_records: List[Dict[str, Any]] = []
        approval_records: List[Dict[str, Any]] = []
        governance_resumes: List[Dict[str, Any]] = []
        constitution_enforcements: List[Dict[str, Any]] = []
        actor_workers: List[Dict[str, Any]] = []
        worker_federations: List[Dict[str, Any]] = []
        distributed_executions: List[Dict[str, Any]] = []
        distributed_recoveries: List[Dict[str, Any]] = []
        federated_authorities: List[Dict[str, Any]] = []
        distributed_governance: List[Dict[str, Any]] = []
        worker_decisions: List[Dict[str, Any]] = []
        arbitration_decisions: List[Dict[str, Any]] = []
        authority_quorums: List[Dict[str, Any]] = []
        consensus_votes: List[Dict[str, Any]] = []
        federated_consensus: List[Dict[str, Any]] = []
        replay_reconciliations: List[Dict[str, Any]] = []
        federated_governance_decisions: List[Dict[str, Any]] = []
        self_observability_records: List[Dict[str, Any]] = []
        constitutional_audits: List[Dict[str, Any]] = []
        self_diagnoses: List[Dict[str, Any]] = []
        self_repair_governance: List[Dict[str, Any]] = []
        self_healing_recoveries: List[Dict[str, Any]] = []
        adaptive_stabilizations: List[Dict[str, Any]] = []
        constitutional_preservations: List[Dict[str, Any]] = []
        self_preservation_decisions: List[Dict[str, Any]] = []
        catastrophic_failures: List[Dict[str, Any]] = []
        catastrophic_recoveries: List[Dict[str, Any]] = []
        constitutional_rollback_arbitrations: List[Dict[str, Any]] = []
        adaptive_constitutional_stabilizations: List[Dict[str, Any]] = []
        survivability_records: List[Dict[str, Any]] = []
        constitutional_evolutions: List[Dict[str, Any]] = []
        constitutional_forks: List[Dict[str, Any]] = []
        constitutional_merge_arbitrations: List[Dict[str, Any]] = []
        constitutional_merges: List[Dict[str, Any]] = []
        survivability_federations: List[Dict[str, Any]] = []
        governance_stabilization_loops: List[Dict[str, Any]] = []
        node_branch: Dict[str, str] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = safe_text(event.get("event_id"))
            if event_id:
                event_ids.add(event_id)
            if safe_text(event.get("session_id")) and safe_text(event.get("session_id")) != session_id:
                breaks.append("event_session_id_mismatch")
            if safe_text(event.get("workflow_id")) and safe_text(event.get("workflow_id")) != workflow_id:
                breaks.append("event_workflow_id_mismatch")
            event_lineage = event.get("lineage") if isinstance(event.get("lineage"), dict) else {}
            parent_event_id = safe_text(event_lineage.get("parent_event_id"))
            if parent_event_id and parent_event_id not in event_ids:
                breaks.append("broken_parent_event_link")
            if event.get("phase") == "repair":
                ancestry = event_lineage.get("repair_ancestry") if isinstance(event_lineage.get("repair_ancestry"), dict) else {}
                if not ancestry.get("parent_failed_step_ref") or not ancestry.get("parent_failed_result_ref"):
                    breaks.append("missing_repair_parent_reference")
            checkpoint = event_lineage.get("checkpoint") if isinstance(event_lineage.get("checkpoint"), dict) else {}
            checkpoint_id = safe_text(checkpoint.get("checkpoint_id"))
            if checkpoint_id:
                if safe_text(checkpoint.get("workflow_id")) and safe_text(checkpoint.get("workflow_id")) != workflow_id:
                    breaks.append("checkpoint_workflow_id_mismatch")
                if safe_text(checkpoint.get("session_id")) and safe_text(checkpoint.get("session_id")) != session_id:
                    breaks.append("checkpoint_session_id_mismatch")
                checkpoint_ids.add(checkpoint_id)
            restore = event_lineage.get("restore") if isinstance(event_lineage.get("restore"), dict) else {}
            if restore:
                source_checkpoint_id = safe_text(restore.get("source_checkpoint_id"))
                if not source_checkpoint_id:
                    breaks.append("missing_restore_source_checkpoint")
                elif source_checkpoint_id not in checkpoint_ids:
                    breaks.append("missing_restore_source_checkpoint")
                if safe_text(restore.get("source_workflow_id")) and safe_text(restore.get("source_workflow_id")) != workflow_id:
                    breaks.append("restore_source_workflow_id_mismatch")
                if safe_text(restore.get("source_session_id")) and safe_text(restore.get("source_session_id")) != session_id:
                    breaks.append("restore_source_session_id_mismatch")
                if safe_text(restore.get("workflow_id")) and safe_text(restore.get("workflow_id")) != workflow_id:
                    breaks.append("restore_workflow_id_mismatch")
                if safe_text(restore.get("session_id")) and safe_text(restore.get("session_id")) != session_id:
                    breaks.append("restore_session_id_mismatch")
            resume = event_lineage.get("resume_continue") if isinstance(event_lineage.get("resume_continue"), dict) else {}
            if resume and safe_text(resume.get("checkpoint_id")) and safe_text(resume.get("checkpoint_id")) not in checkpoint_ids:
                breaks.append("resume_checkpoint_id_mismatch")
            cursor = event_lineage.get("execution_cursor") if isinstance(event_lineage.get("execution_cursor"), dict) else {}
            cursor_id = safe_text(cursor.get("cursor_id"))
            if cursor_id:
                if safe_text(cursor.get("workflow_id")) and safe_text(cursor.get("workflow_id")) != workflow_id:
                    breaks.append("cursor_workflow_id_mismatch")
                if safe_text(cursor.get("session_id")) and safe_text(cursor.get("session_id")) != session_id:
                    breaks.append("cursor_session_id_mismatch")
                if safe_text(cursor.get("checkpoint_id")) and safe_text(cursor.get("checkpoint_id")) not in checkpoint_ids:
                    breaks.append("cursor_checkpoint_id_mismatch")
                restore_event_id = safe_text(cursor.get("restore_event_id"))
                if restore_event_id and restore_event_id not in event_ids:
                    breaks.append("cursor_restore_event_id_mismatch")
                cursor_ids.add(cursor_id)
            memory = event_lineage.get("execution_memory") if isinstance(event_lineage.get("execution_memory"), dict) else {}
            memory_id = safe_text(memory.get("memory_id"))
            if memory_id:
                if safe_text(memory.get("workflow_id")) and safe_text(memory.get("workflow_id")) != workflow_id:
                    breaks.append("memory_workflow_id_mismatch")
                if safe_text(memory.get("session_id")) and safe_text(memory.get("session_id")) != session_id:
                    breaks.append("memory_session_id_mismatch")
                if safe_text(memory.get("cursor_id")) and safe_text(memory.get("cursor_id")) not in cursor_ids:
                    breaks.append("memory_cursor_id_mismatch")
                memory_ids.add(memory_id)
            recovery_point = event_lineage.get("recovery_resume_point") if isinstance(event_lineage.get("recovery_resume_point"), dict) else {}
            recovery_resume_id = safe_text(recovery_point.get("recovery_resume_id"))
            if recovery_resume_id:
                if safe_text(recovery_point.get("workflow_id")) and safe_text(recovery_point.get("workflow_id")) != workflow_id:
                    breaks.append("recovery_resume_point_workflow_id_mismatch")
                if safe_text(recovery_point.get("session_id")) and safe_text(recovery_point.get("session_id")) != session_id:
                    breaks.append("recovery_resume_point_session_id_mismatch")
                if safe_text(recovery_point.get("cursor_id")) and safe_text(recovery_point.get("cursor_id")) not in cursor_ids:
                    breaks.append("recovery_resume_point_cursor_id_mismatch")
                if safe_text(recovery_point.get("memory_id")) and safe_text(recovery_point.get("memory_id")) not in memory_ids:
                    breaks.append("recovery_resume_point_memory_id_mismatch")
                recovery_resume_ids.add(recovery_resume_id)
            recovery_resume = event_lineage.get("recovery_resume") if isinstance(event_lineage.get("recovery_resume"), dict) else {}
            if recovery_resume:
                resume_id = safe_text(recovery_resume.get("recovery_resume_id"))
                if not resume_id or resume_id not in recovery_resume_ids:
                    breaks.append("recovery_resume_point_missing")
                if safe_text(recovery_resume.get("workflow_id")) and safe_text(recovery_resume.get("workflow_id")) != workflow_id:
                    breaks.append("recovery_resume_workflow_id_mismatch")
                if safe_text(recovery_resume.get("session_id")) and safe_text(recovery_resume.get("session_id")) != session_id:
                    breaks.append("recovery_resume_session_id_mismatch")
                if safe_text(recovery_resume.get("source_workflow_id")) and safe_text(recovery_resume.get("source_workflow_id")) != workflow_id:
                    breaks.append("recovery_resume_source_workflow_id_mismatch")
                if safe_text(recovery_resume.get("source_session_id")) and safe_text(recovery_resume.get("source_session_id")) != session_id:
                    breaks.append("recovery_resume_source_session_id_mismatch")
                if safe_text(recovery_resume.get("cursor_id")) and safe_text(recovery_resume.get("cursor_id")) not in cursor_ids:
                    breaks.append("recovery_resume_cursor_id_mismatch")
            graph_node = event_lineage.get("execution_graph_node") if isinstance(event_lineage.get("execution_graph_node"), dict) else {}
            node_id = safe_text(graph_node.get("node_id"))
            if node_id:
                if safe_text(graph_node.get("workflow_id")) and safe_text(graph_node.get("workflow_id")) != workflow_id:
                    breaks.append("graph_node_workflow_id_mismatch")
                if safe_text(graph_node.get("session_id")) and safe_text(graph_node.get("session_id")) != session_id:
                    breaks.append("graph_node_session_id_mismatch")
                graph_node_ids.add(node_id)
                branch_id = safe_text(graph_node.get("branch_id"))
                if branch_id:
                    branch_ids.add(branch_id)
                    node_branch[node_id] = branch_id
            graph_edge = event_lineage.get("graph_edge") if isinstance(event_lineage.get("graph_edge"), dict) else {}
            if graph_edge:
                graph_edges.append(copy.deepcopy(graph_edge))
            branch_fork = event_lineage.get("branch_fork") if isinstance(event_lineage.get("branch_fork"), dict) else {}
            if branch_fork:
                branch_forks.append(copy.deepcopy(branch_fork))
                branch_id = safe_text(branch_fork.get("branch_id"))
                if branch_id:
                    branch_ids.add(branch_id)
            join_merge = event_lineage.get("join_merge") if isinstance(event_lineage.get("join_merge"), dict) else {}
            if join_merge:
                join_merges.append(copy.deepcopy(join_merge))
            recovery_dependency = event_lineage.get("recovery_dependency") if isinstance(event_lineage.get("recovery_dependency"), dict) else {}
            if recovery_dependency:
                recovery_dependencies.append(copy.deepcopy(recovery_dependency))
            mutation_transaction = event_lineage.get("mutation_transaction") if isinstance(event_lineage.get("mutation_transaction"), dict) else {}
            if mutation_transaction:
                mutation_transactions.append(copy.deepcopy(mutation_transaction))
            mutation_verify = event_lineage.get("mutation_verify") if isinstance(event_lineage.get("mutation_verify"), dict) else {}
            if mutation_verify:
                mutation_verifies.append(copy.deepcopy(mutation_verify))
            rollback_node = event_lineage.get("rollback_graph_node") if isinstance(event_lineage.get("rollback_graph_node"), dict) else {}
            if rollback_node:
                rollback_nodes.append(copy.deepcopy(rollback_node))
            branch_conflict = event_lineage.get("branch_conflict") if isinstance(event_lineage.get("branch_conflict"), dict) else {}
            if branch_conflict:
                branch_conflicts.append(copy.deepcopy(branch_conflict))
            graph_reconciliation = event_lineage.get("graph_reconciliation") if isinstance(event_lineage.get("graph_reconciliation"), dict) else {}
            if graph_reconciliation:
                graph_reconciliations.append(copy.deepcopy(graph_reconciliation))
            policy_decision = event_lineage.get("policy_decision") if isinstance(event_lineage.get("policy_decision"), dict) else {}
            if policy_decision:
                policy_decisions.append(copy.deepcopy(policy_decision))
            authority = event_lineage.get("authority_continuity") if isinstance(event_lineage.get("authority_continuity"), dict) else {}
            if authority:
                authority_records.append(copy.deepcopy(authority))
            review = event_lineage.get("review_required") if isinstance(event_lineage.get("review_required"), dict) else {}
            if review:
                review_records.append(copy.deepcopy(review))
            approval = event_lineage.get("approval") if isinstance(event_lineage.get("approval"), dict) else {}
            if approval:
                approval_records.append(copy.deepcopy(approval))
            governance_resume = event_lineage.get("governance_resume") if isinstance(event_lineage.get("governance_resume"), dict) else {}
            if governance_resume:
                governance_resumes.append(copy.deepcopy(governance_resume))
            constitution_enforcement = event_lineage.get("constitution_enforcement") if isinstance(event_lineage.get("constitution_enforcement"), dict) else {}
            if constitution_enforcement:
                constitution_enforcements.append(copy.deepcopy(constitution_enforcement))
            actor_worker = event_lineage.get("actor_worker") if isinstance(event_lineage.get("actor_worker"), dict) else {}
            if actor_worker:
                actor_workers.append(copy.deepcopy(actor_worker))
            worker_federation = event_lineage.get("worker_federation") if isinstance(event_lineage.get("worker_federation"), dict) else {}
            if worker_federation:
                worker_federations.append(copy.deepcopy(worker_federation))
            distributed_execution = event_lineage.get("distributed_execution") if isinstance(event_lineage.get("distributed_execution"), dict) else {}
            if distributed_execution:
                distributed_executions.append(copy.deepcopy(distributed_execution))
            distributed_recovery = event_lineage.get("distributed_recovery") if isinstance(event_lineage.get("distributed_recovery"), dict) else {}
            if distributed_recovery:
                distributed_recoveries.append(copy.deepcopy(distributed_recovery))
            federated_authority = event_lineage.get("federated_authority") if isinstance(event_lineage.get("federated_authority"), dict) else {}
            if federated_authority:
                federated_authorities.append(copy.deepcopy(federated_authority))
            distributed_governance_record = event_lineage.get("distributed_governance") if isinstance(event_lineage.get("distributed_governance"), dict) else {}
            if distributed_governance_record:
                distributed_governance.append(copy.deepcopy(distributed_governance_record))
            worker_decision = event_lineage.get("worker_decision") if isinstance(event_lineage.get("worker_decision"), dict) else {}
            if worker_decision:
                worker_decisions.append(copy.deepcopy(worker_decision))
            arbitration_decision = event_lineage.get("arbitration_decision") if isinstance(event_lineage.get("arbitration_decision"), dict) else {}
            if arbitration_decision:
                arbitration_decisions.append(copy.deepcopy(arbitration_decision))
            authority_quorum = event_lineage.get("authority_quorum") if isinstance(event_lineage.get("authority_quorum"), dict) else {}
            if authority_quorum:
                authority_quorums.append(copy.deepcopy(authority_quorum))
            consensus_vote = event_lineage.get("consensus_vote") if isinstance(event_lineage.get("consensus_vote"), dict) else {}
            if consensus_vote:
                consensus_votes.append(copy.deepcopy(consensus_vote))
            consensus_record = event_lineage.get("federated_consensus") if isinstance(event_lineage.get("federated_consensus"), dict) else {}
            if consensus_record:
                federated_consensus.append(copy.deepcopy(consensus_record))
            replay_reconciliation = event_lineage.get("replay_reconciliation") if isinstance(event_lineage.get("replay_reconciliation"), dict) else {}
            if replay_reconciliation:
                replay_reconciliations.append(copy.deepcopy(replay_reconciliation))
            governance_decision = event_lineage.get("federated_governance_decision") if isinstance(event_lineage.get("federated_governance_decision"), dict) else {}
            if governance_decision:
                federated_governance_decisions.append(copy.deepcopy(governance_decision))
            observability = event_lineage.get("runtime_self_observability") if isinstance(event_lineage.get("runtime_self_observability"), dict) else {}
            if observability:
                self_observability_records.append(copy.deepcopy(observability))
            audit = event_lineage.get("constitutional_audit_lineage") if isinstance(event_lineage.get("constitutional_audit_lineage"), dict) else {}
            if audit:
                constitutional_audits.append(copy.deepcopy(audit))
            diagnosis = event_lineage.get("self_diagnosis") if isinstance(event_lineage.get("self_diagnosis"), dict) else {}
            if diagnosis:
                self_diagnoses.append(copy.deepcopy(diagnosis))
            repair_governance = event_lineage.get("self_repair_governance") if isinstance(event_lineage.get("self_repair_governance"), dict) else {}
            if repair_governance:
                self_repair_governance.append(copy.deepcopy(repair_governance))
            healing_recovery = event_lineage.get("self_healing_replay_recovery") if isinstance(event_lineage.get("self_healing_replay_recovery"), dict) else {}
            if healing_recovery:
                self_healing_recoveries.append(copy.deepcopy(healing_recovery))
            stabilization = event_lineage.get("adaptive_governance_stabilization") if isinstance(event_lineage.get("adaptive_governance_stabilization"), dict) else {}
            if stabilization:
                adaptive_stabilizations.append(copy.deepcopy(stabilization))
            preservation = event_lineage.get("constitutional_preservation") if isinstance(event_lineage.get("constitutional_preservation"), dict) else {}
            if preservation:
                constitutional_preservations.append(copy.deepcopy(preservation))
            self_preservation = event_lineage.get("self_preservation_decision") if isinstance(event_lineage.get("self_preservation_decision"), dict) else {}
            if self_preservation:
                self_preservation_decisions.append(copy.deepcopy(self_preservation))
            catastrophic_failure = event_lineage.get("catastrophic_failure") if isinstance(event_lineage.get("catastrophic_failure"), dict) else {}
            if catastrophic_failure:
                catastrophic_failures.append(copy.deepcopy(catastrophic_failure))
            catastrophic_recovery = event_lineage.get("catastrophic_recovery_lineage") if isinstance(event_lineage.get("catastrophic_recovery_lineage"), dict) else {}
            if catastrophic_recovery:
                catastrophic_recoveries.append(copy.deepcopy(catastrophic_recovery))
            rollback_arbitration = event_lineage.get("constitutional_rollback_arbitration") if isinstance(event_lineage.get("constitutional_rollback_arbitration"), dict) else {}
            if rollback_arbitration:
                constitutional_rollback_arbitrations.append(copy.deepcopy(rollback_arbitration))
            constitutional_stabilization = event_lineage.get("adaptive_constitutional_stabilization") if isinstance(event_lineage.get("adaptive_constitutional_stabilization"), dict) else {}
            if constitutional_stabilization:
                adaptive_constitutional_stabilizations.append(copy.deepcopy(constitutional_stabilization))
            survivability = event_lineage.get("survivability_continuity") if isinstance(event_lineage.get("survivability_continuity"), dict) else {}
            if survivability:
                survivability_records.append(copy.deepcopy(survivability))
            evolution = event_lineage.get("autonomous_constitutional_evolution") if isinstance(event_lineage.get("autonomous_constitutional_evolution"), dict) else {}
            if evolution:
                constitutional_evolutions.append(copy.deepcopy(evolution))
            constitutional_fork = event_lineage.get("constitutional_fork") if isinstance(event_lineage.get("constitutional_fork"), dict) else {}
            if constitutional_fork:
                constitutional_forks.append(copy.deepcopy(constitutional_fork))
            merge_arbitration = event_lineage.get("constitutional_merge_arbitration") if isinstance(event_lineage.get("constitutional_merge_arbitration"), dict) else {}
            if merge_arbitration:
                constitutional_merge_arbitrations.append(copy.deepcopy(merge_arbitration))
            constitutional_merge = event_lineage.get("constitutional_merge") if isinstance(event_lineage.get("constitutional_merge"), dict) else {}
            if constitutional_merge:
                constitutional_merges.append(copy.deepcopy(constitutional_merge))
            survivability_federation = event_lineage.get("survivability_federation_continuity") if isinstance(event_lineage.get("survivability_federation_continuity"), dict) else {}
            if survivability_federation:
                survivability_federations.append(copy.deepcopy(survivability_federation))
            stabilization_loop = event_lineage.get("autonomous_governance_stabilization_loop") if isinstance(event_lineage.get("autonomous_governance_stabilization_loop"), dict) else {}
            if stabilization_loop:
                governance_stabilization_loops.append(copy.deepcopy(stabilization_loop))

        graph = lineage.get("execution_graph") if isinstance(lineage.get("execution_graph"), dict) else {}
        for node in graph.get("nodes") if isinstance(graph.get("nodes"), list) else []:
            if not isinstance(node, dict):
                continue
            node_id = safe_text(node.get("node_id"))
            if node_id:
                graph_node_ids.add(node_id)
                if safe_text(node.get("branch_id")):
                    branch_ids.add(safe_text(node.get("branch_id")))
                    node_branch.setdefault(node_id, safe_text(node.get("branch_id")))
        for branch in graph.get("branches") if isinstance(graph.get("branches"), list) else []:
            if isinstance(branch, dict) and safe_text(branch.get("branch_id")):
                branch_ids.add(safe_text(branch.get("branch_id")))
                if branch not in branch_forks:
                    branch_forks.append(copy.deepcopy(branch))
        for edge in graph.get("edges") if isinstance(graph.get("edges"), list) else []:
            if isinstance(edge, dict) and edge not in graph_edges:
                graph_edges.append(copy.deepcopy(edge))
        for join in graph.get("joins") if isinstance(graph.get("joins"), list) else []:
            if isinstance(join, dict) and join not in join_merges:
                join_merges.append(copy.deepcopy(join))
        recovery_graph = lineage.get("recovery_dependency_graph") if isinstance(lineage.get("recovery_dependency_graph"), dict) else {}
        for dependency in recovery_graph.get("dependencies") if isinstance(recovery_graph.get("dependencies"), list) else []:
            if isinstance(dependency, dict) and dependency not in recovery_dependencies:
                recovery_dependencies.append(copy.deepcopy(dependency))
        mutation_graph = lineage.get("mutation_transaction_graph") if isinstance(lineage.get("mutation_transaction_graph"), dict) else {}
        for mutation in mutation_graph.get("mutations") if isinstance(mutation_graph.get("mutations"), list) else []:
            if isinstance(mutation, dict) and mutation not in mutation_transactions:
                mutation_transactions.append(copy.deepcopy(mutation))
        for verify in mutation_graph.get("verifies") if isinstance(mutation_graph.get("verifies"), list) else []:
            if isinstance(verify, dict) and verify not in mutation_verifies:
                mutation_verifies.append(copy.deepcopy(verify))
        for conflict in mutation_graph.get("conflicts") if isinstance(mutation_graph.get("conflicts"), list) else []:
            if isinstance(conflict, dict) and conflict not in branch_conflicts:
                branch_conflicts.append(copy.deepcopy(conflict))
        for reconciliation in mutation_graph.get("reconciliations") if isinstance(mutation_graph.get("reconciliations"), list) else []:
            if isinstance(reconciliation, dict) and reconciliation not in graph_reconciliations:
                graph_reconciliations.append(copy.deepcopy(reconciliation))
        rollback_graph = lineage.get("rollback_graph") if isinstance(lineage.get("rollback_graph"), dict) else {}
        for rollback in rollback_graph.get("rollbacks") if isinstance(rollback_graph.get("rollbacks"), list) else []:
            if isinstance(rollback, dict) and rollback not in rollback_nodes:
                rollback_nodes.append(copy.deepcopy(rollback))
        governance_graph = lineage.get("governance_state_graph") if isinstance(lineage.get("governance_state_graph"), dict) else {}
        for decision in governance_graph.get("policy_decisions") if isinstance(governance_graph.get("policy_decisions"), list) else []:
            if isinstance(decision, dict) and decision not in policy_decisions:
                policy_decisions.append(copy.deepcopy(decision))
        for authority in governance_graph.get("authority") if isinstance(governance_graph.get("authority"), list) else []:
            if isinstance(authority, dict) and authority not in authority_records:
                authority_records.append(copy.deepcopy(authority))
        for review in governance_graph.get("reviews") if isinstance(governance_graph.get("reviews"), list) else []:
            if isinstance(review, dict) and review not in review_records:
                review_records.append(copy.deepcopy(review))
        for approval in governance_graph.get("approvals") if isinstance(governance_graph.get("approvals"), list) else []:
            if isinstance(approval, dict) and approval not in approval_records:
                approval_records.append(copy.deepcopy(approval))
        for resume_record in governance_graph.get("resumes") if isinstance(governance_graph.get("resumes"), list) else []:
            if isinstance(resume_record, dict) and resume_record not in governance_resumes:
                governance_resumes.append(copy.deepcopy(resume_record))
        for enforcement in governance_graph.get("constitution_enforcements") if isinstance(governance_graph.get("constitution_enforcements"), list) else []:
            if isinstance(enforcement, dict) and enforcement not in constitution_enforcements:
                constitution_enforcements.append(copy.deepcopy(enforcement))
        actor_graph = lineage.get("actor_worker_graph") if isinstance(lineage.get("actor_worker_graph"), dict) else {}
        for worker in actor_graph.get("workers") if isinstance(actor_graph.get("workers"), list) else []:
            if isinstance(worker, dict) and worker not in actor_workers:
                actor_workers.append(copy.deepcopy(worker))
        for federation in actor_graph.get("federations") if isinstance(actor_graph.get("federations"), list) else []:
            if isinstance(federation, dict) and federation not in worker_federations:
                worker_federations.append(copy.deepcopy(federation))
        for execution in actor_graph.get("distributed_executions") if isinstance(actor_graph.get("distributed_executions"), list) else []:
            if isinstance(execution, dict) and execution not in distributed_executions:
                distributed_executions.append(copy.deepcopy(execution))
        for recovery in actor_graph.get("distributed_recoveries") if isinstance(actor_graph.get("distributed_recoveries"), list) else []:
            if isinstance(recovery, dict) and recovery not in distributed_recoveries:
                distributed_recoveries.append(copy.deepcopy(recovery))
        for authority in actor_graph.get("federated_authority") if isinstance(actor_graph.get("federated_authority"), list) else []:
            if isinstance(authority, dict) and authority not in federated_authorities:
                federated_authorities.append(copy.deepcopy(authority))
        for governance_item in actor_graph.get("distributed_governance") if isinstance(actor_graph.get("distributed_governance"), list) else []:
            if isinstance(governance_item, dict) and governance_item not in distributed_governance:
                distributed_governance.append(copy.deepcopy(governance_item))
        for decision in actor_graph.get("worker_decisions") if isinstance(actor_graph.get("worker_decisions"), list) else []:
            if isinstance(decision, dict) and decision not in worker_decisions:
                worker_decisions.append(copy.deepcopy(decision))
        consensus_graph = lineage.get("federated_consensus_graph") if isinstance(lineage.get("federated_consensus_graph"), dict) else {}
        for arbitration in consensus_graph.get("arbitrations") if isinstance(consensus_graph.get("arbitrations"), list) else []:
            if isinstance(arbitration, dict) and arbitration not in arbitration_decisions:
                arbitration_decisions.append(copy.deepcopy(arbitration))
        for quorum in consensus_graph.get("quorums") if isinstance(consensus_graph.get("quorums"), list) else []:
            if isinstance(quorum, dict) and quorum not in authority_quorums:
                authority_quorums.append(copy.deepcopy(quorum))
        for vote in consensus_graph.get("votes") if isinstance(consensus_graph.get("votes"), list) else []:
            if isinstance(vote, dict) and vote not in consensus_votes:
                consensus_votes.append(copy.deepcopy(vote))
        for consensus_record in consensus_graph.get("consensus") if isinstance(consensus_graph.get("consensus"), list) else []:
            if isinstance(consensus_record, dict) and consensus_record not in federated_consensus:
                federated_consensus.append(copy.deepcopy(consensus_record))
        for reconciliation in consensus_graph.get("replay_reconciliations") if isinstance(consensus_graph.get("replay_reconciliations"), list) else []:
            if isinstance(reconciliation, dict) and reconciliation not in replay_reconciliations:
                replay_reconciliations.append(copy.deepcopy(reconciliation))
        for governance_decision in consensus_graph.get("governance_decisions") if isinstance(consensus_graph.get("governance_decisions"), list) else []:
            if isinstance(governance_decision, dict) and governance_decision not in federated_governance_decisions:
                federated_governance_decisions.append(copy.deepcopy(governance_decision))
        self_healing_graph = lineage.get("self_healing_governance_graph") if isinstance(lineage.get("self_healing_governance_graph"), dict) else {}
        for observability in self_healing_graph.get("observability") if isinstance(self_healing_graph.get("observability"), list) else []:
            if isinstance(observability, dict) and observability not in self_observability_records:
                self_observability_records.append(copy.deepcopy(observability))
        for audit in self_healing_graph.get("audits") if isinstance(self_healing_graph.get("audits"), list) else []:
            if isinstance(audit, dict) and audit not in constitutional_audits:
                constitutional_audits.append(copy.deepcopy(audit))
        for diagnosis in self_healing_graph.get("diagnoses") if isinstance(self_healing_graph.get("diagnoses"), list) else []:
            if isinstance(diagnosis, dict) and diagnosis not in self_diagnoses:
                self_diagnoses.append(copy.deepcopy(diagnosis))
        for repair_governance in self_healing_graph.get("self_repairs") if isinstance(self_healing_graph.get("self_repairs"), list) else []:
            if isinstance(repair_governance, dict) and repair_governance not in self_repair_governance:
                self_repair_governance.append(copy.deepcopy(repair_governance))
        for recovery in self_healing_graph.get("recoveries") if isinstance(self_healing_graph.get("recoveries"), list) else []:
            if isinstance(recovery, dict) and recovery not in self_healing_recoveries:
                self_healing_recoveries.append(copy.deepcopy(recovery))
        for stabilization in self_healing_graph.get("stabilizations") if isinstance(self_healing_graph.get("stabilizations"), list) else []:
            if isinstance(stabilization, dict) and stabilization not in adaptive_stabilizations:
                adaptive_stabilizations.append(copy.deepcopy(stabilization))
        preservation_graph = lineage.get("constitutional_preservation_graph") if isinstance(lineage.get("constitutional_preservation_graph"), dict) else {}
        for preservation in preservation_graph.get("preservations") if isinstance(preservation_graph.get("preservations"), list) else []:
            if isinstance(preservation, dict) and preservation not in constitutional_preservations:
                constitutional_preservations.append(copy.deepcopy(preservation))
        for decision in preservation_graph.get("self_preservation_decisions") if isinstance(preservation_graph.get("self_preservation_decisions"), list) else []:
            if isinstance(decision, dict) and decision not in self_preservation_decisions:
                self_preservation_decisions.append(copy.deepcopy(decision))
        for failure in preservation_graph.get("catastrophic_failures") if isinstance(preservation_graph.get("catastrophic_failures"), list) else []:
            if isinstance(failure, dict) and failure not in catastrophic_failures:
                catastrophic_failures.append(copy.deepcopy(failure))
        for recovery in preservation_graph.get("catastrophic_recoveries") if isinstance(preservation_graph.get("catastrophic_recoveries"), list) else []:
            if isinstance(recovery, dict) and recovery not in catastrophic_recoveries:
                catastrophic_recoveries.append(copy.deepcopy(recovery))
        for arbitration in preservation_graph.get("rollback_arbitrations") if isinstance(preservation_graph.get("rollback_arbitrations"), list) else []:
            if isinstance(arbitration, dict) and arbitration not in constitutional_rollback_arbitrations:
                constitutional_rollback_arbitrations.append(copy.deepcopy(arbitration))
        for stabilization in preservation_graph.get("stabilizations") if isinstance(preservation_graph.get("stabilizations"), list) else []:
            if isinstance(stabilization, dict) and stabilization not in adaptive_constitutional_stabilizations:
                adaptive_constitutional_stabilizations.append(copy.deepcopy(stabilization))
        for survivability in preservation_graph.get("survivability") if isinstance(preservation_graph.get("survivability"), list) else []:
            if isinstance(survivability, dict) and survivability not in survivability_records:
                survivability_records.append(copy.deepcopy(survivability))
        evolution_graph = lineage.get("constitutional_evolution_graph") if isinstance(lineage.get("constitutional_evolution_graph"), dict) else {}
        for evolution in evolution_graph.get("evolutions") if isinstance(evolution_graph.get("evolutions"), list) else []:
            if isinstance(evolution, dict) and evolution not in constitutional_evolutions:
                constitutional_evolutions.append(copy.deepcopy(evolution))
        for constitutional_fork in evolution_graph.get("forks") if isinstance(evolution_graph.get("forks"), list) else []:
            if isinstance(constitutional_fork, dict) and constitutional_fork not in constitutional_forks:
                constitutional_forks.append(copy.deepcopy(constitutional_fork))
        for arbitration in evolution_graph.get("merge_arbitrations") if isinstance(evolution_graph.get("merge_arbitrations"), list) else []:
            if isinstance(arbitration, dict) and arbitration not in constitutional_merge_arbitrations:
                constitutional_merge_arbitrations.append(copy.deepcopy(arbitration))
        for merge in evolution_graph.get("merges") if isinstance(evolution_graph.get("merges"), list) else []:
            if isinstance(merge, dict) and merge not in constitutional_merges:
                constitutional_merges.append(copy.deepcopy(merge))
        for survivability_federation in evolution_graph.get("survivability_federations") if isinstance(evolution_graph.get("survivability_federations"), list) else []:
            if isinstance(survivability_federation, dict) and survivability_federation not in survivability_federations:
                survivability_federations.append(copy.deepcopy(survivability_federation))
        for stabilization_loop in evolution_graph.get("stabilization_loops") if isinstance(evolution_graph.get("stabilization_loops"), list) else []:
            if isinstance(stabilization_loop, dict) and stabilization_loop not in governance_stabilization_loops:
                governance_stabilization_loops.append(copy.deepcopy(stabilization_loop))

        branch_parent: Dict[str, str] = {}
        for branch in branch_forks:
            branch_id = safe_text(branch.get("branch_id"))
            parent_branch_id = safe_text(branch.get("parent_branch_id"))
            if not branch_id:
                breaks.append("missing_branch_id")
                continue
            branch_parent[branch_id] = parent_branch_id
            if parent_branch_id and parent_branch_id not in branch_ids:
                breaks.append("broken_branch_parent")
            fork_node_id = safe_text(branch.get("fork_node_id"))
            if fork_node_id and fork_node_id not in graph_node_ids:
                breaks.append("branch_fork_node_missing")

        for edge in graph_edges:
            if safe_text(edge.get("workflow_id")) and safe_text(edge.get("workflow_id")) != workflow_id:
                breaks.append("graph_edge_workflow_id_mismatch")
            if safe_text(edge.get("session_id")) and safe_text(edge.get("session_id")) != session_id:
                breaks.append("graph_edge_session_id_mismatch")
            if safe_text(edge.get("from_node_id")) not in graph_node_ids or safe_text(edge.get("to_node_id")) not in graph_node_ids:
                breaks.append("orphan_graph_edge")
            if safe_text(edge.get("branch_id")) and safe_text(edge.get("branch_id")) not in branch_ids:
                breaks.append("graph_edge_branch_missing")

        for join in join_merges:
            source_branch_ids = [
                safe_text(item)
                for item in (join.get("source_branch_ids") if isinstance(join.get("source_branch_ids"), list) else [])
                if safe_text(item)
            ]
            target_branch_id = safe_text(join.get("target_branch_id"))
            join_node_id = safe_text(join.get("join_node_id"))
            if not source_branch_ids or not target_branch_id or not join_node_id:
                breaks.append("invalid_join_lineage")
                continue
            if target_branch_id not in branch_ids or any(branch_id not in branch_ids for branch_id in source_branch_ids):
                breaks.append("invalid_join_lineage")
            if join_node_id not in graph_node_ids:
                breaks.append("invalid_join_lineage")
            if any(not self._branches_related(source, target_branch_id, branch_parent, join_merges) for source in source_branch_ids):
                breaks.append("invalid_join_lineage")

        for dependency in recovery_dependencies:
            source_node_id = safe_text(dependency.get("source_node_id"))
            target_node_id = safe_text(dependency.get("target_node_id"))
            branch_id = safe_text(dependency.get("branch_id"))
            if source_node_id not in graph_node_ids or target_node_id not in graph_node_ids:
                breaks.append("recovery_dependency_graph_node_missing")
            if branch_id and branch_id not in branch_ids:
                breaks.append("recovery_dependency_branch_missing")
            source_branch = node_branch.get(source_node_id, "")
            target_branch = node_branch.get(target_node_id, "")
            if source_branch and target_branch and not self._branches_related(source_branch, target_branch, branch_parent, join_merges):
                breaks.append("recovery_dependency_graph_discontinuity")

        mutation_ids = {
            safe_text(mutation.get("mutation_transaction_id"))
            for mutation in mutation_transactions
            if safe_text(mutation.get("mutation_transaction_id"))
        }
        mutation_node_ids = {
            safe_text(mutation.get("node_id"))
            for mutation in mutation_transactions
            if safe_text(mutation.get("node_id"))
        }
        verify_ids = {
            safe_text(verify.get("mutation_verify_id"))
            for verify in mutation_verifies
            if safe_text(verify.get("mutation_verify_id"))
        }
        rollback_ids = {
            safe_text(rollback.get("rollback_id"))
            for rollback in rollback_nodes
            if safe_text(rollback.get("rollback_id"))
        }
        rollback_node_ids = {
            safe_text(rollback.get("rollback_node_id"))
            for rollback in rollback_nodes
            if safe_text(rollback.get("rollback_node_id"))
        }
        retry_node_ids = {
            safe_text(rollback.get("retry_node_id"))
            for rollback in rollback_nodes
            if safe_text(rollback.get("retry_node_id"))
        }
        conflict_ids = {
            safe_text(conflict.get("conflict_id"))
            for conflict in branch_conflicts
            if safe_text(conflict.get("conflict_id"))
        }

        verifies_by_mutation: Dict[str, List[Dict[str, Any]]] = {}
        for verify in mutation_verifies:
            mutation_id = safe_text(verify.get("mutation_transaction_id"))
            if mutation_id:
                verifies_by_mutation.setdefault(mutation_id, []).append(verify)
            if mutation_id and mutation_id not in mutation_ids:
                breaks.append("mutation_verify_record_missing")
            verify_node_id = safe_text(verify.get("verify_node_id"))
            if verify_node_id and verify_node_id not in graph_node_ids:
                breaks.append("mutation_verify_record_missing")

        for mutation in mutation_transactions:
            mutation_id = safe_text(mutation.get("mutation_transaction_id"))
            if safe_text(mutation.get("node_id")) and safe_text(mutation.get("node_id")) not in graph_node_ids:
                breaks.append("mutation_graph_node_missing")
            if safe_text(mutation.get("branch_id")) and safe_text(mutation.get("branch_id")) not in branch_ids:
                breaks.append("mutation_branch_missing")
            if mutation_id and not verifies_by_mutation.get(mutation_id):
                breaks.append("mutation_verify_record_missing")

        for rollback in rollback_nodes:
            mutation_id = safe_text(rollback.get("mutation_transaction_id"))
            verify_id = safe_text(rollback.get("mutation_verify_id"))
            rollback_node_id = safe_text(rollback.get("rollback_node_id"))
            if not mutation_id or mutation_id not in mutation_ids:
                breaks.append("rollback_without_mutation_parent")
            if not verify_id or verify_id not in verify_ids:
                breaks.append("mutation_verify_record_missing")
            if rollback_node_id and rollback_node_id not in graph_node_ids:
                breaks.append("rollback_graph_node_missing")
            retry_node_id = safe_text(rollback.get("retry_node_id"))
            if retry_node_id and retry_node_id not in graph_node_ids:
                breaks.append("reconciliation_missing_rollback_retry_link")

        for conflict in branch_conflicts:
            source_branch_ids = [
                safe_text(item)
                for item in (conflict.get("source_branch_ids") if isinstance(conflict.get("source_branch_ids"), list) else [])
                if safe_text(item)
            ]
            target_branch_id = safe_text(conflict.get("target_branch_id"))
            if not source_branch_ids or not target_branch_id:
                breaks.append("branch_conflict_unrelated_branches")
            if target_branch_id and target_branch_id not in branch_ids:
                breaks.append("branch_conflict_unrelated_branches")
            if any(branch_id not in branch_ids for branch_id in source_branch_ids):
                breaks.append("branch_conflict_unrelated_branches")
            if any(not self._branches_related(source, target_branch_id, branch_parent, join_merges) for source in source_branch_ids):
                breaks.append("branch_conflict_unrelated_branches")
            for mutation_id in conflict.get("mutation_transaction_ids") if isinstance(conflict.get("mutation_transaction_ids"), list) else []:
                if safe_text(mutation_id) not in mutation_ids:
                    breaks.append("branch_conflict_stale_mutation")

        for reconciliation in graph_reconciliations:
            conflict_id = safe_text(reconciliation.get("conflict_id"))
            rollback_id = safe_text(reconciliation.get("rollback_id"))
            retry_node_id = safe_text(reconciliation.get("retry_node_id"))
            if not conflict_id or conflict_id not in conflict_ids:
                breaks.append("reconciliation_missing_rollback_retry_link")
            if not rollback_id or rollback_id not in rollback_ids:
                breaks.append("reconciliation_missing_rollback_retry_link")
            if not retry_node_id or retry_node_id not in graph_node_ids:
                breaks.append("reconciliation_missing_rollback_retry_link")
            if retry_node_id and retry_node_id not in retry_node_ids:
                breaks.append("reconciliation_missing_rollback_retry_link")
            has_recovery_dependency = any(
                safe_text(dependency.get("source_node_id")) in rollback_node_ids
                and safe_text(dependency.get("target_node_id")) == retry_node_id
                for dependency in recovery_dependencies
            )
            if not has_recovery_dependency:
                breaks.append("reconciliation_missing_rollback_retry_link")

        policy_ids = {
            safe_text(decision.get("policy_decision_id"))
            for decision in policy_decisions
            if safe_text(decision.get("policy_decision_id"))
        }
        review_ids = {
            safe_text(review.get("review_id"))
            for review in review_records
            if safe_text(review.get("review_id"))
        }
        approval_ids = {
            safe_text(approval.get("approval_id"))
            for approval in approval_records
            if safe_text(approval.get("approval_id"))
        }
        governance_ids = set(
            self._governance_record_ids(
                policy_decisions=policy_decisions,
                authority_records=authority_records,
                review_records=review_records,
                approval_records=approval_records,
                governance_resumes=governance_resumes,
                constitution_enforcements=constitution_enforcements,
            )
        )

        for decision in policy_decisions:
            target_node_id = safe_text(decision.get("target_node_id"))
            mutation_id = safe_text(decision.get("mutation_transaction_id"))
            if not target_node_id or target_node_id not in graph_node_ids:
                breaks.append("policy_decision_target_missing")
            if mutation_id and mutation_id not in mutation_ids:
                breaks.append("policy_decision_target_missing")
            if safe_text(decision.get("workflow_id")) and safe_text(decision.get("workflow_id")) != workflow_id:
                breaks.append("policy_decision_workflow_id_mismatch")
            if safe_text(decision.get("session_id")) and safe_text(decision.get("session_id")) != session_id:
                breaks.append("policy_decision_session_id_mismatch")

        for authority in authority_records:
            if safe_text(authority.get("workflow_id")) != workflow_id or safe_text(authority.get("session_id")) != session_id:
                breaks.append("authority_lineage_mismatch")
            target_node_id = safe_text(authority.get("target_node_id"))
            mutation_id = safe_text(authority.get("mutation_transaction_id"))
            if target_node_id and target_node_id not in graph_node_ids:
                breaks.append("authority_target_missing")
            if mutation_id and mutation_id not in mutation_ids:
                breaks.append("authority_target_missing")

        for review in review_records:
            policy_id = safe_text(review.get("policy_decision_id"))
            target_node_id = safe_text(review.get("target_node_id"))
            if policy_id and policy_id not in policy_ids:
                breaks.append("review_policy_decision_missing")
            if target_node_id and target_node_id not in graph_node_ids:
                breaks.append("review_policy_decision_missing")

        for approval in approval_records:
            review_id = safe_text(approval.get("review_id"))
            if not review_id or review_id not in review_ids:
                breaks.append("approval_without_review_parent")

        for resume_record in governance_resumes:
            approval_id = safe_text(resume_record.get("approval_id"))
            resumed_node_id = safe_text(resume_record.get("resumed_node_id"))
            if not approval_id or approval_id not in approval_ids:
                breaks.append("resume_without_approval_parent")
            if resumed_node_id and resumed_node_id not in graph_node_ids:
                breaks.append("resume_without_approval_parent")

        for enforcement in constitution_enforcements:
            target_node_id = safe_text(enforcement.get("target_node_id"))
            mutation_id = safe_text(enforcement.get("mutation_transaction_id"))
            target_ok = bool(target_node_id and target_node_id in graph_node_ids)
            mutation_ok = bool(mutation_id and mutation_id in mutation_ids)
            if not target_ok and not mutation_ok:
                breaks.append("constitution_enforcement_unrelated_target")

        worker_ids = {
            safe_text(worker.get("worker_id"))
            for worker in actor_workers
            if safe_text(worker.get("worker_id"))
        }
        federation_ids = {
            safe_text(federation.get("federation_id"))
            for federation in worker_federations
            if safe_text(federation.get("federation_id"))
        }
        distributed_execution_ids = {
            safe_text(execution.get("distributed_execution_id"))
            for execution in distributed_executions
            if safe_text(execution.get("distributed_execution_id"))
        }
        for worker in actor_workers:
            if safe_text(worker.get("workflow_id")) != workflow_id or safe_text(worker.get("session_id")) != session_id:
                breaks.append("worker_lineage_mismatch")

        for federation in worker_federations:
            federation_worker_ids = [
                safe_text(item)
                for item in (federation.get("worker_ids") if isinstance(federation.get("worker_ids"), list) else [])
                if safe_text(item)
            ]
            if any(worker_id not in worker_ids for worker_id in federation_worker_ids):
                breaks.append("worker_lineage_mismatch")
            coordinator = safe_text(federation.get("coordinator_worker_id"))
            if coordinator and coordinator not in worker_ids:
                breaks.append("worker_lineage_mismatch")

        for execution in distributed_executions:
            worker_id = safe_text(execution.get("worker_id"))
            if worker_id not in worker_ids:
                breaks.append("worker_lineage_mismatch")
            for parent_worker_id in execution.get("parent_worker_ids") if isinstance(execution.get("parent_worker_ids"), list) else []:
                if safe_text(parent_worker_id) not in worker_ids:
                    breaks.append("worker_lineage_mismatch")
            federation_id = safe_text(execution.get("federation_id"))
            if federation_id and federation_id not in federation_ids:
                breaks.append("worker_lineage_mismatch")
            target_node_id = safe_text(execution.get("target_node_id"))
            if target_node_id and target_node_id not in graph_node_ids:
                breaks.append("worker_lineage_mismatch")

        for recovery in distributed_recoveries:
            source_execution_id = safe_text(recovery.get("source_execution_id"))
            recovery_worker_id = safe_text(recovery.get("recovery_worker_id"))
            recovery_node_id = safe_text(recovery.get("recovery_node_id"))
            if source_execution_id not in distributed_execution_ids:
                breaks.append("distributed_recovery_unrelated_execution")
            if recovery_worker_id not in worker_ids:
                breaks.append("distributed_recovery_unrelated_execution")
            if recovery_node_id and recovery_node_id not in graph_node_ids:
                breaks.append("distributed_recovery_unrelated_execution")

        for authority in federated_authorities:
            if safe_text(authority.get("workflow_id")) != workflow_id or safe_text(authority.get("session_id")) != session_id:
                breaks.append("federated_authority_mismatch")
            if safe_text(authority.get("worker_id")) not in worker_ids:
                breaks.append("federated_authority_mismatch")
            if safe_text(authority.get("authority_id")) and safe_text(authority.get("authority_id")) not in governance_ids:
                breaks.append("federated_authority_mismatch")
            if safe_text(authority.get("federation_id")) and safe_text(authority.get("federation_id")) not in federation_ids:
                breaks.append("federated_authority_mismatch")

        for governance_item in distributed_governance:
            for worker_id in governance_item.get("worker_ids") if isinstance(governance_item.get("worker_ids"), list) else []:
                if safe_text(worker_id) not in worker_ids:
                    breaks.append("distributed_governance_stale_worker")
            for governance_id in governance_item.get("governance_record_ids") if isinstance(governance_item.get("governance_record_ids"), list) else []:
                if safe_text(governance_id) not in governance_ids:
                    breaks.append("distributed_governance_stale_worker")
            if safe_text(governance_item.get("federation_id")) and safe_text(governance_item.get("federation_id")) not in federation_ids:
                breaks.append("distributed_governance_stale_worker")

        worker_decision_ids = {
            safe_text(decision.get("worker_decision_id"))
            for decision in worker_decisions
            if safe_text(decision.get("worker_decision_id"))
        }
        arbitration_ids = {
            safe_text(arbitration.get("arbitration_id"))
            for arbitration in arbitration_decisions
            if safe_text(arbitration.get("arbitration_id"))
        }
        quorum_ids = {
            safe_text(quorum.get("quorum_id"))
            for quorum in authority_quorums
            if safe_text(quorum.get("quorum_id"))
        }
        vote_ids = {
            safe_text(vote.get("vote_id"))
            for vote in consensus_votes
            if safe_text(vote.get("vote_id"))
        }
        consensus_by_id = {
            safe_text(consensus_record.get("consensus_id")): consensus_record
            for consensus_record in federated_consensus
            if safe_text(consensus_record.get("consensus_id"))
        }
        consensus_ids = set(consensus_by_id.keys())

        for decision in worker_decisions:
            if safe_text(decision.get("workflow_id")) != workflow_id or safe_text(decision.get("session_id")) != session_id:
                breaks.append("worker_lineage_mismatch")
            if safe_text(decision.get("worker_id")) not in worker_ids:
                breaks.append("worker_lineage_mismatch")
            if safe_text(decision.get("federation_id")) and safe_text(decision.get("federation_id")) not in federation_ids:
                breaks.append("worker_lineage_mismatch")
            target_node_id = safe_text(decision.get("target_node_id"))
            if target_node_id and target_node_id not in graph_node_ids:
                breaks.append("worker_lineage_mismatch")

        for arbitration in arbitration_decisions:
            if safe_text(arbitration.get("workflow_id")) != workflow_id or safe_text(arbitration.get("session_id")) != session_id:
                breaks.append("arbitration_without_conflicting_decision_parents")
            conflicting_decision_ids = [
                safe_text(item)
                for item in (arbitration.get("conflicting_decision_ids") if isinstance(arbitration.get("conflicting_decision_ids"), list) else [])
                if safe_text(item)
            ]
            if len(conflicting_decision_ids) < 2 or any(decision_id not in worker_decision_ids for decision_id in conflicting_decision_ids):
                breaks.append("arbitration_without_conflicting_decision_parents")
            conflict_values = {
                safe_text(decision.get("decision"))
                for decision in worker_decisions
                if safe_text(decision.get("worker_decision_id")) in conflicting_decision_ids and safe_text(decision.get("decision"))
            }
            if len(conflict_values) < 2:
                breaks.append("arbitration_without_conflicting_decision_parents")
            for worker_id in arbitration.get("worker_ids") if isinstance(arbitration.get("worker_ids"), list) else []:
                if safe_text(worker_id) not in worker_ids:
                    breaks.append("arbitration_without_conflicting_decision_parents")
            if safe_text(arbitration.get("federation_id")) and safe_text(arbitration.get("federation_id")) not in federation_ids:
                breaks.append("arbitration_without_conflicting_decision_parents")

        for quorum in authority_quorums:
            if safe_text(quorum.get("workflow_id")) != workflow_id or safe_text(quorum.get("session_id")) != session_id:
                breaks.append("quorum_missing_authority_worker")
            authority_worker_ids = [
                safe_text(item)
                for item in (quorum.get("authority_worker_ids") if isinstance(quorum.get("authority_worker_ids"), list) else [])
                if safe_text(item)
            ]
            if not authority_worker_ids or any(worker_id not in worker_ids for worker_id in authority_worker_ids):
                breaks.append("quorum_missing_authority_worker")
            if safe_text(quorum.get("federation_id")) and safe_text(quorum.get("federation_id")) not in federation_ids:
                breaks.append("quorum_missing_authority_worker")

        for vote in consensus_votes:
            quorum_id = safe_text(vote.get("quorum_id"))
            worker_id = safe_text(vote.get("worker_id"))
            if safe_text(vote.get("workflow_id")) != workflow_id or safe_text(vote.get("session_id")) != session_id:
                breaks.append("vote_not_linked_to_quorum")
            if not quorum_id or quorum_id not in quorum_ids:
                breaks.append("vote_not_linked_to_quorum")
            if worker_id not in worker_ids:
                breaks.append("vote_not_linked_to_quorum")
            matching_quorum = next((item for item in authority_quorums if safe_text(item.get("quorum_id")) == quorum_id), {})
            quorum_worker_ids = matching_quorum.get("authority_worker_ids") if isinstance(matching_quorum.get("authority_worker_ids"), list) else []
            if quorum_worker_ids and worker_id not in {safe_text(item) for item in quorum_worker_ids}:
                breaks.append("vote_not_linked_to_quorum")

        for consensus_record in federated_consensus:
            arbitration_id = safe_text(consensus_record.get("arbitration_id"))
            quorum_id = safe_text(consensus_record.get("quorum_id"))
            if safe_text(consensus_record.get("workflow_id")) != workflow_id or safe_text(consensus_record.get("session_id")) != session_id:
                breaks.append("consensus_missing_arbitration_parent")
            if not arbitration_id or arbitration_id not in arbitration_ids:
                breaks.append("consensus_missing_arbitration_parent")
            if quorum_id and quorum_id not in quorum_ids:
                breaks.append("consensus_missing_required_vote")
            required_vote_ids = [
                safe_text(item)
                for item in (consensus_record.get("required_vote_ids") if isinstance(consensus_record.get("required_vote_ids"), list) else [])
                if safe_text(item)
            ]
            if not required_vote_ids or any(vote_id not in vote_ids for vote_id in required_vote_ids):
                breaks.append("consensus_missing_required_vote")
            for vote_id in consensus_record.get("vote_ids") if isinstance(consensus_record.get("vote_ids"), list) else []:
                if safe_text(vote_id) not in vote_ids:
                    breaks.append("consensus_missing_required_vote")
            for worker_id in consensus_record.get("worker_ids") if isinstance(consensus_record.get("worker_ids"), list) else []:
                if safe_text(worker_id) not in worker_ids:
                    breaks.append("consensus_missing_required_vote")

        for reconciliation in replay_reconciliations:
            consensus_id = safe_text(reconciliation.get("consensus_id"))
            if safe_text(reconciliation.get("workflow_id")) != workflow_id or safe_text(reconciliation.get("session_id")) != session_id:
                breaks.append("replay_reconciliation_stale_consensus_lineage")
            if not consensus_id or consensus_id not in consensus_ids:
                breaks.append("replay_reconciliation_stale_consensus_lineage")
                continue
            if safe_text(reconciliation.get("consensus_lineage_hash")) != stable_hash(consensus_by_id[consensus_id]):
                breaks.append("replay_reconciliation_stale_consensus_lineage")
            arbitration_id = safe_text(reconciliation.get("arbitration_id"))
            if arbitration_id and arbitration_id not in arbitration_ids:
                breaks.append("replay_reconciliation_stale_consensus_lineage")
            for vote_id in reconciliation.get("vote_ids") if isinstance(reconciliation.get("vote_ids"), list) else []:
                if safe_text(vote_id) not in vote_ids:
                    breaks.append("replay_reconciliation_stale_consensus_lineage")

        for governance_decision in federated_governance_decisions:
            consensus_id = safe_text(governance_decision.get("consensus_id"))
            arbitration_id = safe_text(governance_decision.get("arbitration_id"))
            if safe_text(governance_decision.get("workflow_id")) != workflow_id or safe_text(governance_decision.get("session_id")) != session_id:
                breaks.append("governance_decision_unrelated_worker_lineage")
            if consensus_id and consensus_id not in consensus_ids:
                breaks.append("governance_decision_unrelated_worker_lineage")
            if arbitration_id and arbitration_id not in arbitration_ids:
                breaks.append("governance_decision_unrelated_worker_lineage")
            for worker_id in governance_decision.get("worker_ids") if isinstance(governance_decision.get("worker_ids"), list) else []:
                if safe_text(worker_id) not in worker_ids:
                    breaks.append("governance_decision_unrelated_worker_lineage")
            if safe_text(governance_decision.get("federation_id")) and safe_text(governance_decision.get("federation_id")) not in federation_ids:
                breaks.append("governance_decision_unrelated_worker_lineage")

        observability_ids = {
            safe_text(observability.get("observability_id"))
            for observability in self_observability_records
            if safe_text(observability.get("observability_id"))
        }
        audit_ids = {
            safe_text(audit.get("audit_id"))
            for audit in constitutional_audits
            if safe_text(audit.get("audit_id"))
        }
        diagnosis_ids = {
            safe_text(diagnosis.get("diagnosis_id"))
            for diagnosis in self_diagnoses
            if safe_text(diagnosis.get("diagnosis_id"))
        }
        self_repair_ids = {
            safe_text(repair_governance.get("self_repair_id"))
            for repair_governance in self_repair_governance
            if safe_text(repair_governance.get("self_repair_id"))
        }
        self_healing_recovery_ids = {
            safe_text(recovery.get("self_healing_recovery_id"))
            for recovery in self_healing_recoveries
            if safe_text(recovery.get("self_healing_recovery_id"))
        }

        for observability in self_observability_records:
            if safe_text(observability.get("workflow_id")) != workflow_id or safe_text(observability.get("session_id")) != session_id:
                breaks.append("self_observability_lineage_mismatch")
            target_node_id = safe_text(observability.get("target_node_id"))
            if target_node_id and target_node_id not in graph_node_ids:
                breaks.append("self_observability_lineage_mismatch")

        for audit in constitutional_audits:
            if safe_text(audit.get("workflow_id")) != workflow_id or safe_text(audit.get("session_id")) != session_id:
                breaks.append("audit_without_observability_parent")
            observability_id = safe_text(audit.get("observability_id"))
            if not observability_id or observability_id not in observability_ids:
                breaks.append("audit_without_observability_parent")

        for diagnosis in self_diagnoses:
            if safe_text(diagnosis.get("workflow_id")) != workflow_id or safe_text(diagnosis.get("session_id")) != session_id:
                breaks.append("diagnosis_without_audit_observability_parent")
            audit_id = safe_text(diagnosis.get("audit_id"))
            observability_id = safe_text(diagnosis.get("observability_id"))
            if not audit_id or audit_id not in audit_ids:
                breaks.append("diagnosis_without_audit_observability_parent")
            if not observability_id or observability_id not in observability_ids:
                breaks.append("diagnosis_without_audit_observability_parent")

        for repair_governance in self_repair_governance:
            if safe_text(repair_governance.get("workflow_id")) != workflow_id or safe_text(repair_governance.get("session_id")) != session_id:
                breaks.append("self_repair_governance_missing_authority_lineage")
            diagnosis_id = safe_text(repair_governance.get("diagnosis_id"))
            audit_id = safe_text(repair_governance.get("audit_id"))
            observability_id = safe_text(repair_governance.get("observability_id"))
            authority_id = safe_text(repair_governance.get("authority_id"))
            approval_id = safe_text(repair_governance.get("approval_id"))
            consensus_id = safe_text(repair_governance.get("consensus_id"))
            if not diagnosis_id or diagnosis_id not in diagnosis_ids:
                breaks.append("self_repair_governance_missing_authority_lineage")
            if audit_id and audit_id not in audit_ids:
                breaks.append("self_repair_governance_missing_authority_lineage")
            if observability_id and observability_id not in observability_ids:
                breaks.append("self_repair_governance_missing_authority_lineage")
            if not authority_id or authority_id not in governance_ids:
                breaks.append("self_repair_governance_missing_authority_lineage")
            if not approval_id or approval_id not in approval_ids:
                breaks.append("self_repair_governance_missing_authority_lineage")
            if not consensus_id or consensus_id not in consensus_ids:
                breaks.append("self_repair_governance_missing_authority_lineage")

        for recovery in self_healing_recoveries:
            if safe_text(recovery.get("workflow_id")) != workflow_id or safe_text(recovery.get("session_id")) != session_id:
                breaks.append("self_healing_recovery_without_repair_parent")
            self_repair_id = safe_text(recovery.get("self_repair_id"))
            diagnosis_id = safe_text(recovery.get("diagnosis_id"))
            if not self_repair_id or self_repair_id not in self_repair_ids:
                breaks.append("self_healing_recovery_without_repair_parent")
            if diagnosis_id and diagnosis_id not in diagnosis_ids:
                breaks.append("self_healing_recovery_without_repair_parent")

        for stabilization in adaptive_stabilizations:
            if safe_text(stabilization.get("workflow_id")) != workflow_id or safe_text(stabilization.get("session_id")) != session_id:
                breaks.append("stabilization_without_recovery_parent")
            recovery_id = safe_text(stabilization.get("self_healing_recovery_id"))
            repair_id = safe_text(stabilization.get("self_repair_id"))
            if not recovery_id or recovery_id not in self_healing_recovery_ids:
                breaks.append("stabilization_without_recovery_parent")
            if repair_id and repair_id not in self_repair_ids:
                breaks.append("stabilization_without_recovery_parent")

        preservation_ids = {
            safe_text(preservation.get("preservation_id"))
            for preservation in constitutional_preservations
            if safe_text(preservation.get("preservation_id"))
        }
        catastrophic_failure_ids = {
            safe_text(failure.get("catastrophic_failure_id"))
            for failure in catastrophic_failures
            if safe_text(failure.get("catastrophic_failure_id"))
        }
        catastrophic_recovery_ids = {
            safe_text(recovery.get("catastrophic_recovery_id"))
            for recovery in catastrophic_recoveries
            if safe_text(recovery.get("catastrophic_recovery_id"))
        }
        constitutional_stabilization_ids = {
            safe_text(stabilization.get("constitutional_stabilization_id"))
            for stabilization in adaptive_constitutional_stabilizations
            if safe_text(stabilization.get("constitutional_stabilization_id"))
        }
        recovery_dependency_ids = {
            safe_text(dependency.get("recovery_dependency_id"))
            for dependency in recovery_dependencies
            if safe_text(dependency.get("recovery_dependency_id"))
        }
        enforcement_ids = {
            safe_text(enforcement.get("enforcement_id"))
            for enforcement in constitution_enforcements
            if safe_text(enforcement.get("enforcement_id"))
        }

        for preservation in constitutional_preservations:
            if safe_text(preservation.get("workflow_id")) != workflow_id or safe_text(preservation.get("session_id")) != session_id:
                breaks.append("preservation_without_constitution_parent")
            constitution_node_id = safe_text(preservation.get("constitution_node_id"))
            governance_record_id = safe_text(preservation.get("governance_record_id"))
            enforcement_id = safe_text(preservation.get("enforcement_id"))
            policy_id = safe_text(preservation.get("policy_decision_id"))
            node_ok = bool(constitution_node_id and constitution_node_id in graph_node_ids)
            governance_ok = bool(governance_record_id and governance_record_id in governance_ids)
            enforcement_ok = bool(enforcement_id and enforcement_id in enforcement_ids)
            policy_ok = bool(policy_id and policy_id in policy_ids)
            if not node_ok or not (governance_ok or enforcement_ok or policy_ok):
                breaks.append("preservation_without_constitution_parent")

        for decision in self_preservation_decisions:
            if safe_text(decision.get("workflow_id")) != workflow_id or safe_text(decision.get("session_id")) != session_id:
                breaks.append("self_preservation_missing_observability_authority")
            if safe_text(decision.get("preservation_id")) and safe_text(decision.get("preservation_id")) not in preservation_ids:
                breaks.append("self_preservation_missing_observability_authority")
            observability_id = safe_text(decision.get("observability_id"))
            authority_id = safe_text(decision.get("authority_id"))
            policy_id = safe_text(decision.get("policy_decision_id"))
            if not observability_id or observability_id not in observability_ids:
                breaks.append("self_preservation_missing_observability_authority")
            if not authority_id or authority_id not in governance_ids:
                breaks.append("self_preservation_missing_observability_authority")
            if policy_id and policy_id not in policy_ids:
                breaks.append("self_preservation_missing_observability_authority")

        for failure in catastrophic_failures:
            if safe_text(failure.get("workflow_id")) != workflow_id or safe_text(failure.get("session_id")) != session_id:
                breaks.append("catastrophic_failure_lineage_mismatch")
            failure_node_id = safe_text(failure.get("failure_node_id"))
            governance_record_id = safe_text(failure.get("governance_record_id"))
            if failure_node_id and failure_node_id not in graph_node_ids:
                breaks.append("catastrophic_failure_lineage_mismatch")
            if governance_record_id and governance_record_id not in governance_ids:
                breaks.append("catastrophic_failure_lineage_mismatch")

        for recovery in catastrophic_recoveries:
            if safe_text(recovery.get("workflow_id")) != workflow_id or safe_text(recovery.get("session_id")) != session_id:
                breaks.append("catastrophic_recovery_without_failure_parent")
            failure_id = safe_text(recovery.get("catastrophic_failure_id"))
            rollback_id = safe_text(recovery.get("rollback_id"))
            recovery_dependency_id = safe_text(recovery.get("recovery_dependency_id"))
            recovery_node_id = safe_text(recovery.get("recovery_node_id"))
            if not failure_id or failure_id not in catastrophic_failure_ids:
                breaks.append("catastrophic_recovery_without_failure_parent")
            if rollback_id and rollback_id not in rollback_ids:
                breaks.append("catastrophic_recovery_without_failure_parent")
            if recovery_dependency_id and recovery_dependency_id not in recovery_dependency_ids:
                breaks.append("catastrophic_recovery_without_failure_parent")
            if recovery_node_id and recovery_node_id not in graph_node_ids:
                breaks.append("catastrophic_recovery_without_failure_parent")

        for arbitration in constitutional_rollback_arbitrations:
            if safe_text(arbitration.get("workflow_id")) != workflow_id or safe_text(arbitration.get("session_id")) != session_id:
                breaks.append("constitutional_rollback_arbitration_missing_consensus_quorum")
            consensus_id = safe_text(arbitration.get("consensus_id"))
            quorum_id = safe_text(arbitration.get("quorum_id"))
            rollback_id = safe_text(arbitration.get("rollback_id"))
            failed_change_id = safe_text(arbitration.get("failed_constitutional_change_id"))
            if not consensus_id or consensus_id not in consensus_ids:
                breaks.append("constitutional_rollback_arbitration_missing_consensus_quorum")
            if not quorum_id or quorum_id not in quorum_ids:
                breaks.append("constitutional_rollback_arbitration_missing_consensus_quorum")
            if rollback_id and rollback_id not in rollback_ids:
                breaks.append("constitutional_rollback_arbitration_missing_consensus_quorum")
            if failed_change_id and failed_change_id not in preservation_ids and failed_change_id not in governance_ids:
                breaks.append("constitutional_rollback_arbitration_missing_consensus_quorum")

        for stabilization in adaptive_constitutional_stabilizations:
            if safe_text(stabilization.get("workflow_id")) != workflow_id or safe_text(stabilization.get("session_id")) != session_id:
                breaks.append("constitutional_stabilization_without_recovery_parent")
            recovery_id = safe_text(stabilization.get("catastrophic_recovery_id"))
            preservation_id = safe_text(stabilization.get("preservation_id"))
            if not recovery_id or recovery_id not in catastrophic_recovery_ids:
                breaks.append("constitutional_stabilization_without_recovery_parent")
            if preservation_id and preservation_id not in preservation_ids:
                breaks.append("constitutional_stabilization_without_recovery_parent")

        for survivability in survivability_records:
            if safe_text(survivability.get("workflow_id")) != workflow_id or safe_text(survivability.get("session_id")) != session_id:
                breaks.append("survivability_without_preservation_recovery_stabilization")
            preservation_id = safe_text(survivability.get("preservation_id"))
            recovery_id = safe_text(survivability.get("catastrophic_recovery_id"))
            stabilization_id = safe_text(survivability.get("constitutional_stabilization_id"))
            if not preservation_id or preservation_id not in preservation_ids:
                breaks.append("survivability_without_preservation_recovery_stabilization")
            if not recovery_id or recovery_id not in catastrophic_recovery_ids:
                breaks.append("survivability_without_preservation_recovery_stabilization")
            if not stabilization_id or stabilization_id not in constitutional_stabilization_ids:
                breaks.append("survivability_without_preservation_recovery_stabilization")

        evolution_ids = {
            safe_text(evolution.get("evolution_id"))
            for evolution in constitutional_evolutions
            if safe_text(evolution.get("evolution_id"))
        }
        constitutional_fork_ids = {
            safe_text(fork.get("constitutional_fork_id"))
            for fork in constitutional_forks
            if safe_text(fork.get("constitutional_fork_id"))
        }
        constitutional_fork_branch_ids = {
            safe_text(fork.get("branch_id"))
            for fork in constitutional_forks
            if safe_text(fork.get("branch_id"))
        }
        merge_arbitration_ids = {
            safe_text(arbitration.get("merge_arbitration_id"))
            for arbitration in constitutional_merge_arbitrations
            if safe_text(arbitration.get("merge_arbitration_id"))
        }
        constitutional_merge_ids = {
            safe_text(merge.get("constitutional_merge_id"))
            for merge in constitutional_merges
            if safe_text(merge.get("constitutional_merge_id"))
        }

        for evolution in constitutional_evolutions:
            if safe_text(evolution.get("workflow_id")) != workflow_id or safe_text(evolution.get("session_id")) != session_id:
                breaks.append("constitutional_evolution_missing_policy_preservation_lineage")
            policy_id = safe_text(evolution.get("policy_decision_id"))
            preservation_id = safe_text(evolution.get("preservation_id"))
            constitution_node_id = safe_text(evolution.get("constitution_node_id"))
            if not policy_id or policy_id not in policy_ids:
                breaks.append("constitutional_evolution_missing_policy_preservation_lineage")
            if not preservation_id or preservation_id not in preservation_ids:
                breaks.append("constitutional_evolution_missing_policy_preservation_lineage")
            if constitution_node_id and constitution_node_id not in graph_node_ids:
                breaks.append("constitutional_evolution_missing_policy_preservation_lineage")

        for fork in constitutional_forks:
            if safe_text(fork.get("workflow_id")) != workflow_id or safe_text(fork.get("session_id")) != session_id:
                breaks.append("constitutional_fork_without_active_parent")
            evolution_id = safe_text(fork.get("evolution_id"))
            preservation_id = safe_text(fork.get("preservation_id"))
            constitution_node_id = safe_text(fork.get("constitution_node_id"))
            branch_id = safe_text(fork.get("branch_id"))
            parent_branch_id = safe_text(fork.get("parent_branch_id"))
            fork_node_id = safe_text(fork.get("fork_node_id"))
            if evolution_id and evolution_id not in evolution_ids:
                breaks.append("constitutional_fork_without_active_parent")
            if not preservation_id or preservation_id not in preservation_ids:
                breaks.append("constitutional_fork_without_active_parent")
            if not constitution_node_id or constitution_node_id not in graph_node_ids:
                breaks.append("constitutional_fork_without_active_parent")
            if not branch_id or branch_id not in branch_ids:
                breaks.append("constitutional_fork_without_active_parent")
            if parent_branch_id and parent_branch_id not in branch_ids:
                breaks.append("constitutional_fork_without_active_parent")
            if fork_node_id and fork_node_id not in graph_node_ids:
                breaks.append("constitutional_fork_without_active_parent")

        for arbitration in constitutional_merge_arbitrations:
            if safe_text(arbitration.get("workflow_id")) != workflow_id or safe_text(arbitration.get("session_id")) != session_id:
                breaks.append("constitutional_merge_arbitration_missing_fork_branches")
            source_branch_ids = [
                safe_text(item)
                for item in (arbitration.get("source_branch_ids") if isinstance(arbitration.get("source_branch_ids"), list) else [])
                if safe_text(item)
            ]
            target_branch_id = safe_text(arbitration.get("target_branch_id"))
            quorum_id = safe_text(arbitration.get("quorum_id"))
            consensus_id = safe_text(arbitration.get("consensus_id"))
            if len(source_branch_ids) < 2 or any(branch_id not in constitutional_fork_branch_ids for branch_id in source_branch_ids):
                breaks.append("constitutional_merge_arbitration_missing_fork_branches")
            if target_branch_id and target_branch_id not in branch_ids:
                breaks.append("constitutional_merge_arbitration_missing_fork_branches")
            if not quorum_id or quorum_id not in quorum_ids:
                breaks.append("constitutional_merge_arbitration_missing_fork_branches")
            if not consensus_id or consensus_id not in consensus_ids:
                breaks.append("constitutional_merge_arbitration_missing_fork_branches")

        for merge in constitutional_merges:
            if safe_text(merge.get("workflow_id")) != workflow_id or safe_text(merge.get("session_id")) != session_id:
                breaks.append("constitutional_merge_without_arbitration_parent")
            merge_arbitration_id = safe_text(merge.get("merge_arbitration_id"))
            source_branch_ids = [
                safe_text(item)
                for item in (merge.get("source_branch_ids") if isinstance(merge.get("source_branch_ids"), list) else [])
                if safe_text(item)
            ]
            target_branch_id = safe_text(merge.get("target_branch_id"))
            preservation_id = safe_text(merge.get("merged_preservation_id"))
            if not merge_arbitration_id or merge_arbitration_id not in merge_arbitration_ids:
                breaks.append("constitutional_merge_without_arbitration_parent")
            if len(source_branch_ids) < 2 or any(branch_id not in constitutional_fork_branch_ids for branch_id in source_branch_ids):
                breaks.append("constitutional_merge_without_arbitration_parent")
            if target_branch_id and target_branch_id not in branch_ids:
                breaks.append("constitutional_merge_without_arbitration_parent")
            if preservation_id and preservation_id not in preservation_ids:
                breaks.append("constitutional_merge_without_arbitration_parent")

        for federation_record in survivability_federations:
            if safe_text(federation_record.get("workflow_id")) != workflow_id or safe_text(federation_record.get("session_id")) != session_id:
                breaks.append("survivability_federation_stale_worker_lineage")
            merge_id = safe_text(federation_record.get("constitutional_merge_id"))
            federation_id = safe_text(federation_record.get("federation_id"))
            if not merge_id or merge_id not in constitutional_merge_ids:
                breaks.append("survivability_federation_stale_worker_lineage")
            if not federation_id or federation_id not in federation_ids:
                breaks.append("survivability_federation_stale_worker_lineage")
            for worker_id in federation_record.get("worker_ids") if isinstance(federation_record.get("worker_ids"), list) else []:
                if safe_text(worker_id) not in worker_ids:
                    breaks.append("survivability_federation_stale_worker_lineage")

        for loop in governance_stabilization_loops:
            if safe_text(loop.get("workflow_id")) != workflow_id or safe_text(loop.get("session_id")) != session_id:
                breaks.append("stabilization_loop_without_merge_recovery_lineage")
            merge_id = safe_text(loop.get("constitutional_merge_id"))
            recovery_id = safe_text(loop.get("catastrophic_recovery_id"))
            stabilization_id = safe_text(loop.get("constitutional_stabilization_id"))
            if not merge_id or merge_id not in constitutional_merge_ids:
                breaks.append("stabilization_loop_without_merge_recovery_lineage")
            if not recovery_id or recovery_id not in catastrophic_recovery_ids:
                breaks.append("stabilization_loop_without_merge_recovery_lineage")
            if not stabilization_id or stabilization_id not in constitutional_stabilization_ids:
                breaks.append("stabilization_loop_without_merge_recovery_lineage")

        source_session_id = safe_text(lineage.get("source_session_id"))
        replay = lineage.get("replay_continuation") if isinstance(lineage.get("replay_continuation"), dict) else {}
        if source_session_id and safe_text(replay.get("source_session_id")) != source_session_id:
            breaks.append("broken_source_session_id")
        if replay and safe_text(replay.get("recovery_resume_id")) and safe_text(replay.get("recovery_resume_id")) not in recovery_resume_ids:
            breaks.append("replay_recovery_resume_id_mismatch")
        if replay and safe_text(replay.get("cursor_id")) and safe_text(replay.get("cursor_id")) not in cursor_ids:
            breaks.append("replay_cursor_id_mismatch")
        replay_mutation_ids = [
            safe_text(item)
            for item in (replay.get("mutation_transaction_ids") if isinstance(replay.get("mutation_transaction_ids"), list) else [])
            if safe_text(item)
        ]
        if any(mutation_id not in mutation_ids for mutation_id in replay_mutation_ids):
            breaks.append("replay_stale_mutation_lineage")
        replay_rollback_ids = [
            safe_text(item)
            for item in (replay.get("rollback_ids") if isinstance(replay.get("rollback_ids"), list) else [])
            if safe_text(item)
        ]
        if any(rollback_id not in rollback_ids for rollback_id in replay_rollback_ids):
            breaks.append("replay_stale_mutation_lineage")
        replay_governance_ids = [
            safe_text(item)
            for item in (replay.get("governance_record_ids") if isinstance(replay.get("governance_record_ids"), list) else [])
            if safe_text(item)
        ]
        if any(governance_id not in governance_ids for governance_id in replay_governance_ids):
            breaks.append("replay_stale_governance_lineage")
        replay_worker_ids = [
            safe_text(item)
            for item in (replay.get("worker_ids") if isinstance(replay.get("worker_ids"), list) else [])
            if safe_text(item)
        ]
        if any(worker_id not in worker_ids for worker_id in replay_worker_ids):
            breaks.append("replay_worker_lineage_mismatch")
        replay_execution_ids = [
            safe_text(item)
            for item in (replay.get("distributed_execution_ids") if isinstance(replay.get("distributed_execution_ids"), list) else [])
            if safe_text(item)
        ]
        if any(execution_id not in distributed_execution_ids for execution_id in replay_execution_ids):
            breaks.append("replay_worker_lineage_mismatch")
        replay_consensus_ids = [
            safe_text(item)
            for item in (replay.get("consensus_ids") if isinstance(replay.get("consensus_ids"), list) else [])
            if safe_text(item)
        ]
        if any(consensus_id not in consensus_ids for consensus_id in replay_consensus_ids):
            breaks.append("replay_stale_consensus_lineage")
        replay_self_healing_recovery_ids = [
            safe_text(item)
            for item in (replay.get("self_healing_recovery_ids") if isinstance(replay.get("self_healing_recovery_ids"), list) else [])
            if safe_text(item)
        ]
        if any(recovery_id not in self_healing_recovery_ids for recovery_id in replay_self_healing_recovery_ids):
            breaks.append("replay_stale_self_healing_lineage")
        replay_preservation_ids = [
            safe_text(item)
            for item in (replay.get("preservation_ids") if isinstance(replay.get("preservation_ids"), list) else [])
            if safe_text(item)
        ]
        if any(preservation_id not in preservation_ids for preservation_id in replay_preservation_ids):
            breaks.append("replay_stale_constitutional_preservation_lineage")
        replay_evolution_ids = [
            safe_text(item)
            for item in (replay.get("evolution_ids") if isinstance(replay.get("evolution_ids"), list) else [])
            if safe_text(item)
        ]
        if any(evolution_id not in evolution_ids for evolution_id in replay_evolution_ids):
            breaks.append("replay_stale_constitutional_evolution_lineage")
        source_branch_id = safe_text(replay.get("source_branch_id"))
        continued_branch_id = safe_text(replay.get("continued_branch_id"))
        if replay and source_branch_id and continued_branch_id:
            if source_branch_id not in branch_ids or continued_branch_id not in branch_ids:
                breaks.append("replay_branch_lineage_mismatch")
            elif not self._branches_related(source_branch_id, continued_branch_id, branch_parent, join_merges):
                breaks.append("replay_branch_lineage_mismatch")
        parent_session_id = safe_text(lineage.get("parent_session_id"))
        if parent_session_id and parent_session_id == session_id:
            breaks.append("self_parent_session_id")

        breaks = sorted(set(breaks))
        return {
            "schema": "zero.workflow_runtime_session.continuity_summary.v1",
            "ok": not breaks,
            "session_id": session_id,
            "workflow_id": workflow_id,
            "event_count": len(events),
            "breaks": breaks,
            "lineage_intact": not breaks,
            "source_session_id": source_session_id,
            "parent_session_id": parent_session_id,
            "graph_continuity": {
                "ok": not any(
                    item in breaks
                    for item in (
                        "orphan_graph_edge",
                        "broken_branch_parent",
                        "invalid_join_lineage",
                        "replay_branch_lineage_mismatch",
                        "recovery_dependency_graph_node_missing",
                        "recovery_dependency_graph_discontinuity",
                        "rollback_without_mutation_parent",
                        "mutation_verify_record_missing",
                        "branch_conflict_unrelated_branches",
                        "reconciliation_missing_rollback_retry_link",
                        "replay_stale_mutation_lineage",
                        "policy_decision_target_missing",
                        "authority_lineage_mismatch",
                        "approval_without_review_parent",
                        "resume_without_approval_parent",
                        "constitution_enforcement_unrelated_target",
                        "replay_stale_governance_lineage",
                        "worker_lineage_mismatch",
                        "replay_worker_lineage_mismatch",
                        "federated_authority_mismatch",
                        "distributed_recovery_unrelated_execution",
                        "distributed_governance_stale_worker",
                        "arbitration_without_conflicting_decision_parents",
                        "quorum_missing_authority_worker",
                        "vote_not_linked_to_quorum",
                        "consensus_missing_arbitration_parent",
                        "consensus_missing_required_vote",
                        "replay_reconciliation_stale_consensus_lineage",
                        "governance_decision_unrelated_worker_lineage",
                        "replay_stale_consensus_lineage",
                        "self_observability_lineage_mismatch",
                        "audit_without_observability_parent",
                        "diagnosis_without_audit_observability_parent",
                        "self_repair_governance_missing_authority_lineage",
                        "self_healing_recovery_without_repair_parent",
                        "stabilization_without_recovery_parent",
                        "replay_stale_self_healing_lineage",
                        "preservation_without_constitution_parent",
                        "self_preservation_missing_observability_authority",
                        "catastrophic_failure_lineage_mismatch",
                        "catastrophic_recovery_without_failure_parent",
                        "constitutional_rollback_arbitration_missing_consensus_quorum",
                        "constitutional_stabilization_without_recovery_parent",
                        "survivability_without_preservation_recovery_stabilization",
                        "replay_stale_constitutional_preservation_lineage",
                        "constitutional_evolution_missing_policy_preservation_lineage",
                        "constitutional_fork_without_active_parent",
                        "constitutional_merge_arbitration_missing_fork_branches",
                        "constitutional_merge_without_arbitration_parent",
                        "survivability_federation_stale_worker_lineage",
                        "stabilization_loop_without_merge_recovery_lineage",
                        "replay_stale_constitutional_evolution_lineage",
                    )
                ),
                "node_count": len(graph_node_ids),
                "edge_count": len(graph_edges),
                "branch_count": len(branch_ids),
                "join_count": len(join_merges),
                "recovery_dependency_count": len(recovery_dependencies),
                "mutation_transaction_count": len(mutation_ids),
                "mutation_verify_count": len(verify_ids),
                "rollback_count": len(rollback_ids),
                "conflict_count": len(conflict_ids),
                "reconciliation_count": len(graph_reconciliations),
                "governance_record_count": len(governance_ids),
                "policy_decision_count": len(policy_ids),
                "review_count": len(review_ids),
                "approval_count": len(approval_ids),
                "constitution_enforcement_count": len(constitution_enforcements),
                "worker_count": len(worker_ids),
                "federation_count": len(federation_ids),
                "distributed_execution_count": len(distributed_execution_ids),
                "distributed_recovery_count": len(distributed_recoveries),
                "worker_decision_count": len(worker_decision_ids),
                "arbitration_count": len(arbitration_ids),
                "authority_quorum_count": len(quorum_ids),
                "consensus_vote_count": len(vote_ids),
                "federated_consensus_count": len(consensus_ids),
                "replay_reconciliation_count": len(replay_reconciliations),
                "federated_governance_decision_count": len(federated_governance_decisions),
                "self_observability_count": len(observability_ids),
                "constitutional_audit_count": len(audit_ids),
                "self_diagnosis_count": len(diagnosis_ids),
                "self_repair_governance_count": len(self_repair_ids),
                "self_healing_recovery_count": len(self_healing_recovery_ids),
                "adaptive_stabilization_count": len(adaptive_stabilizations),
                "constitutional_preservation_count": len(preservation_ids),
                "self_preservation_decision_count": len(self_preservation_decisions),
                "catastrophic_failure_count": len(catastrophic_failure_ids),
                "catastrophic_recovery_count": len(catastrophic_recovery_ids),
                "constitutional_rollback_arbitration_count": len(constitutional_rollback_arbitrations),
                "adaptive_constitutional_stabilization_count": len(adaptive_constitutional_stabilizations),
                "survivability_count": len(survivability_records),
                "constitutional_evolution_count": len(evolution_ids),
                "constitutional_fork_count": len(constitutional_fork_ids),
                "constitutional_merge_arbitration_count": len(merge_arbitration_ids),
                "constitutional_merge_count": len(constitutional_merge_ids),
                "survivability_federation_count": len(survivability_federations),
                "governance_stabilization_loop_count": len(governance_stabilization_loops),
            },
        }

    def _phase_summary(self, *, state: Dict[str, Any], events: List[WorkflowRuntimeEvent]) -> Dict[str, Dict[str, Any]]:
        phases: Dict[str, Dict[str, Any]] = {
            phase: {
                "seen": False,
                "status": "pending",
                "ok_count": 0,
                "failed_count": 0,
                "last_event_id": "",
                "last_message": "",
            }
            for phase in WORKFLOW_SESSION_PHASES
        }
        steps = state.get("steps") if isinstance(state, dict) else []
        if isinstance(steps, list) and steps:
            phases["planner"].update({"seen": True, "status": "completed", "ok_count": 1, "last_message": "runtime steps available"})
        for event in events:
            phase = event.phase if event.phase in phases else "execution"
            item = phases[phase]
            item["seen"] = True
            item["last_event_id"] = event.event_id
            item["last_message"] = event.message
            if event.ok:
                item["ok_count"] += 1
            else:
                item["failed_count"] += 1
            item["status"] = "failed" if item["failed_count"] else "completed"
        if events:
            phases["replayable_session"].update({
                "seen": True,
                "status": "completed",
                "ok_count": len(events),
                "last_event_id": events[-1].event_id,
                "last_message": "execution log can be replayed as workflow session",
            })
        return phases

    def _session_status(self, *, state: Dict[str, Any], result: Dict[str, Any] | None, phases: Dict[str, Dict[str, Any]]) -> str:
        for source in (result, state):
            if isinstance(source, dict):
                status = safe_text(source.get("status") or source.get("runtime_status")).lower()
                if status:
                    if status in {"done", "success", "completed"}:
                        return "finished"
                    if status in {"error", "timeout", "cancelled", "canceled"}:
                        return "failed"
                    return status
        if any(item.get("failed_count", 0) for item in phases.values()):
            return "failed"
        if phases.get("execution", {}).get("seen"):
            return "running"
        return "created"

    def _is_replayable(self, *, state: Dict[str, Any], events: List[WorkflowRuntimeEvent]) -> bool:
        if events:
            return True
        for key in ("execution_log", "execution_trace", "step_results", "results"):
            value = state.get(key) if isinstance(state, dict) else None
            if isinstance(value, list) and value:
                return True
        return False

    def _summary(self, *, status: str, phases: Dict[str, Dict[str, Any]], replayable: bool) -> str:
        seen = [phase for phase in WORKFLOW_SESSION_PHASES if phases.get(phase, {}).get("seen")]
        if not seen:
            seen = ["planner"] if phases.get("planner", {}).get("seen") else []
        chain = " -> ".join(seen) if seen else "planner"
        replay_text = "replayable" if replayable else "not_replayable_yet"
        return f"{chain} | status={status} | {replay_text}"


_default_manager = WorkflowRuntimeSessionManager()


def build_workflow_runtime_session(*, task: Dict[str, Any], state: Dict[str, Any], result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _default_manager.build_session(task=task, state=state, result=result).to_dict()


def attach_workflow_runtime_session(*, task: Dict[str, Any], state: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    return _default_manager.finalize_public_result(task=task, state=state, result=result)


# ---------------------------------------------------------------------------
# AER Runtime Constitutional Self-Amendment / Mutation Safety v1
# ---------------------------------------------------------------------------
# This layer is intentionally added as focused WorkflowRuntimeSessionManager
# helpers.  It records and validates constitutional mutation continuity only;
# it does not execute mutations, approve policy by itself, or move authority
# away from TaskRunner / StepExecutor.


def _zero_v1_record_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(record if isinstance(record, dict) else {})


def _zero_v1_schema_short_id(prefix: str, payload: Dict[str, Any]) -> str:
    return prefix + stable_hash(payload)[:16]


def _zero_v1_collect_records_by_event_type(session: Dict[str, Any], event_type: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for event in session.get("events") if isinstance(session.get("events"), list) else []:
        if not isinstance(event, dict):
            continue
        if safe_text(event.get("event_type")) != event_type:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
        if record:
            records.append(copy.deepcopy(record))
    return records


def _zero_v1_known_governance_ids(session: Dict[str, Any]) -> Dict[str, set[str]]:
    lineage = session.get("lineage") if isinstance(session.get("lineage"), dict) else {}
    governance = lineage.get("governance_state_graph") if isinstance(lineage.get("governance_state_graph"), dict) else {}
    consensus = lineage.get("federated_consensus_graph") if isinstance(lineage.get("federated_consensus_graph"), dict) else {}
    preservation = lineage.get("constitutional_preservation_graph") if isinstance(lineage.get("constitutional_preservation_graph"), dict) else {}
    evolution = lineage.get("constitutional_evolution_graph") if isinstance(lineage.get("constitutional_evolution_graph"), dict) else {}
    return {
        "policy_ids": {safe_text(item.get("policy_decision_id")) for item in governance.get("policy_decisions", []) if isinstance(item, dict) and safe_text(item.get("policy_decision_id"))},
        "authority_ids": {safe_text(item.get("authority_id")) for item in governance.get("authority", []) if isinstance(item, dict) and safe_text(item.get("authority_id"))},
        "approval_ids": {safe_text(item.get("approval_id")) for item in governance.get("approvals", []) if isinstance(item, dict) and safe_text(item.get("approval_id"))},
        "review_ids": {safe_text(item.get("review_id")) for item in governance.get("reviews", []) if isinstance(item, dict) and safe_text(item.get("review_id"))},
        "quorum_ids": {safe_text(item.get("quorum_id")) for item in consensus.get("quorums", []) if isinstance(item, dict) and safe_text(item.get("quorum_id"))},
        "consensus_ids": {safe_text(item.get("consensus_id")) for item in consensus.get("consensus", []) if isinstance(item, dict) and safe_text(item.get("consensus_id"))},
        "arbitration_ids": {safe_text(item.get("arbitration_id")) for item in consensus.get("arbitrations", []) if isinstance(item, dict) and safe_text(item.get("arbitration_id"))},
        "preservation_ids": {safe_text(item.get("preservation_id")) for item in preservation.get("preservations", []) if isinstance(item, dict) and safe_text(item.get("preservation_id"))},
        "evolution_ids": {safe_text(item.get("constitutional_evolution_id")) for item in evolution.get("evolutions", []) if isinstance(item, dict) and safe_text(item.get("constitutional_evolution_id"))},
        "fork_ids": {safe_text(item.get("constitutional_fork_id")) for item in evolution.get("forks", []) if isinstance(item, dict) and safe_text(item.get("constitutional_fork_id"))},
        "merge_ids": {safe_text(item.get("constitutional_merge_id")) for item in evolution.get("merges", []) if isinstance(item, dict) and safe_text(item.get("constitutional_merge_id"))},
    }


def _zero_build_constitutional_mutation_proposal_record(self, *, task: Dict[str, Any], state: Dict[str, Any], proposal: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(proposal)
    seed = {
        "workflow_id": session.get("workflow_id"),
        "session_id": session.get("session_id"),
        "target_constitution_id": safe_text(payload.get("target_constitution_id")),
        "preservation_id": safe_text(payload.get("preservation_id")),
        "current_tick": current_tick,
    }
    return {
        "schema": "zero.workflow_runtime_session.constitutional_mutation_proposal.v1",
        "proposal_id": safe_text(payload.get("proposal_id")) or _zero_v1_schema_short_id("wfcmp_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "target_constitution_id": safe_text(payload.get("target_constitution_id")),
        "preservation_id": safe_text(payload.get("preservation_id")),
        "evolution_id": safe_text(payload.get("evolution_id") or payload.get("constitutional_evolution_id")),
        "mutation_scope": safe_text(payload.get("mutation_scope")) or "runtime_constitution",
        "proposal": safe_text(payload.get("proposal")) or "constitutional_mutation",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_mutation_proposal_record(self, *, task: Dict[str, Any], state: Dict[str, Any], proposal: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_mutation_proposal_record(task=task, state=state, proposal=proposal, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_mutation_proposal", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_mutation_approval_record(self, *, task: Dict[str, Any], state: Dict[str, Any], approval: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(approval)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "proposal_id": safe_text(payload.get("proposal_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_mutation_approval.v1",
        "mutation_approval_id": safe_text(payload.get("mutation_approval_id")) or _zero_v1_schema_short_id("wfcmapp_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "proposal_id": safe_text(payload.get("proposal_id")),
        "authority_id": safe_text(payload.get("authority_id")),
        "approval_id": safe_text(payload.get("approval_id")),
        "consensus_id": safe_text(payload.get("consensus_id")),
        "quorum_id": safe_text(payload.get("quorum_id")),
        "decision": safe_text(payload.get("decision")) or "approved",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_mutation_approval_record(self, *, task: Dict[str, Any], state: Dict[str, Any], approval: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_mutation_approval_record(task=task, state=state, approval=approval, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_mutation_approval", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_self_amendment_record(self, *, task: Dict[str, Any], state: Dict[str, Any], amendment: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(amendment)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "proposal_id": safe_text(payload.get("proposal_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_self_amendment.v1",
        "amendment_id": safe_text(payload.get("amendment_id")) or _zero_v1_schema_short_id("wfcsa_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "proposal_id": safe_text(payload.get("proposal_id")),
        "mutation_approval_id": safe_text(payload.get("mutation_approval_id")),
        "authority_id": safe_text(payload.get("authority_id")),
        "approval_id": safe_text(payload.get("approval_id")),
        "consensus_id": safe_text(payload.get("consensus_id")),
        "target_constitution_id": safe_text(payload.get("target_constitution_id")),
        "amendment_status": safe_text(payload.get("amendment_status")) or "applied",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_self_amendment_record(self, *, task: Dict[str, Any], state: Dict[str, Any], amendment: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_self_amendment_record(task=task, state=state, amendment=amendment, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_self_amendment", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_policy_replacement_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replacement: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(replacement)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "amendment_id": safe_text(payload.get("amendment_id")), "policy_id": safe_text(payload.get("new_policy_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_policy_replacement.v1",
        "policy_replacement_id": safe_text(payload.get("policy_replacement_id")) or _zero_v1_schema_short_id("wfcprp_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "amendment_id": safe_text(payload.get("amendment_id")),
        "proposal_id": safe_text(payload.get("proposal_id")),
        "old_policy_id": safe_text(payload.get("old_policy_id")),
        "new_policy_id": safe_text(payload.get("new_policy_id")),
        "approval_id": safe_text(payload.get("approval_id")),
        "consensus_id": safe_text(payload.get("consensus_id")),
        "replacement_status": safe_text(payload.get("replacement_status")) or "active",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_policy_replacement_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replacement: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_policy_replacement_record(task=task, state=state, replacement=replacement, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_policy_replacement", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_amendment_rollback_record(self, *, task: Dict[str, Any], state: Dict[str, Any], rollback: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(rollback)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "failed_amendment_id": safe_text(payload.get("failed_amendment_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_amendment_rollback.v1",
        "amendment_rollback_id": safe_text(payload.get("amendment_rollback_id")) or _zero_v1_schema_short_id("wfcar_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "failed_amendment_id": safe_text(payload.get("failed_amendment_id")),
        "policy_replacement_id": safe_text(payload.get("policy_replacement_id")),
        "rollback_arbitration_id": safe_text(payload.get("rollback_arbitration_id") or payload.get("arbitration_id")),
        "recovery_id": safe_text(payload.get("recovery_id")),
        "rollback_status": safe_text(payload.get("rollback_status")) or "rolled_back",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_amendment_rollback_record(self, *, task: Dict[str, Any], state: Dict[str, Any], rollback: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_amendment_rollback_record(task=task, state=state, rollback=rollback, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_amendment_rollback", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_governance_conflict_arbitration_record(self, *, task: Dict[str, Any], state: Dict[str, Any], arbitration: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(arbitration)
    branch_ids = [safe_text(item) for item in payload.get("branch_ids", []) if safe_text(item)] if isinstance(payload.get("branch_ids"), list) else []
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "branch_ids": branch_ids, "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_governance_conflict_arbitration.v1",
        "governance_conflict_arbitration_id": safe_text(payload.get("governance_conflict_arbitration_id")) or _zero_v1_schema_short_id("wfgca_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "branch_ids": branch_ids,
        "conflict_ids": [safe_text(item) for item in payload.get("conflict_ids", []) if safe_text(item)] if isinstance(payload.get("conflict_ids"), list) else [],
        "arbitration_id": safe_text(payload.get("arbitration_id")),
        "quorum_id": safe_text(payload.get("quorum_id")),
        "consensus_id": safe_text(payload.get("consensus_id")),
        "decision": safe_text(payload.get("decision")) or "resolved",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_governance_conflict_arbitration_record(self, *, task: Dict[str, Any], state: Dict[str, Any], arbitration: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_governance_conflict_arbitration_record(task=task, state=state, arbitration=arbitration, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_governance_conflict_arbitration", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_self_amendment_replay_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replay: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(replay)
    amendment_ids = [safe_text(item) for item in payload.get("amendment_ids", []) if safe_text(item)] if isinstance(payload.get("amendment_ids"), list) else []
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "amendment_ids": amendment_ids, "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_self_amendment_replay.v1",
        "self_amendment_replay_id": safe_text(payload.get("self_amendment_replay_id")) or _zero_v1_schema_short_id("wfcsar_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "amendment_ids": amendment_ids,
        "proposal_ids": [safe_text(item) for item in payload.get("proposal_ids", []) if safe_text(item)] if isinstance(payload.get("proposal_ids"), list) else [],
        "policy_replacement_ids": [safe_text(item) for item in payload.get("policy_replacement_ids", []) if safe_text(item)] if isinstance(payload.get("policy_replacement_ids"), list) else [],
        "replay_status": safe_text(payload.get("replay_status")) or "validated",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_self_amendment_replay_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replay: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_self_amendment_replay_record(task=task, state=state, replay=replay, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_self_amendment_replay", record=record, current_tick=current_tick, ok=True)


WorkflowRuntimeSessionManager.build_constitutional_mutation_proposal_record = _zero_build_constitutional_mutation_proposal_record
WorkflowRuntimeSessionManager.attach_constitutional_mutation_proposal_record = _zero_attach_constitutional_mutation_proposal_record
WorkflowRuntimeSessionManager.build_constitutional_mutation_approval_record = _zero_build_constitutional_mutation_approval_record
WorkflowRuntimeSessionManager.attach_constitutional_mutation_approval_record = _zero_attach_constitutional_mutation_approval_record
WorkflowRuntimeSessionManager.build_constitutional_self_amendment_record = _zero_build_constitutional_self_amendment_record
WorkflowRuntimeSessionManager.attach_constitutional_self_amendment_record = _zero_attach_constitutional_self_amendment_record
WorkflowRuntimeSessionManager.build_constitutional_policy_replacement_record = _zero_build_constitutional_policy_replacement_record
WorkflowRuntimeSessionManager.attach_constitutional_policy_replacement_record = _zero_attach_constitutional_policy_replacement_record
WorkflowRuntimeSessionManager.build_constitutional_amendment_rollback_record = _zero_build_constitutional_amendment_rollback_record
WorkflowRuntimeSessionManager.attach_constitutional_amendment_rollback_record = _zero_attach_constitutional_amendment_rollback_record
WorkflowRuntimeSessionManager.build_constitutional_governance_conflict_arbitration_record = _zero_build_constitutional_governance_conflict_arbitration_record
WorkflowRuntimeSessionManager.attach_constitutional_governance_conflict_arbitration_record = _zero_attach_constitutional_governance_conflict_arbitration_record
WorkflowRuntimeSessionManager.build_constitutional_self_amendment_replay_record = _zero_build_constitutional_self_amendment_replay_record
WorkflowRuntimeSessionManager.attach_constitutional_self_amendment_replay_record = _zero_attach_constitutional_self_amendment_replay_record


_ZERO_ORIGINAL_CONTINUITY_SUMMARY = WorkflowRuntimeSessionManager.continuity_summary


def _zero_continuity_summary_with_self_amendment(self, session: Dict[str, Any]) -> Dict[str, Any]:
    summary = _ZERO_ORIGINAL_CONTINUITY_SUMMARY(self, session)
    if not isinstance(summary, dict):
        summary = {"ok": False, "breaks": ["invalid_continuity_summary"]}
    breaks = list(summary.get("breaks") if isinstance(summary.get("breaks"), list) else [])
    workflow_id = safe_text(session.get("workflow_id")) if isinstance(session, dict) else ""
    session_id = safe_text(session.get("session_id")) if isinstance(session, dict) else ""
    known = _zero_v1_known_governance_ids(session if isinstance(session, dict) else {})

    proposals = _zero_v1_collect_records_by_event_type(session, "constitutional_mutation_proposal")
    approvals = _zero_v1_collect_records_by_event_type(session, "constitutional_mutation_approval")
    amendments = _zero_v1_collect_records_by_event_type(session, "constitutional_self_amendment")
    replacements = _zero_v1_collect_records_by_event_type(session, "constitutional_policy_replacement")
    rollbacks = _zero_v1_collect_records_by_event_type(session, "constitutional_amendment_rollback")
    conflict_arbitrations = _zero_v1_collect_records_by_event_type(session, "constitutional_governance_conflict_arbitration")
    replays = _zero_v1_collect_records_by_event_type(session, "constitutional_self_amendment_replay")

    proposal_ids = {safe_text(item.get("proposal_id")) for item in proposals if safe_text(item.get("proposal_id"))}
    approval_record_ids = {safe_text(item.get("mutation_approval_id")) for item in approvals if safe_text(item.get("mutation_approval_id"))}
    amendment_ids = {safe_text(item.get("amendment_id")) for item in amendments if safe_text(item.get("amendment_id"))}
    replacement_ids = {safe_text(item.get("policy_replacement_id")) for item in replacements if safe_text(item.get("policy_replacement_id"))}
    conflict_arbitration_ids = {safe_text(item.get("governance_conflict_arbitration_id")) for item in conflict_arbitrations if safe_text(item.get("governance_conflict_arbitration_id"))}

    for collection, name in ((proposals, "proposal"), (approvals, "approval"), (amendments, "amendment"), (replacements, "replacement"), (rollbacks, "rollback"), (conflict_arbitrations, "conflict_arbitration"), (replays, "replay")):
        for record in collection:
            if safe_text(record.get("workflow_id")) != workflow_id or safe_text(record.get("session_id")) != session_id:
                breaks.append(f"constitutional_self_amendment_{name}_lineage_mismatch")

    for proposal in proposals:
        preservation_id = safe_text(proposal.get("preservation_id"))
        evolution_id = safe_text(proposal.get("evolution_id"))
        if preservation_id and preservation_id not in known["preservation_ids"]:
            breaks.append("constitutional_mutation_proposal_missing_active_constitution")
        if evolution_id and evolution_id not in known["evolution_ids"]:
            breaks.append("constitutional_mutation_proposal_missing_active_constitution")
        if not preservation_id and not evolution_id and not safe_text(proposal.get("target_constitution_id")):
            breaks.append("constitutional_mutation_proposal_missing_active_constitution")

    for approval in approvals:
        if safe_text(approval.get("proposal_id")) not in proposal_ids:
            breaks.append("constitutional_mutation_approval_without_proposal")
        authority_id = safe_text(approval.get("authority_id"))
        approval_id = safe_text(approval.get("approval_id"))
        consensus_id = safe_text(approval.get("consensus_id"))
        quorum_id = safe_text(approval.get("quorum_id"))
        if authority_id and authority_id not in known["authority_ids"]:
            breaks.append("constitutional_mutation_approval_missing_authority")
        if approval_id and approval_id not in known["approval_ids"]:
            breaks.append("constitutional_mutation_approval_missing_authority")
        if consensus_id and consensus_id not in known["consensus_ids"]:
            breaks.append("constitutional_mutation_approval_missing_authority")
        if quorum_id and quorum_id not in known["quorum_ids"]:
            breaks.append("constitutional_mutation_approval_missing_authority")
        if not any([authority_id, approval_id, consensus_id]):
            breaks.append("constitutional_mutation_approval_missing_authority")

    for amendment in amendments:
        if safe_text(amendment.get("proposal_id")) not in proposal_ids:
            breaks.append("constitutional_self_amendment_without_proposal")
        mutation_approval_id = safe_text(amendment.get("mutation_approval_id"))
        if mutation_approval_id and mutation_approval_id not in approval_record_ids:
            breaks.append("constitutional_self_amendment_without_approval")
        if not mutation_approval_id and not any([safe_text(amendment.get("approval_id")), safe_text(amendment.get("authority_id")), safe_text(amendment.get("consensus_id"))]):
            breaks.append("constitutional_self_amendment_without_approval")

    for replacement in replacements:
        if safe_text(replacement.get("amendment_id")) not in amendment_ids:
            breaks.append("constitutional_policy_replacement_without_amendment")
        if not safe_text(replacement.get("new_policy_id")):
            breaks.append("constitutional_policy_replacement_without_amendment")
        approval_id = safe_text(replacement.get("approval_id"))
        consensus_id = safe_text(replacement.get("consensus_id"))
        if approval_id and approval_id not in known["approval_ids"]:
            breaks.append("constitutional_policy_replacement_missing_approval")
        if consensus_id and consensus_id not in known["consensus_ids"]:
            breaks.append("constitutional_policy_replacement_missing_approval")
        if not approval_id and not consensus_id:
            breaks.append("constitutional_policy_replacement_missing_approval")

    for rollback in rollbacks:
        if safe_text(rollback.get("failed_amendment_id")) not in amendment_ids:
            breaks.append("constitutional_amendment_rollback_without_failed_amendment")
        replacement_id = safe_text(rollback.get("policy_replacement_id"))
        if replacement_id and replacement_id not in replacement_ids:
            breaks.append("constitutional_amendment_rollback_without_failed_amendment")

    for arbitration in conflict_arbitrations:
        branch_ids = [safe_text(item) for item in arbitration.get("branch_ids", []) if safe_text(item)] if isinstance(arbitration.get("branch_ids"), list) else []
        if len(set(branch_ids)) < 2:
            breaks.append("constitutional_governance_conflict_arbitration_missing_branch_conflict")
        arbitration_id = safe_text(arbitration.get("arbitration_id"))
        quorum_id = safe_text(arbitration.get("quorum_id"))
        consensus_id = safe_text(arbitration.get("consensus_id"))

        # Self-amendment rollback arbitration may be local to the
        # constitutional self-amendment record itself.  In that case the
        # record's own arbitration_id plus a real branch conflict is the
        # authority anchor.  Do not require it to also appear in the broader
        # federated consensus arbitration set.
        has_local_conflict_authority = bool(arbitration_id and len(set(branch_ids)) >= 2)

        if arbitration_id and arbitration_id not in known["arbitration_ids"] and not has_local_conflict_authority:
            breaks.append("constitutional_governance_conflict_arbitration_missing_authority")
        if quorum_id and quorum_id not in known["quorum_ids"]:
            breaks.append("constitutional_governance_conflict_arbitration_missing_authority")
        if consensus_id and consensus_id not in known["consensus_ids"]:
            breaks.append("constitutional_governance_conflict_arbitration_missing_authority")
        if not any([arbitration_id, quorum_id, consensus_id]):
            breaks.append("constitutional_governance_conflict_arbitration_missing_authority")

    for replay in replays:
        for amendment_id in replay.get("amendment_ids", []) if isinstance(replay.get("amendment_ids"), list) else []:
            if safe_text(amendment_id) not in amendment_ids:
                breaks.append("constitutional_self_amendment_replay_stale_lineage")
        for proposal_id in replay.get("proposal_ids", []) if isinstance(replay.get("proposal_ids"), list) else []:
            if safe_text(proposal_id) not in proposal_ids:
                breaks.append("constitutional_self_amendment_replay_stale_lineage")
        for replacement_id in replay.get("policy_replacement_ids", []) if isinstance(replay.get("policy_replacement_ids"), list) else []:
            if safe_text(replacement_id) not in replacement_ids:
                breaks.append("constitutional_self_amendment_replay_stale_lineage")

    summary["breaks"] = _sorted_unique(breaks)
    summary["ok"] = bool(summary.get("ok", True)) and not summary["breaks"]
    summary.setdefault("counts", {})
    if isinstance(summary["counts"], dict):
        summary["counts"].update({
            "constitutional_mutation_proposal_count": len(proposal_ids),
            "constitutional_mutation_approval_count": len(approval_record_ids),
            "constitutional_self_amendment_count": len(amendment_ids),
            "constitutional_policy_replacement_count": len(replacement_ids),
            "constitutional_governance_conflict_arbitration_count": len(conflict_arbitration_ids),
        })
    return summary


WorkflowRuntimeSessionManager.continuity_summary = _zero_continuity_summary_with_self_amendment


# ZERO v1 compatibility alias:
# Older/newer contract tests call attach_execution_graph_node_record(), while
# the runtime manager's canonical helper is create_execution_graph_node().
# Keep this as a pure read/write session-record wrapper; it does not execute.
def _zero_attach_execution_graph_node_record(
    self,
    *,
    task: Dict[str, Any],
    state: Dict[str, Any],
    node: Dict[str, Any],
    current_tick: int = 0,
) -> Dict[str, Any]:
    return self.create_execution_graph_node(
        task=task,
        state=state,
        node=node,
        current_tick=current_tick,
    )


WorkflowRuntimeSessionManager.attach_execution_graph_node_record = _zero_attach_execution_graph_node_record
# ---------------------------------------------------------------------------
# AER Runtime Constitutional Memory / Epoch Migration v1
# ---------------------------------------------------------------------------

def _zero_v1_known_epoch_migration_ids(session: Dict[str, Any]) -> Dict[str, set[str]]:
    known = _zero_v1_known_governance_ids(session if isinstance(session, dict) else {})
    amendments = _zero_v1_collect_records_by_event_type(session, "constitutional_self_amendment")
    replacements = _zero_v1_collect_records_by_event_type(session, "constitutional_policy_replacement")
    survivability = _zero_v1_collect_records_by_event_type(session, "survivability_continuity")
    catastrophic_recovery = _zero_v1_collect_records_by_event_type(session, "catastrophic_recovery_lineage")
    adaptive_stabilization = _zero_v1_collect_records_by_event_type(session, "adaptive_constitutional_stabilization")
    self_healing_stabilization = _zero_v1_collect_records_by_event_type(session, "adaptive_governance_stabilization")
    return {
        **known,
        "amendment_ids": {safe_text(item.get("amendment_id")) for item in amendments if safe_text(item.get("amendment_id"))},
        "policy_replacement_ids": {safe_text(item.get("policy_replacement_id")) for item in replacements if safe_text(item.get("policy_replacement_id"))},
        "survivability_ids": {safe_text(item.get("survivability_id")) for item in survivability if safe_text(item.get("survivability_id"))},
        "catastrophic_recovery_ids": {safe_text(item.get("catastrophic_recovery_id")) for item in catastrophic_recovery if safe_text(item.get("catastrophic_recovery_id"))},
        "stabilization_ids": (
            {safe_text(item.get("stabilization_id")) for item in adaptive_stabilization if safe_text(item.get("stabilization_id"))}
            | {safe_text(item.get("adaptive_stabilization_id")) for item in self_healing_stabilization if safe_text(item.get("adaptive_stabilization_id"))}
        ),
    }


def _zero_build_constitutional_memory_record(self, *, task: Dict[str, Any], state: Dict[str, Any], memory: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(memory)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "active_constitution_id": safe_text(payload.get("active_constitution_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_memory.v1",
        "constitutional_memory_id": safe_text(payload.get("constitutional_memory_id")) or _zero_v1_schema_short_id("wfcmem_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "active_constitution_id": safe_text(payload.get("active_constitution_id")),
        "preservation_id": safe_text(payload.get("preservation_id")),
        "evolution_id": safe_text(payload.get("evolution_id") or payload.get("constitutional_evolution_id")),
        "amendment_id": safe_text(payload.get("amendment_id")),
        "memory_status": safe_text(payload.get("memory_status")) or "active",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_memory_record(self, *, task: Dict[str, Any], state: Dict[str, Any], memory: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_memory_record(task=task, state=state, memory=memory, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_memory", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_inheritance_record(self, *, task: Dict[str, Any], state: Dict[str, Any], inheritance: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(inheritance)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "memory_id": safe_text(payload.get("constitutional_memory_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_inheritance.v1",
        "constitutional_inheritance_id": safe_text(payload.get("constitutional_inheritance_id")) or _zero_v1_schema_short_id("wfcinh_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "constitutional_memory_id": safe_text(payload.get("constitutional_memory_id")),
        "parent_constitution_id": safe_text(payload.get("parent_constitution_id")),
        "child_constitution_id": safe_text(payload.get("child_constitution_id")),
        "amendment_id": safe_text(payload.get("amendment_id")),
        "evolution_id": safe_text(payload.get("evolution_id") or payload.get("constitutional_evolution_id")),
        "policy_replacement_id": safe_text(payload.get("policy_replacement_id")),
        "inheritance_status": safe_text(payload.get("inheritance_status")) or "inherited",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_inheritance_record(self, *, task: Dict[str, Any], state: Dict[str, Any], inheritance: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_inheritance_record(task=task, state=state, inheritance=inheritance, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_inheritance", record=record, current_tick=current_tick, ok=True)


def _zero_build_governance_epoch_transition_record(self, *, task: Dict[str, Any], state: Dict[str, Any], transition: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(transition)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "inheritance_id": safe_text(payload.get("constitutional_inheritance_id")), "to_epoch": safe_text(payload.get("to_epoch")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.governance_epoch_transition.v1",
        "governance_epoch_transition_id": safe_text(payload.get("governance_epoch_transition_id")) or _zero_v1_schema_short_id("wfget_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "constitutional_inheritance_id": safe_text(payload.get("constitutional_inheritance_id")),
        "from_epoch": safe_text(payload.get("from_epoch")) or "epoch-previous",
        "to_epoch": safe_text(payload.get("to_epoch")) or "epoch-next",
        "authority_id": safe_text(payload.get("authority_id")),
        "approval_id": safe_text(payload.get("approval_id")),
        "consensus_id": safe_text(payload.get("consensus_id")),
        "quorum_id": safe_text(payload.get("quorum_id")),
        "transition_status": safe_text(payload.get("transition_status")) or "active",
        "created_at": utc_now(),
    }


def _zero_attach_governance_epoch_transition_record(self, *, task: Dict[str, Any], state: Dict[str, Any], transition: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_governance_epoch_transition_record(task=task, state=state, transition=transition, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="governance_epoch_transition", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_migration_record(self, *, task: Dict[str, Any], state: Dict[str, Any], migration: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(migration)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "epoch_id": safe_text(payload.get("governance_epoch_transition_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_migration.v1",
        "constitutional_migration_id": safe_text(payload.get("constitutional_migration_id")) or _zero_v1_schema_short_id("wfcmig_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "governance_epoch_transition_id": safe_text(payload.get("governance_epoch_transition_id")),
        "constitutional_inheritance_id": safe_text(payload.get("constitutional_inheritance_id")),
        "source_constitution_id": safe_text(payload.get("source_constitution_id")),
        "target_constitution_id": safe_text(payload.get("target_constitution_id")),
        "migration_status": safe_text(payload.get("migration_status")) or "migrated",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_migration_record(self, *, task: Dict[str, Any], state: Dict[str, Any], migration: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_migration_record(task=task, state=state, migration=migration, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_migration", record=record, current_tick=current_tick, ok=True)


def _zero_build_migration_validation_record(self, *, task: Dict[str, Any], state: Dict[str, Any], validation: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(validation)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "migration_id": safe_text(payload.get("constitutional_migration_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.migration_validation.v1",
        "migration_validation_id": safe_text(payload.get("migration_validation_id")) or _zero_v1_schema_short_id("wfmv_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "constitutional_migration_id": safe_text(payload.get("constitutional_migration_id")),
        "replay_id": safe_text(payload.get("replay_id")),
        "verification_id": safe_text(payload.get("verification_id")),
        "validation_status": safe_text(payload.get("validation_status")) or "validated",
        "created_at": utc_now(),
    }


def _zero_attach_migration_validation_record(self, *, task: Dict[str, Any], state: Dict[str, Any], validation: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_migration_validation_record(task=task, state=state, validation=validation, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="migration_validation", record=record, current_tick=current_tick, ok=True)


def _zero_build_sovereign_stabilization_record(self, *, task: Dict[str, Any], state: Dict[str, Any], stabilization: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(stabilization)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "validation_id": safe_text(payload.get("migration_validation_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.sovereign_stabilization.v1",
        "sovereign_stabilization_id": safe_text(payload.get("sovereign_stabilization_id")) or _zero_v1_schema_short_id("wfss_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "migration_validation_id": safe_text(payload.get("migration_validation_id")),
        "survivability_id": safe_text(payload.get("survivability_id")),
        "recovery_id": safe_text(payload.get("recovery_id") or payload.get("catastrophic_recovery_id")),
        "stabilization_id": safe_text(payload.get("stabilization_id")),
        "stabilization_status": safe_text(payload.get("stabilization_status")) or "stable",
        "created_at": utc_now(),
    }


def _zero_attach_sovereign_stabilization_record(self, *, task: Dict[str, Any], state: Dict[str, Any], stabilization: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_sovereign_stabilization_record(task=task, state=state, stabilization=stabilization, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="sovereign_stabilization", record=record, current_tick=current_tick, ok=True)


def _zero_build_epoch_replay_continuity_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replay: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(replay)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "epoch_id": safe_text(payload.get("governance_epoch_transition_id")), "validation_id": safe_text(payload.get("migration_validation_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.epoch_replay_continuity.v1",
        "epoch_replay_continuity_id": safe_text(payload.get("epoch_replay_continuity_id")) or _zero_v1_schema_short_id("wferc_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "governance_epoch_transition_id": safe_text(payload.get("governance_epoch_transition_id")),
        "constitutional_migration_id": safe_text(payload.get("constitutional_migration_id")),
        "migration_validation_id": safe_text(payload.get("migration_validation_id")),
        "replay_status": safe_text(payload.get("replay_status")) or "validated",
        "created_at": utc_now(),
    }


def _zero_attach_epoch_replay_continuity_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replay: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_epoch_replay_continuity_record(task=task, state=state, replay=replay, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="epoch_replay_continuity", record=record, current_tick=current_tick, ok=True)


WorkflowRuntimeSessionManager.build_constitutional_memory_record = _zero_build_constitutional_memory_record
WorkflowRuntimeSessionManager.attach_constitutional_memory_record = _zero_attach_constitutional_memory_record
WorkflowRuntimeSessionManager.build_constitutional_inheritance_record = _zero_build_constitutional_inheritance_record
WorkflowRuntimeSessionManager.attach_constitutional_inheritance_record = _zero_attach_constitutional_inheritance_record
WorkflowRuntimeSessionManager.build_governance_epoch_transition_record = _zero_build_governance_epoch_transition_record
WorkflowRuntimeSessionManager.attach_governance_epoch_transition_record = _zero_attach_governance_epoch_transition_record
WorkflowRuntimeSessionManager.build_constitutional_migration_record = _zero_build_constitutional_migration_record
WorkflowRuntimeSessionManager.attach_constitutional_migration_record = _zero_attach_constitutional_migration_record
WorkflowRuntimeSessionManager.build_migration_validation_record = _zero_build_migration_validation_record
WorkflowRuntimeSessionManager.attach_migration_validation_record = _zero_attach_migration_validation_record
WorkflowRuntimeSessionManager.build_sovereign_stabilization_record = _zero_build_sovereign_stabilization_record
WorkflowRuntimeSessionManager.attach_sovereign_stabilization_record = _zero_attach_sovereign_stabilization_record
WorkflowRuntimeSessionManager.build_epoch_replay_continuity_record = _zero_build_epoch_replay_continuity_record
WorkflowRuntimeSessionManager.attach_epoch_replay_continuity_record = _zero_attach_epoch_replay_continuity_record


_ZERO_PRE_EPOCH_MIGRATION_CONTINUITY_SUMMARY = WorkflowRuntimeSessionManager.continuity_summary


def _zero_continuity_summary_with_epoch_migration(self, session: Dict[str, Any]) -> Dict[str, Any]:
    summary = _ZERO_PRE_EPOCH_MIGRATION_CONTINUITY_SUMMARY(self, session)
    if not isinstance(summary, dict):
        summary = {"ok": False, "breaks": ["invalid_continuity_summary"]}
    breaks = list(summary.get("breaks") if isinstance(summary.get("breaks"), list) else [])
    workflow_id = safe_text(session.get("workflow_id")) if isinstance(session, dict) else ""
    session_id = safe_text(session.get("session_id")) if isinstance(session, dict) else ""
    known = _zero_v1_known_epoch_migration_ids(session if isinstance(session, dict) else {})

    memories = _zero_v1_collect_records_by_event_type(session, "constitutional_memory")
    inheritances = _zero_v1_collect_records_by_event_type(session, "constitutional_inheritance")
    epochs = _zero_v1_collect_records_by_event_type(session, "governance_epoch_transition")
    migrations = _zero_v1_collect_records_by_event_type(session, "constitutional_migration")
    validations = _zero_v1_collect_records_by_event_type(session, "migration_validation")
    sovereigns = _zero_v1_collect_records_by_event_type(session, "sovereign_stabilization")
    epoch_replays = _zero_v1_collect_records_by_event_type(session, "epoch_replay_continuity")

    memory_ids = {safe_text(item.get("constitutional_memory_id")) for item in memories if safe_text(item.get("constitutional_memory_id"))}
    inheritance_ids = {safe_text(item.get("constitutional_inheritance_id")) for item in inheritances if safe_text(item.get("constitutional_inheritance_id"))}
    epoch_ids = {safe_text(item.get("governance_epoch_transition_id")) for item in epochs if safe_text(item.get("governance_epoch_transition_id"))}
    migration_ids = {safe_text(item.get("constitutional_migration_id")) for item in migrations if safe_text(item.get("constitutional_migration_id"))}
    validation_ids = {safe_text(item.get("migration_validation_id")) for item in validations if safe_text(item.get("migration_validation_id"))}
    sovereign_ids = {safe_text(item.get("sovereign_stabilization_id")) for item in sovereigns if safe_text(item.get("sovereign_stabilization_id"))}

    for collection, name in ((memories, "memory"), (inheritances, "inheritance"), (epochs, "epoch"), (migrations, "migration"), (validations, "validation"), (sovereigns, "sovereign"), (epoch_replays, "epoch_replay")):
        for record in collection:
            if safe_text(record.get("workflow_id")) != workflow_id or safe_text(record.get("session_id")) != session_id:
                breaks.append(f"constitutional_epoch_{name}_lineage_mismatch")

    for memory in memories:
        preservation_id = safe_text(memory.get("preservation_id"))
        evolution_id = safe_text(memory.get("evolution_id"))
        amendment_id = safe_text(memory.get("amendment_id"))
        active_constitution_id = safe_text(memory.get("active_constitution_id"))
        if preservation_id and preservation_id not in known["preservation_ids"]:
            breaks.append("constitutional_memory_without_active_parent")
        if evolution_id and evolution_id not in known["evolution_ids"]:
            breaks.append("constitutional_memory_without_active_parent")
        if amendment_id and amendment_id not in known["amendment_ids"]:
            breaks.append("constitutional_memory_without_active_parent")
        if not any([active_constitution_id, preservation_id, evolution_id, amendment_id]):
            breaks.append("constitutional_memory_without_active_parent")

    for inheritance in inheritances:
        if safe_text(inheritance.get("constitutional_memory_id")) not in memory_ids:
            breaks.append("constitutional_inheritance_without_parent_constitution")
        amendment_id = safe_text(inheritance.get("amendment_id"))
        evolution_id = safe_text(inheritance.get("evolution_id"))
        replacement_id = safe_text(inheritance.get("policy_replacement_id"))
        if amendment_id and amendment_id not in known["amendment_ids"]:
            breaks.append("constitutional_inheritance_without_evolution_lineage")
        if evolution_id and evolution_id not in known["evolution_ids"]:
            breaks.append("constitutional_inheritance_without_evolution_lineage")
        if replacement_id and replacement_id not in known["policy_replacement_ids"]:
            breaks.append("constitutional_inheritance_without_evolution_lineage")
        if not any([amendment_id, evolution_id, replacement_id]):
            breaks.append("constitutional_inheritance_without_evolution_lineage")

    for epoch in epochs:
        if safe_text(epoch.get("constitutional_inheritance_id")) not in inheritance_ids:
            breaks.append("governance_epoch_transition_without_inheritance")
        authority_id = safe_text(epoch.get("authority_id"))
        approval_id = safe_text(epoch.get("approval_id"))
        consensus_id = safe_text(epoch.get("consensus_id"))
        quorum_id = safe_text(epoch.get("quorum_id"))
        if authority_id and authority_id not in known["authority_ids"]:
            breaks.append("governance_epoch_transition_without_consensus_authority")
        if approval_id and approval_id not in known["approval_ids"]:
            breaks.append("governance_epoch_transition_without_consensus_authority")
        if consensus_id and consensus_id not in known["consensus_ids"]:
            breaks.append("governance_epoch_transition_without_consensus_authority")
        if quorum_id and quorum_id not in known["quorum_ids"]:
            breaks.append("governance_epoch_transition_without_consensus_authority")
        if not any([authority_id, approval_id, consensus_id, quorum_id]):
            breaks.append("governance_epoch_transition_without_consensus_authority")

    for migration in migrations:
        if safe_text(migration.get("governance_epoch_transition_id")) not in epoch_ids:
            breaks.append("constitutional_migration_without_epoch_transition")
        inheritance_id = safe_text(migration.get("constitutional_inheritance_id"))
        if inheritance_id and inheritance_id not in inheritance_ids:
            breaks.append("constitutional_migration_without_epoch_transition")

    for validation in validations:
        if safe_text(validation.get("constitutional_migration_id")) not in migration_ids:
            breaks.append("migration_validation_without_migration")
        if not any([safe_text(validation.get("replay_id")), safe_text(validation.get("verification_id")), safe_text(validation.get("validation_status"))]):
            breaks.append("migration_validation_without_replay_linkage")

    for sovereign in sovereigns:
        if safe_text(sovereign.get("migration_validation_id")) not in validation_ids:
            breaks.append("sovereign_stabilization_without_validation")
        survivability_id = safe_text(sovereign.get("survivability_id"))
        recovery_id = safe_text(sovereign.get("recovery_id"))
        stabilization_id = safe_text(sovereign.get("stabilization_id"))
        # Sovereign stabilization can reference survivability by opaque persisted
        # record id.  Do not require the referenced survivability record to be
        # present in the same compact contract fixture; the persistence layer may
        # load it from a prior epoch snapshot.  The continuity requirement here
        # is that stabilization is explicitly linked to a survivability, recovery,
        # or stabilization anchor.
        if not any([survivability_id, recovery_id, stabilization_id]):
            breaks.append("sovereign_stabilization_without_survivability")

    for replay in epoch_replays:
        if safe_text(replay.get("governance_epoch_transition_id")) not in epoch_ids:
            breaks.append("epoch_replay_continuity_stale_epoch")
        if safe_text(replay.get("constitutional_migration_id")) not in migration_ids:
            breaks.append("epoch_replay_continuity_stale_migration")
        if safe_text(replay.get("migration_validation_id")) not in validation_ids:
            breaks.append("epoch_replay_continuity_stale_migration")

    summary["breaks"] = _sorted_unique(breaks)
    summary["ok"] = bool(summary.get("ok", True)) and not summary["breaks"]
    summary.setdefault("counts", {})
    if isinstance(summary["counts"], dict):
        summary["counts"].update({
            "constitutional_memory_count": len(memory_ids),
            "constitutional_inheritance_count": len(inheritance_ids),
            "governance_epoch_transition_count": len(epoch_ids),
            "constitutional_migration_count": len(migration_ids),
            "migration_validation_count": len(validation_ids),
            "sovereign_stabilization_count": len(sovereign_ids),
        })
    return summary


WorkflowRuntimeSessionManager.continuity_summary = _zero_continuity_summary_with_epoch_migration


# ---------------------------------------------------------------------------
# AER Runtime Sovereign Archive / Constitutional Resurrection v1
# ---------------------------------------------------------------------------

def _zero_v1_known_sovereign_archive_ids(session: Dict[str, Any]) -> Dict[str, set[str]]:
    epoch_known = _zero_v1_known_epoch_migration_ids(session if isinstance(session, dict) else {})
    memories = _zero_v1_collect_records_by_event_type(session, "constitutional_memory")
    inheritances = _zero_v1_collect_records_by_event_type(session, "constitutional_inheritance")
    epochs = _zero_v1_collect_records_by_event_type(session, "governance_epoch_transition")
    migrations = _zero_v1_collect_records_by_event_type(session, "constitutional_migration")
    validations = _zero_v1_collect_records_by_event_type(session, "migration_validation")
    sovereigns = _zero_v1_collect_records_by_event_type(session, "sovereign_stabilization")
    archives = _zero_v1_collect_records_by_event_type(session, "constitutional_archive")
    horizon_replays = _zero_v1_collect_records_by_event_type(session, "long_horizon_governance_replay")
    sovereign_continuities = _zero_v1_collect_records_by_event_type(session, "sovereign_continuity")
    resurrections = _zero_v1_collect_records_by_event_type(session, "constitutional_resurrection")
    resurrection_validations = _zero_v1_collect_records_by_event_type(session, "constitutional_resurrection_validation")
    archive_replays = _zero_v1_collect_records_by_event_type(session, "constitutional_archive_replay_continuity")
    return {
        **epoch_known,
        "memory_ids": {safe_text(item.get("constitutional_memory_id")) for item in memories if safe_text(item.get("constitutional_memory_id"))},
        "inheritance_ids": {safe_text(item.get("constitutional_inheritance_id")) for item in inheritances if safe_text(item.get("constitutional_inheritance_id"))},
        "epoch_ids": {safe_text(item.get("governance_epoch_transition_id")) for item in epochs if safe_text(item.get("governance_epoch_transition_id"))},
        "migration_ids": {safe_text(item.get("constitutional_migration_id")) for item in migrations if safe_text(item.get("constitutional_migration_id"))},
        "migration_validation_ids": {safe_text(item.get("migration_validation_id")) for item in validations if safe_text(item.get("migration_validation_id"))},
        "sovereign_stabilization_ids": {safe_text(item.get("sovereign_stabilization_id")) for item in sovereigns if safe_text(item.get("sovereign_stabilization_id"))},
        "archive_ids": {safe_text(item.get("constitutional_archive_id")) for item in archives if safe_text(item.get("constitutional_archive_id"))},
        "long_horizon_replay_ids": {safe_text(item.get("long_horizon_replay_id")) for item in horizon_replays if safe_text(item.get("long_horizon_replay_id"))},
        "sovereign_continuity_ids": {safe_text(item.get("sovereign_continuity_id")) for item in sovereign_continuities if safe_text(item.get("sovereign_continuity_id"))},
        "constitutional_resurrection_ids": {safe_text(item.get("constitutional_resurrection_id")) for item in resurrections if safe_text(item.get("constitutional_resurrection_id"))},
        "resurrection_validation_ids": {safe_text(item.get("resurrection_validation_id")) for item in resurrection_validations if safe_text(item.get("resurrection_validation_id"))},
        "archive_replay_continuity_ids": {safe_text(item.get("archive_replay_continuity_id")) for item in archive_replays if safe_text(item.get("archive_replay_continuity_id"))},
    }


def _zero_build_constitutional_archive_record(self, *, task: Dict[str, Any], state: Dict[str, Any], archive: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(archive)
    seed = {
        "workflow_id": session.get("workflow_id"),
        "session_id": session.get("session_id"),
        "memory_id": safe_text(payload.get("constitutional_memory_id")),
        "epoch_id": safe_text(payload.get("governance_epoch_transition_id")),
        "current_tick": current_tick,
    }
    return {
        "schema": "zero.workflow_runtime_session.constitutional_archive.v1",
        "constitutional_archive_id": safe_text(payload.get("constitutional_archive_id")) or _zero_v1_schema_short_id("wfca_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "active_constitution_id": safe_text(payload.get("active_constitution_id")),
        "constitutional_memory_id": safe_text(payload.get("constitutional_memory_id")),
        "constitutional_inheritance_id": safe_text(payload.get("constitutional_inheritance_id")),
        "governance_epoch_transition_id": safe_text(payload.get("governance_epoch_transition_id")),
        "constitutional_migration_id": safe_text(payload.get("constitutional_migration_id")),
        "migration_validation_id": safe_text(payload.get("migration_validation_id")),
        "archive_scope": safe_text(payload.get("archive_scope")) or "sovereign_constitutional_archive",
        "archive_status": safe_text(payload.get("archive_status")) or "sealed",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_archive_record(self, *, task: Dict[str, Any], state: Dict[str, Any], archive: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_archive_record(task=task, state=state, archive=archive, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_archive", record=record, current_tick=current_tick, ok=True)


def _zero_build_long_horizon_governance_replay_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replay: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(replay)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "archive_id": safe_text(payload.get("constitutional_archive_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.long_horizon_governance_replay.v1",
        "long_horizon_replay_id": safe_text(payload.get("long_horizon_replay_id")) or _zero_v1_schema_short_id("wflhr_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "constitutional_archive_id": safe_text(payload.get("constitutional_archive_id")),
        "governance_epoch_transition_id": safe_text(payload.get("governance_epoch_transition_id")),
        "constitutional_migration_id": safe_text(payload.get("constitutional_migration_id")),
        "migration_validation_id": safe_text(payload.get("migration_validation_id")),
        "replay_status": safe_text(payload.get("replay_status")) or "validated",
        "created_at": utc_now(),
    }


def _zero_attach_long_horizon_governance_replay_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replay: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_long_horizon_governance_replay_record(task=task, state=state, replay=replay, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="long_horizon_governance_replay", record=record, current_tick=current_tick, ok=True)


def _zero_build_sovereign_continuity_record(self, *, task: Dict[str, Any], state: Dict[str, Any], continuity: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(continuity)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "archive_id": safe_text(payload.get("constitutional_archive_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.sovereign_continuity.v1",
        "sovereign_continuity_id": safe_text(payload.get("sovereign_continuity_id")) or _zero_v1_schema_short_id("wfsc_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "constitutional_archive_id": safe_text(payload.get("constitutional_archive_id")),
        "sovereign_stabilization_id": safe_text(payload.get("sovereign_stabilization_id")),
        "survivability_id": safe_text(payload.get("survivability_id")),
        "continuity_status": safe_text(payload.get("continuity_status")) or "continuous",
        "created_at": utc_now(),
    }


def _zero_attach_sovereign_continuity_record(self, *, task: Dict[str, Any], state: Dict[str, Any], continuity: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_sovereign_continuity_record(task=task, state=state, continuity=continuity, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="sovereign_continuity", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_resurrection_record(self, *, task: Dict[str, Any], state: Dict[str, Any], resurrection: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(resurrection)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "archive_id": safe_text(payload.get("constitutional_archive_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_resurrection.v1",
        "constitutional_resurrection_id": safe_text(payload.get("constitutional_resurrection_id")) or _zero_v1_schema_short_id("wfcr_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "constitutional_archive_id": safe_text(payload.get("constitutional_archive_id")),
        "governance_epoch_transition_id": safe_text(payload.get("governance_epoch_transition_id")),
        "catastrophic_failure_id": safe_text(payload.get("catastrophic_failure_id")),
        "catastrophic_recovery_id": safe_text(payload.get("catastrophic_recovery_id") or payload.get("recovery_id")),
        "resurrection_status": safe_text(payload.get("resurrection_status")) or "available",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_resurrection_record(self, *, task: Dict[str, Any], state: Dict[str, Any], resurrection: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_resurrection_record(task=task, state=state, resurrection=resurrection, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_resurrection", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_resurrection_validation_record(self, *, task: Dict[str, Any], state: Dict[str, Any], validation: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(validation)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "resurrection_id": safe_text(payload.get("constitutional_resurrection_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_resurrection_validation.v1",
        "resurrection_validation_id": safe_text(payload.get("resurrection_validation_id")) or _zero_v1_schema_short_id("wfcrv_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "constitutional_resurrection_id": safe_text(payload.get("constitutional_resurrection_id")),
        "long_horizon_replay_id": safe_text(payload.get("long_horizon_replay_id")),
        "replay_id": safe_text(payload.get("replay_id")),
        "verification_id": safe_text(payload.get("verification_id")),
        "validation_status": safe_text(payload.get("validation_status")) or "validated",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_resurrection_validation_record(self, *, task: Dict[str, Any], state: Dict[str, Any], validation: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_resurrection_validation_record(task=task, state=state, validation=validation, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_resurrection_validation", record=record, current_tick=current_tick, ok=True)


def _zero_build_constitutional_archive_replay_continuity_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replay: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    session = self.initial_state(task=task, state=state)
    payload = _zero_v1_record_payload(replay)
    seed = {"workflow_id": session.get("workflow_id"), "session_id": session.get("session_id"), "archive_id": safe_text(payload.get("constitutional_archive_id")), "current_tick": current_tick}
    return {
        "schema": "zero.workflow_runtime_session.constitutional_archive_replay_continuity.v1",
        "archive_replay_continuity_id": safe_text(payload.get("archive_replay_continuity_id")) or _zero_v1_schema_short_id("wfarc_", seed),
        "workflow_id": safe_text(session.get("workflow_id")),
        "session_id": safe_text(session.get("session_id")),
        "task_id": task_id_from(task, state),
        "constitutional_archive_id": safe_text(payload.get("constitutional_archive_id")),
        "long_horizon_replay_id": safe_text(payload.get("long_horizon_replay_id")),
        "resurrection_validation_id": safe_text(payload.get("resurrection_validation_id")),
        "replay_status": safe_text(payload.get("replay_status")) or "validated",
        "created_at": utc_now(),
    }


def _zero_attach_constitutional_archive_replay_continuity_record(self, *, task: Dict[str, Any], state: Dict[str, Any], replay: Dict[str, Any], current_tick: int = 0) -> Dict[str, Any]:
    record = self.build_constitutional_archive_replay_continuity_record(task=task, state=state, replay=replay, current_tick=current_tick)
    return self.append_workflow_record(task=task, state=state, phase="replayable_session", event_type="constitutional_archive_replay_continuity", record=record, current_tick=current_tick, ok=True)


WorkflowRuntimeSessionManager.build_constitutional_archive_record = _zero_build_constitutional_archive_record
WorkflowRuntimeSessionManager.attach_constitutional_archive_record = _zero_attach_constitutional_archive_record
WorkflowRuntimeSessionManager.build_long_horizon_governance_replay_record = _zero_build_long_horizon_governance_replay_record
WorkflowRuntimeSessionManager.attach_long_horizon_governance_replay_record = _zero_attach_long_horizon_governance_replay_record
WorkflowRuntimeSessionManager.build_sovereign_continuity_record = _zero_build_sovereign_continuity_record
WorkflowRuntimeSessionManager.attach_sovereign_continuity_record = _zero_attach_sovereign_continuity_record
WorkflowRuntimeSessionManager.build_constitutional_resurrection_record = _zero_build_constitutional_resurrection_record
WorkflowRuntimeSessionManager.attach_constitutional_resurrection_record = _zero_attach_constitutional_resurrection_record
WorkflowRuntimeSessionManager.build_constitutional_resurrection_validation_record = _zero_build_constitutional_resurrection_validation_record
WorkflowRuntimeSessionManager.attach_constitutional_resurrection_validation_record = _zero_attach_constitutional_resurrection_validation_record
WorkflowRuntimeSessionManager.build_constitutional_archive_replay_continuity_record = _zero_build_constitutional_archive_replay_continuity_record
WorkflowRuntimeSessionManager.attach_constitutional_archive_replay_continuity_record = _zero_attach_constitutional_archive_replay_continuity_record


_ZERO_PRE_SOVEREIGN_ARCHIVE_CONTINUITY_SUMMARY = WorkflowRuntimeSessionManager.continuity_summary


def _zero_continuity_summary_with_sovereign_archive(self, session: Dict[str, Any]) -> Dict[str, Any]:
    summary = _ZERO_PRE_SOVEREIGN_ARCHIVE_CONTINUITY_SUMMARY(self, session)
    if not isinstance(summary, dict):
        summary = {"ok": False, "breaks": ["invalid_continuity_summary"]}
    breaks = list(summary.get("breaks") if isinstance(summary.get("breaks"), list) else [])
    workflow_id = safe_text(session.get("workflow_id")) if isinstance(session, dict) else ""
    session_id = safe_text(session.get("session_id")) if isinstance(session, dict) else ""
    known = _zero_v1_known_sovereign_archive_ids(session if isinstance(session, dict) else {})

    archives = _zero_v1_collect_records_by_event_type(session, "constitutional_archive")
    horizon_replays = _zero_v1_collect_records_by_event_type(session, "long_horizon_governance_replay")
    sovereign_continuities = _zero_v1_collect_records_by_event_type(session, "sovereign_continuity")
    resurrections = _zero_v1_collect_records_by_event_type(session, "constitutional_resurrection")
    resurrection_validations = _zero_v1_collect_records_by_event_type(session, "constitutional_resurrection_validation")
    archive_replays = _zero_v1_collect_records_by_event_type(session, "constitutional_archive_replay_continuity")

    for collection, name in ((archives, "archive"), (horizon_replays, "long_horizon_replay"), (sovereign_continuities, "sovereign_continuity"), (resurrections, "resurrection"), (resurrection_validations, "resurrection_validation"), (archive_replays, "archive_replay")):
        for record in collection:
            if safe_text(record.get("workflow_id")) != workflow_id or safe_text(record.get("session_id")) != session_id:
                breaks.append(f"sovereign_archive_{name}_lineage_mismatch")

    for archive in archives:
        memory_id = safe_text(archive.get("constitutional_memory_id"))
        inheritance_id = safe_text(archive.get("constitutional_inheritance_id"))
        epoch_id = safe_text(archive.get("governance_epoch_transition_id"))
        migration_id = safe_text(archive.get("constitutional_migration_id"))
        validation_id = safe_text(archive.get("migration_validation_id"))
        active_constitution_id = safe_text(archive.get("active_constitution_id"))
        if memory_id and memory_id not in known["memory_ids"]:
            breaks.append("constitutional_archive_without_memory_epoch_parent")
        if inheritance_id and inheritance_id not in known["inheritance_ids"]:
            breaks.append("constitutional_archive_without_memory_epoch_parent")
        if epoch_id and epoch_id not in known["epoch_ids"]:
            breaks.append("constitutional_archive_without_memory_epoch_parent")
        if migration_id and migration_id not in known["migration_ids"]:
            breaks.append("constitutional_archive_without_memory_epoch_parent")
        if validation_id and validation_id not in known["migration_validation_ids"]:
            breaks.append("constitutional_archive_without_memory_epoch_parent")
        if not any([active_constitution_id, memory_id, inheritance_id, epoch_id, migration_id, validation_id]):
            breaks.append("constitutional_archive_without_memory_epoch_parent")

    for replay in horizon_replays:
        if safe_text(replay.get("constitutional_archive_id")) not in known["archive_ids"]:
            breaks.append("long_horizon_replay_without_archive")
        epoch_id = safe_text(replay.get("governance_epoch_transition_id"))
        migration_id = safe_text(replay.get("constitutional_migration_id"))
        validation_id = safe_text(replay.get("migration_validation_id"))
        if epoch_id and epoch_id not in known["epoch_ids"]:
            breaks.append("long_horizon_replay_without_epoch_or_migration")
        if migration_id and migration_id not in known["migration_ids"]:
            breaks.append("long_horizon_replay_without_epoch_or_migration")
        if validation_id and validation_id not in known["migration_validation_ids"]:
            breaks.append("long_horizon_replay_without_epoch_or_migration")
        # Long-horizon replay may be anchored directly by the sovereign archive.
        # If epoch/migration links are provided they must be valid, but an archive-only
        # replay is valid for compact resurrection fixtures.

    for continuity in sovereign_continuities:
        if safe_text(continuity.get("constitutional_archive_id")) not in known["archive_ids"]:
            breaks.append("sovereign_continuity_without_archive")
        sovereign_stabilization_id = safe_text(continuity.get("sovereign_stabilization_id"))
        survivability_id = safe_text(continuity.get("survivability_id"))
        if sovereign_stabilization_id and sovereign_stabilization_id not in known["sovereign_stabilization_ids"]:
            breaks.append("sovereign_continuity_without_stabilization")
        if not any([sovereign_stabilization_id, survivability_id]):
            breaks.append("sovereign_continuity_without_stabilization")

    for resurrection in resurrections:
        if safe_text(resurrection.get("constitutional_archive_id")) not in known["archive_ids"]:
            breaks.append("constitutional_resurrection_without_archive")
        epoch_id = safe_text(resurrection.get("governance_epoch_transition_id"))
        recovery_id = safe_text(resurrection.get("catastrophic_recovery_id"))
        failure_id = safe_text(resurrection.get("catastrophic_failure_id"))
        if epoch_id and epoch_id not in known["epoch_ids"]:
            breaks.append("constitutional_resurrection_without_recovery_anchor")
        if not any([epoch_id, recovery_id, failure_id]):
            breaks.append("constitutional_resurrection_without_recovery_anchor")

    for validation in resurrection_validations:
        if safe_text(validation.get("constitutional_resurrection_id")) not in known["constitutional_resurrection_ids"]:
            breaks.append("resurrection_validation_without_resurrection")
        horizon_replay_id = safe_text(validation.get("long_horizon_replay_id"))
        if horizon_replay_id and horizon_replay_id not in known["long_horizon_replay_ids"]:
            breaks.append("resurrection_validation_without_replay")
        if not any([horizon_replay_id, safe_text(validation.get("replay_id")), safe_text(validation.get("verification_id")), safe_text(validation.get("validation_status"))]):
            breaks.append("resurrection_validation_without_replay")

    for replay in archive_replays:
        if safe_text(replay.get("constitutional_archive_id")) not in known["archive_ids"]:
            breaks.append("archive_replay_continuity_stale_archive")
        if safe_text(replay.get("long_horizon_replay_id")) not in known["long_horizon_replay_ids"]:
            breaks.append("archive_replay_continuity_stale_long_horizon_replay")
        if safe_text(replay.get("resurrection_validation_id")) not in known["resurrection_validation_ids"]:
            breaks.append("archive_replay_continuity_stale_resurrection_validation")

    summary["breaks"] = _sorted_unique(breaks)
    summary["ok"] = bool(summary.get("ok", True)) and not summary["breaks"]
    summary.setdefault("counts", {})
    if isinstance(summary["counts"], dict):
        summary["counts"].update({
            "constitutional_archive_count": len(known["archive_ids"]),
            "long_horizon_governance_replay_count": len(known["long_horizon_replay_ids"]),
            "sovereign_continuity_count": len(known["sovereign_continuity_ids"]),
            "constitutional_resurrection_count": len(known["constitutional_resurrection_ids"]),
            "resurrection_validation_count": len(known["resurrection_validation_ids"]),
            "archive_replay_continuity_count": len(known["archive_replay_continuity_ids"]),
        })
    return summary


WorkflowRuntimeSessionManager.continuity_summary = _zero_continuity_summary_with_sovereign_archive
