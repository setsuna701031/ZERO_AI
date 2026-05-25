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
            )
        if source_session_id:
            lineage["replay_continuation"] = {
                "source_session_id": source_session_id,
                "continued_session_id": session_id,
                "workflow_id": workflow_id,
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
        lineage = {
            "schema": "zero.workflow_runtime_session.lineage.v1",
            "workflow_id": workflow_id,
            "session_id": session_id,
            "task_id": task_id_from(task, state),
            "source_session_id": source_session_id,
            "parent_session_id": parent_session_id,
            "root_session_id": parent_session_id or source_session_id or session_id,
            "event_ids_by_phase": event_ids_by_phase,
            "repair_ancestry": repair_events[-20:],
            "retry_chain": retry_events[-20:],
        }
        if source_session_id:
            lineage["replay_continuation"] = {
                "source_session_id": source_session_id,
                "continued_session_id": session_id,
                "workflow_id": workflow_id,
                "event_count": len(events),
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
        return {
            "schema": "zero.workflow_runtime_session.retry_chain.v1",
            "retry_chain_id": "wfr_" + stable_hash(chain_seed)[:16],
            "retry_attempt": retry_count,
            "parent_event_id": parent_event.event_id if parent_event else "",
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

        source_session_id = safe_text(lineage.get("source_session_id"))
        replay = lineage.get("replay_continuation") if isinstance(lineage.get("replay_continuation"), dict) else {}
        if source_session_id and safe_text(replay.get("source_session_id")) != source_session_id:
            breaks.append("broken_source_session_id")
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
