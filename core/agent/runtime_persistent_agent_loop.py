from __future__ import annotations

from copy import deepcopy
import time
from typing import Any, Mapping

from core.agent.runtime_agent_controller import RuntimeAgentController
from core.runtime.runtime_operator_session import fingerprint, time_text


CONTRACT = "zero.agent.persistent_agent_loop_result.v1"


class RuntimePersistentAgentLoop:
    def __init__(self, controller: RuntimeAgentController):
        self.controller = controller

    def _checkpoint(self, *, entry: Mapping[str, Any] | None, result: Mapping[str, Any] | None, now: Any = None) -> dict[str, Any]:
        state = self.controller.load_state(); iteration = int(state.get("loop_iteration") or 0) + 1; at = time_text(now)
        checkpoint = {"checkpoint_id": f"agent-checkpoint-{fingerprint({'agent': state['agent_id'], 'iteration': iteration, 'entry': (entry or {}).get('entry_id')})[:20]}", "loop_iteration": iteration, "entry_id": (entry or {}).get("entry_id"), "entry_status": (result or {}).get("status"), "created_at": at}
        checkpoints = list(state.get("checkpoints") or []); checkpoints.append(checkpoint)
        return self.controller.refresh_state(now=now, loop_iteration=iteration, checkpoints=checkpoints, last_result=deepcopy(result))

    def run(self, *, max_missions: int = 1, max_iterations: int = 10, stop_on_failure: bool = False, stop_on_blocked: bool = False, idle_exit: bool = True, wait_seconds: float = 0.0, now: Any = None) -> dict[str, Any]:
        if isinstance(max_missions, bool) or not isinstance(max_missions, int) or max_missions < 1: raise ValueError("invalid_agent_max_missions")
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1: raise ValueError("invalid_agent_max_iterations")
        if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, (int, float)) or not 0 <= wait_seconds <= 60: raise ValueError("invalid_agent_wait_seconds")
        state = self.controller.load_state()
        if state.get("stop_requested"): return self._result(state, [], "stop_requested", now=now)
        if state.get("pause_requested"): return self._result(state, [], "pause_requested", now=now)
        state = self.controller.refresh_state(now=now, agent_status="running", started_at=state.get("started_at") or time_text(now), completed_at=None, last_error=None)
        self.controller._publish("agent.started", suffix=str(state["loop_iteration"]), now=now)
        self.controller.recover(now=now)
        processed = []; stopped_reason = "iteration_limit_reached"
        for _ in range(max_iterations):
            state = self.controller.load_state()
            if state.get("stop_requested"): stopped_reason = "stop_requested"; break
            if state.get("pause_requested"): stopped_reason = "pause_requested"; break
            if len(processed) >= max_missions: stopped_reason = "max_missions_reached"; break
            entry = self.controller.claim_next(now=now)
            if entry is None:
                stopped_reason = "idle"
                if idle_exit: break
                if wait_seconds: time.sleep(wait_seconds)
                self._checkpoint(entry=None, result={"status": "idle"}, now=now)
                continue
            result = self.controller.process_entry(entry["entry_id"], max_iterations=max_iterations, now=now)
            processed.append({"entry_id": result["entry_id"], "status": result["status"], "mission_id": result.get("mission_id"), "session_id": result.get("mission_session_id")})
            self._checkpoint(entry=entry, result=result, now=now)
            if result["status"] == "failed" and stop_on_failure: stopped_reason = "stop_on_failure"; break
            if result["status"] in {"blocked", "waiting_for_approval"} and stop_on_blocked: stopped_reason = "stop_on_blocked"; break
        state = self.controller.load_state()
        if stopped_reason == "pause_requested": final_status = "paused"
        elif stopped_reason == "stop_requested": final_status = "stopped"
        else: final_status = "idle"
        state = self.controller.refresh_state(now=now, agent_status=final_status, current_entry_id=None, completed_at=time_text(now) if final_status == "stopped" else None)
        if final_status == "idle": self.controller._publish("agent.idle", suffix=str(state["loop_iteration"]), now=now)
        return self._result(state, processed, stopped_reason, now=now)

    def _result(self, state: Mapping[str, Any], processed: list[dict[str, Any]], stopped_reason: str, *, now: Any = None) -> dict[str, Any]:
        entries = self.controller.list(); counts = {status: sum(1 for item in entries if item["status"] == status) for status in ("pending", "waiting_for_approval", "completed", "blocked", "failed", "cancelled")}
        value = {"contract": CONTRACT, "agent_id": state.get("agent_id"), "agent_status": state.get("agent_status"), "stopped_reason": stopped_reason, "selected_entry_ids": [item["entry_id"] for item in processed], "processed": deepcopy(processed), "started": len(processed), "completed": sum(item["status"] == "completed" for item in processed), "waiting_approval": counts["waiting_for_approval"], "blocked": counts["blocked"], "failed": counts["failed"], "pending": counts["pending"], "loop_iteration": state.get("loop_iteration"), "missions_started": state.get("missions_started"), "missions_completed": state.get("missions_completed"), "missions_blocked": state.get("missions_blocked"), "missions_failed": state.get("missions_failed"), "generated_at": time_text(now)}
        value["result_fingerprint"] = fingerprint(value); return value


__all__ = ["CONTRACT", "RuntimePersistentAgentLoop"]
