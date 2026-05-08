from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict


TERMINAL_STATUSES = {
    "finished",
    "failed",
    "cancelled",
    "timeout",
}

READONLY_RUNTIME_MODES = {
    "replay",
    "audit",
    "repair_replay",
}

NON_EXECUTION_MODES = READONLY_RUNTIME_MODES


class RuntimeTransitionPolicyError(ValueError):
    """Raised when a runtime transition violates runtime transition policy."""


@dataclass(frozen=True)
class RuntimeTransitionDecision:
    ok: bool
    reason: str = ""
    current_status: str = ""
    next_status: str = ""
    runtime_mode: str = "execute"
    owner: str = ""
    action: str = ""
    policy: str = "runtime_transition_policy_v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "reason": self.reason,
            "current_status": self.current_status,
            "next_status": self.next_status,
            "runtime_mode": self.runtime_mode,
            "owner": self.owner,
            "action": self.action,
            "policy": self.policy,
        }


class RuntimeTransitionPolicy:
    """
    Runtime transition legality policy.

    Ownership answers: who may mutate runtime state.
    This policy answers: whether the requested state transition is legal.

    Phase 1 rules:
    - finished/failed/cancelled/timeout cannot reopen to running.
    - blocked cannot transition to running unless the action explicitly
      indicates unblock/replan/retry review flow.
    - replay/audit/repair_replay cannot transition into executing/running.
    """

    RUNNING_STATUSES = {"running", "ready", "planning", "replanning", "retrying"}
    BLOCKED_STATUSES = {"blocked", "waiting", "waiting_review", "waiting_blocker", "paused", "review_required"}
    ALLOWED_BLOCKED_REOPEN_ACTION_TOKENS = {
        "unblock",
        "replan",
        "retry",
        "resume",
        "review",
        "blocker_resolved",
        "remove_blocker",
    }

    def check_transition(
        self,
        *,
        current_state: Dict[str, Any],
        updates: Dict[str, Any],
        owner: str = "",
        action: str = "",
    ) -> RuntimeTransitionDecision:
        state = copy.deepcopy(current_state if isinstance(current_state, dict) else {})
        patch = copy.deepcopy(updates if isinstance(updates, dict) else {})

        current_status = self._normalize_status(state.get("status"))
        next_status = self._normalize_status(patch.get("status", current_status))
        runtime_mode = self._runtime_mode(state=state, updates=patch)
        owner_text = str(owner or "").strip().lower()
        action_text = str(action or "").strip().lower()

        if runtime_mode in READONLY_RUNTIME_MODES and next_status in self.RUNNING_STATUSES:
            return RuntimeTransitionDecision(
                ok=False,
                reason=f"{runtime_mode} runtime cannot transition to execution status {next_status}",
                current_status=current_status,
                next_status=next_status,
                runtime_mode=runtime_mode,
                owner=owner_text,
                action=action_text,
            )

        if current_status in TERMINAL_STATUSES and next_status in self.RUNNING_STATUSES:
            return RuntimeTransitionDecision(
                ok=False,
                reason=f"terminal runtime status {current_status} cannot transition to {next_status}",
                current_status=current_status,
                next_status=next_status,
                runtime_mode=runtime_mode,
                owner=owner_text,
                action=action_text,
            )

        if current_status in self.BLOCKED_STATUSES and next_status in self.RUNNING_STATUSES:
            if not self._action_allows_blocked_reopen(action_text):
                return RuntimeTransitionDecision(
                    ok=False,
                    reason=f"blocked runtime status {current_status} requires explicit unblock/replan action before {next_status}",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                )

        return RuntimeTransitionDecision(
            ok=True,
            reason="transition allowed",
            current_status=current_status,
            next_status=next_status,
            runtime_mode=runtime_mode,
            owner=owner_text,
            action=action_text,
        )

    def _normalize_status(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        return text or "queued"

    def _runtime_mode(self, *, state: Dict[str, Any], updates: Dict[str, Any]) -> str:
        for payload in (updates, state):
            value = str(payload.get("runtime_mode") or "").strip().lower()
            if value:
                return value

            runtime_context = payload.get("runtime_context")
            if isinstance(runtime_context, dict):
                value = str(runtime_context.get("runtime_mode") or "").strip().lower()
                if value:
                    return value

            repair_context = payload.get("repair_context")
            if isinstance(repair_context, dict):
                value = str(repair_context.get("runtime_mode") or "").strip().lower()
                if value:
                    return value

        return "execute"

    def _action_allows_blocked_reopen(self, action: str) -> bool:
        text = str(action or "").strip().lower()
        if not text:
            return False
        return any(token in text for token in self.ALLOWED_BLOCKED_REOPEN_ACTION_TOKENS)


def check_runtime_transition(
    *,
    current_state: Dict[str, Any],
    updates: Dict[str, Any],
    owner: str = "",
    action: str = "",
) -> Dict[str, Any]:
    return RuntimeTransitionPolicy().check_transition(
        current_state=current_state,
        updates=updates,
        owner=owner,
        action=action,
    ).to_dict()
