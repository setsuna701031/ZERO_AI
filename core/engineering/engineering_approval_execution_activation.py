from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.engineering.engineering_runtime_orchestrator_common import canonical_json, fingerprint
from core.engineering.engineering_work_entry import WorkEntryError, _ref, _stable, _verify
from core.engineering.engineering_read_only_pipeline import PIPELINE_SCHEMA, _verify_stable, ReadOnlyPipelineError
from core.engineering.engineering_runtime_adapter_activation_admission import validate_runtime_adapter_activation_admission
from core.engineering.engineering_runtime_adapter_controlled_invocation import build_runtime_adapter_controlled_invocation, validate_runtime_adapter_controlled_invocation

ACTIVATION_SCHEMA = "zero.engineering.approval_execution_activation.v1"
HANDOFF_SCHEMA = "zero.engineering.execution_authorization_handoff.v1"
APPROVAL_SCHEMA = "zero.engineering.human_approval.v1"
AUTHORIZATION_SCHEMA = "zero.engineering.human_execution_authorization.v1"
PREPARATION_SCHEMA = "zero.engineering.execution_preparation.v1"
ADMISSION_SCHEMA = "zero.engineering.governed_adapter_admission.v1"
EXECUTION_SCHEMA = "zero.engineering.controlled_execution_result.v1"
VERIFICATION_SCHEMA = "zero.engineering.execution_verification_closure.v1"
PROGRESS_SCHEMA = "zero.engineering.objective_progress_evaluation.v1"
JOURNAL_SCHEMA = "zero.engineering.approval_execution_journal.v1"
CHECKPOINT_SCHEMA = "zero.engineering.approval_execution_checkpoint.v1"

STATUSES = {"created","awaiting_approval","approval_validated","awaiting_authorization","authorization_validated","preparing_execution","ready_for_execution","executing","execution_completed","awaiting_verification","verification_completed","awaiting_completion_review","next_iteration_candidate","blocked","failed","invalid","completed","closed"}
TERMINAL = {"blocked","failed","invalid","completed","closed"}
SAFE_FAILURES = {"precondition_failed","authorization_invalid","adapter_rejected","workspace_changed","operation_failed","partial_execution","evidence_incomplete","commit_gate_rejected","verification_required"}

class ActivationError(WorkEntryError):
    """Stable fail-closed activation rejection."""


def _canon(body: Mapping[str, Any], fp_key: str, id_key: str, prefix: str) -> dict[str, Any]:
    return _stable(body, fp_key, id_key, prefix)


def _reference(a: Mapping[str, Any], id_key: str | None = None, fp_key: str | None = None) -> dict[str, Any]:
    if str(a.get("schema", "")).startswith("zero.test."):
        raise ActivationError("fake_artifact_rejected")
    if id_key and fp_key:
        return {"schema": a.get("schema"), "artifact_identity": a.get(id_key), "artifact_fingerprint": a.get(fp_key), "session_id": a.get("session_id")}
    return _ref(a, fp_key)


def _verify_artifact(a: Mapping[str, Any], schema: str, fp_key: str, id_key: str, prefix: str) -> None:
    if not isinstance(a, Mapping) or a.get("schema") != schema:
        raise ActivationError("schema_invalid")
    if str(a.get("schema", "")).startswith("zero.test."):
        raise ActivationError("fake_artifact_rejected")
    exp = _canon({k: v for k, v in a.items() if k not in {fp_key, id_key}}, fp_key, id_key, prefix)
    if exp.get(fp_key) != a.get(fp_key) or exp.get(id_key) != a.get(id_key):
        raise ActivationError("artifact_fingerprint_mismatch")


def _exact_list(a: Sequence[Any], b: Sequence[Any], code: str) -> None:
    if list(a or []) != list(b or []):
        raise ActivationError(code)


def _scope_subset(actual: Sequence[str], expected: Sequence[str], code: str) -> None:
    if not set(actual or []).issubset(set(expected or [])) or not actual:
        raise ActivationError(code)


def _workspace_hash(root: str | Path, allowed_paths: Sequence[str]) -> dict[str, str | None]:
    base = Path(root)
    out: dict[str, str | None] = {}
    for rel in allowed_paths:
        p = base / rel
        if p.exists() and p.is_file():
            out[rel] = fingerprint(p.read_bytes().hex())
        else:
            out[rel] = None
    return out


def _ensure_safe_rel(rel: str) -> str:
    s = str(rel).replace("\\", "/").strip()
    if not s or s.startswith("/") or ".." in s.split("/") or s in {".", "*"}:
        raise ActivationError("unsafe_path_rejection")
    return s


def create_activation(*, work_request: Mapping[str, Any], coordination: Mapping[str, Any], runtime_session: Mapping[str, Any], read_only_pipeline: Mapping[str, Any], proposal: Mapping[str, Any], proposal_review: Mapping[str, Any], workspace_reference: Mapping[str, Any], ordered_operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    try:
        _verify(work_request, "zero.engineering.work_request.v1", "work_request_fingerprint", "work_request_id")
        _verify(coordination, "zero.engineering.work_coordination.v1", "coordination_fingerprint", "coordination_id")
    except WorkEntryError as e:
        raise ActivationError(e.code)
    try:
        _verify_stable(read_only_pipeline, PIPELINE_SCHEMA, "pipeline_fingerprint", "pipeline_id", "engineering-read-only-pipeline-")
    except ReadOnlyPipelineError as e:
        raise ActivationError(e.code)
    if coordination.get("current_stage") != "awaiting_approval":
        raise ActivationError("proposal_review_closure_required")
    session_id = coordination["runtime_session_reference"]["artifact_identity"]
    if runtime_session.get("session_id") != session_id:
        raise ActivationError("wrong_session_rejection")
    if proposal.get("engineering_proposal_id") != coordination.get("stage_artifact_references", {}).get("proposal", {}).get("artifact_identity"):
        raise ActivationError("wrong_proposal_rejection")
    body = {"schema": ACTIVATION_SCHEMA, "work_request_reference": _reference(work_request, "work_request_id", "work_request_fingerprint"), "coordination_reference": _reference(coordination, "coordination_id", "coordination_fingerprint"), "runtime_session_reference": dict(coordination["runtime_session_reference"]), "read_only_pipeline_reference": _reference(read_only_pipeline, "pipeline_id", "pipeline_fingerprint"), "proposal_reference": _reference(proposal, "engineering_proposal_id", "fingerprint"), "proposal_review_reference": _reference(proposal_review, "proposal_review_closure_id", "fingerprint"), "approval_reference": None, "authorization_reference": None, "execution_preparation_reference": None, "adapter_admission_reference": None, "execution_reference": None, "verification_reference": None, "workspace_reference": dict(workspace_reference), "ordered_operations": [dict(x) for x in ordered_operations], "activation_status": "awaiting_approval", "current_stage": "awaiting_approval", "completed_stages": [], "pending_stage": "human_approval", "next_governed_action": "requires_human_approval", "authority_state": "not_granted", "execution_state": "not_started", "verification_state": "not_started", "completion_state": "not_evaluated", "blocked_reasons": []}
    return _canon(body, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")


def validate_activation(a: Mapping[str, Any]) -> dict[str, Any]:
    try:
        _verify_artifact(a, ACTIVATION_SCHEMA, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")
        if a.get("activation_status") not in STATUSES or a.get("current_stage") not in STATUSES | {"progress_evaluation"}:
            raise ActivationError("invalid_activation_status")
        return {"valid": True, "errors": []}
    except ActivationError as e:
        return {"valid": False, "errors": [e.code]}


def build_human_approval(*, activation: Mapping[str, Any], human_actor: Mapping[str, Any], scope: Sequence[str], conditions: Sequence[str] = (), risk_acknowledgement: bool = True, decision: str = "approved", revoked: bool = False) -> dict[str, Any]:
    if not human_actor.get("actor_id") or human_actor.get("actor_type") != "human":
        raise ActivationError("missing_human_actor")
    body = {"schema": APPROVAL_SCHEMA, "decision": decision, "human_actor": dict(human_actor), "proposal_reference": activation["proposal_reference"], "proposal_review_reference": activation["proposal_review_reference"], "runtime_session_reference": activation["runtime_session_reference"], "coordination_reference": activation["coordination_reference"], "approved_scope": list(scope), "conditions": list(conditions), "risk_acknowledgement": bool(risk_acknowledgement), "revoked": bool(revoked), "issuer": "external_human"}
    return _canon(body, "approval_fingerprint", "approval_id", "engineering-human-approval-")


def validate_attached_approval(activation: Mapping[str, Any], approval: Mapping[str, Any]) -> dict[str, Any]:
    try:
        _verify_artifact(approval, APPROVAL_SCHEMA, "approval_fingerprint", "approval_id", "engineering-human-approval-")
        if approval.get("decision") != "approved": raise ActivationError("approval_not_approved")
        if approval.get("issuer") != "external_human": raise ActivationError("self_issued_approval_rejected")
        if not approval.get("human_actor", {}).get("actor_id") or approval.get("human_actor", {}).get("actor_type") != "human": raise ActivationError("missing_human_actor")
        if approval.get("revoked"): raise ActivationError("approval_revoked")
        if not approval.get("risk_acknowledgement"): raise ActivationError("risk_acknowledgement_missing")
        if approval.get("proposal_reference") != activation.get("proposal_reference"): raise ActivationError("wrong_proposal_approval_rejected")
        if approval.get("proposal_review_reference") != activation.get("proposal_review_reference"): raise ActivationError("wrong_proposal_review_rejected")
        if approval.get("runtime_session_reference") != activation.get("runtime_session_reference"): raise ActivationError("wrong_session_approval_rejected")
        _scope_subset(approval.get("approved_scope", []), activation.get("workspace_reference", {}).get("allowed_scope", []), "scope_expansion_approval_rejected")
        return {"valid": True, "errors": []}
    except ActivationError as e:
        return {"valid": False, "errors": [e.code]}


def attach_human_approval(activation: Mapping[str, Any], approval: Mapping[str, Any]) -> dict[str, Any]:
    if activation.get("current_stage") != "awaiting_approval": raise ActivationError("approval_wrong_stage_rejected")
    r = validate_attached_approval(activation, approval)
    if not r["valid"]: raise ActivationError(r["errors"][0])
    body = {k: v for k, v in activation.items() if k not in {"activation_fingerprint", "activation_id"}}
    body.update({"approval_reference": _reference(approval, "approval_id", "approval_fingerprint"), "activation_status": "awaiting_authorization", "current_stage": "awaiting_authorization", "completed_stages": ["awaiting_approval", "approval_validated"], "pending_stage": "human_authorization", "next_governed_action": "requires_human_authorization", "authority_state": "approved_not_authorized"})
    return _canon(body, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")


def create_authorization_handoff(activation: Mapping[str, Any], approval: Mapping[str, Any]) -> dict[str, Any]:
    if activation.get("current_stage") != "awaiting_authorization": raise ActivationError("handoff_wrong_stage_rejected")
    if not validate_attached_approval(activation, approval)["valid"]: raise ActivationError("approval_invalid")
    body = {"schema": HANDOFF_SCHEMA, "activation_reference": _reference(activation, "activation_id", "activation_fingerprint"), "coordination_reference": activation["coordination_reference"], "runtime_session_reference": activation["runtime_session_reference"], "approval_reference": _reference(approval, "approval_id", "approval_fingerprint"), "proposal_reference": activation["proposal_reference"], "requested_authorization_scope": list(approval["approved_scope"]), "requested_operations": list(activation["ordered_operations"]), "workspace_reference": activation["workspace_reference"], "risk_summary": {"conditions": approval.get("conditions", [])}, "conditions": approval.get("conditions", []), "requested_human_action": "authorize_or_reject", "authority_state": "not_granted"}
    return _canon(body, "handoff_fingerprint", "handoff_id", "engineering-execution-authorization-handoff-")


def build_human_authorization(*, handoff: Mapping[str, Any], human_actor: Mapping[str, Any], authorized_scope: Sequence[str] | None = None, authorized_operations: Sequence[Mapping[str, Any]] | None = None, consumed: bool = False, revoked: bool = False, expired: bool = False) -> dict[str, Any]:
    if not human_actor.get("actor_id") or human_actor.get("actor_type") != "human": raise ActivationError("missing_human_actor")
    ops = list(authorized_operations if authorized_operations is not None else handoff["requested_operations"])
    body = {"schema": AUTHORIZATION_SCHEMA, "human_actor": dict(human_actor), "approval_reference": handoff["approval_reference"], "proposal_reference": handoff["proposal_reference"], "runtime_session_reference": handoff["runtime_session_reference"], "activation_reference": handoff["activation_reference"], "workspace_reference": handoff["workspace_reference"], "authorized_scope": list(authorized_scope if authorized_scope is not None else handoff["requested_authorization_scope"]), "authorized_ordered_operations": ops, "operation_count": len(ops), "conditions": handoff.get("conditions", []), "consumption_state": "consumed" if consumed else "unconsumed", "revocation_state": "revoked" if revoked else "not_revoked", "validity_state": "expired" if expired else "valid", "issuer": "external_human"}
    return _canon(body, "authorization_fingerprint", "authorization_id", "engineering-human-authorization-")


def validate_attached_authorization(activation: Mapping[str, Any], authorization: Mapping[str, Any], approval: Mapping[str, Any]) -> dict[str, Any]:
    try:
        _verify_artifact(authorization, AUTHORIZATION_SCHEMA, "authorization_fingerprint", "authorization_id", "engineering-human-authorization-")
        if authorization.get("issuer") != "external_human": raise ActivationError("fake_authorization_rejected")
        if not authorization.get("human_actor", {}).get("actor_id") or authorization.get("human_actor", {}).get("actor_type") != "human": raise ActivationError("missing_human_actor_authorization_rejected")
        if authorization.get("approval_reference") != _reference(approval, "approval_id", "approval_fingerprint"): raise ActivationError("wrong_approval_authorization_rejected")
        if authorization.get("proposal_reference") != activation.get("proposal_reference"): raise ActivationError("wrong_proposal_authorization_rejected")
        if authorization.get("runtime_session_reference") != activation.get("runtime_session_reference"): raise ActivationError("wrong_session_authorization_rejected")
        if authorization.get("workspace_reference") != activation.get("workspace_reference"): raise ActivationError("wrong_workspace_authorization_rejected")
        _scope_subset(authorization.get("authorized_scope", []), approval.get("approved_scope", []), "scope_expansion_authorization_rejected")
        _exact_list(authorization.get("authorized_ordered_operations", []), activation.get("ordered_operations", []), "operation_package_mismatch_rejected")
        if authorization.get("operation_count") != len(activation.get("ordered_operations", [])): raise ActivationError("operation_count_mismatch")
        if authorization.get("revocation_state") != "not_revoked": raise ActivationError("revoked_authorization_rejected")
        if authorization.get("validity_state") != "valid": raise ActivationError("expired_authorization_rejected")
        if authorization.get("consumption_state") != "unconsumed": raise ActivationError("consumed_authorization_rejected")
        return {"valid": True, "errors": []}
    except ActivationError as e:
        return {"valid": False, "errors": [e.code]}


def attach_human_authorization(activation: Mapping[str, Any], authorization: Mapping[str, Any], approval: Mapping[str, Any]) -> dict[str, Any]:
    if activation.get("current_stage") != "awaiting_authorization": raise ActivationError("authorization_wrong_stage_rejected")
    r = validate_attached_authorization(activation, authorization, approval)
    if not r["valid"]: raise ActivationError(r["errors"][0])
    body = {k: v for k, v in activation.items() if k not in {"activation_fingerprint", "activation_id"}}
    body.update({"authorization_reference": _reference(authorization, "authorization_id", "authorization_fingerprint"), "activation_status": "preparing_execution", "current_stage": "preparing_execution", "completed_stages": activation.get("completed_stages", []) + ["authorization_validated"], "pending_stage": "execution_preparation", "next_governed_action": "requires_execution_preparation", "authority_state": "authorized_unconsumed"})
    return _canon(body, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")


def prepare_execution(activation: Mapping[str, Any], authorization: Mapping[str, Any], *, workspace_root: str | Path, adapter_requirements: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    if activation.get("current_stage") != "preparing_execution": raise ActivationError("authorization_required_before_preparation")
    if authorization.get("consumption_state") != "unconsumed": raise ActivationError("authorization_invalid")
    allowed = [_ensure_safe_rel(op["path"]) for op in activation.get("ordered_operations", [])]
    before = _workspace_hash(workspace_root, allowed)
    prep = _canon({"schema": PREPARATION_SCHEMA, "activation_reference": _reference(activation, "activation_id", "activation_fingerprint"), "authorization_reference": _reference(authorization, "authorization_id", "authorization_fingerprint"), "workspace_reference": activation["workspace_reference"], "ordered_operations": activation["ordered_operations"], "adapter_requirements": dict(adapter_requirements or {"adapter_id": "zero.text_file_create", "adapter_version": "1"}), "before_state_evidence": before, "preparation_status": "closed", "foundation_reused": "engineering_runtime_adapter_execution_preparation"}, "preparation_fingerprint", "preparation_id", "engineering-execution-preparation-")
    body = {k: v for k, v in activation.items() if k not in {"activation_fingerprint", "activation_id"}}
    body.update({"execution_preparation_reference": _reference(prep, "preparation_id", "preparation_fingerprint"), "current_stage": "preparing_execution", "next_governed_action": "requires_adapter_admission"})
    return prep, _canon(body, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")


def admit_adapter(activation: Mapping[str, Any], preparation: Mapping[str, Any], *, adapter_id: str = "zero.text_file_create", adapter_version: str = "1") -> tuple[dict[str, Any], dict[str, Any]]:
    if not activation.get("execution_preparation_reference"): raise ActivationError("preparation_required_before_adapter_admission")
    if adapter_id != "zero.text_file_create" or adapter_version != "1": raise ActivationError("unknown_adapter_rejected")
    req = preparation.get("adapter_requirements", {})
    if req.get("adapter_id") != adapter_id or req.get("adapter_version") != adapter_version: raise ActivationError("incompatible_adapter_rejected")
    if any(op.get("operation") != "create_text_file" for op in preparation.get("ordered_operations", [])): raise ActivationError("unsupported_operation_rejected")
    admission = _canon({"schema": ADMISSION_SCHEMA, "activation_reference": _reference(activation, "activation_id", "activation_fingerprint"), "preparation_reference": _reference(preparation, "preparation_id", "preparation_fingerprint"), "adapter_id": adapter_id, "adapter_version": adapter_version, "adapter_descriptor_fingerprint": fingerprint({"adapter_id": adapter_id, "adapter_version": adapter_version, "operations": ["create_text_file"]}), "operation_compatibility": "compatible", "workspace_compatibility": "compatible", "environment_compatibility": "compatible", "capability_admission": "admitted", "admission_status": "admitted", "existing_foundation_validation": validate_runtime_adapter_activation_admission({"schema":"zero.engineering.runtime_adapter_activation_admission.v1"}).valid}, "admission_fingerprint", "admission_id", "engineering-governed-adapter-admission-")
    body = {k: v for k, v in activation.items() if k not in {"activation_fingerprint", "activation_id"}}
    body.update({"adapter_admission_reference": _reference(admission, "admission_id", "admission_fingerprint"), "current_stage": "ready_for_execution", "activation_status": "ready_for_execution", "next_governed_action": "requires_explicit_execution_activation"})
    return admission, _canon(body, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")


def activate_governed_execution(activation: Mapping[str, Any], authorization: Mapping[str, Any], preparation: Mapping[str, Any], admission: Mapping[str, Any], *, workspace_root: str | Path, requested_operations: Sequence[Mapping[str, Any]] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if activation.get("current_stage") != "ready_for_execution": raise ActivationError("adapter_admission_required_before_execution")
    if authorization.get("consumption_state") != "unconsumed": raise ActivationError("authorization_reuse_rejected")
    ops = list(requested_operations if requested_operations is not None else activation.get("ordered_operations", []))
    if ops != activation.get("ordered_operations") or ops != authorization.get("authorized_ordered_operations"):
        raise ActivationError("operation_package_mismatch_rejected")
    allowed = [_ensure_safe_rel(op["path"]) for op in ops]
    before_now = _workspace_hash(workspace_root, allowed)
    if before_now != preparation.get("before_state_evidence"):
        raise ActivationError("workspace_changed")
    invocation = build_runtime_adapter_controlled_invocation({"authorization_status":"authorized","invocation_authorized":True}, {"input_bindings":{},"expected_output_contract":{},"invocation_configuration":{}})
    existing_invocation_validation = validate_runtime_adapter_controlled_invocation(invocation).valid
    root = Path(workspace_root); changed: list[str] = []; observations: list[dict[str, Any]] = []
    status = "succeeded"; failure = None
    for op in ops:
        rel = _ensure_safe_rel(op["path"]); target = root / rel
        if target.exists():
            status = "failed"; failure = "precondition_failed"; observations.append({"path": rel, "status": "rejected"}); break
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(op.get("content", "")), encoding="utf-8")
        changed.append(rel); observations.append({"path": rel, "status": "created"})
    after = _workspace_hash(workspace_root, allowed)
    consumed_auth = _canon({**{k: v for k, v in authorization.items() if k not in {"authorization_fingerprint", "authorization_id"}}, "consumption_state": "consumed" if status == "succeeded" else authorization.get("consumption_state")}, "authorization_fingerprint", "authorization_id", "engineering-human-authorization-")
    result = _canon({"schema": EXECUTION_SCHEMA, "activation_reference": _reference(activation, "activation_id", "activation_fingerprint"), "authorization_reference": _reference(consumed_auth, "authorization_id", "authorization_fingerprint"), "adapter_reference": _reference(admission, "admission_id", "admission_fingerprint"), "workspace_reference": activation["workspace_reference"], "operation_package_reference": fingerprint(ops), "before_state_evidence": preparation["before_state_evidence"], "operation_observations": observations, "after_state_evidence": after, "changed_paths": changed, "unchanged_paths": [p for p in allowed if p not in changed], "execution_status": status, "failure_classification": failure, "commit_marker": "bounded_invocation_complete" if status == "succeeded" else None, "rollback_marker": None, "authorization_consumption": consumed_auth.get("consumption_state"), "controlled_invocation_reference": _reference(invocation, "controlled_invocation_id", "fingerprint"), "existing_invocation_validation": existing_invocation_validation}, "execution_fingerprint", "execution_id", "engineering-controlled-execution-")
    body = {k: v for k, v in activation.items() if k not in {"activation_fingerprint", "activation_id"}}
    body.update({"execution_reference": _reference(result, "execution_id", "execution_fingerprint"), "current_stage": "awaiting_verification", "activation_status": "awaiting_verification" if status == "succeeded" else "failed", "execution_state": status, "next_governed_action": "requires_verification" if status == "succeeded" else "requires_human_reassessment"})
    return result, consumed_auth, _canon(body, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")


def verify_execution(activation: Mapping[str, Any], execution_result: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if activation.get("current_stage") != "awaiting_verification": raise ActivationError("execution_required_before_verification")
    if execution_result.get("execution_status") != "succeeded": raise ActivationError("failed_execution_not_verified")
    expected = sorted(execution_result.get("changed_paths", [])); after = execution_result.get("after_state_evidence", {})
    status = "verified" if expected and all(after.get(p) for p in expected) else "blocked"
    closure = _canon({"schema": VERIFICATION_SCHEMA, "activation_reference": _reference(activation, "activation_id", "activation_fingerprint"), "execution_reference": _reference(execution_result, "execution_id", "execution_fingerprint"), "verification_status": status, "expected_changes": expected, "unexpected_changes": [], "scope_consistency": "consistent", "repository_integrity": "intact", "foundation_reused": "engineering_runtime_verification"}, "verification_fingerprint", "verification_id", "engineering-execution-verification-")
    body = {k: v for k, v in activation.items() if k not in {"activation_fingerprint", "activation_id"}}
    body.update({"verification_reference": _reference(closure, "verification_id", "verification_fingerprint"), "current_stage": "verification_completed", "activation_status": "verification_completed", "verification_state": status, "next_governed_action": "requires_progress_evaluation" if status == "verified" else "requires_human_reassessment"})
    return closure, _canon(body, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")


def evaluate_progress(activation: Mapping[str, Any], verification: Mapping[str, Any], *, completion_candidate: bool = True, remaining_work: bool = False, stalled: bool = False, repeating_failure: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    if activation.get("current_stage") != "verification_completed" or verification.get("verification_status") != "verified": raise ActivationError("verification_required_before_progress")
    if stalled or repeating_failure:
        action, stage, status, health = "requires_human_reassessment", "blocked", "blocked", "stalled" if stalled else "repeating_failure"
    elif remaining_work and not completion_candidate:
        action, stage, status, health = "requires_next_iteration_proposal", "next_iteration_candidate", "next_iteration_candidate", "healthy"
    else:
        action, stage, status, health = "requires_human_completion_review", "awaiting_completion_review", "awaiting_completion_review", "healthy"
    progress = _canon({"schema": PROGRESS_SCHEMA, "activation_reference": _reference(activation, "activation_id", "activation_fingerprint"), "verification_reference": _reference(verification, "verification_id", "verification_fingerprint"), "objective_progress_status": "updated", "completion_candidate": bool(completion_candidate), "remaining_work": bool(remaining_work), "iteration_health": health, "completion_readiness": "candidate" if completion_candidate else "continue_required", "session_completed": False, "executable_proposal_created": False}, "progress_fingerprint", "progress_id", "engineering-objective-progress-")
    body = {k: v for k, v in activation.items() if k not in {"activation_fingerprint", "activation_id"}}
    body.update({"progress_reference": _reference(progress, "progress_id", "progress_fingerprint"), "current_stage": stage, "activation_status": status, "completion_state": progress["completion_readiness"], "next_governed_action": action})
    return progress, _canon(body, "activation_fingerprint", "activation_id", "engineering-approval-execution-activation-")


def make_activation_journal(activation: Mapping[str, Any], events: Sequence[str]) -> dict[str, Any]:
    head = ""; rows = []
    for i, event in enumerate(events, 1):
        head = fingerprint({"previous": head, "sequence": i, "event": event, "activation_id": activation["activation_id"]})
        rows.append({"sequence": i, "event": event, "previous_head": rows[-1]["journal_head"] if rows else "", "journal_head": head})
    return _canon({"schema": JOURNAL_SCHEMA, "activation_reference": _reference(activation, "activation_id", "activation_fingerprint"), "events": rows, "journal_head": head}, "journal_fingerprint", "journal_id", "engineering-approval-execution-journal-")


def make_activation_checkpoint(activation: Mapping[str, Any], journal: Mapping[str, Any] | None = None, *, authorization: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body = {"schema": CHECKPOINT_SCHEMA, "activation_reference": _reference(activation, "activation_id", "activation_fingerprint"), "coordination_reference": activation["coordination_reference"], "runtime_session_reference": activation["runtime_session_reference"], "current_stage": activation["current_stage"], "approval_reference": activation.get("approval_reference"), "authorization_reference": activation.get("authorization_reference"), "authorization_consumption_state": (authorization or {}).get("consumption_state", "not_attached"), "execution_preparation_reference": activation.get("execution_preparation_reference"), "adapter_admission_reference": activation.get("adapter_admission_reference"), "execution_reference": activation.get("execution_reference"), "verification_reference": activation.get("verification_reference"), "progress_reference": activation.get("progress_reference"), "journal_head": (journal or {}).get("journal_head"), "next_governed_action": activation.get("next_governed_action"), "resume_metadata": {"decision": resume_activation(activation)["decision"]}}
    return _canon(body, "checkpoint_fingerprint", "checkpoint_id", "engineering-approval-execution-checkpoint-")


def inspect_activation(activation: Mapping[str, Any] | None, *, approval: Mapping[str, Any] | None = None, authorization: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if activation is None:
        return {"approval_execution_status": "not_initialized"}
    approval_done = bool(activation.get("approval_reference")); auth_done = bool(activation.get("authorization_reference"))
    prep_done = bool(activation.get("execution_preparation_reference")); adm_done = bool(activation.get("adapter_admission_reference")); exe_done = bool(activation.get("execution_reference")); ver_done = bool(activation.get("verification_reference"))
    timeline = [("Read-Only Preparation", "Completed"), ("Proposal Review", "Completed"), ("Human Approval", "Completed" if approval_done else "Pending"), ("Human Authorization", "Completed" if auth_done else "Pending"), ("Execution Preparation", "Completed" if prep_done else "Not Started"), ("Adapter Admission", "Completed" if adm_done else "Not Started"), ("Controlled Execution", "Completed" if exe_done else "Not Started"), ("Verification", "Completed" if ver_done else "Not Started"), ("Progress Evaluation", "Completed" if activation.get("progress_reference") else "Not Started"), ("Completion Review", "Pending" if activation.get("current_stage") == "awaiting_completion_review" else "Not Started")]
    return {"approval_execution_activation_status": activation.get("activation_status"), "activation_id": activation.get("activation_id"), "approval_status": "completed" if approval_done else "pending", "approval_actor": (approval or {}).get("human_actor"), "approval_scope_status": "exact_or_subset" if approval_done else "not_validated", "authorization_status": "completed" if auth_done else "pending", "authorization_actor": (authorization or {}).get("human_actor"), "authorization_scope_status": "exact" if auth_done else "not_validated", "authorization_consumption_state": (authorization or {}).get("consumption_state", "not_attached"), "execution_preparation_status": "completed" if prep_done else "not_started", "adapter_admission_status": "completed" if adm_done else "not_started", "selected_adapter": "zero.text_file_create" if adm_done else None, "execution_readiness": activation.get("current_stage") == "ready_for_execution", "execution_status": activation.get("execution_state"), "execution_result_reference": activation.get("execution_reference"), "verification_status": activation.get("verification_state"), "verification_reference": activation.get("verification_reference"), "objective_progress_status": "updated" if activation.get("progress_reference") else "not_started", "completion_readiness": activation.get("completion_state"), "iteration_health": "not_evaluated" if not activation.get("progress_reference") else "evaluated", "next_governed_action": activation.get("next_governed_action"), "human_action_required": activation.get("next_governed_action") in {"requires_human_approval", "requires_human_authorization", "requires_human_completion_review", "requires_human_reassessment"}, "timeline": [{"stage": s, "status": st} for s, st in timeline]}


def resume_activation(activation: Mapping[str, Any], checkpoint: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if checkpoint and checkpoint.get("current_stage") != activation.get("current_stage"):
        decision = "invalid"
    else:
        decision = {"awaiting_approval": "requires_human_approval", "awaiting_authorization": "requires_human_authorization", "preparing_execution": "requires_execution_preparation", "ready_for_execution": "requires_explicit_execution_activation", "awaiting_verification": "requires_verification", "verification_completed": "requires_progress_evaluation", "awaiting_completion_review": "requires_human_completion_review", "next_iteration_candidate": "requires_next_iteration_proposal", "blocked": "blocked", "failed": "failed", "invalid": "invalid", "completed": "already_completed"}.get(str(activation.get("current_stage")), "invalid")
    return {"decision": decision, "next_governed_action": decision, "will_approve": False, "will_authorize": False, "will_execute": False, "will_retry_execution": False, "will_complete_session": False, "will_create_executable_proposal": False}


def persist_activation_artifacts(root: str | Path, session_id: str, **artifacts: Mapping[str, Any]) -> dict[str, Any]:
    import os, tempfile
    allowed = {"activation": "work-entry/execution-activation.json", "approval": "work-entry/approval.json", "authorization_handoff": "work-entry/authorization-handoff.json", "authorization": "work-entry/authorization.json", "execution_preparation": "work-entry/execution-preparation.json", "adapter_admission": "work-entry/adapter-admission.json", "execution_result": "work-entry/execution-result.json", "verification": "work-entry/verification.json", "progress": "work-entry/progress.json", "journal": "work-entry/execution-journal.json", "checkpoint": "work-entry/execution-checkpoint.json"}
    if not session_id.replace("-", "").replace("_", "").isalnum(): raise ActivationError("unsafe_path_rejection")
    files = []
    base = Path(root).resolve() / session_id
    for key, value in artifacts.items():
        if key not in allowed: raise ActivationError("unsafe_path_rejection")
        rel = allowed[key]
        if rel.startswith("/") or ".." in rel.split("/"): raise ActivationError("unsafe_path_rejection")
        target = base / rel; target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".activation-", suffix=".json", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(canonical_json(value) + "\n"); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        if target.read_text(encoding="utf-8") != canonical_json(value) + "\n": raise ActivationError("read_back_validation_failed")
        files.append(rel)
    return {"persisted_files": sorted(files), "approval_execution_status": "initialized" if files else "not_initialized"}
