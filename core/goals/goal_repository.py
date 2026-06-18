from __future__ import annotations

"""Append-only JSONL persistence for passive goal progress records."""

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from core.goals.goal_contract import GOAL_EVENT_SCHEMA, clean_required_text, clean_status
from core.goals.goal_progress import GoalProgress, GoalResumePoint
from core.goals.goal_state_machine import GoalStateMachine
from core.goals.goal_transition import GoalTransition
from core.goals.goal_completion_authority import GoalCompletionResult, is_accepted_goal_completion_result
from core.goals.persistent_goal import PersistentGoal, PersistentSubgoal, utc_now


class GoalRepository:
    def __init__(
        self,
        repo_root: str | Path,
        *,
        storage_path: str | Path | None = None,
        state_machine: GoalStateMachine | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.state_machine = state_machine or GoalStateMachine()
        self.storage_path = Path(storage_path) if storage_path is not None else Path("runtime/goals/goals.jsonl")
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    def append_goal(self, goal: PersistentGoal | Mapping[str, Any]) -> dict[str, Any]:
        record = goal.to_dict() if isinstance(goal, PersistentGoal) else PersistentGoal.from_mapping(goal).to_dict()
        if self.get_goal(record["goal_id"]) is not None:
            raise ValueError(f"goal_already_exists:{record['goal_id']}")
        return self._append("goal_appended", record)

    def append_subgoal(self, subgoal: PersistentSubgoal | Mapping[str, Any]) -> dict[str, Any]:
        record = subgoal.to_dict() if isinstance(subgoal, PersistentSubgoal) else PersistentSubgoal.from_mapping(subgoal).to_dict()
        if self.get_goal(record["goal_id"]) is None:
            raise KeyError(record["goal_id"])
        if self.get_subgoal(record["subgoal_id"]) is not None:
            raise ValueError(f"subgoal_already_exists:{record['subgoal_id']}")
        return self._append("subgoal_appended", record)

    def update_goal_status(
        self,
        goal_id: str,
        status: str,
        *,
        evidence_refs: list[Any] | None = None,
        reason: str | None = None,
        resume_point: Any = None,
        action: str | None = None,
        completion_attestation: GoalCompletionResult | None = None,
    ) -> dict[str, Any]:
        existing = self.get_goal(goal_id)
        if existing is None:
            raise KeyError(clean_required_text(goal_id, "goal_id"))
        target_status = clean_status(status)
        if target_status == "completed" and (
            not is_accepted_goal_completion_result(completion_attestation, goal_id=goal_id)
        ):
            raise ValueError("canonical_completion_attestation_required")
        if target_status != "completed":
            self._validate_transition(
                GoalTransition(
                    "goal",
                    goal_id,
                    existing["status"],
                    target_status,
                    action or self._infer_action(target_status),
                    reason,
                    resume_point,
                    evidence_refs if evidence_refs is not None else existing.get("evidence_refs") or [],
                ),
                all_subgoals_completed=self._all_subgoals_completed(goal_id),
            )
        existing["status"] = target_status
        existing["updated_at"] = utc_now()
        if evidence_refs is not None:
            existing["evidence_refs"] = copy.deepcopy(evidence_refs)
        return self._append("goal_status_updated", PersistentGoal.from_mapping(existing).to_dict())

    def update_subgoal_status(
        self,
        subgoal_id: str,
        status: str,
        *,
        progress: float | None = None,
        blocked_reason: str | None = None,
        resume_point: Any = None,
        evidence_refs: list[Any] | None = None,
        reason: str | None = None,
        action: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_subgoal(subgoal_id)
        if existing is None:
            raise KeyError(clean_required_text(subgoal_id, "subgoal_id"))
        target_status = clean_status(status)
        self._validate_transition(
            GoalTransition(
                "subgoal",
                subgoal_id,
                existing["status"],
                target_status,
                action or self._infer_action(target_status),
                reason or blocked_reason,
                resume_point if resume_point is not None else existing.get("resume_point"),
                evidence_refs if evidence_refs is not None else existing.get("evidence_refs") or [],
            )
        )
        existing["status"] = target_status
        existing["updated_at"] = utc_now()
        if progress is not None:
            existing["progress"] = progress
        if blocked_reason is not None:
            existing["blocked_reason"] = blocked_reason
        if resume_point is not None:
            existing["resume_point"] = (
                resume_point.to_dict() if isinstance(resume_point, GoalResumePoint) else copy.deepcopy(resume_point)
            )
        if evidence_refs is not None:
            existing["evidence_refs"] = copy.deepcopy(evidence_refs)
        return self._append("subgoal_status_updated", PersistentSubgoal.from_mapping(existing).to_dict())

    def record_progress(self, progress: GoalProgress | Mapping[str, Any]) -> dict[str, Any]:
        incoming = progress.to_dict() if isinstance(progress, GoalProgress) else GoalProgress.from_mapping(progress).to_dict()
        if self.get_goal(incoming["goal_id"]) is None:
            raise KeyError(incoming["goal_id"])
        previous = self.get_progress(incoming["goal_id"])
        if previous is not None:
            incoming["completed_subgoals"] = self._union(
                previous.get("completed_subgoals"), incoming.get("completed_subgoals")
            )
            incoming["blocked_subgoals"] = self._union(
                previous.get("blocked_subgoals"), incoming.get("blocked_subgoals")
            )
            if incoming.get("resume_point") is None:
                incoming["resume_point"] = copy.deepcopy(previous.get("resume_point"))
        incoming["updated_at"] = utc_now()
        return self._append("progress_recorded", GoalProgress.from_mapping(incoming).to_dict())

    def list_goals(self) -> list[dict[str, Any]]:
        state = self._replay()
        return sorted(
            (copy.deepcopy(value) for value in state["goals"].values()),
            key=lambda item: (str(item.get("created_at") or ""), str(item.get("goal_id") or "")),
        )

    def list_subgoals(self, goal_id: str) -> list[dict[str, Any]]:
        target = clean_required_text(goal_id, "goal_id")
        state = self._replay()
        return sorted(
            (
                copy.deepcopy(value)
                for value in state["subgoals"].values()
                if value.get("goal_id") == target
            ),
            key=lambda item: (int(item.get("order") or 0), str(item.get("subgoal_id") or "")),
        )

    def get_goal(self, goal_id: str) -> dict[str, Any] | None:
        value = self._replay()["goals"].get(clean_required_text(goal_id, "goal_id"))
        return copy.deepcopy(value) if value is not None else None

    def get_subgoal(self, subgoal_id: str) -> dict[str, Any] | None:
        value = self._replay()["subgoals"].get(clean_required_text(subgoal_id, "subgoal_id"))
        return copy.deepcopy(value) if value is not None else None

    def get_progress(self, goal_id: str) -> dict[str, Any] | None:
        value = self._replay()["progress"].get(clean_required_text(goal_id, "goal_id"))
        return copy.deepcopy(value) if value is not None else None

    def get_resume_point(self, goal_id: str) -> dict[str, Any] | None:
        progress = self.get_progress(goal_id)
        if progress is not None and isinstance(progress.get("resume_point"), Mapping):
            return copy.deepcopy(dict(progress["resume_point"]))
        candidates = [
            subgoal.get("resume_point")
            for subgoal in self.list_subgoals(goal_id)
            if isinstance(subgoal.get("resume_point"), Mapping)
        ]
        return copy.deepcopy(dict(candidates[0])) if candidates else None

    def list_history(self, goal_id: str | None = None) -> list[dict[str, Any]]:
        target = clean_required_text(goal_id, "goal_id") if goal_id is not None else None
        events = self._load_events()
        if target is None:
            return events
        return [event for event in events if event["payload"].get("goal_id") == target]

    def get_orchestration_snapshot(self, goal_id: str) -> dict[str, Any]:
        target = clean_required_text(goal_id, "goal_id")
        return {
            "goal": self.get_goal(target),
            "subgoals": self.list_subgoals(target),
            "progress": self.get_progress(target),
            "resume_point": self.get_resume_point(target),
        }

    def _append(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = copy.deepcopy(dict(payload))
        event = {
            "schema": GOAL_EVENT_SCHEMA,
            "event_type": event_type,
            "recorded_at": utc_now(),
            "payload": record,
        }
        try:
            encoded = json.dumps(event, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("goal_record_must_be_json_serializable") from exc
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("a", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
        return copy.deepcopy(record)

    def _load_events(self) -> list[dict[str, Any]]:
        if not self.storage_path.is_file():
            return []
        events: list[dict[str, Any]] = []
        with self.storage_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid_goal_jsonl_line:{line_number}") from exc
                if not isinstance(event, Mapping) or not isinstance(event.get("payload"), Mapping):
                    raise ValueError(f"invalid_goal_event_line:{line_number}")
                events.append(copy.deepcopy(dict(event)))
        return events

    def _replay(self) -> dict[str, dict[str, dict[str, Any]]]:
        state: dict[str, dict[str, dict[str, Any]]] = {"goals": {}, "subgoals": {}, "progress": {}}
        for event in self._load_events():
            payload = event["payload"]
            record_type = payload.get("record_type")
            if record_type == "goal":
                record = PersistentGoal.from_mapping(payload).to_dict()
                state["goals"][record["goal_id"]] = record
            elif record_type == "subgoal":
                record = PersistentSubgoal.from_mapping(payload).to_dict()
                state["subgoals"][record["subgoal_id"]] = record
            elif record_type == "progress":
                record = GoalProgress.from_mapping(payload).to_dict()
                state["progress"][record["goal_id"]] = record
        return state

    @staticmethod
    def _union(first: Any, second: Any) -> list[str]:
        result: list[str] = []
        for value in list(first or []) + list(second or []):
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    def _all_subgoals_completed(self, goal_id: str) -> bool:
        subgoals = self.list_subgoals(goal_id)
        return all(item["status"] == "completed" for item in subgoals)

    @staticmethod
    def _infer_action(target_status: str) -> str:
        return {
            "planned": "plan",
            "active": "start",
            "blocked": "block",
            "resumable": "resume_ready",
            "completed": "complete",
            "failed": "fail",
        }.get(target_status, target_status)

    def _validate_transition(
        self,
        transition: GoalTransition,
        *,
        all_subgoals_completed: bool | None = None,
    ) -> None:
        result = self.state_machine.transition(
            transition,
            all_subgoals_completed=all_subgoals_completed,
        )
        if not result.accepted:
            raise ValueError(f"{result.reason}:{result.blocked_reason}")


__all__ = ["GoalRepository"]
