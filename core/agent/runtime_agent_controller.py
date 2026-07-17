from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.agent.runtime_mission_inbox import (add_mission_entry, cancel_mission_entry, claim_next_mission_entry,
    create_mission_inbox, get_mission_entry, list_mission_entries, load_mission_inbox, reprioritize_mission_entry,
    save_mission_inbox, update_mission_entry)
from core.runtime.runtime_operator_session import fingerprint, time_text


CONTRACT = "zero.agent.persistent_agent_state.v1"
STATUSES = {"created", "running", "idle", "paused", "stopping", "stopped", "blocked", "failed"}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _unsafe(path: Path) -> bool:
    try: return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError: return False


def prepare_agent_workspace_root(value: Any, *, create: bool) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute() and ".." in raw.parts:
        raise ValueError("unsafe_workspace_path_traversal")
    path = raw.resolve(strict=False)
    if not path.exists():
        if not create:
            raise ValueError("workspace_root_not_found")
        ancestor = path.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        if not ancestor.exists() or _unsafe(ancestor):
            raise ValueError("unsafe_workspace_parent")
        path.mkdir(parents=True, exist_ok=True)
    path = path.resolve(strict=True)
    if not path.is_dir(): raise ValueError("workspace_root_not_directory")
    if _unsafe(path): raise ValueError("unsafe_workspace_root")
    return path


def default_agent_state_root(workspace_root: Any) -> Path:
    workspace = Path(workspace_root).resolve(strict=False)
    identity = fingerprint(str(workspace).replace("\\", "/").casefold())[:16]
    return workspace.parent / ".zero_ai_runtime" / "agent" / identity


def project_mission_result(result: Any, *, mission: Any = None, session: Any = None,
                           expected_mission_id: str | None = None,
                           expected_session_id: str | None = None) -> dict[str, Any]:
    """Project heterogeneous Mission Runtime evidence into one Agent entry state."""
    roots = [_mapping(result), _mapping(mission), _mapping(session)]
    mappings: list[dict[str, Any]] = []
    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            item = dict(value); mappings.append(item)
            for nested in item.values(): collect(nested)
        elif isinstance(value, list):
            for nested in value: collect(nested)
    for root in roots: collect(root)

    def values(*keys: str) -> list[str]:
        return [str(item[key]).strip().casefold() for item in mappings for key in keys
                if item.get(key) is not None and str(item.get(key)).strip()]

    mission_ids = [str(root.get("mission_id") or _mapping(root.get("mission_reference")).get("mission_id") or "").strip().casefold() for root in roots]
    session_ids = [str(root.get("session_id") or root.get("mission_session_id") or _mapping(root.get("session_reference")).get("session_id") or "").strip().casefold() for root in roots]
    mission_ids = [value for value in mission_ids if value]
    session_ids = [value for value in session_ids if value]
    if expected_mission_id and mission_ids and any(value != expected_mission_id.casefold() for value in mission_ids):
        return {"entry_status": "blocked", "reason": "agent_mission_identity_mismatch"}
    if expected_session_id and session_ids and any(value != expected_session_id.casefold() for value in session_ids):
        return {"entry_status": "blocked", "reason": "agent_session_identity_mismatch"}

    status_sources = list(roots)
    status_keys = ("bootstrap_status", "mission_status", "session_status", "execution_status", "status", "transaction_status", "validation_status", "rollback_status", "plan_status", "approval_status")
    statuses = {str(item[key]).strip().casefold() for item in status_sources for key in status_keys if item.get(key) is not None and str(item.get(key)).strip()}
    lifecycle_values = {"completed", "already_completed", "failed", "blocked", "cancelled", "canceled", "running", "waiting_for_plan_confirmation", "waiting_for_operator", "waiting_for_operator_approval"}
    if not statuses & lifecycle_values:
        for root in roots:
            status_sources.extend(_mapping(root.get(key)) for key in ("runtime_result", "last_result", "transaction_result") if isinstance(root.get(key), Mapping))
        statuses = {str(item[key]).strip().casefold() for item in status_sources for key in status_keys if item.get(key) is not None and str(item.get(key)).strip()}
    reasons = values("reason") + [str(reason).strip().casefold() for item in mappings for reason in (item.get("reasons") or []) if str(reason).strip()]
    failures = [item.get("failure") for item in mappings if item.get("failure") not in (None, {}, [], "")]
    denied = "denied" in statuses or any("denied" in reason for reason in reasons)
    safety_terms = ("fingerprint", "unsafe", "unsupported", "approval_scope", "expired", "safety", "policy", "identity_mismatch")
    failed_statuses = {"failed", "validation_failed", "rollback_failed", "transaction_failed", "rolled_back", "error", "unrecoverable"}
    blocked_statuses = {"blocked", "expired", "unsupported", "invalid"}
    cancelled_statuses = {"cancelled", "canceled", "stopped_by_cancellation"}
    waiting_statuses = {"waiting_for_plan_confirmation", "waiting_for_operator", "waiting_for_operator_approval", "pending_approval"}
    running_statuses = {"running", "preparing", "selected", "registered", "resumable", "scheduler_running", "daemon_running"}
    completed_statuses = {"completed", "already_completed"}

    if statuses & cancelled_statuses:
        return {"entry_status": "cancelled", "reason": "mission_cancelled"}
    if denied or statuses & blocked_statuses or any(term in reason for reason in reasons for term in safety_terms):
        return {"entry_status": "blocked", "reason": "operator_denied" if denied else (reasons[0] if reasons else "mission_blocked")}
    if statuses & failed_statuses or failures:
        return {"entry_status": "failed", "reason": reasons[0] if reasons else "mission_failed"}
    approval_required = any(item.get("approval_required") is True for item in mappings)
    approved = "approved" in statuses
    if statuses & waiting_statuses or "pending" in {str(item.get("approval_status")).casefold() for item in status_sources} or (approval_required and not approved):
        return {"entry_status": "waiting_for_approval", "reason": "operator_approval_required"}
    if statuses & completed_statuses:
        return {"entry_status": "completed", "reason": "mission_completed"}
    if statuses & running_statuses:
        return {"entry_status": "running", "reason": "mission_resumable"}
    return {"entry_status": "failed", "reason": "ambiguous_mission_result"}


def _unsigned(state: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(state); value.pop("agent_fingerprint", None); return value


def seal_agent_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = _unsigned(state); value["agent_fingerprint"] = fingerprint(value); return value


def validate_agent_state(state: Mapping[str, Any]) -> list[str]:
    value = _mapping(state); reasons = []
    if value.get("contract") != CONTRACT: reasons.append("invalid_agent_state_contract")
    if value.get("agent_fingerprint") != fingerprint(_unsigned(value)): reasons.append("agent_state_fingerprint_mismatch")
    if value.get("agent_status") not in STATUSES: reasons.append("invalid_agent_status")
    for field in ("agent_id", "inbox_path", "event_bus_path", "workspace_root", "state_root"):
        if not str(value.get(field) or "").strip(): reasons.append(f"{field}_required")
    for field in ("loop_iteration", "missions_started", "missions_completed", "missions_blocked", "missions_failed"):
        if isinstance(value.get(field), bool) or not isinstance(value.get(field), int) or value.get(field, -1) < 0: reasons.append(f"invalid_{field}")
    if not isinstance(value.get("queue_snapshot"), list): reasons.append("queue_snapshot_required")
    return sorted(set(reasons))


def save_agent_state(state: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path).resolve(strict=False)
    if destination.exists() and _unsafe(destination): raise ValueError("unsafe_agent_state_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination.parent): raise ValueError("unsafe_agent_state_directory")
    value = seal_agent_state(state); reasons = validate_agent_state(value)
    if reasons: raise ValueError(";".join(reasons))
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return value


def load_agent_state(path: Any) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source): raise ValueError("unsafe_agent_state_path")
    try: value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_agent_state_json") from exc
    reasons = validate_agent_state(value)
    if reasons: raise ValueError(";".join(reasons))
    return value


class RuntimeAgentController:
    def __init__(self, *, workspace_root: Any, state_root: Any = None, create_workspace: bool = True, now: Any = None):
        self.workspace_root = prepare_agent_workspace_root(workspace_root, create=create_workspace)
        self.state_root = Path(state_root).resolve(strict=False) if state_root is not None else default_agent_state_root(self.workspace_root)
        ancestor = self.state_root.parent
        while not ancestor.exists() and ancestor != ancestor.parent: ancestor = ancestor.parent
        if not ancestor.exists() or _unsafe(ancestor): raise ValueError("unsafe_agent_state_parent")
        self.state_root.mkdir(parents=True, exist_ok=True)
        if _unsafe(self.state_root): raise ValueError("unsafe_agent_state_root")
        self.inbox_path = self.state_root / "mission-inbox.json"
        self.agent_state_path = self.state_root / "agent-state.json"
        self.event_bus_path = self.state_root / "agent-event-bus.json"
        self.activity_memory_path = self.state_root / "activity-memory.jsonl"
        self.reflection_root = self.state_root / "reflections"
        self._initialize(now=now)

    def _initialize(self, *, now: Any = None) -> None:
        if not self.inbox_path.exists(): save_mission_inbox(create_mission_inbox(workspace_root=self.workspace_root, state_root=self.state_root, now=now), self.inbox_path)
        if not self.event_bus_path.exists():
            from core.runtime.runtime_event_bus import create_event_bus_state, save_event_bus_state
            save_event_bus_state(create_event_bus_state(state_path=self.event_bus_path, bus_name="zero-autonomous-agent", now=now), self.event_bus_path)
        if not self.agent_state_path.exists():
            at = time_text(now); identity = {"workspace": str(self.workspace_root).replace("\\", "/").casefold(), "state": str(self.state_root).replace("\\", "/").casefold()}
            state = {"contract": CONTRACT, "agent_id": f"runtime-agent-{fingerprint(identity)[:20]}", "agent_status": "created", "current_entry_id": None, "current_mission_id": None, "current_session_id": None, "started_at": None, "updated_at": at, "completed_at": None, "pause_requested": False, "stop_requested": False, "loop_iteration": 0, "missions_started": 0, "missions_completed": 0, "missions_blocked": 0, "missions_failed": 0, "last_result": None, "last_error": None, "last_reflection": None, "last_experience_id": None, "inbox_path": str(self.inbox_path.resolve()), "queue_snapshot": [], "event_bus_path": str(self.event_bus_path.resolve()), "activity_memory_path": str(self.activity_memory_path.resolve()), "workspace_root": str(self.workspace_root), "state_root": str(self.state_root.resolve()), "checkpoints": []}
            save_agent_state(state, self.agent_state_path)
        self.refresh_state(now=now, activity_memory_path=str(self.activity_memory_path.resolve()))

    def load_inbox(self) -> dict[str, Any]: return load_mission_inbox(self.inbox_path)
    def load_state(self) -> dict[str, Any]: return load_agent_state(self.agent_state_path)
    def load_memory(self):
        from core.runtime.runtime_memory_model import RuntimeActivityMemory
        return RuntimeActivityMemory(self.activity_memory_path)

    def _queue_snapshot(self, inbox: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [{key: item.get(key) for key in ("entry_id", "priority", "status", "mission_id", "mission_session_id", "updated_at")} for item in list_mission_entries(inbox)]

    def refresh_state(self, *, now: Any = None, **updates: Any) -> dict[str, Any]:
        state = self.load_state() if self.agent_state_path.exists() else {}
        inbox = self.load_inbox(); state.update(deepcopy(updates)); state["queue_snapshot"] = self._queue_snapshot(inbox); state["updated_at"] = time_text(now)
        return save_agent_state(state, self.agent_state_path)

    def _publish(self, topic: str, *, entry: Mapping[str, Any] | None = None, suffix: str = "", payload_extra: Mapping[str, Any] | None = None, now: Any = None) -> None:
        from core.runtime.runtime_event_bus import load_event_bus_state, publish, save_event_bus_state
        state = self.load_state(); item = _mapping(entry); bus = load_event_bus_state(self.event_bus_path)
        payload = {"agent_id": state["agent_id"], "entry_id": item.get("entry_id"), "mission_id": item.get("mission_id"), "session_id": item.get("mission_session_id"), "agent_status": state.get("agent_status"), "entry_status": item.get("status"), "timestamp": time_text(now)}
        payload.update(_mapping(payload_extra))
        key = f"{state['agent_id']}:{topic}:{item.get('entry_id') or 'agent'}:{suffix or item.get('status') or state.get('agent_status')}"
        bus, _ = publish(bus, event_type="audit", topic=topic, source=state["agent_id"], payload=payload, idempotency_key=key, correlation_id=item.get("mission_id") or item.get("entry_id") or state["agent_id"], now=now)
        save_event_bus_state(bus, self.event_bus_path)

    def publish_coordination_event(self, topic: str, *, correlation_id: str, subject_id: str | None = None,
                                   payload: Mapping[str, Any] | None = None, suffix: str = "", now: Any = None) -> None:
        extra = _mapping(payload); extra["correlation_id"] = str(correlation_id)
        synthetic = {"entry_id": subject_id or correlation_id, "mission_id": correlation_id, "status": extra.get("goal_status")}
        self._publish(topic, entry=synthetic, suffix=suffix, payload_extra=extra, now=now)

    def runtime_mission_budget(self, requested_limit: int) -> dict[str, Any]:
        if isinstance(requested_limit, bool) or not isinstance(requested_limit, int) or requested_limit < 1: raise ValueError("invalid_runtime_mission_budget_request")
        state = self.load_state(); unavailable = bool(state.get("pause_requested") or state.get("stop_requested") or state.get("agent_status") in {"paused", "stopped", "stopping"})
        active_statuses = {"selected", "preparing", "running"}; active = sum(entry.get("status") in active_statuses for entry in self.list())
        invariant = active <= requested_limit; available = 0 if unavailable or not invariant else max(0, requested_limit - active)
        value = {"contract": "zero.agent.runtime_mission_budget.v1", "agent_id": state["agent_id"], "requested_limit": requested_limit, "runtime_budget": requested_limit, "active_mission_count": active, "available_mission_starts": available, "invariant_satisfied": invariant, "runtime_available": not unavailable and invariant, "reason": "agent_not_runnable" if unavailable else "active_missions_exceed_runtime_budget" if not invariant else "bounded_runtime_capacity", "agent_state_fingerprint": state["agent_fingerprint"]}
        value["budget_fingerprint"] = fingerprint(value); return value

    def add(self, natural_language: str, *, priority: str = "normal", target_root: Any = None, tags: list[str] | None = None, max_attempts: int = 3, input_id: str | None = None, not_before: Any = None, now: Any = None) -> dict[str, Any]:
        inbox, entry, created = add_mission_entry(self.load_inbox(), natural_language, workspace_root=self.workspace_root, target_root=target_root or self.workspace_root, priority=priority, tags=tags, max_attempts=max_attempts, input_id=input_id, not_before=not_before, now=now)
        if created: save_mission_inbox(inbox, self.inbox_path); self.refresh_state(now=now); self._publish("agent.entry.added", entry=entry, now=now)
        return entry

    def list(self, *, status: str | None = None) -> list[dict[str, Any]]: return list_mission_entries(self.load_inbox(), status=status)
    def show(self, entry_id: str) -> dict[str, Any]: return get_mission_entry(self.load_inbox(), entry_id)

    def _update_entry_metadata(self, entry_id: str, updates: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
        inbox, entry = update_mission_entry(self.load_inbox(), entry_id, updates=updates, now=now)
        save_mission_inbox(inbox, self.inbox_path); self.refresh_state(now=now); return entry

    def memory_list(self, *, outcome: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        return self.load_memory().experience_records(outcome=outcome, limit=limit)

    def memory_show(self, experience_id: str) -> dict[str, Any]:
        return self.load_memory().experience(experience_id)

    def memory_search(self, text: str, *, top_k: int = 3) -> dict[str, Any]:
        from core.runtime.runtime_activity_memory_query import query_relevant_experiences
        return query_relevant_experiences(self.load_memory(), text, workspace_context=str(self.workspace_root), top_k=top_k)

    def planning(self, entry_id: str, *, explain: bool = False) -> dict[str, Any]:
        entry = self.show(entry_id)
        artifact_path = Path(str(entry.get("bootstrap_artifact_path") or ""))
        if not artifact_path.is_file(): raise ValueError("planning_feedback_not_prepared")
        artifact = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
        claimed = artifact.get("artifact_fingerprint"); unsigned = deepcopy(artifact); unsigned.pop("artifact_fingerprint", None)
        if claimed != fingerprint(unsigned): raise ValueError("bootstrap_artifact_fingerprint_mismatch")
        reference = _mapping(artifact.get("planning_feedback_reference")); feedback = {}
        if reference.get("path"):
            from core.runtime.runtime_agent_planning_feedback import load_planning_feedback
            feedback = load_planning_feedback(reference["path"])
            if feedback.get("feedback_fingerprint") != reference.get("fingerprint"): raise ValueError("planning_feedback_reference_mismatch")
        value = {"entry_id": entry_id, "mission_id": entry.get("mission_id"), "planning_feedback_status": artifact.get("planning_feedback_status"), "feedback_id": feedback.get("feedback_id"), "feedback_fingerprint": feedback.get("feedback_fingerprint"), "experiences_used": deepcopy(feedback.get("experience_references") or []), "matched_tokens": deepcopy(feedback.get("matched_tokens") or []), "applied_recommendations": deepcopy(artifact.get("applied_recommendations") or []), "ignored_recommendations": deepcopy(artifact.get("ignored_recommendations") or []), "goal_plan_before": deepcopy(artifact.get("goal_plan_before_feedback") or []), "goal_plan_after": deepcopy(artifact.get("goal_plan_after_feedback") or []), "added_validations": deepcopy(feedback.get("recommended_validations") or []), "risk_notes": deepcopy(feedback.get("risk_notes") or []), "scope_preserved": True, "approval_preserved": True, "confidence": feedback.get("confidence", 0.0), "planning_feedback_path": reference.get("path"), "planning_feedback_error": artifact.get("planning_feedback_error")}
        if explain: value["explanation"] = {"memory_experiences_used": value["experiences_used"], "recommendations_considered": value["applied_recommendations"] + value["ignored_recommendations"], "goal_changes": {"before_count": len(value["goal_plan_before"]), "after_count": len(value["goal_plan_after"])}, "validation_changes": value["added_validations"], "scope_preserved": True, "approval_preserved": True}
        return value

    def planning_preview(self, natural_language: str, *, target_root: Any = None, now: Any = None) -> dict[str, Any]:
        from core.runtime.runtime_agent_planning_feedback import build_agent_planning_feedback
        from core.runtime.runtime_memory_guided_goal_planner import apply_planning_feedback_to_goal_plan, summarize_goal_plan
        from core.runtime.runtime_natural_language_mission_bootstrap import _goal_plan, interpret_natural_language_mission
        target = prepare_agent_workspace_root(target_root or self.workspace_root, create=False)
        interpretation = interpret_natural_language_mission(natural_language, target_root=target)
        try: context = self._memory_context({"normalized_input": interpretation["normalized_input"], "workspace_root": str(self.workspace_root)})
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError): context = None
        baseline = _goal_plan(interpretation) if interpretation["supported"] else []
        feedback = build_agent_planning_feedback(interpretation["normalized_input"], structured_intents=interpretation["structured_intents"], memory_context=context, workspace_root=self.workspace_root, target_root=target, safety_constraints=["controlled_execution", "path_containment", "operator_approval"], now=now)
        guided = apply_planning_feedback_to_goal_plan(baseline, feedback) if baseline else {"goal_plan": [], "goal_plan_before_feedback": summarize_goal_plan([]), "goal_plan_after_feedback": summarize_goal_plan([]), "applied_recommendations": feedback["applied_recommendations"], "ignored_recommendations": feedback["ignored_recommendations"]}
        return {"entry_id": None, "feedback_id": feedback["feedback_id"], "feedback_fingerprint": feedback["feedback_fingerprint"], "experiences_used": feedback["experience_references"], "matched_tokens": feedback["matched_tokens"], "applied_recommendations": guided["applied_recommendations"], "ignored_recommendations": guided["ignored_recommendations"], "goal_plan_before": guided["goal_plan_before_feedback"], "goal_plan_after": guided["goal_plan_after_feedback"], "added_validations": feedback["recommended_validations"], "risk_notes": feedback["risk_notes"], "scope_preserved": True, "approval_preserved": True, "confidence": feedback["confidence"], "prepare_only": True, "supported": interpretation["supported"]}

    def _memory_context(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        from core.runtime.runtime_activity_memory_query import build_memory_context
        text = str(entry.get("normalized_input") or entry.get("original_input"))
        operations: list[str] = []; targets: list[str] = []
        try:
            from core.runtime.runtime_natural_language_mission_bootstrap import interpret_natural_language_mission
            interpretation = interpret_natural_language_mission(text, target_root=entry.get("target_root") or entry.get("workspace_root") or self.workspace_root)
            operations = [str(item.get("operation")) for item in interpretation.get("structured_intents") or [] if item.get("operation")]
            targets = [str(item.get("path")) for item in interpretation.get("structured_intents") or [] if item.get("path")]
        except (OSError, ValueError, TypeError):
            pass
        return build_memory_context(self.load_memory(), text, operation_types=operations, target_paths=targets, workspace_context=str(entry.get("workspace_root")), top_k=3)

    def reflect(self, entry_id: str, *, rebuild: bool = False, now: Any = None) -> dict[str, Any]:
        entry = self.show(entry_id)
        if entry.get("status") not in {"completed", "blocked", "failed", "cancelled"}: raise ValueError("terminal_entry_required_for_reflection")
        from core.agent.runtime_mission_reflection import build_mission_reflection, load_reflection, save_reflection
        from core.runtime.runtime_memory_model import build_runtime_activity_experience
        mission = {}; session = {}; artifact = {}
        if entry.get("bootstrap_artifact_path"):
            path = Path(entry["bootstrap_artifact_path"])
            if path.exists():
                artifact = json.loads(path.read_text(encoding="utf-8-sig")); claimed = artifact.get("artifact_fingerprint"); unsigned = deepcopy(artifact); unsigned.pop("artifact_fingerprint", None)
                if claimed != fingerprint(unsigned): raise ValueError("bootstrap_artifact_fingerprint_mismatch")
                mission_ref = _mapping(artifact.get("mission_reference")); session_ref = _mapping(artifact.get("session_reference"))
                if mission_ref.get("mission_id") and mission_ref.get("mission_id") != entry.get("mission_id"): raise ValueError("reflection_mission_identity_mismatch")
                if session_ref.get("session_id") and session_ref.get("session_id") != entry.get("mission_session_id"): raise ValueError("reflection_session_identity_mismatch")
                if mission_ref.get("path"):
                    from core.runtime.runtime_mission_model import load_mission
                    mission = load_mission(mission_ref["path"], check_expiry=False)
                if session_ref.get("path"):
                    from core.runtime.runtime_mission_session import load_mission_session_state
                    session = load_mission_session_state(session_ref["path"])
        reflection = build_mission_reflection(entry, agent_id=self.load_state()["agent_id"], mission=mission, session=session, artifact=artifact, now=entry.get("memory_recorded_at") or now)
        reflection_path = self.reflection_root / f"{reflection['reflection_id']}.json"
        if reflection_path.exists():
            try:
                existing = load_reflection(reflection_path)
                if existing.get("entry_id") != entry_id or existing.get("mission_id") != entry.get("mission_id"): raise ValueError("reflection_identity_mismatch")
                reflection = existing
            except ValueError:
                if not rebuild: raise
                reflection = save_reflection(reflection, reflection_path)
        else: reflection = save_reflection(reflection, reflection_path)
        experience, created = self.load_memory().record_experience(build_runtime_activity_experience(reflection, entry=entry, artifact=artifact, reflection_path=reflection_path))
        updated = self._update_entry_metadata(entry_id, {"reflection_id": reflection["reflection_id"], "reflection_path": str(reflection_path.resolve()), "experience_id": experience["experience_id"], "memory_recorded_at": entry.get("memory_recorded_at") or time_text(now), "reflection_status": "completed", "reflection_error": None}, now=now)
        state = self.load_state(); last_result = _mapping(state.get("last_result")); last_result["reflection_reference"] = {"reflection_id": reflection["reflection_id"], "experience_id": experience["experience_id"]}
        self.refresh_state(now=now, last_result=last_result, last_reflection={"reflection_id": reflection["reflection_id"], "path": str(reflection_path.resolve())}, last_experience_id=experience["experience_id"])
        self._publish("agent.entry.reflection_created", entry=updated, suffix=reflection["reflection_id"], payload_extra={"reflection_id": reflection["reflection_id"], "experience_id": experience["experience_id"], "idempotency_key": reflection["idempotency_key"]}, now=now)
        self._publish("agent.entry.experience_recorded", entry=updated, suffix=experience["experience_id"], payload_extra={"reflection_id": reflection["reflection_id"], "experience_id": experience["experience_id"]}, now=now)
        return {"reflection": reflection, "experience": experience, "created": created}

    def _reflect_terminal_safely(self, entry_id: str, *, now: Any = None) -> dict[str, Any]:
        try:
            self.reflect(entry_id, now=now)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            entry = self._update_entry_metadata(entry_id, {"reflection_status": "blocked" if "identity" in str(exc) or "fingerprint" in str(exc) else "failed", "reflection_error": {"reasons": [str(exc)]}}, now=now)
            self._publish("agent.entry.reflection_failed", entry=entry, suffix=fingerprint(str(exc))[:12], payload_extra={"error": str(exc)}, now=now)
        return self.show(entry_id)

    def _reflection_complete(self, entry: Mapping[str, Any]) -> bool:
        if entry.get("reflection_status") != "completed" or not entry.get("reflection_path") or not Path(entry["reflection_path"]).is_file(): return False
        try: return any(record.get("reflection_id") == entry.get("reflection_id") for record in self.load_memory().experience_records())
        except (OSError, ValueError): return False

    def priority(self, entry_id: str, priority: str, *, now: Any = None) -> dict[str, Any]:
        inbox, entry = reprioritize_mission_entry(self.load_inbox(), entry_id, priority, now=now); save_mission_inbox(inbox, self.inbox_path); self.refresh_state(now=now); return entry

    def cancel(self, entry_id: str, *, now: Any = None) -> dict[str, Any]:
        current = self.show(entry_id)
        if current.get("bootstrap_artifact_path"):
            path = Path(current["bootstrap_artifact_path"]); raw = json.loads(path.read_text(encoding="utf-8-sig")); mission_ref = _mapping(raw.get("mission_reference"))
            if mission_ref.get("path"):
                from core.runtime.runtime_mission_model import load_mission
                from core.runtime.runtime_mission_orchestrator import cancel_mission
                mission = load_mission(mission_ref["path"], check_expiry=False)
                cancel_mission(mission, operator_id=self.load_state()["agent_id"], now=now)
        inbox, entry = cancel_mission_entry(self.load_inbox(), entry_id, now=now); save_mission_inbox(inbox, self.inbox_path); self.refresh_state(now=now); self._publish("agent.entry.cancelled", entry=entry, now=now); return self._reflect_terminal_safely(entry_id, now=now)

    def claim_next(self, *, now: Any = None) -> dict[str, Any] | None:
        state = self.load_state(); inbox, entry = claim_next_mission_entry(self.load_inbox(), agent_id=state["agent_id"], now=now)
        if entry is None: return None
        save_mission_inbox(inbox, self.inbox_path); self.refresh_state(now=now, current_entry_id=entry["entry_id"], current_mission_id=entry.get("mission_id"), current_session_id=entry.get("mission_session_id"), missions_started=state["missions_started"] + 1); self._publish("agent.entry.selected", entry=entry, suffix=entry["claim_token"], now=now); return entry

    def _set_entry(self, entry_id: str, status: str, *, result: Any = None, failure: Any = None, extra: Mapping[str, Any] | None = None, now: Any = None) -> dict[str, Any]:
        old = self.show(entry_id); updates = _mapping(extra); updates.update(last_result=deepcopy(result), failure=deepcopy(failure))
        inbox, entry = update_mission_entry(self.load_inbox(), entry_id, status=status, updates=updates, now=now); save_mission_inbox(inbox, self.inbox_path)
        state = self.load_state(); counters = {}
        if old["status"] != status:
            if status == "completed": counters["missions_completed"] = state["missions_completed"] + 1
            elif status == "blocked": counters["missions_blocked"] = state["missions_blocked"] + 1
            elif status == "failed": counters["missions_failed"] = state["missions_failed"] + 1
        self.refresh_state(now=now, current_entry_id=None if status in {"completed", "blocked", "failed", "cancelled", "waiting_for_approval"} else entry_id, current_mission_id=entry.get("mission_id"), current_session_id=entry.get("mission_session_id"), last_result=deepcopy(result), last_error=deepcopy(failure), **counters)
        topic = {"preparing":"agent.entry.prepared", "waiting_for_approval":"agent.entry.waiting_for_approval", "running":"agent.entry.running", "completed":"agent.entry.completed", "blocked":"agent.entry.blocked", "failed":"agent.entry.failed"}.get(status)
        if topic: self._publish(topic, entry=entry, now=now)
        return self._reflect_terminal_safely(entry_id, now=now) if status in {"completed", "blocked", "failed", "cancelled"} else entry

    def _artifact_projection(self, entry: Mapping[str, Any], *, now: Any = None) -> tuple[str, dict[str, Any], dict[str, Any]]:
        path = Path(str(entry.get("bootstrap_artifact_path") or ""))
        if not path.exists(): raise ValueError("bootstrap_artifact_missing")
        raw = json.loads(path.read_text(encoding="utf-8-sig")); claimed = raw.get("artifact_fingerprint"); unsigned = deepcopy(raw); unsigned.pop("artifact_fingerprint", None)
        if claimed != fingerprint(unsigned): raise ValueError("bootstrap_artifact_fingerprint_mismatch")
        mission_ref = _mapping(raw.get("mission_reference")); session_ref = _mapping(raw.get("session_reference"))
        if mission_ref.get("mission_id") != entry.get("mission_id") or session_ref.get("session_id") != entry.get("mission_session_id"): raise ValueError("agent_mission_identity_mismatch")
        from core.runtime.runtime_mission_model import load_mission
        from core.runtime.runtime_mission_session import load_mission_session_state
        mission = load_mission(mission_ref["path"], check_expiry=False); session = load_mission_session_state(session_ref["path"])
        return str(mission.get("mission_status")), mission, session

    def recover(self, *, now: Any = None) -> dict[str, Any]:
        inbox = self.load_inbox(); changed = False
        for item in list_mission_entries(inbox):
            if item["status"] not in {"selected", "preparing", "running", "paused"}: continue
            try:
                if not item.get("bootstrap_artifact_path"):
                    inbox, _ = update_mission_entry(inbox, item["entry_id"], status="pending", updates={"claimed_by": None, "claim_token": None, "claimed_at": None}, now=now)
                else:
                    mission_status, mission, session = self._artifact_projection(item, now=now)
                    projection = project_mission_result({"mission_status": mission_status}, mission=mission, session=session,
                        expected_mission_id=item.get("mission_id"), expected_session_id=item.get("mission_session_id"))
                    status = projection["entry_status"]
                    if status in {"completed", "cancelled"}: inbox, _ = update_mission_entry(inbox, item["entry_id"], status=status, updates={"last_result": mission.get("mission_evidence"), "failure": None}, now=now)
                    elif status == "waiting_for_approval": inbox, _ = update_mission_entry(inbox, item["entry_id"], status=status, updates={"approval_required": True, "approval_status": "pending"}, now=now)
                    elif status in {"blocked", "failed"}: inbox, _ = update_mission_entry(inbox, item["entry_id"], status=status, updates={"failure": mission.get("failure") or {"reasons": [projection["reason"]]}}, now=now)
                    else: inbox, _ = update_mission_entry(inbox, item["entry_id"], status="pending", updates={"claimed_by": None, "claim_token": None, "claimed_at": None}, now=now)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                inbox, _ = update_mission_entry(inbox, item["entry_id"], status="blocked", updates={"failure": {"reasons": [str(exc)]}}, now=now)
            changed = True
        if changed: save_mission_inbox(inbox, self.inbox_path)
        for terminal in list_mission_entries(self.load_inbox()):
            if terminal["status"] in {"completed", "blocked", "failed", "cancelled"} and not self._reflection_complete(terminal): self._reflect_terminal_safely(terminal["entry_id"], now=now)
        inbox = self.load_inbox(); entries = list_mission_entries(inbox); prior = self.load_state()
        state = self.refresh_state(now=now, current_entry_id=None, current_mission_id=None, current_session_id=None,
            missions_started=max(prior["missions_started"], sum(int(item.get("attempt_count") or 0) > 0 for item in entries)),
            missions_completed=max(prior["missions_completed"], sum(item["status"] == "completed" for item in entries)),
            missions_blocked=max(prior["missions_blocked"], sum(item["status"] == "blocked" for item in entries)),
            missions_failed=max(prior["missions_failed"], sum(item["status"] == "failed" for item in entries)))
        return state

    def process_entry(self, entry_id: str, *, max_iterations: int = 20, now: Any = None) -> dict[str, Any]:
        entry = self.show(entry_id)
        if entry["status"] != "selected" or entry.get("claimed_by") != self.load_state()["agent_id"]: raise ValueError("mission_entry_not_claimed_by_agent")
        entry = self._set_entry(entry_id, "preparing", now=now)
        try:
            memory_error = None
            try: memory_context = self._memory_context(entry)
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                memory_error = str(exc); memory_context = {"contract": "zero.runtime.agent_memory_context.v1", "query_text": entry.get("normalized_input"), "experience_references": [], "successful_patterns": [], "failure_patterns": [], "recommended_validations": [], "risk_notes": ["memory_context_unavailable"], "matched_tokens": []}; memory_context["context_fingerprint"] = fingerprint(memory_context)
            entry = self._update_entry_metadata(entry_id, {"memory_context_used": memory_context, "memory_context_error": memory_error}, now=now)
            references = [item.get("experience_id") for item in memory_context.get("experience_references") or []]
            self._publish("agent.entry.memory_context_loaded", entry=entry, suffix=memory_context["context_fingerprint"], payload_extra={"matched_experience_ids": references, "context_fingerprint": memory_context["context_fingerprint"]}, now=now)
            entry = self._set_entry(entry_id, "running", now=now)
            if entry.get("bootstrap_artifact_path"):
                mission_status, mission, session = self._artifact_projection(entry, now=now)
                if mission_status not in {"completed", "waiting_for_plan_confirmation", "waiting_for_operator", "blocked", "failed", "cancelled", "expired"}:
                    from core.runtime.runtime_natural_language_mission_bootstrap import NaturalLanguageMissionBootstrap
                    NaturalLanguageMissionBootstrap().resume(entry["mission_session_id"], workspace_root=entry["workspace_root"], max_iterations=max_iterations, now=now)
                    mission_status, mission, session = self._artifact_projection(entry, now=now)
                result = {"mission_status": mission_status, "session_status": session.get("session_status"), "mission_evidence": mission.get("mission_evidence")}
            else:
                from core.runtime.runtime_natural_language_mission_bootstrap import NaturalLanguageMissionBootstrap
                result = NaturalLanguageMissionBootstrap().run(entry["original_input"], workspace_root=entry["workspace_root"], target_root=entry["target_root"], operator_id=self.load_state()["agent_id"], memory_context=memory_context, max_iterations=max_iterations, now=now)
                mission_ref = _mapping(result.get("mission_reference")); session_ref = _mapping(result.get("session_reference")); plan_ref = _mapping(result.get("execution_plan_reference"))
                feedback_ref = _mapping(result.get("planning_feedback_reference"))
                planning_updates = {"planning_feedback_id": feedback_ref.get("feedback_id"), "planning_feedback_path": feedback_ref.get("path"), "planning_feedback_fingerprint": feedback_ref.get("fingerprint"), "memory_recommendations_applied": deepcopy(result.get("applied_recommendations") or []), "memory_recommendations_ignored": deepcopy(result.get("ignored_recommendations") or []), "planning_feedback_status": result.get("planning_feedback_status"), "planning_feedback_error": result.get("planning_feedback_error")}
                entry = self._set_entry(entry_id, "running", result=result, extra={"mission_id": mission_ref.get("mission_id"), "mission_session_id": session_ref.get("session_id"), "bootstrap_artifact_path": result.get("artifact_path"), "execution_plan_path": plan_ref.get("path"), "approval_required": result.get("approval_required"), "approval_status": result.get("approval_status"), **planning_updates}, now=now)
                event_extra = {"feedback_id": feedback_ref.get("feedback_id"), "experience_ids": references, "applied_count": len(planning_updates["memory_recommendations_applied"]), "ignored_count": len(planning_updates["memory_recommendations_ignored"]), "idempotency_key": feedback_ref.get("fingerprint")}
                if result.get("planning_feedback_status") == "failed":
                    self._publish("agent.entry.planning_feedback_failed", entry=entry, suffix=str(feedback_ref.get("feedback_id") or fingerprint(str(result.get("planning_feedback_error")))[:12]), payload_extra=event_extra, now=now)
                else:
                    self._publish("agent.entry.planning_feedback_created", entry=entry, suffix=str(feedback_ref.get("feedback_id")), payload_extra=event_extra, now=now)
                    self._publish("agent.entry.planning_feedback_applied", entry=entry, suffix=str(feedback_ref.get("feedback_id")), payload_extra=event_extra, now=now)
                    if planning_updates["memory_recommendations_ignored"]: self._publish("agent.entry.planning_feedback_ignored", entry=entry, suffix=str(feedback_ref.get("feedback_id")), payload_extra=event_extra, now=now)
            current = self.show(entry_id)
            _, mission, session = self._artifact_projection(current, now=now)
            projection = project_mission_result(result, mission=mission, session=session,
                expected_mission_id=current.get("mission_id"), expected_session_id=current.get("mission_session_id"))
            status = projection["entry_status"]
            if status == "completed": return self._set_entry(entry_id, status, result=result, failure=None, now=now)
            if status == "waiting_for_approval": return self._set_entry(entry_id, status, result=result, failure=None, extra={"approval_required": True, "approval_status": "pending"}, now=now)
            if status == "cancelled": return self._set_entry(entry_id, status, result=result, failure={"reasons": [projection["reason"]]}, now=now)
            if status in {"blocked", "failed"}: return self._set_entry(entry_id, status, result=result, failure=result.get("failure") or {"reasons": [projection["reason"]]}, now=now)
            return self._set_entry(entry_id, "running", result=result, failure=None, now=now)
        except OSError as exc:
            current = self.show(entry_id); retry = current["attempt_count"] < current["max_attempts"]
            return self._set_entry(entry_id, "pending" if retry else "failed", failure={"reasons": [str(exc)], "retryable": retry}, now=now)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self._set_entry(entry_id, "blocked", failure={"reasons": [str(exc)]}, now=now)
        except Exception as exc:
            return self._set_entry(entry_id, "failed", failure={"reasons": [f"{type(exc).__name__}:{exc}"], "critical": True}, now=now)

    def approve(self, entry_id: str, *, operator_id: str, deny: bool = False, reason: str = "", now: Any = None) -> dict[str, Any]:
        entry = self.show(entry_id)
        if entry["status"] != "waiting_for_approval": raise ValueError("mission_entry_not_waiting_for_approval")
        from core.runtime.runtime_mission_execution_approval_flow import execute_approved_mission, review_mission_execution_plan
        approval = review_mission_execution_plan(entry["bootstrap_artifact_path"], decision="deny" if deny else "approve", operator_id=operator_id, reason=reason, now=now)
        if deny: return self._set_entry(entry_id, "blocked", result=approval, failure={"reasons": ["operator_denied"], "approval_id": approval.get("approval_id")}, extra={"approval_status": "denied"}, now=now)
        result = execute_approved_mission(entry["bootstrap_artifact_path"], operator_id=operator_id, max_iterations=20, now=now)
        _, mission, session = self._artifact_projection(entry, now=now)
        projection = project_mission_result(result, mission=mission, session=session,
            expected_mission_id=entry.get("mission_id"), expected_session_id=entry.get("mission_session_id"))
        status = projection["entry_status"]
        return self._set_entry(entry_id, status, result=result, failure=None if status == "completed" else {"reasons": [projection["reason"]]}, extra={"approval_status": "approved"}, now=now)

    def pause(self, *, now: Any = None) -> dict[str, Any]:
        state = self.refresh_state(now=now, agent_status="paused", pause_requested=True); self._publish("agent.paused", suffix=str(state["loop_iteration"]), now=now); return state
    def resume(self, *, now: Any = None) -> dict[str, Any]:
        state = self.refresh_state(now=now, agent_status="idle", pause_requested=False, stop_requested=False); self._publish("agent.resumed", suffix=str(state["loop_iteration"]), now=now); return state
    def stop(self, *, now: Any = None) -> dict[str, Any]:
        state = self.refresh_state(now=now, agent_status="stopped", stop_requested=True, completed_at=time_text(now)); self._publish("agent.stop_requested", suffix=str(state["loop_iteration"]), now=now); self._publish("agent.stopped", suffix=str(state["loop_iteration"]), now=now); return state


__all__ = ["CONTRACT", "RuntimeAgentController", "STATUSES", "default_agent_state_root", "load_agent_state", "prepare_agent_workspace_root", "project_mission_result", "save_agent_state", "seal_agent_state", "validate_agent_state"]
