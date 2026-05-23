from __future__ import annotations

import copy
from typing import Any, Callable

from core.runtime.runtime_recovery_policy import RuntimeRecoveryPolicy
from core.runtime.runtime_recovery_state import (
    RECOVERY_CONTINUATION_REQUIRES_REVIEW,
    RECOVERY_EXECUTION_STATUS_BLOCKED,
    RECOVERY_EXECUTION_STATUS_COMPLETED,
    RECOVERY_EXECUTION_STATUS_FAILED,
    RECOVERY_EXECUTION_STATUS_SKIPPED,
    RuntimeRecoveryExecutionAction,
    RuntimeRecoveryExecutionResult,
    RuntimeRecoveryExecutionStore,
    build_recovery_execution_id,
    normalize_recovery_chain_payload,
    utc_timestamp,
)

RecoveryHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class RuntimeRecoveryExecutor:
    """Executes a recovery chain in governed, non-destructive mode by default."""

    def __init__(
        self,
        *,
        policy: RuntimeRecoveryPolicy | None = None,
        journal: Any = None,
        handlers: dict[str, RecoveryHandler] | None = None,
        store: RuntimeRecoveryExecutionStore | None = None,
    ) -> None:
        self.policy = policy if policy is not None else RuntimeRecoveryPolicy()
        self.journal = journal
        self.handlers: dict[str, RecoveryHandler] = dict(handlers or {})
        self.store = store if store is not None else RuntimeRecoveryExecutionStore()

    def register_handler(self, action_type: str, handler: RecoveryHandler) -> None:
        action = str(action_type or "").strip()
        if not action:
            raise ValueError("recovery_action_type_required")
        if not callable(handler):
            raise TypeError("recovery_handler_must_be_callable")
        self.handlers[action] = handler

    def execute_recovery(
        self,
        recovery_chain: Any,
        *,
        source_state: dict[str, Any] | None = None,
        approval: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryExecutionResult:
        chain = normalize_recovery_chain_payload(recovery_chain)
        recovery_id = str(chain.get("recovery_id") or "").strip()
        source_session_id = str(chain.get("source_session_id") or "").strip()
        execution_id = build_recovery_execution_id(recovery_id, {"metadata": metadata or {}})
        chain_status = str(chain.get("status") or "").strip().lower()
        verification = copy.deepcopy(chain.get("verification_result") if isinstance(chain.get("verification_result"), dict) else {})
        before_state = copy.deepcopy(source_state if isinstance(source_state, dict) else {})
        working_state = copy.deepcopy(before_state)
        audit_events: list[dict[str, Any]] = []
        action_results: list[dict[str, Any]] = []

        self._append_audit(
            audit_events,
            recovery_id=recovery_id,
            execution_id=execution_id,
            event_type="recovery_execution_started",
            payload={"chain_status": chain_status},
        )

        planned_actions = self._build_execution_actions(chain)
        blocked = False
        failed = False

        for action in planned_actions:
            decision = self.policy.decide_action(
                action_type=action.action_type,
                chain_status=chain_status,
                chain_payload=chain,
                approval=approval,
            )
            if not decision.allowed:
                blocked = True
                resolved = RuntimeRecoveryExecutionAction(
                    action_id=action.action_id,
                    action_type=action.action_type,
                    status=RECOVERY_EXECUTION_STATUS_BLOCKED,
                    reason=decision.reason,
                    required=action.required,
                    payload=action.payload,
                    result={"policy_decision": decision.to_dict()},
                    created_at=action.created_at,
                    updated_at=utc_timestamp(),
                )
                action_results.append(resolved.to_dict())
                self._append_audit(
                    audit_events,
                    recovery_id=recovery_id,
                    execution_id=execution_id,
                    event_type="recovery_action_blocked",
                    payload=resolved.to_dict(),
                )
                if action.required:
                    break
                continue

            try:
                action_result = self._execute_action(
                    action=action,
                    chain=chain,
                    working_state=working_state,
                    approval=approval,
                )
                if isinstance(action_result.get("source_state"), dict):
                    working_state = copy.deepcopy(action_result["source_state"])
                status = RECOVERY_EXECUTION_STATUS_COMPLETED if bool(action_result.get("ok", True)) else RECOVERY_EXECUTION_STATUS_FAILED
                if status == RECOVERY_EXECUTION_STATUS_FAILED:
                    failed = True
                resolved = RuntimeRecoveryExecutionAction(
                    action_id=action.action_id,
                    action_type=action.action_type,
                    status=status,
                    reason=decision.reason,
                    required=action.required,
                    payload=action.payload,
                    result={"policy_decision": decision.to_dict(), **copy.deepcopy(action_result)},
                    created_at=action.created_at,
                    updated_at=utc_timestamp(),
                )
                action_results.append(resolved.to_dict())
                self._append_audit(
                    audit_events,
                    recovery_id=recovery_id,
                    execution_id=execution_id,
                    event_type="recovery_action_completed" if status == RECOVERY_EXECUTION_STATUS_COMPLETED else "recovery_action_failed",
                    payload=resolved.to_dict(),
                )
            except Exception as exc:
                failed = True
                resolved = RuntimeRecoveryExecutionAction(
                    action_id=action.action_id,
                    action_type=action.action_type,
                    status=RECOVERY_EXECUTION_STATUS_FAILED,
                    reason=str(exc),
                    required=action.required,
                    payload=action.payload,
                    result={"error": str(exc), "policy_decision": decision.to_dict()},
                    created_at=action.created_at,
                    updated_at=utc_timestamp(),
                )
                action_results.append(resolved.to_dict())
                self._append_audit(
                    audit_events,
                    recovery_id=recovery_id,
                    execution_id=execution_id,
                    event_type="recovery_action_failed",
                    payload=resolved.to_dict(),
                )
                if action.required:
                    break

        after_state = copy.deepcopy(working_state)
        source_state_mutated = before_state != after_state
        continuation = self.policy.decide_continuation(
            chain_status=chain_status,
            verification_result=verification,
        )
        if blocked:
            status = RECOVERY_EXECUTION_STATUS_BLOCKED
        elif failed:
            status = RECOVERY_EXECUTION_STATUS_FAILED
            if continuation == "ready_for_continuation":
                continuation = RECOVERY_CONTINUATION_REQUIRES_REVIEW
        else:
            status = RECOVERY_EXECUTION_STATUS_COMPLETED

        self._append_audit(
            audit_events,
            recovery_id=recovery_id,
            execution_id=execution_id,
            event_type="recovery_execution_finished",
            payload={
                "status": status,
                "continuation_decision": continuation,
                "source_state_mutated": source_state_mutated,
            },
        )

        result = RuntimeRecoveryExecutionResult(
            execution_id=execution_id,
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            status=status,
            continuation_decision=continuation,
            action_results=action_results,
            verification_snapshot=verification,
            recovery_chain_status=chain_status,
            source_state_before=before_state,
            source_state_after=after_state,
            source_state_mutated=source_state_mutated,
            audit_events=audit_events,
            metadata=copy.deepcopy(metadata or {}),
        )
        self.store.put(result)
        self._append_journal("runtime_recovery_execution_result", result.to_dict(), {"recovery_id": recovery_id})
        return result

    def _build_execution_actions(self, chain: dict[str, Any]) -> list[RuntimeRecoveryExecutionAction]:
        recovery_id = str(chain.get("recovery_id") or "recovery").strip() or "recovery"
        plan = chain.get("recovery_plan") if isinstance(chain.get("recovery_plan"), dict) else {}
        status = str(chain.get("status") or "").strip().lower()
        actions: list[RuntimeRecoveryExecutionAction] = []

        replay_reference = chain.get("replay_reference") if isinstance(chain.get("replay_reference"), dict) else {}
        if replay_reference:
            actions.append(
                RuntimeRecoveryExecutionAction(
                    action_id=f"{recovery_id}-exec-replay-candidate",
                    action_type="execute_replay_candidate",
                    reason="use replay reference as recovery evidence candidate",
                    payload={"replay_reference": copy.deepcopy(replay_reference)},
                )
            )

        rollback_reference = chain.get("rollback_reference") if isinstance(chain.get("rollback_reference"), dict) else {}
        if bool(plan.get("rollback_required")) or status == "rollback_required" or rollback_reference:
            actions.append(
                RuntimeRecoveryExecutionAction(
                    action_id=f"{recovery_id}-exec-rollback-prepare",
                    action_type="prepare_rollback",
                    reason="represent rollback path without auto-applying it",
                    payload={"rollback_reference": copy.deepcopy(rollback_reference)},
                )
            )
            actions.append(
                RuntimeRecoveryExecutionAction(
                    action_id=f"{recovery_id}-exec-rollback-apply",
                    action_type="execute_rollback",
                    reason="rollback execution is high risk and must be explicitly approved",
                    payload={"rollback_reference": copy.deepcopy(rollback_reference)},
                    required=False,
                )
            )

        actions.append(
            RuntimeRecoveryExecutionAction(
                action_id=f"{recovery_id}-exec-verify",
                action_type="verify_recovery",
                reason="carry recovery verification snapshot into execution result",
                payload={"verification_result": copy.deepcopy(chain.get("verification_result") or {})},
            )
        )

        if status == "verified":
            actions.append(
                RuntimeRecoveryExecutionAction(
                    action_id=f"{recovery_id}-exec-continuation",
                    action_type="recommend_continuation",
                    reason="verified recovery chain can recommend runtime continuation",
                    payload={"chain_status": status},
                    required=False,
                )
            )

        if status == "unrecoverable":
            actions.append(
                RuntimeRecoveryExecutionAction(
                    action_id=f"{recovery_id}-exec-block",
                    action_type="continue_runtime",
                    reason="unrecoverable chains must not continue runtime",
                    payload={"chain_status": status},
                    required=True,
                )
            )

        return actions

    def _execute_action(
        self,
        *,
        action: RuntimeRecoveryExecutionAction,
        chain: dict[str, Any],
        working_state: dict[str, Any],
        approval: dict[str, Any] | None,
    ) -> dict[str, Any]:
        handler = self.handlers.get(action.action_type)
        if handler is not None:
            return handler(
                copy.deepcopy(action.to_dict()),
                {
                    "chain": copy.deepcopy(chain),
                    "source_state": copy.deepcopy(working_state),
                    "approval": copy.deepcopy(approval or {}),
                },
            )

        if action.action_type == "execute_replay_candidate":
            replay_reference = action.payload.get("replay_reference") if isinstance(action.payload, dict) else {}
            return {
                "ok": True,
                "mode": "reference_only_replay_candidate",
                "replay_reference": copy.deepcopy(replay_reference if isinstance(replay_reference, dict) else {}),
            }

        if action.action_type == "prepare_rollback":
            rollback_reference = action.payload.get("rollback_reference") if isinstance(action.payload, dict) else {}
            return {
                "ok": True,
                "mode": "rollback_prepared_not_executed",
                "rollback_reference": copy.deepcopy(rollback_reference if isinstance(rollback_reference, dict) else {}),
                "message": "rollback is represented but not blindly executed",
            }

        if action.action_type == "verify_recovery":
            return {
                "ok": True,
                "mode": "verification_snapshot_attached",
                "verification_result": copy.deepcopy(action.payload.get("verification_result") if isinstance(action.payload, dict) else {}),
            }

        if action.action_type == "recommend_continuation":
            return {
                "ok": True,
                "mode": "continuation_recommended",
                "message": "runtime continuation can be considered by the caller",
            }

        if action.action_type == "continue_runtime":
            return {
                "ok": False,
                "mode": "blocked_by_default",
                "message": "runtime continuation requires a verified non-rollback recovery chain",
            }

        if action.action_type in {"execute_rollback", "apply_rollback"}:
            return {
                "ok": False,
                "mode": "rollback_not_bound",
                "message": "no rollback handler registered; rollback was not executed",
            }

        return {
            "ok": True,
            "mode": RECOVERY_EXECUTION_STATUS_SKIPPED,
            "message": "no default recovery action effect",
        }

    def _append_audit(
        self,
        audit_events: list[dict[str, Any]],
        *,
        recovery_id: str,
        execution_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        event = {
            "event_type": event_type,
            "recovery_id": recovery_id,
            "execution_id": execution_id,
            "payload": copy.deepcopy(payload),
            "timestamp": utc_timestamp(),
            "source": "runtime_recovery_executor",
        }
        audit_events.append(event)
        self._append_journal("runtime_recovery_execution_audit_event", event, {"recovery_id": recovery_id})

    def _append_journal(self, record_type: str, payload: dict[str, Any], metadata: dict[str, Any]) -> None:
        if self.journal is None:
            return
        try:
            self.journal.append(record_type, payload=payload, metadata=metadata)
        except Exception:
            return


__all__ = ["RuntimeRecoveryExecutor", "RecoveryHandler"]
