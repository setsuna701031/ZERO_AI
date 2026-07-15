from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_active_execution_authorization import authorize_active_execution
from core.runtime.runtime_apply_execution_plan_builder import build_runtime_apply_execution_plan
from core.runtime.runtime_change_proposal_engine import build_runtime_change_proposal
from core.runtime.runtime_controlled_apply_admission import RuntimeControlledApplyAdmission
from core.runtime.runtime_controlled_execution_activation import activate_controlled_execution
from core.runtime.runtime_execution_plan_review_gate import review_execution_plan
from core.runtime.runtime_operator_approval_gate import RuntimeOperatorApprovalGate
from core.runtime.runtime_transactional_active_execution import (BUNDLE_CONTRACT, REQUEST_CONTRACT, execute_transactional_active_plan)
from core.runtime.runtime_operator_session import (CONTRACT, INPUT_CONTRACT, add_checkpoint, fingerprint,
    load_runtime_session, root_identity, save_runtime_session, seal_session, set_artifact, time_text, transition, validate_session)

ARTIFACT_NAMES = ("proposal", "approval", "admission", "execution_plan", "plan_review",
    "controlled_execution_request", "controlled_execution_result", "active_authorization",
    "active_authorization_result", "candidate_bundle", "invocation_request", "transaction_result", "final_evidence")
ACTION_TO_INPUT = {"operator_approval": "proposal_approval", "execution_plan_review": "execution_plan_review",
    "controlled_execution_request": "controlled_execution_request", "active_execution_authorization": "active_execution_authorization",
    "candidate_bundle": "candidate_bundle", "transactional_invocation": "transactional_invocation"}
ACTION_CONTRACT = {"operator_approval": "zero.runtime.operator_approval_gate.v1",
    "execution_plan_review": "zero.runtime.execution_plan_operator_review.v1",
    "controlled_execution_request": "zero.runtime.operator_execution_request.v1",
    "active_execution_authorization": "zero.runtime.active_authorization_request.v1",
    "candidate_bundle": BUNDLE_CONTRACT, "transactional_invocation": REQUEST_CONTRACT}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}

def _proposal(natural_task: Any, task_id: str, config: Mapping[str, Any]) -> dict[str, Any]:
    supplied = _mapping(config.get("proposal")) or _mapping(_mapping(natural_task).get("proposal_artifact"))
    if supplied: return supplied
    task = str(_mapping(natural_task).get("text") or _mapping(natural_task).get("task") or natural_task).strip()
    targets = list(_mapping(natural_task).get("target_files") or config.get("target_files") or [])
    return build_runtime_change_proposal(goal=task, task_id=task_id,
        runner_result={"ok": False, "changed_files": targets},
        workspace_observation={}, repair_advice={"repair_needed": True, "advisor_status": "repair_advised",
            "failure_category": "validation_failure", "repairability": "likely_repairable", "failure_reasons": ["operator_requested_change"]})

def _pause(session: Mapping[str, Any], status: str, phase: str, action: str, *, now: Any, operator_id: str = "") -> dict[str, Any]:
    value = transition(session, status, phase=phase, now=now); value["required_action"] = action
    value["required_input_contract"] = ACTION_CONTRACT[action]; value["pause_reason"] = f"{action}_required"
    value = add_checkpoint(value, phase, outputs=[value.get("artifact_fingerprints", {}).get(name, "") for name in ARTIFACT_NAMES if value.get("artifacts", {}).get(name) is not None], required_next_action=action, operator_id=operator_id, now=now)
    return seal_session(value)

def create_runtime_session(natural_task: Any, *, target_root: Any, workspace_root: Any,
                           session_path: Any = None, now: Any = None,
                           runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = _mapping(runtime_config); at = time_text(now); expiry = time_text(config.get("session_expires_at") or (datetime.fromisoformat(at) + timedelta(days=7)))
    natural = _mapping(natural_task) or {"text": str(natural_task)}
    task_id = str(natural.get("task_id") or f"natural-task-{fingerprint(natural)[:16]}")
    seed = {"task_id": task_id, "natural_task": natural, "target": root_identity(target_root), "workspace": root_identity(workspace_root), "created_at": at}
    session = {"contract": CONTRACT, "session_id": f"runtime-session-{fingerprint(seed)[:20]}", "session_status": "created",
        "task_id": task_id, "natural_task": natural, "created_at": at, "updated_at": at, "expires_at": expiry,
        "target_root_identity": seed["target"], "workspace_root_identity": seed["workspace"], "operator_context": {},
        "current_phase": "session_created", "required_action": "none", "required_input_contract": None,
        "checkpoints": [], "artifacts": {name: None for name in ARTIFACT_NAMES}, "artifact_fingerprints": {},
        "identity_chain": {}, "phase_history": [], "pause_reason": None, "failure": None, "completed": False,
        "processed_input_ids": [], "operator_actions": [], "audit_record": {"event_type": "runtime_session_created", "created_at": at}}
    session = seal_session(session); session = transition(session, "running", phase="proposal_building", now=now)
    proposal = _proposal(natural, task_id, config); session = set_artifact(session, "proposal", proposal)
    session["identity_chain"]["proposal_id"] = proposal.get("proposal_id"); session = seal_session(session)
    session = _pause(session, "waiting_for_operator_approval", "proposal_ready", "operator_approval", now=now)
    if session_path is not None: session = save_runtime_session(session, session_path)
    return session

def _block(session: Mapping[str, Any], reasons: list[str], *, now: Any, critical: bool = False) -> dict[str, Any]:
    value = transition(session, "failed" if critical else "blocked", phase="critical_failure" if critical else "blocked", now=now)
    value["failure"] = {"critical": critical, "reasons": reasons}; value["required_action"] = "none"; value["required_input_contract"] = None
    return seal_session(value)

def _input(session: Mapping[str, Any], operator_input: Any, now: Any) -> tuple[dict[str, Any], dict[str, Any], bool]:
    envelope = _mapping(operator_input)
    if envelope.get("contract") != INPUT_CONTRACT: raise ValueError("invalid_operator_input_contract")
    if envelope.get("session_id") != session.get("session_id"): raise ValueError("operator_input_session_mismatch")
    if not str(envelope.get("input_id") or "").strip() or not str(envelope.get("operator_id") or "").strip(): raise ValueError("operator_identity_required")
    if envelope["input_id"] in session.get("processed_input_ids", []): return _mapping(session), envelope, True
    if envelope.get("input_type") != ACTION_TO_INPUT.get(session.get("required_action")): raise ValueError("wrong_phase_input")
    try:
        if datetime.fromisoformat(time_text(envelope.get("submitted_at"))) > datetime.fromisoformat(time_text(now or datetime.now(timezone.utc))) + timedelta(minutes=5): raise ValueError("operator_input_from_future")
    except (TypeError, ValueError) as exc: raise ValueError("invalid_operator_input_time") from exc
    return _mapping(session), envelope, False

def resume_runtime_session(session: Mapping[str, Any], *, operator_input: Any = None, target_root: Any = None,
                           workspace_root: Any = None, now: Any = None, runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = _mapping(runtime_config); original = _mapping(session)
    reasons = validate_session(original, target_root=target_root, workspace_root=workspace_root, now=now)
    if reasons: raise ValueError(";".join(reasons))
    if original.get("session_status") in {"completed", "blocked", "failed", "expired", "cancelled"}: return original
    value, envelope, duplicate = _input(original, operator_input, now)
    if duplicate: return value
    payload = _mapping(envelope.get("payload")); operator = str(envelope["operator_id"])
    value = transition(value, "running" if value["session_status"] != "waiting_for_transaction_invocation" else "transaction_running", now=now)
    action = original["required_action"]
    try:
        if action == "operator_approval":
            proposal = value["artifacts"]["proposal"]
            approval = payload if payload.get("schema") == "zero.runtime.operator_approval_gate.v1" else RuntimeOperatorApprovalGate(clock=lambda: time_text(now)).review(proposal=proposal, operator_id=operator, **payload)
            value = set_artifact(value, "approval", approval)
            if approval.get("approval_status") != "approved": value = _block(value, [approval.get("reason") or "approval_not_approved"], now=now)
            else:
                admission = RuntimeControlledApplyAdmission(clock=lambda: time_text(now)).admit(proposal=proposal, approval_record=approval, controlled=True, now=now)
                plan = build_runtime_apply_execution_plan(proposal=proposal, approval_record=approval, admission_record=admission, now=now)
                value = set_artifact(set_artifact(value, "admission", admission), "execution_plan", plan)
                if plan.get("plan_status") != "ready": value = _block(value, [plan.get("plan_status", "plan_not_ready")], now=now)
                else: value = _pause(value, "waiting_for_plan_review", "execution_plan_ready", "execution_plan_review", now=now, operator_id=operator)
        elif action == "execution_plan_review":
            result = review_execution_plan(value["artifacts"]["execution_plan"], payload, now=now); value = set_artifact(value, "plan_review", result)
            if result.get("review_status") != "approved": value = _block(value, list(result.get("reasons") or ["plan_review_not_approved"]), now=now)
            else: value = _pause(value, "waiting_for_active_authorization", "plan_review_approved", "controlled_execution_request", now=now, operator_id=operator)
        elif action == "controlled_execution_request":
            value = set_artifact(value, "controlled_execution_request", payload)
            result = activate_controlled_execution(value["artifacts"]["execution_plan"], value["artifacts"]["plan_review"], payload, target_root=target_root, now=now, runtime_config=config)
            value = set_artifact(value, "controlled_execution_result", result)
            if result.get("activation_status") != "completed": value = _block(value, list(result.get("reasons") or ["dry_run_blocked"]), now=now)
            else: value = _pause(value, "waiting_for_active_authorization", "controlled_dry_run_completed", "active_execution_authorization", now=now, operator_id=operator)
        elif action == "active_execution_authorization":
            value = set_artifact(value, "active_authorization", payload); result = authorize_active_execution(value["artifacts"]["controlled_execution_result"], payload, now=now)
            value = set_artifact(value, "active_authorization_result", result)
            if result.get("authorization_status") != "authorized": value = _block(value, list(result.get("reasons") or ["active_authorization_not_authorized"]), now=now)
            else: value = _pause(value, "waiting_for_candidate_bundle", "active_execution_prepared", "candidate_bundle", now=now, operator_id=operator)
        elif action == "candidate_bundle":
            auth = value["artifacts"]["active_authorization_result"]
            expected_scope = auth.get("authorized_scope")
            files = payload.get("files") if isinstance(payload.get("files"), list) else []
            scope = [str(item.get("relative_path", "")).replace("\\", "/") for item in files if isinstance(item, Mapping)]
            bundle_copy = deepcopy(payload); claimed = bundle_copy.pop("bundle_fingerprint", None)
            bundle_reasons = []
            if payload.get("contract") != BUNDLE_CONTRACT: bundle_reasons.append("invalid_candidate_bundle_contract")
            if payload.get("plan_id") != auth.get("plan_id") or payload.get("authorization_result_id") != auth.get("authorization_result_id"): bundle_reasons.append("candidate_identity_mismatch")
            if scope != expected_scope: bundle_reasons.append("candidate_scope_mismatch")
            if claimed != fingerprint(bundle_copy): bundle_reasons.append("candidate_fingerprint_mismatch")
            if bundle_reasons: value = _block(value, bundle_reasons, now=now)
            else:
                value = set_artifact(value, "candidate_bundle", payload); value = _pause(value, "waiting_for_transaction_invocation", "candidate_bundle_ready", "transactional_invocation", now=now, operator_id=operator)
        elif action == "transactional_invocation":
            value = set_artifact(value, "invocation_request", payload)
            result = execute_transactional_active_plan(value["artifacts"]["active_authorization_result"], payload, value["artifacts"]["candidate_bundle"], target_root=target_root, transaction_workspace_root=workspace_root, now=now, runtime_config=config)
            value = set_artifact(value, "transaction_result", result); status = result.get("transaction_status")
            if status == "rollback_failed": value = _block(value, list(result.get("reasons") or [status]), now=now, critical=True)
            elif status == "blocked": value = _block(value, list(result.get("reasons") or [status]), now=now)
            else:
                value = transition(value, "completed", phase="transaction_completed" if status == "committed" else "transaction_rolled_back", now=now); value["completed"] = True
                evidence = build_runtime_session_final_evidence(value); value = set_artifact(value, "final_evidence", evidence); value["required_action"] = "none"; value["required_input_contract"] = None; value["pause_reason"] = None
        else: raise ValueError("unsupported_required_action")
    finally:
        value.setdefault("processed_input_ids", []).append(envelope["input_id"])
        value.setdefault("operator_actions", []).append({"input_id": envelope["input_id"], "input_type": envelope["input_type"], "operator_id": operator, "submitted_at": envelope.get("submitted_at")})
    return seal_session(value)

def build_runtime_session_final_evidence(session: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = session.get("artifacts", {}); tx = artifacts.get("transaction_result") or {}
    value = {"contract": "zero.runtime.operator_session_final_evidence.v1", "session_id": session.get("session_id"), "task_id": session.get("task_id"),
        "natural_task_fingerprint": fingerprint(session.get("natural_task")), "identity_chain": deepcopy(session.get("identity_chain")),
        "final_transaction_status": tx.get("transaction_status"), "validation_status": tx.get("validation_status"), "rollback_status": tx.get("rollback_status"),
        "committed_paths": deepcopy(tx.get("committed_paths") or tx.get("changed_files") or []), "rolled_back_paths": deepcopy(tx.get("rolled_back_paths") or []),
        "operator_actions_timeline": deepcopy(session.get("operator_actions")), "phase_checkpoints": deepcopy(session.get("checkpoints")), "session_audit_chain": deepcopy(session.get("phase_history"))}
    value["outcome"] = "transaction_committed" if tx.get("transaction_status") == "committed" else "transaction_rolled_back"
    value["final_evidence_fingerprint"] = fingerprint(value); return value

def cancel_runtime_session(session: Mapping[str, Any], *, operator_id: str, now: Any = None) -> dict[str, Any]:
    if not str(operator_id).strip(): raise ValueError("operator_id_required")
    if session.get("session_status") in {"completed", "failed", "cancelled"}: return _mapping(session)
    value = transition(session, "cancelled", phase="cancelled", now=now); value["required_action"] = "none"; value["required_input_contract"] = None
    return seal_session(value)

__all__ = ["build_runtime_session_final_evidence", "cancel_runtime_session", "create_runtime_session", "load_runtime_session", "resume_runtime_session", "save_runtime_session"]
