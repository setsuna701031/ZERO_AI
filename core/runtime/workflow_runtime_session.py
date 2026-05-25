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
