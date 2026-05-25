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
