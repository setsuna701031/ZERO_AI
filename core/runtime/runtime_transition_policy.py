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
    policy: str = "runtime_transition_policy_v3"
    details: Dict[str, Any] | None = None

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
            "details": copy.deepcopy(self.details or {}),
        }


class RuntimeTransitionPolicy:
    """
    Runtime transition legality policy.
    """

    RUNNING_STATUSES = {"running", "ready", "planning", "replanning", "retrying"}
    BLOCKED_STATUSES = {"blocked", "waiting", "waiting_review", "waiting_blocker", "paused", "review_required"}
    REVIEW_STATUSES = {"waiting_review", "review_required"}
    RECOVERY_ACTIONS = {"rollback_restore", "rollback_reopen", "rollback_retry", "restore_repair_backup"}

    ALLOWED_BLOCKED_REOPEN_ACTION_TOKENS = {
        "unblock",
        "replan",
        "retry",
        "resume",
        "review",
        "blocker_resolved",
        "remove_blocker",
    }

    REVIEW_RESOLUTION_KEYS = {
        "review_resolved",
        "review_approved",
        "review_resolution",
        "blocker_resolved",
        "unblock_confirmed",
        "replan_approved",
    }

    REVIEW_RESOLUTION_VALUES = {
        "approved",
        "resolved",
        "accepted",
        "confirmed",
        "unblocked",
        "replan_approved",
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

        if (
            action_text in self.RECOVERY_ACTIONS
            or str(patch.get("recovery_action") or "").strip().lower() in self.RECOVERY_ACTIONS
        ):
            recovery_decision = self.check_recovery_transition(
                current_state=state,
                updates=patch,
                owner=owner_text,
                action=action_text or str(patch.get("recovery_action") or ""),
            )

            if not recovery_decision.ok:
                return recovery_decision

        if runtime_mode in READONLY_RUNTIME_MODES and next_status in self.RUNNING_STATUSES:
            return self._deny(
                reason=f"{runtime_mode} runtime cannot transition to execution status {next_status}",
                current_status=current_status,
                next_status=next_status,
                runtime_mode=runtime_mode,
                owner=owner_text,
                action=action_text,
                details={"rule": "readonly_runtime_no_execution"},
            )

        if current_status in TERMINAL_STATUSES and next_status in self.RUNNING_STATUSES:
            if not self._is_explicit_rollback_recovery_reopen(
                state=state,
                updates=patch,
                action=action_text,
            ):
                return self._deny(
                    reason=f"terminal runtime status {current_status} cannot transition to {next_status}",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "terminal_no_reopen"},
                )

        if next_status == "retrying":
            retry_decision = self._check_retry_legality(
                state=state,
                updates=patch,
                current_status=current_status,
                next_status=next_status,
                runtime_mode=runtime_mode,
                owner=owner_text,
                action=action_text,
            )

            if retry_decision is not None:
                return retry_decision

        if current_status in self.REVIEW_STATUSES and next_status in self.RUNNING_STATUSES:
            if not self._action_allows_blocked_reopen(action_text):
                return self._deny(
                    reason=f"review runtime status {current_status} requires explicit review resolution action before {next_status}",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "review_reopen_requires_action"},
                )

            if not self._has_review_resolution(state=state, updates=patch, action=action_text):
                return self._deny(
                    reason=f"review runtime status {current_status} requires resolved/approved review before {next_status}",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "review_reopen_requires_resolution"},
                )

        if current_status in self.BLOCKED_STATUSES and next_status in self.RUNNING_STATUSES:
            if not self._action_allows_blocked_reopen(action_text):
                return self._deny(
                    reason=f"blocked runtime status {current_status} requires explicit unblock/replan action before {next_status}",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "blocked_reopen_requires_action"},
                )

            if current_status in {"blocked", "waiting_blocker"} and not self._has_blocker_resolution(
                state=state,
                updates=patch,
                action=action_text,
            ):
                return self._deny(
                    reason=f"blocked runtime status {current_status} requires blocker resolution before {next_status}",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "blocked_reopen_requires_resolution"},
                )

        return RuntimeTransitionDecision(
            ok=True,
            reason="transition allowed",
            current_status=current_status,
            next_status=next_status,
            runtime_mode=runtime_mode,
            owner=owner_text,
            action=action_text,
            details={"rule": "allowed"},
        )

    def check_recovery_transition(
        self,
        *,
        current_state: Dict[str, Any],
        updates: Dict[str, Any] | None = None,
        owner: str = "",
        action: str = "",
    ) -> RuntimeTransitionDecision:
        state = copy.deepcopy(current_state if isinstance(current_state, dict) else {})
        patch = copy.deepcopy(updates if isinstance(updates, dict) else {})

        current_status = self._normalize_status(state.get("status"))
        next_status = self._normalize_status(patch.get("status", current_status))
        runtime_mode = self._runtime_mode(state=state, updates=patch)
        owner_text = str(owner or "").strip().lower()
        action_text = str(action or patch.get("recovery_action") or "").strip().lower()

        if runtime_mode in READONLY_RUNTIME_MODES:
            return self._deny(
                reason=f"{runtime_mode} runtime cannot perform rollback recovery transition",
                current_status=current_status,
                next_status=next_status,
                runtime_mode=runtime_mode,
                owner=owner_text,
                action=action_text,
                details={"rule": "readonly_runtime_no_rollback_recovery"},
            )

        if action_text in {"rollback_restore", "restore_repair_backup", ""}:
            rollback = self._rollback_payload(state=state, updates=patch)

            if not isinstance(rollback, dict):
                return self._deny(
                    reason="rollback recovery requires rollback metadata",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "rollback_requires_metadata"},
                )

            if not bool(rollback.get("restore_available", False)):
                return self._deny(
                    reason="rollback recovery requires restore_available rollback metadata",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "rollback_requires_restore_available"},
                )

        if action_text in {"rollback_reopen", "rollback_retry"}:
            rollback_result = self._rollback_result_payload(state=state, updates=patch)

            if not isinstance(rollback_result, dict) or rollback_result.get("ok") is not True:
                return self._deny(
                    reason="rollback reopen/retry requires successful rollback_result",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "rollback_reopen_requires_successful_result"},
                )

            if current_status in TERMINAL_STATUSES and "rollback" not in action_text:
                return self._deny(
                    reason=f"terminal runtime status {current_status} requires explicit rollback recovery action before {next_status}",
                    current_status=current_status,
                    next_status=next_status,
                    runtime_mode=runtime_mode,
                    owner=owner_text,
                    action=action_text,
                    details={"rule": "terminal_reopen_requires_rollback_action"},
                )

        return RuntimeTransitionDecision(
            ok=True,
            reason="recovery transition allowed",
            current_status=current_status,
            next_status=next_status,
            runtime_mode=runtime_mode,
            owner=owner_text,
            action=action_text,
            details={"rule": "recovery_allowed"},
        )

    def _deny(
        self,
        *,
        reason: str,
        current_status: str,
        next_status: str,
        runtime_mode: str,
        owner: str,
        action: str,
        details: Dict[str, Any] | None = None,
    ) -> RuntimeTransitionDecision:
        return RuntimeTransitionDecision(
            ok=False,
            reason=reason,
            current_status=current_status,
            next_status=next_status,
            runtime_mode=runtime_mode,
            owner=owner,
            action=action,
            details=copy.deepcopy(details or {}),
        )

    def _check_retry_legality(
        self,
        *,
        state: Dict[str, Any],
        updates: Dict[str, Any],
        current_status: str,
        next_status: str,
        runtime_mode: str,
        owner: str,
        action: str,
    ) -> RuntimeTransitionDecision | None:
        retry_budget = updates.get("retry_budget")

        if not isinstance(retry_budget, dict):
            retry_budget = state.get("retry_budget")

        exhausted = False
        remaining = None

        if isinstance(retry_budget, dict):
            exhausted = bool(retry_budget.get("exhausted", False))

            if "remaining" in retry_budget:
                remaining = self._safe_int(retry_budget.get("remaining"), None)

            elif "retry_budget_remaining" in retry_budget:
                remaining = self._safe_int(retry_budget.get("retry_budget_remaining"), None)

        if remaining is None:
            if "retry_budget_remaining" in updates:
                remaining = self._safe_int(updates.get("retry_budget_remaining"), None)

            elif "retry_budget_remaining" in state:
                remaining = self._safe_int(state.get("retry_budget_remaining"), None)

        if exhausted or remaining == 0:
            return self._deny(
                reason="retry transition requires available retry budget",
                current_status=current_status,
                next_status=next_status,
                runtime_mode=runtime_mode,
                owner=owner,
                action=action,
                details={
                    "rule": "retry_requires_budget",
                    "retry_budget_exhausted": exhausted,
                    "retry_budget_remaining": remaining,
                },
            )

        return None

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

    def _has_review_resolution(
        self,
        *,
        state: Dict[str, Any],
        updates: Dict[str, Any],
        action: str,
    ) -> bool:
        if self._has_resolution_marker(updates):
            return True

        if self._has_resolution_marker(state):
            return True

        if "approved" in action or "resolved" in action or "confirmed" in action:
            return True

        review_status = str(
            updates.get("review_status")
            or state.get("review_status")
            or ""
        ).strip().lower()

        if review_status in self.REVIEW_RESOLUTION_VALUES:
            return True

        review_payload = updates.get("review_payload")

        if not isinstance(review_payload, dict):
            review_payload = state.get("review_payload")

        if isinstance(review_payload, dict) and self._has_resolution_marker(review_payload):
            return True

        return False

    def _has_blocker_resolution(
        self,
        *,
        state: Dict[str, Any],
        updates: Dict[str, Any],
        action: str,
    ) -> bool:
        if self._has_resolution_marker(updates):
            return True

        if "resolved" in action or "unblock" in action or "remove_blocker" in action:
            return True

        blockers = updates.get("blockers")

        if not isinstance(blockers, list):
            blockers = state.get("blockers")

        if isinstance(blockers, list):
            active = [
                item
                for item in blockers
                if isinstance(item, dict)
                and str(item.get("status") or "").strip().lower()
                not in {"resolved", "approved", "cleared", "removed"}
            ]

            return len(active) == 0

        active_count = updates.get("active_blocker_count", state.get("active_blocker_count"))

        try:
            return int(active_count or 0) == 0

        except Exception:
            return False

    def _has_resolution_marker(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False

        for key in self.REVIEW_RESOLUTION_KEYS:
            if key in payload:
                value = payload.get(key)

                if isinstance(value, bool):
                    if value:
                        return True

                else:
                    text = str(value or "").strip().lower()

                    if text in self.REVIEW_RESOLUTION_VALUES or text in {"true", "yes", "1"}:
                        return True

        resolution = payload.get("resolution")

        if isinstance(resolution, dict):
            status = str(resolution.get("status") or "").strip().lower()

            if status in self.REVIEW_RESOLUTION_VALUES:
                return True

        return False

    def _rollback_payload(
        self,
        *,
        state: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        for payload in (updates, state):
            rollback = payload.get("rollback")

            if isinstance(rollback, dict):
                return rollback

            repair_context = payload.get("repair_context")

            if isinstance(repair_context, dict):
                rollback = repair_context.get("rollback")

                if isinstance(rollback, dict):
                    return rollback

        return None

    def _rollback_result_payload(
        self,
        *,
        state: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        for payload in (updates, state):
            rollback_result = payload.get("rollback_result")

            if isinstance(rollback_result, dict):
                return rollback_result

            repair_context = payload.get("repair_context")

            if isinstance(repair_context, dict):
                rollback_result = repair_context.get("rollback_result")

                if isinstance(rollback_result, dict):
                    return rollback_result

        return None

    def _is_explicit_rollback_recovery_reopen(
        self,
        *,
        state: Dict[str, Any],
        updates: Dict[str, Any],
        action: str,
    ) -> bool:
        text = str(action or updates.get("recovery_action") or "").strip().lower()

        if text not in {"rollback_reopen", "rollback_retry"}:
            return False

        decision = self.check_recovery_transition(
            current_state=state,
            updates=updates,
            owner="task_runtime",
            action=text,
        )

        return decision.ok

    def _safe_int(self, value: Any, default: int | None = 0) -> int | None:
        try:
            return int(value)

        except Exception:
            return default


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


def check_recovery_transition(
    *,
    current_state: Dict[str, Any],
    updates: Dict[str, Any] | None = None,
    owner: str = "",
    action: str = "",
) -> Dict[str, Any]:
    return RuntimeTransitionPolicy().check_recovery_transition(
        current_state=current_state,
        updates=updates or {},
        owner=owner,
        action=action,
    ).to_dict()