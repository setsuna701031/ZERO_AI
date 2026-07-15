from __future__ import annotations

from copy import deepcopy
import threading
from typing import Any, Callable, Mapping

from core.agent.runtime_goal_controller import RuntimeGoalController
from core.operator.runtime_operator_dashboard_api import OperatorDashboardReadService
from core.runtime.runtime_operator_session import fingerprint


class OperatorDashboardActionService:
    def __init__(self, controller: RuntimeGoalController | Callable[[], RuntimeGoalController], read_service: OperatorDashboardReadService,
                 *, enabled: bool = True, max_idempotency_records: int = 512,
                 time_provider: Callable[[], Any] | None = None):
        self._controller_source = controller
        self._controller: RuntimeGoalController | None = controller if isinstance(controller, RuntimeGoalController) else None
        self.read_service = read_service
        self.enabled = bool(enabled)
        self.max_idempotency_records = max_idempotency_records
        self._now = time_provider or (lambda: None)
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @property
    def controller(self) -> RuntimeGoalController:
        if self._controller is None:
            created = self._controller_source()
            if not isinstance(created, RuntimeGoalController): raise TypeError("runtime_goal_controller_required")
            self._controller = created
        return self._controller

    def execute(self, action: str, resource_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise ValueError("dashboard_read_only_mode")
        body = dict(payload)
        if body.get("confirmation") is not True:
            raise ValueError("operator_confirmation_required")
        operator = str(body.get("operator_identity") or "").strip()
        if not operator:
            raise ValueError("operator_identity_required")
        key = str(body.get("idempotency_key") or "").strip()
        if not key:
            raise ValueError("idempotency_key_required")
        request_fingerprint = fingerprint({"action": action, "resource": resource_id, "payload": body})
        with self._lock:
            prior = self._results.get(key)
            if prior:
                if prior["request_fingerprint"] != request_fingerprint:
                    raise ValueError("idempotency_key_conflict")
                result = deepcopy(prior["result"])
                result["idempotent_replay"] = True
                return result

            if action in {"approve", "deny"}:
                result = self._approval(action, resource_id, body, operator)
            else:
                result = self._goal_action(action, resource_id, body)
            envelope = {
                "contract": "zero.operator.dashboard_action_result.v1",
                "action": action,
                "resource_identity": resource_id,
                "operator_identity": operator,
                "idempotency_key": key,
                "idempotent_replay": False,
                "runtime_result": result,
            }
            envelope["result_fingerprint"] = fingerprint(envelope)
            self._results[key] = {"request_fingerprint": request_fingerprint, "result": deepcopy(envelope)}
            while len(self._results) > self.max_idempotency_records:
                self._results.pop(next(iter(self._results)))
            return envelope

    def _goal_action(self, action: str, goal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        now = self._now()
        if action == "pause": return self.controller.pause(goal_id, now=now)
        if action == "resume": return self.controller.resume(goal_id, now=now)
        if action == "stop": return self.controller.stop(goal_id, now=now)
        if action == "cancel": return self.controller.cancel(goal_id, now=now)
        if action == "replan":
            reason = str(body.get("reason") or "").strip()
            if not reason: raise ValueError("replan_reason_required")
            return self.controller.replan(goal_id, reason=reason, now=now)
        raise ValueError("unknown_dashboard_action")

    def _approval(self, action: str, approval_id: str, body: Mapping[str, Any], operator: str) -> dict[str, Any]:
        approval = self.read_service.find_approval(approval_id)
        for field in ("goal_id", "milestone_id", "entry_id"):
            if body.get(field) != approval.get(field):
                raise ValueError(f"approval_{field}_mismatch")
        if body.get("expected_scope_fingerprint") != approval.get("fingerprint"):
            raise ValueError("approval_scope_fingerprint_mismatch")
        if approval.get("current_status") == "expired":
            raise ValueError("approval_expired")
        reason = str(body.get("reason") or "").strip()
        if action == "deny" and not reason:
            raise ValueError("denial_reason_required")
        return self.controller.approve(str(approval["goal_id"]), str(approval["milestone_id"]),
                                       operator_id=operator, deny=action == "deny", reason=reason, now=self._now())


__all__ = ["OperatorDashboardActionService"]
