from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping

from core.agent.runtime_agent_controller import RuntimeAgentController, default_agent_state_root, prepare_agent_workspace_root
from core.agent.runtime_goal_milestone_planner import plan_goal_milestones
from core.agent.runtime_long_horizon_goal import TERMINAL_GOALS, TERMINAL_MILESTONES, calculate_goal_progress, create_long_horizon_goal, load_long_horizon_goal, save_long_horizon_goal, seal_long_horizon_goal, seal_milestone, stable_milestone_order
from core.agent.runtime_persistent_agent_loop import RuntimePersistentAgentLoop
from core.runtime.runtime_operator_session import fingerprint, time_text


INDEX_CONTRACT = "zero.agent.long_horizon_goal_index.v1"
RUN_RESULT_CONTRACT = "zero.agent.long_horizon_goal_run.v1"


def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class RuntimeGoalController:
    def __init__(self, *, workspace_root: Any, state_root: Any = None, create_workspace: bool = True, now: Any = None):
        self.workspace_root = prepare_agent_workspace_root(workspace_root, create=create_workspace)
        self.agent_state_root = Path(state_root).resolve(strict=False) if state_root is not None else default_agent_state_root(self.workspace_root)
        self.agent = RuntimeAgentController(workspace_root=self.workspace_root, state_root=self.agent_state_root, create_workspace=create_workspace, now=now)
        self.goals_root = self.agent_state_root / "goals"; self.goals_root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.goals_root / "goal-index.json"
        if not self.index_path.exists(): self._save_index({"contract": INDEX_CONTRACT, "goal_ids": [], "goal_references": {}, "created_at": time_text(now), "updated_at": time_text(now)})

    def _seal_index(self, value: Mapping[str, Any]) -> dict[str, Any]:
        result = _mapping(value); result.pop("index_fingerprint", None); result["index_fingerprint"] = fingerprint(result); return result
    def _load_index(self) -> dict[str, Any]:
        try: value = json.loads(self.index_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_long_goal_index_json") from exc
        claimed = value.get("index_fingerprint"); unsigned = _mapping(value); unsigned.pop("index_fingerprint", None)
        if value.get("contract") != INDEX_CONTRACT or claimed != fingerprint(unsigned): raise ValueError("long_goal_index_fingerprint_mismatch")
        return value
    def _save_index(self, value: Mapping[str, Any]) -> dict[str, Any]:
        sealed = self._seal_index(value); self.index_path.parent.mkdir(parents=True, exist_ok=True); temporary = self.index_path.with_name(".goal-index.json.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle: handle.write(json.dumps(sealed, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, self.index_path); return sealed
    def _goal_path(self, goal_id: str) -> Path: return self.goals_root / str(goal_id) / "goal.json"
    def _save(self, goal: Mapping[str, Any]) -> dict[str, Any]: return save_long_horizon_goal(goal, self._goal_path(str(goal["goal_id"])))
    def show(self, goal_id: str) -> dict[str, Any]: return load_long_horizon_goal(self._goal_path(goal_id))
    def list(self, *, status: str | None = None) -> list[dict[str, Any]]:
        index = self._load_index(); values = [self.show(goal_id) for goal_id in index["goal_ids"]]
        return [value for value in values if status is None or value["goal_status"] == status]
    def milestones(self, goal_id: str) -> list[dict[str, Any]]:
        goal = self.show(goal_id); return [_mapping(goal["milestones"][key]) for key in goal["milestone_order"]]

    def runtime_mission_budget(self, requested_limit: int) -> dict[str, Any]:
        return self.agent.runtime_mission_budget(requested_limit)

    def _publish(self, topic: str, goal: Mapping[str, Any], *, milestone: Mapping[str, Any] | None = None, suffix: str = "", now: Any = None) -> None:
        item = _mapping(milestone); entry_ids = list(item.get("mission_entry_ids") or [])
        payload = {"goal_id": goal["goal_id"], "milestone_id": item.get("milestone_id"), "mission_entry_ids": entry_ids, "goal_status": goal.get("goal_status"), "milestone_status": item.get("milestone_status"), "timestamp": time_text(now)}
        self.agent.publish_coordination_event(topic, correlation_id=str(goal["goal_id"]), subject_id=item.get("milestone_id") or str(goal["goal_id"]), payload=payload, suffix=suffix or str(item.get("milestone_status") or goal.get("goal_status") or ""), now=now)

    def _memory_and_feedback(self, goal: Mapping[str, Any], *, now: Any = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
        error = None
        try:
            from core.runtime.runtime_activity_memory_query import build_memory_context
            memory = build_memory_context(self.agent.load_memory(), str(goal["normalized_goal"]), workspace_context=str(goal["workspace_root"]), top_k=3)
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc: memory = None; error = str(exc)
        try:
            from core.runtime.runtime_agent_planning_feedback import build_agent_planning_feedback
            intents = [{"operation": "create_file", "path": "index.html"}, {"operation": "create_file", "path": "styles.css"}] if any(token in str(goal["normalized_goal"]).casefold() for token in ("網站", "website", "static site")) else []
            feedback = build_agent_planning_feedback(str(goal["normalized_goal"]), structured_intents=intents, memory_context=memory, workspace_root=goal["workspace_root"], target_root=goal["target_root"], safety_constraints=list(goal["constraints"]), now=now)
        except (OSError, ValueError, KeyError, TypeError) as exc: feedback = None; error = error or str(exc)
        return memory, feedback, error

    def preview(self, natural_language: str, *, target_root: Any = None, priority: str = "normal", max_replans: int = 3, now: Any = None) -> dict[str, Any]:
        target = prepare_agent_workspace_root(target_root or self.workspace_root, create=False)
        goal = create_long_horizon_goal(natural_language, workspace_root=self.workspace_root, target_root=target, priority=priority, max_replans=max_replans, now=now)
        memory, feedback, error = self._memory_and_feedback(goal, now=now); plan = plan_goal_milestones(goal, memory_context=memory, planning_feedback=feedback, now=now)
        return {"goal": goal, "plan": plan, "memory_feedback_error": error, "prepare_only": True, "target_mutated": False}

    def create(self, natural_language: str, *, target_root: Any = None, priority: str = "normal", max_replans: int = 3, now: Any = None) -> dict[str, Any]:
        target = prepare_agent_workspace_root(target_root or self.workspace_root, create=False)
        goal = create_long_horizon_goal(natural_language, workspace_root=self.workspace_root, target_root=target, priority=priority, max_replans=max_replans, now=now)
        path = self._goal_path(goal["goal_id"])
        if path.exists(): return self.show(goal["goal_id"])
        memory, feedback, error = self._memory_and_feedback(goal, now=now); plan = plan_goal_milestones(goal, memory_context=memory, planning_feedback=feedback, now=now)
        goal["milestones"] = plan["milestones"]; goal["milestone_order"] = plan["milestone_order"]; goal["memory_context_reference"] = _mapping(memory).get("context_fingerprint"); goal["planning_feedback_reference"] = _mapping(feedback).get("feedback_id"); goal["memory_feedback_error"] = error
        if not plan["supported"]: goal["goal_status"] = "blocked"; goal["failure"] = {"reasons": [plan["reason"]]}; goal["manual_review_required"] = True
        else: goal["goal_status"] = "ready"
        goal = self._refresh(goal, now=now, touch=True); saved = self._save(goal)
        index = self._load_index(); index["goal_ids"] = list(index["goal_ids"]) + [goal["goal_id"]]; index["goal_references"][goal["goal_id"]] = str(path.resolve()); index["updated_at"] = time_text(now); self._save_index(index)
        self._publish("long_goal.created", saved, now=now); self._publish("long_goal.planned", saved, now=now)
        if saved["goal_status"] == "blocked": self._publish("long_goal.blocked", saved, now=now); self._record_terminal_experience(saved, now=now)
        return self.show(goal["goal_id"])

    def _refresh(self, goal: Mapping[str, Any], *, now: Any = None, touch: bool = True) -> dict[str, Any]:
        value = _mapping(goal); milestones = _mapping(value.get("milestones")); order = list(value.get("milestone_order") or [])
        progress = calculate_goal_progress(milestones, order); value["progress"] = progress; value["current_milestone_id"] = progress["current_milestone_id"]
        if order and len(progress["completed_milestones"]) == len(order):
            value["goal_status"] = "completed"; value["completed_at"] = value.get("completed_at") or time_text(now); value["failure"] = None
            value["completion_evidence"] = [{"milestone_id": key, "mission_entry_ids": list(_mapping(milestones[key]).get("mission_entry_ids") or []), "evidence_requirements": list(_mapping(milestones[key]).get("evidence_requirements") or [])} for key in order]
        elif value.get("goal_status") in {"cancelled", "stopped"}: pass
        elif value.get("pause_requested"): value["goal_status"] = "paused"
        elif value.get("stop_requested"): value["goal_status"] = "stopped"
        elif progress["waiting_approval_milestones"]: value["goal_status"] = "waiting_for_approval"
        elif progress["failed_milestones"]: value["goal_status"] = "failed"
        elif progress["blocked_milestones"]: value["goal_status"] = "blocked"
        elif progress["completed_milestones"]: value["goal_status"] = "partially_completed" if not progress["running_milestones"] else "running"
        elif order: value["goal_status"] = "ready" if not progress["running_milestones"] else "running"
        if touch: value["updated_at"] = time_text(now)
        return seal_long_horizon_goal(value)

    def _set_milestone(self, goal: dict[str, Any], milestone_id: str, **updates: Any) -> dict[str, Any]:
        milestone = _mapping(goal["milestones"][milestone_id]); milestone.update(deepcopy(updates)); goal["milestones"][milestone_id] = seal_milestone(milestone); return goal

    def _generate(self, goal: dict[str, Any], milestone_id: str, *, now: Any = None) -> tuple[dict[str, Any], list[str]]:
        milestone = _mapping(goal["milestones"][milestone_id])
        if milestone["milestone_status"] == "completed" or milestone["mission_entry_ids"]: return goal, []
        if not all(_mapping(goal["milestones"][dep]).get("milestone_status") == "completed" for dep in milestone["dependencies"]): return goal, []
        milestone["milestone_status"] = "generating_missions"; milestone["started_at"] = milestone.get("started_at") or time_text(now); milestone["updated_at"] = time_text(now); goal["milestones"][milestone_id] = seal_milestone(milestone); self._save(self._refresh(goal, now=now))
        if not milestone["mission_templates"]:
            milestone["milestone_status"] = "completed"; milestone["completed_at"] = time_text(now); milestone["updated_at"] = time_text(now); milestone["reflection_references"] = [{"type": "orchestration_checkpoint", "fingerprint": fingerprint({"goal": goal["goal_id"], "milestone": milestone_id})}]
            goal["milestones"][milestone_id] = seal_milestone(milestone); self._publish("long_goal.milestone.completed", goal, milestone=milestone, now=now); return goal, []
        ids = []
        for template in milestone["mission_templates"]:
            template_id = template["mission_template_id"]; input_id = fingerprint({"goal_id": goal["goal_id"], "milestone_id": milestone_id, "mission_template_id": template_id, "plan_revision": milestone.get("plan_revision", 1)})
            entry = self.agent.add(template["natural_language"], priority=goal["priority"], target_root=goal["target_root"], tags=["long_horizon_goal", goal["goal_id"], milestone_id], max_attempts=milestone["max_attempts"], input_id=input_id, now=now)
            entry = self.agent._update_entry_metadata(entry["entry_id"], {"goal_id": goal["goal_id"], "milestone_id": milestone_id, "mission_template_id": template_id, "parent_goal_reference": str(self._goal_path(goal["goal_id"])), "parent_milestone_reference": {"goal_id": goal["goal_id"], "milestone_id": milestone_id}, "source": "long_horizon_goal", "long_goal_plan_revision": milestone.get("plan_revision", 1)}, now=now)
            ids.append(entry["entry_id"])
            if not any(ref.get("entry_id") == entry["entry_id"] for ref in goal["mission_entry_references"]): goal["mission_entry_references"].append({"entry_id": entry["entry_id"], "milestone_id": milestone_id, "mission_template_id": template_id, "plan_revision": milestone.get("plan_revision", 1)})
        milestone["mission_entry_ids"] = ids; milestone["milestone_status"] = "waiting_for_missions"; milestone["updated_at"] = time_text(now); goal["milestones"][milestone_id] = seal_milestone(milestone)
        self._publish("long_goal.milestone.started", goal, milestone=milestone, now=now); return goal, ids

    def project(self, goal_id: str, *, now: Any = None) -> dict[str, Any]:
        goal = self.show(goal_id)
        if goal["goal_status"] == "completed": return goal
        for milestone_id in goal["milestone_order"]:
            milestone = _mapping(goal["milestones"][milestone_id]); ids = list(milestone.get("mission_entry_ids") or [])
            if not ids: continue
            entries = []
            try:
                for entry_id in ids:
                    entry = self.agent.show(entry_id)
                    if entry.get("goal_id") != goal_id or entry.get("milestone_id") != milestone_id: raise ValueError("long_goal_mission_identity_mismatch")
                    entries.append(entry)
            except ValueError as exc:
                milestone.update(milestone_status="blocked", failure={"reasons": [str(exc)]}, updated_at=time_text(now)); goal["milestones"][milestone_id] = seal_milestone(milestone); self._publish("long_goal.milestone.blocked", goal, milestone=milestone, now=now); continue
            statuses = {entry["status"] for entry in entries}; projected = _mapping(milestone.get("projected_entry_states")); newly_failed = [entry for entry in entries if entry["status"] == "failed" and projected.get(entry["entry_id"]) != "failed"]
            for entry in entries: projected[entry["entry_id"]] = entry["status"]
            milestone["projected_entry_states"] = projected; milestone["reflection_references"] = [{"entry_id": entry["entry_id"], "reflection_id": entry.get("reflection_id")} for entry in entries if entry.get("reflection_id")]; milestone["experience_references"] = [{"entry_id": entry["entry_id"], "experience_id": entry.get("experience_id")} for entry in entries if entry.get("experience_id")]
            if statuses == {"completed"}: milestone["milestone_status"] = "completed"; milestone["completed_at"] = milestone.get("completed_at") or time_text(now); milestone["failure"] = None; topic = "long_goal.milestone.completed"
            elif "waiting_for_approval" in statuses: milestone["milestone_status"] = "waiting_for_approval"; topic = "long_goal.milestone.waiting_for_approval"
            elif "failed" in statuses: milestone["attempt_count"] += len(newly_failed); milestone["milestone_status"] = "failed"; milestone["failure"] = {"reasons": ["mission_entry_failed"], "entry_ids": [entry["entry_id"] for entry in entries if entry["status"] == "failed"]}; topic = "long_goal.milestone.failed"
            elif "blocked" in statuses: milestone["milestone_status"] = "blocked"; milestone["failure"] = {"reasons": ["mission_entry_blocked"], "entry_ids": [entry["entry_id"] for entry in entries if entry["status"] == "blocked"]}; topic = "long_goal.milestone.blocked"
            elif "cancelled" in statuses: milestone["milestone_status"] = "cancelled"; topic = "long_goal.milestone.blocked"
            elif statuses.intersection({"selected", "preparing", "running"}): milestone["milestone_status"] = "running"; topic = None
            else: milestone["milestone_status"] = "waiting_for_missions"; topic = None
            milestone["updated_at"] = time_text(now); goal["milestones"][milestone_id] = seal_milestone(milestone)
            if topic: self._publish(topic, goal, milestone=milestone, now=now)
        before = goal["goal_status"]; goal = self._refresh(goal, now=now); saved = self._save(goal)
        if saved["goal_status"] != before:
            topic = {"waiting_for_approval": "long_goal.waiting_for_approval", "completed": "long_goal.completed", "blocked": "long_goal.blocked", "failed": "long_goal.failed"}.get(saved["goal_status"])
            if topic: self._publish(topic, saved, now=now)
        if saved["goal_status"] in {"completed", "blocked", "failed"}: self._record_terminal_experience(saved, now=now)
        return self.show(goal_id)

    def recover(self, goal_id: str, *, now: Any = None) -> dict[str, Any]:
        goal = self.show(goal_id)
        if goal["goal_status"] == "completed": return goal
        self.agent.recover(now=now)
        for milestone_id in goal["milestone_order"]:
            milestone = _mapping(goal["milestones"][milestone_id])
            if milestone["milestone_status"] == "generating_missions" and not milestone["mission_entry_ids"]: milestone["milestone_status"] = "ready"; milestone["updated_at"] = time_text(now); goal["milestones"][milestone_id] = seal_milestone(milestone)
        self._save(self._refresh(goal, now=now)); return self.project(goal_id, now=now)

    def run(self, goal_id: str, *, max_milestones: int = 1, max_missions: int = 10, max_iterations: int = 20, stop_on_blocked: bool = False, stop_on_failed: bool = False, idle_exit: bool = True, wait_seconds: float = 0.0, now: Any = None) -> dict[str, Any]:
        for value, name in ((max_milestones, "max_milestones"), (max_missions, "max_missions"), (max_iterations, "max_iterations")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1: raise ValueError(f"invalid_goal_{name}")
        if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, (int, float)) or not 0 <= wait_seconds <= 60: raise ValueError("invalid_goal_wait_seconds")
        goal = self.show(goal_id)
        if goal["goal_status"] in TERMINAL_GOALS: return self._result(goal, [], "terminal")
        if goal.get("pause_requested"): return self._result(goal, [], "pause_requested")
        goal = self.recover(goal_id, now=now); generated: list[str] = []; processed: list[str] = []; stopped = "idle"
        if not goal.get("started_at"): goal["started_at"] = time_text(now); goal["goal_status"] = "running"; goal["updated_at"] = time_text(now); goal = self._save(goal); self._publish("long_goal.started", goal, now=now)
        for iteration in range(max_iterations):
            goal = self.project(goal_id, now=now)
            if goal["goal_status"] in TERMINAL_GOALS or goal["goal_status"] == "waiting_for_approval": stopped = goal["goal_status"]; break
            ready = list(goal["progress"]["next_ready_milestone_ids"])
            if not ready:
                pending_existing = []
                for reference in goal.get("mission_entry_references") or []:
                    try:
                        if self.agent.show(reference["entry_id"])["status"] == "pending": pending_existing.append(reference["entry_id"])
                    except ValueError: continue
                if pending_existing:
                    agent_result = RuntimePersistentAgentLoop(self.agent).run(max_missions=min(max_missions, len(pending_existing)), max_iterations=max_iterations, stop_on_failure=stop_on_failed, stop_on_blocked=stop_on_blocked, idle_exit=True, now=now); processed.extend(agent_result["selected_entry_ids"])
                    goal = self.project(goal_id, now=now)
                    continue
                stopped = "idle"
                if idle_exit: break
                if wait_seconds: time.sleep(wait_seconds)
                continue
            for milestone_id in ready[:max_milestones]:
                milestone = _mapping(goal["milestones"][milestone_id]); milestone["milestone_status"] = "ready"; milestone["updated_at"] = time_text(now); goal["milestones"][milestone_id] = seal_milestone(milestone); self._publish("long_goal.milestone.ready", goal, milestone=milestone, now=now)
                goal, ids = self._generate(goal, milestone_id, now=now); generated.extend(ids)
            goal = self._save(self._refresh(goal, now=now)); checkpoint = {"checkpoint_id": f"long-goal-checkpoint-{fingerprint({'goal': goal_id, 'iteration': len(goal['checkpoints']) + 1, 'generated': generated})[:20]}", "iteration": len(goal["checkpoints"]) + 1, "generated_entry_ids": list(generated), "created_at": time_text(now)}; goal["checkpoints"].append(checkpoint); self._save(self._refresh(goal, now=now))
            pending_for_goal = []
            for reference in goal.get("mission_entry_references") or []:
                try:
                    if self.agent.show(reference["entry_id"])["status"] == "pending": pending_for_goal.append(reference["entry_id"])
                except ValueError: continue
            mission_candidates = list(dict.fromkeys(generated + pending_for_goal))
            if mission_candidates:
                agent_result = RuntimePersistentAgentLoop(self.agent).run(max_missions=min(max_missions, len(mission_candidates)), max_iterations=max_iterations, stop_on_failure=stop_on_failed, stop_on_blocked=stop_on_blocked, idle_exit=True, now=now); processed.extend(agent_result["selected_entry_ids"]); generated = []
            goal = self.project(goal_id, now=now)
            if goal["goal_status"] == "waiting_for_approval": stopped = "waiting_for_approval"; break
            if goal["goal_status"] == "blocked" and stop_on_blocked: stopped = "stop_on_blocked"; break
            if goal["goal_status"] == "failed" and stop_on_failed: stopped = "stop_on_failed"; break
            if goal["goal_status"] == "completed": stopped = "completed"; break
        return self._result(self.show(goal_id), processed, stopped)

    def _result(self, goal: Mapping[str, Any], processed: list[str], stopped: str) -> dict[str, Any]:
        return {"contract": RUN_RESULT_CONTRACT, "goal_id": goal["goal_id"], "goal_status": goal["goal_status"], "stopped_reason": stopped, "processed_entry_ids": list(processed), "progress": deepcopy(goal["progress"]), "current_milestone_id": goal.get("current_milestone_id"), "checkpoint_count": len(goal.get("checkpoints") or [])}

    def pause(self, goal_id: str, *, now: Any = None) -> dict[str, Any]:
        goal = self.show(goal_id)
        if goal["goal_status"] in TERMINAL_GOALS: raise ValueError("terminal_long_goal_immutable")
        goal["pause_requested"] = True; goal["goal_status"] = "paused"; goal["updated_at"] = time_text(now); saved = self._save(goal); self._publish("long_goal.paused", saved, now=now); return saved
    def resume(self, goal_id: str, *, now: Any = None) -> dict[str, Any]:
        goal = self.show(goal_id)
        if goal["goal_status"] != "paused": raise ValueError("long_goal_not_paused")
        goal["pause_requested"] = False; goal["goal_status"] = "ready"; goal["updated_at"] = time_text(now); saved = self._save(self._refresh(goal, now=now)); self._publish("long_goal.resumed", saved, now=now); return saved
    def stop(self, goal_id: str, *, now: Any = None) -> dict[str, Any]:
        goal = self.show(goal_id)
        if goal["goal_status"] in TERMINAL_GOALS: return goal
        goal["stop_requested"] = True; goal["goal_status"] = "stopped"; goal["completed_at"] = time_text(now); goal["updated_at"] = time_text(now); saved = self._save(goal); self._publish("long_goal.stop_requested", saved, now=now); self._record_terminal_experience(saved, now=now); return saved
    def cancel(self, goal_id: str, *, now: Any = None) -> dict[str, Any]:
        goal = self.show(goal_id)
        if goal["goal_status"] in TERMINAL_GOALS: return goal
        for milestone_id in goal["milestone_order"]:
            milestone = _mapping(goal["milestones"][milestone_id])
            for entry_id in milestone["mission_entry_ids"]:
                try:
                    if self.agent.show(entry_id)["status"] in {"pending", "selected", "preparing", "waiting_for_approval", "paused"}: self.agent.cancel(entry_id, now=now)
                except ValueError: pass
            if milestone["milestone_status"] not in TERMINAL_MILESTONES: milestone["milestone_status"] = "cancelled"; milestone["completed_at"] = time_text(now); milestone["updated_at"] = time_text(now); goal["milestones"][milestone_id] = seal_milestone(milestone)
        goal["goal_status"] = "cancelled"; goal["completed_at"] = time_text(now); goal["updated_at"] = time_text(now); saved = self._save(self._refresh(goal, now=now)); self._publish("long_goal.cancelled", saved, now=now); self._record_terminal_experience(saved, now=now); return saved

    def approve(self, goal_id: str, milestone_id: str, *, operator_id: str, deny: bool = False, reason: str = "", now: Any = None) -> dict[str, Any]:
        goal = self.show(goal_id); milestone = _mapping(goal["milestones"].get(milestone_id))
        if not milestone: raise ValueError("long_goal_milestone_not_found")
        waiting = [entry_id for entry_id in milestone["mission_entry_ids"] if self.agent.show(entry_id)["status"] == "waiting_for_approval"]
        if not waiting: raise ValueError("milestone_not_waiting_for_approval")
        for entry_id in waiting: self.agent.approve(entry_id, operator_id=operator_id, deny=deny, reason=reason, now=now)
        return self.project(goal_id, now=now)

    def replan(self, goal_id: str, *, reason: str, now: Any = None) -> dict[str, Any]:
        goal = self.show(goal_id)
        if goal["goal_status"] in {"completed", "cancelled", "stopped"}: raise ValueError("terminal_long_goal_not_replannable")
        if goal["replan_count"] >= goal["max_replans"]: raise ValueError("long_goal_max_replans_exceeded")
        affected = next((key for key in goal["milestone_order"] if _mapping(goal["milestones"][key]).get("milestone_status") in {"blocked", "failed"}), None)
        revision = goal["replan_count"] + 1; before = {key: goal["milestones"][key]["milestone_fingerprint"] for key in goal["milestone_order"]}
        if affected:
            original = _mapping(goal["milestones"][affected]); seed = {"goal": goal_id, "revision": revision, "affected": affected, "scope": goal["target_root"]}; precheck_id = f"milestone-{fingerprint(seed)[:20]}"
            precheck = {"contract": "zero.agent.goal_milestone.v1", "milestone_id": precheck_id, "milestone_key": f"precheck_revision_{revision}", "title": "Replan precheck", "description": "Read-only bounded precheck added after failure evidence.", "milestone_status": "pending", "dependencies": list(original["dependencies"]), "priority": original["priority"] + 1, "created_at": time_text(now), "updated_at": time_text(now), "started_at": None, "completed_at": None, "mission_templates": [], "mission_entry_ids": [], "success_criteria": ["Failure evidence reviewed before retry"], "evidence_requirements": ["prior_failure_evidence"], "risk_notes": [str(reason)[:240]], "approval_expected": False, "attempt_count": 0, "max_attempts": 1, "failure": None, "reflection_references": [], "experience_references": [], "planning_feedback_reference": goal.get("planning_feedback_reference"), "plan_revision": revision + 1, "projected_entry_states": {}}
            goal["milestones"][precheck_id] = seal_milestone(precheck); original["dependencies"] = [precheck_id]; original["milestone_status"] = "pending"; original["mission_entry_ids"] = []; original["failure"] = None; original["plan_revision"] = int(original.get("plan_revision", 1)) + 1; original["updated_at"] = time_text(now); goal["milestones"][affected] = seal_milestone(original); goal["milestone_order"] = stable_milestone_order(goal["milestones"])
        goal["replan_count"] = revision; goal["plan_revision"] = int(goal.get("plan_revision", 1)) + 1; goal["replan_history"].append({"revision": revision, "reason": str(reason), "affected_milestone_id": affected, "completed_milestone_ids": list(goal["progress"]["completed_milestones"]), "before_fingerprints": before, "target_root": goal["target_root"], "created_at": time_text(now)}); goal["failure"] = None; goal["updated_at"] = time_text(now); saved = self._save(self._refresh(goal, now=now)); self._publish("long_goal.replanned", saved, suffix=str(revision), now=now); return saved

    def _record_terminal_experience(self, goal: Mapping[str, Any], *, now: Any = None) -> None:
        if goal.get("experience_reference"): return
        try:
            from core.agent.runtime_mission_reflection import build_mission_reflection, save_reflection
            from core.runtime.runtime_memory_model import build_runtime_activity_experience
            entry = {"entry_id": goal["goal_id"], "mission_id": goal["goal_id"], "mission_session_id": f"long-goal-session-{goal['goal_id']}", "status": goal["goal_status"], "original_input": goal["original_input"], "normalized_input": goal["normalized_goal"], "workspace_root": goal["workspace_root"], "attempt_count": goal["replan_count"] + 1, "max_attempts": goal["max_replans"] + 1, "approval_required": any(_mapping(goal["milestones"][key]).get("approval_expected") for key in goal["milestone_order"]), "approval_status": "approved" if goal["goal_status"] == "completed" else None, "last_result": {"completion_percentage": goal["progress"]["completion_percentage"]}, "failure": goal.get("failure")}
            website = any(token in str(goal["normalized_goal"]).casefold() for token in ("網站", "website", "static site"))
            intents = ([{"operation": "create_file", "path": "index.html"}, {"operation": "check_exists", "path": "index.html"}, {"operation": "create_file", "path": "styles.css"}, {"operation": "check_exists", "path": "styles.css"}] if website else [{"operation": "long_horizon_goal", "path": Path(goal["target_root"]).name or "workspace"}])
            artifact = {"structured_intents": intents, "applied_recommendations": [], "ignored_recommendations": [], "memory_context": goal.get("memory_context_reference")}
            reflection = build_mission_reflection(entry, agent_id=self.agent.load_state()["agent_id"], artifact=artifact, now=now); path = self.goals_root / goal["goal_id"] / "goal-reflection.json"; reflection = save_reflection(reflection, path)
            experience, _ = self.agent.load_memory().record_experience(build_runtime_activity_experience(reflection, entry=entry, artifact=artifact, reflection_path=path))
            current = self.show(goal["goal_id"]); current["reflection_reference"] = {"reflection_id": reflection["reflection_id"], "path": str(path)}; current["experience_reference"] = {"experience_id": experience["experience_id"]}; self._save(current)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return


__all__ = ["INDEX_CONTRACT", "RUN_RESULT_CONTRACT", "RuntimeGoalController"]
