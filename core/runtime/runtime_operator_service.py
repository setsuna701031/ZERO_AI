from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_autonomous_checkpoint import (
    build_runtime_loop_checkpoint_record,
)
from core.runtime.runtime_autonomous_execution_enablement import (
    evaluate_autonomous_start_gate,
    evaluate_execution_permission_lease,
    evaluate_runtime_enable_token,
)
from core.runtime.runtime_autonomous_persistence import (
    load_runtime_autonomous_session,
    persist_runtime_autonomous_session,
)
from core.runtime.runtime_autonomous_resume_gate import (
    evaluate_crash_recovery_resume_gate,
)
from core.runtime.runtime_autonomous_cycle_binding import (
    bind_worker_pickup_to_cycle,
    build_cycle_context_state,
)
from core.runtime.runtime_autonomous_cycle_execution_bridge import (
    bridge_cycle_binding_to_execution_request,
    build_execution_request_state,
)
from core.runtime.runtime_controlled_loop_activation import (
    activate_controlled_loop_tick,
    build_controlled_loop_state,
)
from core.runtime.runtime_controlled_tick_decision import (
    build_controlled_tick_decision_state,
    decide_controlled_tick,
)
from core.runtime.runtime_controlled_action_proposal import (
    build_controlled_action_proposal_state,
    propose_controlled_action,
)
from core.runtime.runtime_controlled_action_authorization import (
    authorize_controlled_action,
    build_controlled_action_authorization_state,
)
from core.runtime.runtime_controlled_action_commit import (
    build_controlled_action_commit_state,
    commit_controlled_action,
)
from core.runtime.runtime_execution_admission_gate import (
    admit_runtime_execution,
    build_runtime_execution_admission_state,
)
from core.runtime.runtime_execution_permit import (
    build_runtime_execution_permit_state,
    permit_runtime_execution,
)
from core.runtime.runtime_executor_envelope import (
    build_runtime_executor_envelope_state,
    prepare_runtime_executor_envelope,
)
from core.runtime.runtime_executor_adapter_binding import (
    bind_runtime_executor_adapter,
    build_runtime_executor_adapter_binding_state,
)
from core.runtime.runtime_executor_adapter_attachment import (
    attach_runtime_executor_adapter,
    build_runtime_executor_adapter_attachment_state,
)
from core.runtime.runtime_executor_invocation_approval import (
    build_runtime_executor_invocation_approval_state,
    submit_executor_invocation_approval,
)
from core.runtime.runtime_executor_invocation_gate import (
    build_runtime_executor_invocation_gate_state,
    submit_executor_invocation_gate,
)
from core.runtime.runtime_executor_invocation_record import (
    build_runtime_executor_invocation_record_state,
    submit_executor_invocation_record,
)
from core.runtime.runtime_executor_invocation_dispatch import (
    build_runtime_executor_invocation_dispatch_state,
    submit_executor_invocation_dispatch,
)
from core.runtime.runtime_execution_session_start import (
    build_runtime_execution_session_start_state,
    submit_runtime_execution_session_start,
)
from core.runtime.runtime_execution_result_capture import (
    build_runtime_execution_result_capture_state,
    submit_runtime_execution_result_capture,
)
from core.runtime.runtime_executor_runtime_closure import (
    build_runtime_executor_closure_state,
    submit_executor_runtime_closure,
)
from core.runtime.runtime_controlled_real_executor_unlock import (
    build_controlled_real_executor_unlock_state,
    submit_controlled_real_executor_unlock,
)
from core.runtime.runtime_controlled_mutation_unlock import (
    build_controlled_mutation_state,
    submit_controlled_mutation_unlock,
)
from core.runtime.runtime_commit_apply_binding import (
    build_runtime_commit_apply_state,
    submit_runtime_commit_apply,
)
from core.runtime.runtime_executor_invocation_preparation import (
    evaluate_executor_invocation_preparation,
)
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_goal_queue_admission import (
    build_queue_state,
    submit_goal_session_to_queue,
)
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup
from core.runtime.runtime_operator_config import (
    RuntimeOperatorConfig,
    load_runtime_operator_config,
)


RUNTIME_OPERATOR_SERVICE_SCHEMA = "zero.runtime.operator_service.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


class RuntimeOperatorService:
    def __init__(
        self,
        config: RuntimeOperatorConfig | Mapping[str, Any] | None = None,
        *,
        state: Mapping[str, Any] | None = None,
        controlled_real_executor_adapter: Any = None,
        controlled_mutation_adapter: Any = None,
        governed_commit_adapter: Any = None,
    ) -> None:
        self.config = load_runtime_operator_config(config)
        self._controlled_real_executor_adapter = controlled_real_executor_adapter
        self._controlled_mutation_adapter = controlled_mutation_adapter
        self._governed_commit_adapter = governed_commit_adapter
        self._state = {
            "runtime_session_id": "",
            "runtime_state": "stopped",
            "current_tick": 0,
            "current_cursor": "",
            "last_checkpoint": None,
            "last_result": None,
            "lease_id": "",
            "lease_expiry": 0,
            "emergency_stop_active": False,
            "controller_started": False,
            "queue_entries": [],
            "worker_claims": [],
            "cycle_bindings": [],
            "execution_requests": [],
            "controlled_loop_ticks": [],
            "controlled_tick_decisions": [],
            "controlled_action_proposals": [],
            "controlled_action_authorizations": [],
            "controlled_action_commits": [],
            "runtime_execution_admissions": [],
            "runtime_execution_permits": [],
            "runtime_executor_envelopes": [],
            "runtime_executor_adapter_bindings": [],
            "runtime_executor_adapter_attachments": [],
            "runtime_executor_invocation_preparations": [],
            "runtime_executor_invocation_approvals": [],
            "runtime_executor_invocation_gates": [],
            "runtime_executor_invocation_records": [],
            "runtime_executor_invocation_dispatches": [],
            "runtime_execution_session_starts": [],
            "runtime_execution_result_captures": [],
            "runtime_executor_closures": [],
            "controlled_real_executor_unlocks": [],
            "controlled_mutations": [],
            "runtime_commit_applies": [],
        }
        self._state.update(_mapping(state))

    @property
    def checkpoint_path(self) -> Path:
        return Path(self.config.checkpoint_path)

    def request_emergency_stop(self, reason: str = "operator_request") -> dict[str, Any]:
        self._state["emergency_stop_active"] = True
        self._state["runtime_state"] = "stopped"
        self._state["controller_started"] = False
        return {
            "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
            "ok": True,
            "action": "emergency_stop",
            "reason": _text(reason) or "operator_request",
            "emergency_stop_active": True,
            "runtime_state": "stopped",
            "runtime_state_mutated": True,
        }

    def start(
        self,
        *,
        enable_token: Mapping[str, Any] | None = None,
        lease: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        token_input = _mapping(enable_token) or {
            "token_id": "operator-enable-token",
            "token_identity": "zero-runtime-operator",
            "purpose": "runtime_autonomous_start",
            "runtime_enable_token_valid": True,
        }
        lease_input = _mapping(lease) or {
            "lease_id": "operator-runtime-lease",
            "ttl_seconds": max(1, self.config.max_tick_limit),
        }

        token_record = evaluate_runtime_enable_token(token_input)
        lease_record = evaluate_execution_permission_lease(token_record, lease_input)
        start_gate = evaluate_autonomous_start_gate(
            lease_record,
            {"loop_controller_enabled": True, "tick_cycle_enabled": True},
            {
                "max_iterations": self.config.max_tick_limit,
                "safety_stop_enabled": self.config.emergency_stop_enabled,
                "start_mode": self.config.runtime_mode,
            },
        )

        if self._state.get("emergency_stop_active") is True:
            denied = dict(start_gate)
            denied["autonomous_start_authorized"] = False
            denied["denial_reason"] = "emergency_stop_active"
            start_gate = denied

        if start_gate.get("autonomous_start_authorized") is not True:
            denial_reason = start_gate.get("denial_reason") or "start_not_authorized"
            if token_record.get("token_authorized") is not True:
                denial_reason = token_record.get("denial_reason") or "token_not_authorized"
            elif lease_record.get("lease_authorized") is not True:
                denial_reason = lease_record.get("denial_reason") or "lease_not_authorized"
            return {
                "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
                "ok": False,
                "action": "start",
                "denial_reason": denial_reason,
                "token": token_record,
                "lease": lease_record,
                "start_gate": start_gate,
                "status": self.status(),
                "controller_started": False,
            }

        runtime_session_id = "operator-runtime-session"
        self._state.update(
            {
                "runtime_session_id": runtime_session_id,
                "runtime_state": "active",
                "current_tick": 0,
                "current_cursor": "operator-cursor-0",
                "last_result": None,
                "lease_id": lease_record.get("lease_id"),
                "lease_expiry": self.config.max_tick_limit,
                "controller_started": True,
            }
        )

        return {
            "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
            "ok": True,
            "action": "start",
            "runtime_session_id": runtime_session_id,
            "controller_started": True,
            "token": token_record,
            "lease": lease_record,
            "start_gate": start_gate,
            "status": self.status(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
            "ok": True,
            "action": "status",
            "runtime_session_id": self._state.get("runtime_session_id") or "",
            "runtime_state": self._state.get("runtime_state") or "stopped",
            "active": self._state.get("runtime_state") == "active",
            "paused": self._state.get("runtime_state") == "paused",
            "stopped": self._state.get("runtime_state") == "stopped",
            "current_tick": int(self._state.get("current_tick") or 0),
            "current_cursor": self._state.get("current_cursor") or "",
            "last_checkpoint": self._state.get("last_checkpoint"),
            "last_result": self._state.get("last_result"),
            "lease_id": self._state.get("lease_id") or "",
            "lease_expiry": int(self._state.get("lease_expiry") or 0),
            "emergency_stop_active": self._state.get("emergency_stop_active") is True,
            "controller_started": self._state.get("controller_started") is True,
            "queue_status": self.queue_status(),
            "cycle_status": self.cycle_status(),
            "execution_status": self.execution_status(),
            "loop_status": self.loop_status(),
            "decision_status": self.decision_status(),
            "proposal_status": self.proposal_status(),
            "authorization_status": self.authorization_status(),
            "commit_status": self.commit_status(),
            "execution_admission_status": self.execution_admission_status(),
            "execution_permit_status": self.execution_permit_status(),
            "executor_envelope_status": self.executor_envelope_status(),
            "adapter_binding_status": self.adapter_binding_status(),
            "adapter_attachment_status": self.adapter_attachment_status(),
            "invocation_approval_status": self.invocation_approval_status(),
            "invocation_gate_status": self.invocation_gate_status(),
            "invocation_record_status": self.invocation_record_status(),
            "executor_invocation_dispatch_status": (
                self.executor_invocation_dispatch_status()
            ),
            "runtime_execution_session_start_status": (
                self.runtime_execution_session_start_status()
            ),
            "runtime_execution_result_capture_status": (
                self.runtime_execution_result_capture_status()
            ),
            "runtime_executor_closure_status": self.runtime_executor_closure_status(),
            "controlled_real_executor_unlock_status": (
                self.controlled_real_executor_unlock_status()
            ),
            "controlled_mutation_status": self.controlled_mutation_status(),
            "runtime_commit_apply_status": self.runtime_commit_apply_status(),
        }

    def stop(self, *, reason: str = "operator_stop") -> dict[str, Any]:
        current_tick = int(self._state.get("current_tick") or 0)
        checkpoint = build_runtime_loop_checkpoint_record(
            checkpoint_id=f"operator-checkpoint-{current_tick}",
            runtime_session_id=_text(self._state.get("runtime_session_id"))
            or "operator-runtime-session",
            active_cursor=_text(self._state.get("current_cursor")) or "operator-cursor-0",
            current_tick_index=current_tick,
            last_completed_work_id=_text(self._state.get("last_result")),
            lease_id=_text(self._state.get("lease_id")) or "operator-runtime-lease",
            lease_expiry_tick=int(self._state.get("lease_expiry") or self.config.max_tick_limit),
            runtime_state="active",
        )
        persisted = persist_runtime_autonomous_session(self.checkpoint_path, checkpoint)
        self._state.update(
            {
                "runtime_state": "stopped",
                "last_checkpoint": checkpoint,
                "controller_started": False,
            }
        )
        return {
            "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
            "ok": persisted.get("persisted") is True,
            "action": "stop",
            "shutdown_requested": True,
            "shutdown_reason": _text(reason) or "operator_stop",
            "checkpoint": checkpoint,
            "persistence": persisted,
            "lease_released": True,
            "status": self.status(),
        }

    def resume(self) -> dict[str, Any]:
        loaded = load_runtime_autonomous_session(self.checkpoint_path)
        if loaded.get("persisted") is True and loaded.get("loaded") is not True:
            gate = {
                "resume_authorized": False,
                "denial_reason": "checkpoint_invalid",
                "runtime_state_mutated": False,
                "cursor_advanced": False,
                "work_started": False,
            }
            return {
                "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
                "ok": False,
                "action": "resume",
                "loaded": loaded,
                "resume_gate": gate,
                "denial_reason": "checkpoint_invalid",
                "status": self.status(),
            }
        checkpoint = loaded.get("checkpoint")
        gate = evaluate_crash_recovery_resume_gate(
            checkpoint,
            current_tick_index=int(loaded.get("current_tick_index") or 0),
        )
        if gate.get("resume_authorized") is not True:
            return {
                "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
                "ok": False,
                "action": "resume",
                "loaded": loaded,
                "resume_gate": gate,
                "denial_reason": gate.get("denial_reason") or loaded.get("denial_reason"),
                "status": self.status(),
            }

        self._state.update(
            {
                "runtime_session_id": gate.get("runtime_session_id") or "",
                "runtime_state": "active",
                "current_tick": gate.get("checkpoint_tick_index") or 0,
                "current_cursor": gate.get("active_cursor") or "",
                "last_result": gate.get("last_completed_work_id") or None,
                "lease_id": gate.get("lease_id") or "",
                "lease_expiry": gate.get("lease_expiry") or 0,
                "last_checkpoint": checkpoint,
                "controller_started": True,
            }
        )
        return {
            "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
            "ok": True,
            "action": "resume",
            "loaded": loaded,
            "resume_gate": gate,
            "status": self.status(),
        }

    def health(self) -> dict[str, Any]:
        loaded = load_runtime_autonomous_session(self.checkpoint_path)
        checkpoint_valid = loaded.get("loaded") is True
        lease_state = "missing"
        if self._state.get("lease_id"):
            lease_state = (
                "active"
                if self._state.get("runtime_state") == "active"
                else "inactive"
            )
        elif checkpoint_valid and loaded.get("lease_id"):
            lease_state = "checkpointed"

        persistence_available = self.checkpoint_path.parent.exists() or self.checkpoint_path.exists()
        ready = (
            persistence_available
            and self._state.get("emergency_stop_active") is not True
            and lease_state in {"active", "checkpointed", "inactive"}
        )
        return {
            "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
            "ok": True,
            "action": "health",
            "ready": ready,
            "persistence_available": persistence_available,
            "checkpoint_valid": checkpoint_valid,
            "checkpoint_denial_reason": "" if checkpoint_valid else loaded.get("denial_reason", ""),
            "lease_state": lease_state,
            "emergency_stop_active": self._state.get("emergency_stop_active") is True,
            "runtime_state": self._state.get("runtime_state") or "stopped",
        }

    def run_goal(
        self,
        goal_text: Any,
        *,
        explicit_manual_mode: bool = False,
    ) -> dict[str, Any]:
        result = launch_goal_session(
            goal_text,
            self.config,
            explicit_manual_mode=explicit_manual_mode,
            emergency_stop_active=self._state.get("emergency_stop_active") is True,
        )
        queue_submit = submit_goal_session_to_queue(
            result,
            existing_queue=self._state.get("queue_entries"),
        )
        if result.get("launch_admitted") is True and queue_submit.get("queued") is True:
            pickup = submit_queue_entry_for_worker_pickup(
                queue_submit.get("queue_entry"),
                existing_claims=self._state.get("worker_claims"),
            )
            self._state["worker_claims"] = pickup["claims"]
            queue_entries = list(queue_submit["queue_entries"])
            if pickup.get("claimed") is True and queue_entries:
                queue_entries[-1] = pickup["queue_entry"]
            self._state["queue_entries"] = queue_entries
            cycle_binding = bind_worker_pickup_to_cycle(
                pickup.get("worker_pickup_record"),
                existing_bindings=self._state.get("cycle_bindings"),
            )
            self._state["cycle_bindings"] = cycle_binding["bindings"]
            execution_bridge = bridge_cycle_binding_to_execution_request(
                cycle_binding.get("cycle_binding"),
                existing_requests=self._state.get("execution_requests"),
            )
            self._state["execution_requests"] = execution_bridge["execution_requests"]
            loop_activation = activate_controlled_loop_tick(
                execution_bridge.get("execution_request"),
                existing_ticks=self._state.get("controlled_loop_ticks"),
            )
            self._state["controlled_loop_ticks"] = loop_activation["ticks"]
            tick_decision = decide_controlled_tick(
                loop_activation.get("controlled_loop_tick"),
                existing_decisions=self._state.get("controlled_tick_decisions"),
            )
            self._state["controlled_tick_decisions"] = tick_decision["decisions"]
            action_proposal = propose_controlled_action(
                tick_decision.get("controlled_tick_decision"),
                existing_proposals=self._state.get("controlled_action_proposals"),
            )
            self._state["controlled_action_proposals"] = action_proposal["proposals"]
            action_authorization = authorize_controlled_action(
                action_proposal.get("action_proposal"),
                existing_authorizations=self._state.get(
                    "controlled_action_authorizations"
                ),
            )
            self._state["controlled_action_authorizations"] = action_authorization[
                "authorizations"
            ]
            action_commit = commit_controlled_action(
                action_authorization.get("action_authorization"),
                existing_commits=self._state.get("controlled_action_commits"),
            )
            self._state["controlled_action_commits"] = action_commit["commits"]
            execution_admission = admit_runtime_execution(
                action_commit.get("action_commit"),
                existing_admissions=self._state.get("runtime_execution_admissions"),
            )
            self._state["runtime_execution_admissions"] = execution_admission[
                "admissions"
            ]
            execution_permit = permit_runtime_execution(
                execution_admission.get("execution_admission"),
                existing_permits=self._state.get("runtime_execution_permits"),
            )
            self._state["runtime_execution_permits"] = execution_permit["permits"]
            executor_envelope = prepare_runtime_executor_envelope(
                execution_permit.get("execution_permit"),
                existing_envelopes=self._state.get("runtime_executor_envelopes"),
            )
            self._state["runtime_executor_envelopes"] = executor_envelope[
                "envelopes"
            ]
            executor_adapter_binding = bind_runtime_executor_adapter(
                executor_envelope.get("executor_envelope"),
                existing_bindings=self._state.get(
                    "runtime_executor_adapter_bindings"
                ),
            )
            self._state["runtime_executor_adapter_bindings"] = (
                executor_adapter_binding["bindings"]
            )
            executor_adapter_attachment = attach_runtime_executor_adapter(
                executor_adapter_binding.get("executor_adapter_binding"),
                existing_attachments=self._state.get(
                    "runtime_executor_adapter_attachments"
                ),
            )
            self._state["runtime_executor_adapter_attachments"] = (
                executor_adapter_attachment["attachments"]
            )
            executor_invocation_preparation = (
                evaluate_executor_invocation_preparation(
                    executor_adapter_attachment.get("executor_adapter_attachment"),
                    existing_preparations=self._state.get(
                        "runtime_executor_invocation_preparations"
                    ),
                )
            )
            if executor_invocation_preparation.get(
                "executor_invocation_prepared"
            ) is True:
                self._state["runtime_executor_invocation_preparations"] = [
                    *self._state.get("runtime_executor_invocation_preparations", []),
                    executor_invocation_preparation,
                ]
            executor_invocation_approval = submit_executor_invocation_approval(
                executor_invocation_preparation,
                existing_approvals=self._state.get(
                    "runtime_executor_invocation_approvals"
                ),
            )
            self._state["runtime_executor_invocation_approvals"] = (
                executor_invocation_approval["approvals"]
            )
            executor_invocation_gate = submit_executor_invocation_gate(
                executor_invocation_approval.get("executor_invocation_approval"),
                existing_gates=self._state.get("runtime_executor_invocation_gates"),
            )
            self._state["runtime_executor_invocation_gates"] = (
                executor_invocation_gate["gates"]
            )
            executor_invocation_record = submit_executor_invocation_record(
                executor_invocation_gate.get("executor_invocation_gate"),
                existing_records=self._state.get(
                    "runtime_executor_invocation_records"
                ),
            )
            self._state["runtime_executor_invocation_records"] = (
                executor_invocation_record["records"]
            )
            executor_invocation_dispatch = submit_executor_invocation_dispatch(
                executor_invocation_record.get("executor_invocation_record"),
                existing_dispatches=self._state.get(
                    "runtime_executor_invocation_dispatches"
                ),
            )
            self._state["runtime_executor_invocation_dispatches"] = (
                executor_invocation_dispatch["dispatches"]
            )
            runtime_execution_session_start = (
                submit_runtime_execution_session_start(
                    executor_invocation_dispatch.get(
                        "executor_invocation_dispatch"
                    ),
                    existing_sessions=self._state.get(
                        "runtime_execution_session_starts"
                    ),
                )
            )
            self._state["runtime_execution_session_starts"] = (
                runtime_execution_session_start["sessions"]
            )
            runtime_execution_result_capture = (
                submit_runtime_execution_result_capture(
                    runtime_execution_session_start.get(
                        "runtime_execution_session_start"
                    ),
                    existing_results=self._state.get(
                        "runtime_execution_result_captures"
                    ),
                )
            )
            self._state["runtime_execution_result_captures"] = (
                runtime_execution_result_capture["results"]
            )
            runtime_executor_closure = submit_executor_runtime_closure(
                runtime_execution_result_capture.get(
                    "runtime_execution_result_capture"
                ),
                existing_closures=self._state.get("runtime_executor_closures"),
            )
            self._state["runtime_executor_closures"] = (
                runtime_executor_closure["closures"]
            )
            controlled_real_executor_unlock = (
                submit_controlled_real_executor_unlock(
                    runtime_executor_closure.get("runtime_executor_closure"),
                    safe_executor_adapter=self._controlled_real_executor_adapter,
                    existing_unlocks=self._state.get(
                        "controlled_real_executor_unlocks"
                    ),
                    runtime_operator_service_authorized=True,
                )
            )
            self._state["controlled_real_executor_unlocks"] = (
                controlled_real_executor_unlock["unlocks"]
            )
            mutation_request = dict(
                controlled_real_executor_unlock.get(
                    "controlled_real_executor_result"
                )
                or {}
            )
            launch_package = result.get("package") or {}
            if isinstance(launch_package, Mapping):
                mutation_request.update(
                    {
                        "target_root": launch_package.get("target_root"),
                        "authority_context": launch_package.get(
                            "authority_context",
                            {},
                        ),
                    }
                )

            controlled_mutation_unlock = submit_controlled_mutation_unlock(
                mutation_request,
                governed_mutation_adapter=self._controlled_mutation_adapter,
                existing_mutations=self._state.get("controlled_mutations"),
                runtime_operator_service_authorized=True,
            )
            self._state["controlled_mutations"] = controlled_mutation_unlock[
                "mutations"
            ]
            runtime_commit_apply = submit_runtime_commit_apply(
                controlled_mutation_unlock.get("controlled_mutation_result"),
                governed_commit_adapter=self._governed_commit_adapter,
                existing_commit_applies=self._state.get("runtime_commit_applies"),
            )
            self._state["runtime_commit_applies"] = runtime_commit_apply[
                "commit_apply_records"
            ]
            self._state.update(
                {
                    "runtime_session_id": result.get("runtime_session_id") or "",
                    "runtime_state": "active"
                    if result.get("autonomous_start_requested") is True
                    else "paused",
                    "current_tick": 0,
                    "current_cursor": result.get("work_package_id") or "",
                    "last_result": None,
                    "controller_started": result.get("autonomous_start_requested") is True,
                }
            )
        return {
            "schema": RUNTIME_OPERATOR_SERVICE_SCHEMA,
            "ok": result.get("ok") is True and queue_submit.get("queued") is True,
            "action": "run",
            "goal_id": result.get("goal_id") or "",
            "work_package_id": result.get("work_package_id") or "",
            "runtime_session_id": result.get("runtime_session_id") or "",
            "launch_admitted": result.get("launch_admitted") is True,
            "autonomous_start_requested": result.get("autonomous_start_requested") is True,
            "queued": queue_submit.get("queued") is True,
            "queue_status": queue_submit.get("queue_status") or "denied",
            "queue_admission": queue_submit.get("queue_admission"),
            "worker_pickup_status": (
                pickup.get("worker_pickup_status")
                if "pickup" in locals()
                else "denied"
            ),
            "worker_status": (
                pickup.get("worker_pickup_status")
                if "pickup" in locals()
                else "denied"
            ),
            "worker_pickup": pickup.get("worker_pickup_record") if "pickup" in locals() else None,
            "claimed": pickup.get("claimed") is True if "pickup" in locals() else False,
            "cycle_status": (
                cycle_binding.get("cycle_status")
                if "cycle_binding" in locals()
                else "denied"
            ),
            "cycle_binding": (
                cycle_binding.get("cycle_binding")
                if "cycle_binding" in locals()
                else None
            ),
            "cycle_bound": (
                cycle_binding.get("bound") is True
                if "cycle_binding" in locals()
                else False
            ),
            "execution_status": (
                execution_bridge.get("execution_status")
                if "execution_bridge" in locals()
                else "rejected"
            ),
            "execution_ready": (
                execution_bridge.get("execution_ready") is True
                if "execution_bridge" in locals()
                else False
            ),
            "execution_request": (
                execution_bridge.get("execution_request")
                if "execution_bridge" in locals()
                else None
            ),
            "loop_status": (
                loop_activation.get("loop_status")
                if "loop_activation" in locals()
                else "blocked"
            ),
            "tick_status": (
                loop_activation.get("tick_status")
                if "loop_activation" in locals()
                else "blocked"
            ),
            "controlled_loop_tick": (
                loop_activation.get("controlled_loop_tick")
                if "loop_activation" in locals()
                else None
            ),
            "decision_status": (
                tick_decision.get("decision_status")
                if "tick_decision" in locals()
                else "rejected"
            ),
            "decision_ready": (
                tick_decision.get("decision_ready") is True
                if "tick_decision" in locals()
                else False
            ),
            "controlled_tick_decision": (
                tick_decision.get("controlled_tick_decision")
                if "tick_decision" in locals()
                else None
            ),
            "proposal_status": (
                action_proposal.get("proposal_status")
                if "action_proposal" in locals()
                else "rejected"
            ),
            "action_proposed": (
                action_proposal.get("action_proposed") is True
                if "action_proposal" in locals()
                else False
            ),
            "action_proposal": (
                action_proposal.get("action_proposal")
                if "action_proposal" in locals()
                else None
            ),
            "authorization_status": (
                action_authorization.get("authorization_status")
                if "action_authorization" in locals()
                else "denied"
            ),
            "authorized": (
                action_authorization.get("authorized") is True
                if "action_authorization" in locals()
                else False
            ),
            "action_authorization": (
                action_authorization.get("action_authorization")
                if "action_authorization" in locals()
                else None
            ),
            "commit_status": (
                action_commit.get("commit_status")
                if "action_commit" in locals()
                else "rejected"
            ),
            "committed": (
                action_commit.get("committed") is True
                if "action_commit" in locals()
                else False
            ),
            "action_commit": (
                action_commit.get("action_commit")
                if "action_commit" in locals()
                else None
            ),
            "execution_admission_status": (
                execution_admission.get("execution_admission_status")
                if "execution_admission" in locals()
                else "denied"
            ),
            "execution_allowed": (
                execution_admission.get("execution_allowed") is True
                if "execution_admission" in locals()
                else False
            ),
            "execution_admission": (
                execution_admission.get("execution_admission")
                if "execution_admission" in locals()
                else None
            ),
            "permit_status": (
                execution_permit.get("permit_status")
                if "execution_permit" in locals()
                else "permit_denied"
            ),
            "execution_permitted": (
                execution_permit.get("execution_permitted") is True
                if "execution_permit" in locals()
                else False
            ),
            "execution_permit": (
                execution_permit.get("execution_permit")
                if "execution_permit" in locals()
                else None
            ),
            "executor_envelope_status": (
                executor_envelope.get("executor_envelope_status")
                if "executor_envelope" in locals()
                else "rejected"
            ),
            "execution_started": (
                executor_envelope.get("execution_started") is True
                if "executor_envelope" in locals()
                else False
            ),
            "executor_attached": (
                executor_envelope.get("executor_attached") is True
                if "executor_envelope" in locals()
                else False
            ),
            "executor_envelope": (
                executor_envelope.get("executor_envelope")
                if "executor_envelope" in locals()
                else None
            ),
            "adapter_binding_status": (
                executor_adapter_binding.get("adapter_binding_status")
                if "executor_adapter_binding" in locals()
                else "rejected"
            ),
            "executor_adapter_bound": (
                executor_adapter_binding.get("executor_adapter_bound") is True
                if "executor_adapter_binding" in locals()
                else False
            ),
            "executor_invoked": (
                executor_adapter_binding.get("executor_invoked") is True
                if "executor_adapter_binding" in locals()
                else False
            ),
            "executor_adapter_binding": (
                executor_adapter_binding.get("executor_adapter_binding")
                if "executor_adapter_binding" in locals()
                else None
            ),
            "adapter_attachment_status": (
                executor_adapter_attachment.get("adapter_attachment_status")
                if "executor_adapter_attachment" in locals()
                else "rejected"
            ),
            "executor_adapter_attached": (
                executor_adapter_attachment.get("executor_adapter_attached") is True
                if "executor_adapter_attachment" in locals()
                else False
            ),
            "executor_invoked": (
                executor_invocation_dispatch.get("executor_invoked") is True
                if "executor_invocation_dispatch" in locals()
                else (
                    executor_adapter_attachment.get("executor_invoked") is True
                    if "executor_adapter_attachment" in locals()
                    else (
                        executor_adapter_binding.get("executor_invoked") is True
                        if "executor_adapter_binding" in locals()
                        else False
                    )
                )
            ),
            "execution_started": (
                runtime_execution_session_start.get("execution_started") is True
                if "runtime_execution_session_start" in locals()
                else (
                    executor_adapter_attachment.get("execution_started") is True
                    if "executor_adapter_attachment" in locals()
                    else (
                        executor_envelope.get("execution_started") is True
                        if "executor_envelope" in locals()
                        else False
                    )
                )
            ),
            "executor_adapter_attachment": (
                executor_adapter_attachment.get("executor_adapter_attachment")
                if "executor_adapter_attachment" in locals()
                else None
            ),
            "invocation_approval_status": (
                executor_invocation_approval.get("invocation_approval_status")
                if "executor_invocation_approval" in locals()
                else "rejected"
            ),
            "executor_invocation_approved": (
                executor_invocation_approval.get("executor_invocation_approved") is True
                if "executor_invocation_approval" in locals()
                else False
            ),
            "executor_invocation_approval": (
                executor_invocation_approval.get("executor_invocation_approval")
                if "executor_invocation_approval" in locals()
                else None
            ),
            "invocation_gate_status": (
                executor_invocation_gate.get("invocation_gate_status")
                if "executor_invocation_gate" in locals()
                else "rejected"
            ),
            "executor_invocation_gate_open": (
                executor_invocation_gate.get("executor_invocation_gate_open") is True
                if "executor_invocation_gate" in locals()
                else False
            ),
            "executor_invocation_gate": (
                executor_invocation_gate.get("executor_invocation_gate")
                if "executor_invocation_gate" in locals()
                else None
            ),
            "invocation_record_status": (
                executor_invocation_record.get("invocation_record_status")
                if "executor_invocation_record" in locals()
                else "rejected"
            ),
            "executor_invocation_recorded": (
                executor_invocation_record.get("executor_invocation_recorded") is True
                if "executor_invocation_record" in locals()
                else False
            ),
            "executor_invocation_record": (
                executor_invocation_record.get("executor_invocation_record")
                if "executor_invocation_record" in locals()
                else None
            ),
            "executor_invocation_dispatch_status": (
                executor_invocation_dispatch.get(
                    "executor_invocation_dispatch_status"
                )
                if "executor_invocation_dispatch" in locals()
                else "rejected"
            ),
            "executor_invocation_dispatch": (
                executor_invocation_dispatch.get("executor_invocation_dispatch")
                if "executor_invocation_dispatch" in locals()
                else None
            ),
            "runtime_execution_session_start_status": (
                runtime_execution_session_start.get(
                    "runtime_execution_session_start_status"
                )
                if "runtime_execution_session_start" in locals()
                else "rejected"
            ),
            "execution_dry_run": (
                runtime_execution_session_start.get("execution_dry_run") is True
                if "runtime_execution_session_start" in locals()
                else False
            ),
            "mutation_allowed": (
                controlled_mutation_unlock.get("mutation_allowed") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "runtime_execution_session_start": (
                runtime_execution_session_start.get(
                    "runtime_execution_session_start"
                )
                if "runtime_execution_session_start" in locals()
                else None
            ),
            "runtime_execution_result_capture_status": (
                runtime_execution_result_capture.get(
                    "runtime_execution_result_capture_status"
                )
                if "runtime_execution_result_capture" in locals()
                else "rejected"
            ),
            "execution_completed": (
                runtime_execution_result_capture.get("execution_completed") is True
                if "runtime_execution_result_capture" in locals()
                else False
            ),
            "execution_result_recorded": (
                runtime_execution_result_capture.get(
                    "execution_result_recorded"
                )
                is True
                if "runtime_execution_result_capture" in locals()
                else False
            ),
            "runtime_execution_result_capture": (
                runtime_execution_result_capture.get(
                    "runtime_execution_result_capture"
                )
                if "runtime_execution_result_capture" in locals()
                else None
            ),
            "runtime_executor_closure_status": (
                runtime_executor_closure.get("runtime_executor_closure_status")
                if "runtime_executor_closure" in locals()
                else "rejected"
            ),
            "feedback_recorded": (
                runtime_executor_closure.get("feedback_recorded") is True
                if "runtime_executor_closure" in locals()
                else False
            ),
            "recovery_handoff_recorded": (
                runtime_executor_closure.get("recovery_handoff_recorded") is True
                if "runtime_executor_closure" in locals()
                else False
            ),
            "memory_handoff_recorded": (
                runtime_executor_closure.get("memory_handoff_recorded") is True
                if "runtime_executor_closure" in locals()
                else False
            ),
            "recovery_connected": (
                runtime_executor_closure.get("recovery_connected") is True
                if "runtime_executor_closure" in locals()
                else False
            ),
            "memory_connected": (
                runtime_executor_closure.get("memory_connected") is True
                if "runtime_executor_closure" in locals()
                else False
            ),
            "real_executor_ready": (
                runtime_executor_closure.get("real_executor_ready") is True
                if "runtime_executor_closure" in locals()
                else False
            ),
            "real_executor_enabled": (
                controlled_real_executor_unlock.get("real_executor_enabled") is True
                if "controlled_real_executor_unlock" in locals()
                else False
            ),
            "execution_real": (
                controlled_real_executor_unlock.get("execution_real") is True
                if "controlled_real_executor_unlock" in locals()
                else False
            ),
            "repo_mutation_enabled": (
                controlled_real_executor_unlock.get("repo_mutation_enabled") is True
                if "controlled_real_executor_unlock" in locals()
                else False
            ),
            "runtime_executor_closure": (
                runtime_executor_closure.get("runtime_executor_closure")
                if "runtime_executor_closure" in locals()
                else None
            ),
            "controlled_real_executor_unlock_status": (
                controlled_real_executor_unlock.get(
                    "controlled_real_executor_unlock_status"
                )
                if "controlled_real_executor_unlock" in locals()
                else "rejected"
            ),
            "controlled_real_executor_result": (
                controlled_real_executor_unlock.get(
                    "controlled_real_executor_result"
                )
                if "controlled_real_executor_unlock" in locals()
                else None
            ),
            "controlled_mutation_status": (
                controlled_mutation_unlock.get("controlled_mutation_status")
                if "controlled_mutation_unlock" in locals()
                else "rejected"
            ),
            "controlled_mutation": (
                controlled_mutation_unlock.get("controlled_mutation") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "mutation_started": (
                controlled_mutation_unlock.get("mutation_started") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "mutation_completed": (
                controlled_mutation_unlock.get("mutation_completed") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "validation_passed": (
                controlled_mutation_unlock.get("validation_passed") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "rollback_completed": (
                controlled_mutation_unlock.get("rollback_completed") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "commit_allowed": (
                controlled_mutation_unlock.get("commit_allowed") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "rollback_available": (
                controlled_mutation_unlock.get("rollback_available") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "validation_required": (
                controlled_mutation_unlock.get("validation_required") is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "governed_mutation_adapter_attached": (
                controlled_mutation_unlock.get("governed_mutation_adapter_attached")
                is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "autonomous_runtime_loop_closed": (
                controlled_mutation_unlock.get("autonomous_runtime_loop_closed")
                is True
                if "controlled_mutation_unlock" in locals()
                else False
            ),
            "controlled_mutation_result": (
                controlled_mutation_unlock.get("controlled_mutation_result")
                if "controlled_mutation_unlock" in locals()
                else None
            ),
            "runtime_commit_apply_status": (
                runtime_commit_apply.get("runtime_commit_apply_status")
                if "runtime_commit_apply" in locals()
                else "rejected"
            ),
            "commit_applied": (
                runtime_commit_apply.get("commit_applied") is True
                if "runtime_commit_apply" in locals()
                else False
            ),
            "commit_recorded": (
                runtime_commit_apply.get("commit_recorded") is True
                if "runtime_commit_apply" in locals()
                else False
            ),
            "commit_id": (
                runtime_commit_apply.get("commit_id")
                if "runtime_commit_apply" in locals()
                else ""
            ),
            "git_diff_recorded": (
                runtime_commit_apply.get("git_diff_recorded") is True
                if "runtime_commit_apply" in locals()
                else False
            ),
            "runtime_commit_apply_result": (
                runtime_commit_apply.get("runtime_commit_apply_result")
                if "runtime_commit_apply" in locals()
                else None
            ),
            "denial_reason": result.get("denial_reason")
            or queue_submit.get("denial_reason")
            or (pickup.get("denial_reason") if "pickup" in locals() else "")
            or (
                cycle_binding.get("denial_reason")
                if "cycle_binding" in locals()
                else ""
            )
            or (
                execution_bridge.get("denial_reason")
                if "execution_bridge" in locals()
                else ""
            )
            or (
                loop_activation.get("denial_reason")
                if "loop_activation" in locals()
                else ""
            )
            or (
                tick_decision.get("denial_reason")
                if "tick_decision" in locals()
                else ""
            )
            or (
                action_proposal.get("denial_reason")
                if "action_proposal" in locals()
                else ""
            )
            or (
                action_authorization.get("denial_reason")
                if "action_authorization" in locals()
                else ""
            )
            or (
                action_commit.get("denial_reason")
                if "action_commit" in locals()
                else ""
            )
            or (
                execution_admission.get("denial_reason")
                if "execution_admission" in locals()
                else ""
            )
            or (
                execution_permit.get("denial_reason")
                if "execution_permit" in locals()
                else ""
            )
            or (
                executor_envelope.get("denial_reason")
                if "executor_envelope" in locals()
                else ""
            )
            or (
                executor_adapter_binding.get("denial_reason")
                if "executor_adapter_binding" in locals()
                else ""
            )
            or (
                executor_adapter_attachment.get("denial_reason")
                if "executor_adapter_attachment" in locals()
                else ""
            )
            or (
                executor_invocation_preparation.get("denial_reason")
                if "executor_invocation_preparation" in locals()
                else ""
            )
            or (
                executor_invocation_approval.get("denial_reason")
                if "executor_invocation_approval" in locals()
                else ""
            )
            or (
                executor_invocation_gate.get("denial_reason")
                if "executor_invocation_gate" in locals()
                else ""
            )
            or (
                executor_invocation_record.get("denial_reason")
                if "executor_invocation_record" in locals()
                else ""
            )
            or (
                executor_invocation_dispatch.get("denial_reason")
                if "executor_invocation_dispatch" in locals()
                else ""
            )
            or (
                runtime_execution_session_start.get("denial_reason")
                if "runtime_execution_session_start" in locals()
                else ""
            )
            or (
                runtime_execution_result_capture.get("denial_reason")
                if "runtime_execution_result_capture" in locals()
                else ""
            )
            or (
                runtime_executor_closure.get("denial_reason")
                if "runtime_executor_closure" in locals()
                else ""
            )
            or (
                controlled_real_executor_unlock.get("denial_reason")
                if "controlled_real_executor_unlock" in locals()
                else ""
            )
            or (
                controlled_mutation_unlock.get("denial_reason")
                if "controlled_mutation_unlock" in locals()
                else ""
            )
            or (
                runtime_commit_apply.get("denial_reason")
                if "runtime_commit_apply" in locals()
                else ""
            )
            or "",
            "launch": result,
            "status": self.status(),
            "runtime_state_mutated": False,
            "task_executed": False,
            "direct_dispatch_requested": False,
        }

    def queue_status(self) -> dict[str, Any]:
        return build_queue_state(self._state.get("queue_entries"))

    def cycle_status(self) -> dict[str, Any]:
        return build_cycle_context_state(self._state.get("cycle_bindings"))

    def execution_status(self) -> dict[str, Any]:
        return build_execution_request_state(self._state.get("execution_requests"))

    def loop_status(self) -> dict[str, Any]:
        return build_controlled_loop_state(self._state.get("controlled_loop_ticks"))

    def decision_status(self) -> dict[str, Any]:
        return build_controlled_tick_decision_state(
            self._state.get("controlled_tick_decisions")
        )

    def proposal_status(self) -> dict[str, Any]:
        return build_controlled_action_proposal_state(
            self._state.get("controlled_action_proposals")
        )

    def authorization_status(self) -> dict[str, Any]:
        return build_controlled_action_authorization_state(
            self._state.get("controlled_action_authorizations")
        )

    def commit_status(self) -> dict[str, Any]:
        return build_controlled_action_commit_state(
            self._state.get("controlled_action_commits")
        )

    def execution_admission_status(self) -> dict[str, Any]:
        return build_runtime_execution_admission_state(
            self._state.get("runtime_execution_admissions")
        )

    def execution_permit_status(self) -> dict[str, Any]:
        return build_runtime_execution_permit_state(
            self._state.get("runtime_execution_permits")
        )

    def executor_envelope_status(self) -> dict[str, Any]:
        return build_runtime_executor_envelope_state(
            self._state.get("runtime_executor_envelopes")
        )

    def adapter_binding_status(self) -> dict[str, Any]:
        return build_runtime_executor_adapter_binding_state(
            self._state.get("runtime_executor_adapter_bindings")
        )

    def adapter_attachment_status(self) -> dict[str, Any]:
        return build_runtime_executor_adapter_attachment_state(
            self._state.get("runtime_executor_adapter_attachments")
        )

    def invocation_approval_status(self) -> dict[str, Any]:
        return build_runtime_executor_invocation_approval_state(
            self._state.get("runtime_executor_invocation_approvals")
        )

    def invocation_gate_status(self) -> dict[str, Any]:
        return build_runtime_executor_invocation_gate_state(
            self._state.get("runtime_executor_invocation_gates")
        )

    def invocation_record_status(self) -> dict[str, Any]:
        return build_runtime_executor_invocation_record_state(
            self._state.get("runtime_executor_invocation_records")
        )

    def executor_invocation_dispatch_status(self) -> dict[str, Any]:
        return build_runtime_executor_invocation_dispatch_state(
            self._state.get("runtime_executor_invocation_dispatches")
        )

    def runtime_execution_session_start_status(self) -> dict[str, Any]:
        return build_runtime_execution_session_start_state(
            self._state.get("runtime_execution_session_starts")
        )

    def runtime_execution_result_capture_status(self) -> dict[str, Any]:
        return build_runtime_execution_result_capture_state(
            self._state.get("runtime_execution_result_captures")
        )

    def runtime_executor_closure_status(self) -> dict[str, Any]:
        return build_runtime_executor_closure_state(
            self._state.get("runtime_executor_closures")
        )

    def controlled_real_executor_unlock_status(self) -> dict[str, Any]:
        return build_controlled_real_executor_unlock_state(
            self._state.get("controlled_real_executor_unlocks")
        )

    def controlled_mutation_status(self) -> dict[str, Any]:
        return build_controlled_mutation_state(
            self._state.get("controlled_mutations")
        )

    def runtime_commit_apply_status(self) -> dict[str, Any]:
        return build_runtime_commit_apply_state(
            self._state.get("runtime_commit_applies")
        )


__all__ = [
    "RUNTIME_OPERATOR_SERVICE_SCHEMA",
    "RuntimeOperatorService",
]
