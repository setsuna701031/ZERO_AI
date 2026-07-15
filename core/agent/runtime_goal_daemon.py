from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_daemon_fairness import eligible_goals, select_round_robin
from core.agent.runtime_goal_daemon_projection import progress_goal
from core.agent.runtime_goal_daemon_state import (
    CONTRACT, CYCLE_CONTRACT, VERSION, GoalDaemonConfig, GoalDaemonCycleResult,
    GoalDaemonStatus, create_goal_daemon_state, load_goal_daemon_state,
    positive_integer, save_goal_daemon_state, seal_goal_daemon_cycle,
    validate_goal_daemon_cycle,
)
from core.agent.runtime_goal_daemon_status import build_goal_daemon_status
from core.runtime.runtime_operator_session import fingerprint, time_text


class GoalDaemon:
    """Bounded coordinator over the existing Goal Controller production path."""
    def __init__(self, controller: RuntimeGoalController, *, config: GoalDaemonConfig | None = None,
                 state_path: Any = None, now: Any = None):
        self.controller = controller
        self.state_path = Path(state_path).resolve(strict=False) if state_path is not None else controller.goals_root / "goal-daemon.json"
        if self.state_path.exists():
            state = load_goal_daemon_state(self.state_path)
            self.config = config or GoalDaemonConfig(**dict(state.get("configuration") or {}))
            if state["configuration_fingerprint"] != self.config.configuration_fingerprint: raise ValueError("goal_daemon_configuration_changed")
        else:
            self.config = config or GoalDaemonConfig(); state = create_goal_daemon_state(controller=controller, config=self.config, state_path=self.state_path, now=now)
        self.state = state

    def status(self) -> GoalDaemonStatus:
        return build_goal_daemon_status(load_goal_daemon_state(self.state_path), self.controller.list())

    def run_cycle(self, *, now: Any = None) -> GoalDaemonCycleResult:
        state = load_goal_daemon_state(self.state_path); sequence = int(state["cycle_count"]) + 1
        all_eligible = eligible_goals(self.controller.list()); limit = min(self.config.max_goals_per_cycle, self.config.max_projection_updates_per_cycle)
        selected, next_cursor = select_round_robin(all_eligible, cursor=int(state.get("round_robin_cursor") or 0), limit=limit)
        selected_ids = [goal["goal_id"] for goal in selected]; pre = {goal["goal_id"]: goal["goal_fingerprint"] for goal in selected}
        seed = {"contract": CYCLE_CONTRACT, "version": VERSION, "cycle_sequence": sequence, "selected_goal_ids": selected_ids, "pre_cycle_goal_fingerprints": pre, "configuration_fingerprint": self.config.configuration_fingerprint}
        cycle_id = f"goal-daemon-cycle-{fingerprint(seed)[:20]}"
        state.update(daemon_status="running", started_at=state.get("started_at") or time_text(now), updated_at=time_text(now), last_error=None); save_goal_daemon_state(state, self.state_path)
        runtime_budget = self.controller.runtime_mission_budget(self.config.max_missions_started_per_cycle)
        errors = [] if runtime_budget.get("invariant_satisfied") else [{"goal_id": None, "error": "active_missions_exceed_runtime_budget", "critical": True}]
        results = []; processed = []; mission_budget = int(runtime_budget["available_mission_starts"]); replan_budget = self.config.max_replans_per_cycle
        for goal in selected if not errors else []:
            goal_id = goal["goal_id"]
            try:
                result = progress_goal(self.controller, goal_id, mission_budget=mission_budget, replan_budget=replan_budget, now=now)
                result["pre_goal_fingerprint"] = pre[goal_id]; results.append(result); processed.extend(result["processed_entry_ids"])
                mission_budget = max(0, mission_budget - result["mission_started_count"]); replan_budget = max(0, replan_budget - int(result["replanned"]))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                error = {"goal_id": goal_id, "error": f"{type(exc).__name__}:{exc}", "critical": "fingerprint" in str(exc) or "identity" in str(exc)}; errors.append(error)
                results.append({"goal_id": goal_id, "pre_goal_fingerprint": pre[goal_id], "post_goal_fingerprint": None, "goal_status": "error", "run_result": None, "processed_entry_ids": [], "mission_started_count": 0, "replanned": False, "recovered": False})
                if error["critical"] and self.config.stop_on_critical_error: break
        state = load_goal_daemon_state(self.state_path); state.update(cycle_count=sequence, round_robin_cursor=next_cursor, last_selected_goal_ids=selected_ids, last_cycle_id=cycle_id, last_cycle_timestamp=time_text(now), last_error=errors[-1] if errors else None, daemon_status="failed" if errors and any(item["critical"] for item in errors) else "idle", updated_at=time_text(now)); save_goal_daemon_state(state, self.state_path)
        cycle = seal_goal_daemon_cycle({"contract": CYCLE_CONTRACT, "version": VERSION, "cycle_id": cycle_id, "daemon_id": state["daemon_id"], "cycle_sequence": sequence, "configuration_fingerprint": self.config.configuration_fingerprint, "runtime_mission_budget": runtime_budget, "selected_goal_ids": selected_ids, "pre_cycle_goal_fingerprints": pre, "goal_results": results, "processed_entry_ids": processed, "projection_update_count": len(selected), "mission_started_count": len(processed), "replan_count": self.config.max_replans_per_cycle - replan_budget, "cycle_status": state["daemon_status"], "errors": errors, "created_at": time_text(now)})
        reasons = validate_goal_daemon_cycle(cycle)
        if reasons: raise ValueError(";".join(reasons))
        return GoalDaemonCycleResult(cycle)

    def run(self, *, max_cycles: int = 1, now_provider: Any = None, sleep_provider: Any = None) -> GoalDaemonStatus:
        positive_integer(max_cycles, "max_cycles"); now_fn = now_provider or (lambda: None); sleep_fn = sleep_provider or time.sleep
        try:
            for index in range(max_cycles):
                state = load_goal_daemon_state(self.state_path)
                if state.get("stop_requested") or state.get("daemon_status") == "failed": break
                self.run_cycle(now=now_fn())
                if index + 1 < max_cycles: sleep_fn(float(self.config.poll_interval_seconds))
        except KeyboardInterrupt:
            state = load_goal_daemon_state(self.state_path); state.update(stop_requested=True, daemon_status="stopped", stopped_at=time_text(now_fn()), updated_at=time_text(now_fn())); save_goal_daemon_state(state, self.state_path)
        state = load_goal_daemon_state(self.state_path)
        if state["daemon_status"] != "failed": state.update(daemon_status="stopped", stopped_at=time_text(now_fn()), updated_at=time_text(now_fn())); save_goal_daemon_state(state, self.state_path)
        return self.status()


from core.agent.runtime_goal_daemon_state import (
    load_goal_daemon_state, save_goal_daemon_state, seal_goal_daemon_cycle,
    seal_goal_daemon_state, validate_goal_daemon_state,
)

__all__ = ["CONTRACT", "CYCLE_CONTRACT", "VERSION", "GoalDaemon", "GoalDaemonConfig", "GoalDaemonCycleResult", "GoalDaemonStatus", "load_goal_daemon_state", "save_goal_daemon_state", "seal_goal_daemon_cycle", "seal_goal_daemon_state", "validate_goal_daemon_cycle", "validate_goal_daemon_state"]
