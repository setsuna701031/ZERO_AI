from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

from core.agent.runtime_mission_reflection import load_reflection
from core.runtime.runtime_event_bus import load_event_bus_state, replay
from core.runtime.runtime_memory_model import validate_runtime_activity_experience
from core.runtime.runtime_operator_session import fingerprint

PRIORITY = {name: index for index, name in enumerate(("goal_created", "goal_started", "goal_paused", "goal_resumed", "goal_stopped", "goal_cancelled", "goal_completed", "goal_failed", "goal_blocked", "milestone_ready", "milestone_started", "milestone_waiting_approval", "milestone_approved", "milestone_denied", "milestone_completed", "milestone_failed", "mission_entry_created", "mission_session_created", "mission_recovered", "mission_completed", "replan_requested", "replan_applied", "replan_rejected", "crash_recovery_started", "crash_recovery_completed", "reflection_written", "experience_written"))}
TOPICS = {"long_goal.started": "goal_started", "long_goal.paused": "goal_paused", "long_goal.resumed": "goal_resumed", "long_goal.stop_requested": "goal_stopped", "long_goal.cancelled": "goal_cancelled", "long_goal.completed": "goal_completed", "long_goal.failed": "goal_failed", "long_goal.blocked": "goal_blocked", "long_goal.milestone.ready": "milestone_ready", "long_goal.milestone.completed": "milestone_completed", "long_goal.milestone.failed": "milestone_failed", "long_goal.milestone.waiting_for_approval": "milestone_waiting_approval", "long_goal.replanned": "replan_applied"}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}

def _item(category: str, timestamp: Any, goal_id: str, source_contract: str, source_reference: Any, source_fingerprint: Any, **fields: Any) -> dict[str, Any] | None:
    if category not in PRIORITY or not str(timestamp or "").strip(): return None
    seed = {"category": category, "timestamp": timestamp, "goal_id": goal_id, "source_contract": source_contract, "source_reference": source_reference, **fields}
    return {"event_category": category, "event_identity": f"goal-ops-event-{fingerprint(seed)[:24]}", "source_contract": source_contract, "source_reference": source_reference, "goal_id": goal_id, "milestone_id": fields.get("milestone_id"), "entry_id": fields.get("entry_id"), "mission_id": fields.get("mission_id"), "session_id": fields.get("session_id"), "status": fields.get("status"), "persisted_timestamp": str(timestamp), "summary": fields.get("summary") or category.replace("_", " "), "evidence_references": deepcopy(fields.get("evidence_references") or []), "source_fingerprint": source_fingerprint}

def build_goal_timeline(goal: Mapping[str, Any], sources: Mapping[str, Any], reference_result: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    goal_id = str(goal["goal_id"]); events: list[dict[str, Any]] = []; warnings: list[str] = []
    def add(value: dict[str, Any] | None) -> None:
        if value: events.append(value)
    add(_item("goal_created", goal.get("created_at"), goal_id, str(goal.get("contract")), goal_id, goal.get("goal_fingerprint")))
    for category, timestamp, statuses in (("goal_started", goal.get("started_at"), set()), ("goal_completed", goal.get("completed_at"), {"completed"}), ("goal_failed", goal.get("completed_at") or goal.get("updated_at"), {"failed"}), ("goal_blocked", goal.get("completed_at") or goal.get("updated_at"), {"blocked"}), ("goal_stopped", goal.get("completed_at"), {"stopped"}), ("goal_cancelled", goal.get("completed_at"), {"cancelled"})):
        if (not statuses or goal.get("goal_status") in statuses): add(_item(category, timestamp, goal_id, str(goal.get("contract")), goal_id, goal.get("goal_fingerprint"), status=goal.get("goal_status")))
    for milestone_id in goal.get("milestone_order") or []:
        milestone = _mapping(_mapping(goal.get("milestones")).get(milestone_id)); status = milestone.get("milestone_status"); common = dict(milestone_id=milestone_id, status=status)
        add(_item("milestone_started", milestone.get("started_at"), goal_id, str(milestone.get("contract")), milestone_id, milestone.get("milestone_fingerprint"), **common))
        category = {"ready": "milestone_ready", "waiting_for_approval": "milestone_waiting_approval", "completed": "milestone_completed", "failed": "milestone_failed"}.get(str(status))
        if category: add(_item(category, milestone.get("completed_at") or milestone.get("updated_at"), goal_id, str(milestone.get("contract")), milestone_id, milestone.get("milestone_fingerprint"), **common))
    for chain in reference_result.get("chains") or []:
        base = dict(milestone_id=chain.get("milestone_id"), entry_id=chain.get("entry_id"), mission_id=chain.get("mission_id"), session_id=chain.get("session_id"))
        entry = _mapping(_mapping(sources.get("entries")).get(str(chain.get("entry_id"))))
        add(_item("mission_entry_created", entry.get("created_at"), goal_id, str(entry.get("contract")), chain.get("entry_id"), entry.get("entry_fingerprint"), status=entry.get("status"), **base))
        add(_item("mission_session_created", chain.get("session_created_at"), goal_id, "zero.runtime.mission_session.v1", chain.get("session_id"), chain.get("session_fingerprint"), status=chain.get("session_status"), **base))
        if chain.get("last_recovery_at"): add(_item("mission_recovered", chain.get("last_recovery_at"), goal_id, "zero.runtime.mission_session.v1", chain.get("session_id"), chain.get("session_fingerprint"), status=chain.get("session_status"), **base))
        if chain.get("mission_completed_at"): add(_item("mission_completed", chain.get("mission_completed_at"), goal_id, "zero.runtime.mission.v1", chain.get("mission_id"), chain.get("mission_fingerprint"), status=chain.get("mission_status"), **base))
        approval = _mapping(chain.get("approval")); category = "milestone_approved" if approval.get("status") == "approved" else "milestone_denied" if approval.get("status") in {"denied", "rejected"} else None
        if category: add(_item(category, approval.get("created_at"), goal_id, "zero.runtime.mission_execution_approval.v1", approval.get("approval_id"), approval.get("approval_fingerprint"), status=approval.get("status"), **base))
    for record in goal.get("replan_history") or []:
        add(_item("replan_applied", record.get("created_at"), goal_id, str(goal.get("contract")), f"replan:{record.get('revision')}", fingerprint(record), milestone_id=record.get("affected_milestone_id"), status="applied"))
    reflection_ref = _mapping(goal.get("reflection_reference")); reflection_path = Path(str(reflection_ref.get("path") or ""))
    if reflection_path.is_file():
        try:
            reflection = load_reflection(reflection_path); add(_item("reflection_written", reflection.get("created_at"), goal_id, str(reflection.get("contract")), reflection.get("reflection_id"), reflection.get("reflection_fingerprint"), status=reflection.get("outcome")))
        except ValueError: warnings.append("invalid_reflection_reference")
    experience_id = _mapping(goal.get("experience_reference")).get("experience_id"); memory_path = Path(sources["paths"]["memory"])
    if experience_id and memory_path.is_file():
        for line in memory_path.read_text(encoding="utf-8-sig").splitlines():
            try: record = json.loads(line)
            except json.JSONDecodeError: continue
            if record.get("experience_id") == experience_id:
                if validate_runtime_activity_experience(record): warnings.append("invalid_experience_reference")
                else: add(_item("experience_written", record.get("recorded_at") or record.get("created_at"), goal_id, str(record.get("contract")), experience_id, record.get("experience_fingerprint"), status=record.get("outcome")))
                break
    bus_path = Path(sources["paths"]["event_bus"])
    if bus_path.is_file():
        try:
            bus = load_event_bus_state(bus_path)
            for event in replay(bus):
                payload = _mapping(event.get("payload")); category = TOPICS.get(str(event.get("topic")))
                if category and (payload.get("goal_id") == goal_id or event.get("correlation_id") == goal_id): add(_item(category, event.get("created_at"), goal_id, str(event.get("contract")), event.get("event_id"), event.get("event_fingerprint"), milestone_id=payload.get("milestone_id"), status=payload.get("milestone_status") or payload.get("goal_status")))
        except ValueError: warnings.append("invalid_event_bus_reference")
    unique = {event["event_identity"]: event for event in events}
    return sorted(unique.values(), key=lambda event: (event["persisted_timestamp"], PRIORITY[event["event_category"]], event["event_identity"])), sorted(set(warnings))

__all__ = ["PRIORITY", "build_goal_timeline"]
