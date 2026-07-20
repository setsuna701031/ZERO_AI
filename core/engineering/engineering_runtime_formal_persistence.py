from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from core.engineering.developer_intent import parse_developer_intent
from core.engineering.engineering_approval_common import validate_review_closure
from core.engineering.engineering_approval_intake import build_engineering_approval_intake
from core.engineering.engineering_approval_eligibility import build_engineering_approval_eligibility
from core.engineering.engineering_approval_policy import build_engineering_approval_policy
from core.engineering.engineering_approval_decision import build_engineering_approval_decision
from core.engineering.engineering_approval_conditions import build_engineering_approval_conditions
from core.engineering.engineering_approval_verification import verify_engineering_approval
from core.engineering.engineering_approval_closure import build_engineering_approval_closure, validate_engineering_approval_closure
from core.engineering.engineering_authorization_intake import build_engineering_authorization_intake
from core.engineering.engineering_authorization_eligibility import build_engineering_authorization_eligibility
from core.engineering.engineering_authorization_policy import build_engineering_authorization_policy
from core.engineering.engineering_authorization_decision import build_engineering_authorization_decision
from core.engineering.engineering_authorization_constraints import build_engineering_authorization_constraints
from core.engineering.engineering_authorization_verification import verify_engineering_authorization
from core.engineering.engineering_authorization_closure import build_engineering_authorization_closure, validate_engineering_authorization_closure
from core.engineering.engineering_execution_preparation_intake import build_engineering_execution_preparation_intake
from core.engineering.engineering_execution_eligibility import build_engineering_execution_eligibility
from core.engineering.engineering_execution_preconditions import build_engineering_execution_preconditions
from core.engineering.engineering_execution_environment_requirements import build_engineering_execution_environment_requirements
from core.engineering.engineering_execution_resource_plan import build_engineering_execution_resource_plan
from core.engineering.engineering_execution_validation import validate_engineering_execution_preparation
from core.engineering.engineering_execution_preparation_closure import build_engineering_execution_preparation_closure, validate_engineering_execution_preparation_closure
from core.engineering.engineering_intake_common import identified
from core.engineering.engineering_planning_context import build_engineering_planning_context
from core.engineering.engineering_goal_extraction import extract_engineering_goals
from core.engineering.engineering_work_breakdown import build_engineering_work_breakdown
from core.engineering.engineering_dependency_ordering import build_engineering_dependency_ordering
from core.engineering.engineering_validation_strategy import build_engineering_validation_strategy
from core.engineering.engineering_risk_assessment import build_engineering_risk_assessment
from core.engineering.engineering_plan import build_engineering_plan
from core.engineering.engineering_planning_verification import verify_engineering_plan
from core.engineering.engineering_planning_closure import build_engineering_planning_closure, validate_engineering_planning_closure
from core.engineering.engineering_proposal_intake import OPAQUE_SCOPE
from core.engineering.engineering_proposal_scope import build_engineering_proposal_scope
from core.engineering.engineering_proposed_change_set import build_engineering_proposed_change_set
from core.engineering.engineering_proposal_dependency_mapping import build_engineering_proposal_dependency_mapping
from core.engineering.engineering_proposal_validation_plan import build_engineering_proposal_validation_plan
from core.engineering.engineering_proposal_risk_review import build_engineering_proposal_risk_review
from core.engineering.engineering_proposal import build_engineering_proposal
from core.engineering.engineering_proposal_intake import build_engineering_proposal_intake
from core.engineering.engineering_proposal_verification import verify_engineering_proposal
from core.engineering.engineering_proposal_closure import build_engineering_proposal_closure, validate_engineering_proposal_closure
from core.engineering.mission_bootstrap import bootstrap_engineering_mission
from core.engineering.repository_analysis import analyze_repository
from core.engineering.repository_analysis_closure import validate_repository_analysis_closure
from core.engineering.repository_analysis_request import prepare_repository_analysis_request
from core.engineering.repository_scoped_analysis import explicit_scope_values, normalize_scoped_repository_scope
from core.engineering.engineering_runtime_orchestrator_common import canonical_json
from core.engineering.engineering_runtime_session_store import (
    load_session_store,
    read_session_artifact,
    write_session_artifact,
)


FORMAL_ANALYSIS_FILE = "formal-analysis.json"
FORMAL_PLANNING_FILE = "formal-planning.json"
FORMAL_PROPOSAL_FILE = "formal-proposal.json"
FORMAL_APPROVAL_FILE = "formal-approval.json"
FORMAL_AUTHORIZATION_FILE = "formal-authorization.json"
FORMAL_PREPARATION_FILE = "formal-preparation.json"
INDEX_FILE = "artifact-index.json"


class FormalPersistenceError(RuntimeError):
    pass


ARTIFACT_ID_KEYS = {
    "formal_analysis": "repository_analysis_closure_id",
    "formal_planning": "planning_closure_id",
    "formal_proposal": "proposal_review_closure_id",
    "formal_approval": "approval_closure_id",
    "formal_authorization": "authorization_closure_id",
    "formal_preparation": "execution_preparation_closure_id",
}


def _artifact_ref(value: Mapping[str, Any], *, logical_key: str, filename: str, phase: str, sequence: int) -> dict[str, Any]:
    preferred_key = ARTIFACT_ID_KEYS.get(logical_key)
    artifact_id = value.get(preferred_key) if preferred_key else None
    if not artifact_id:
        artifact_id = next((value[key] for key in value if key.endswith("_id") and not key.startswith("source_")), "")
    return {
        "logical_key": logical_key,
        "artifact_type": logical_key,
        "artifact_id": artifact_id,
        "schema": value.get("schema"),
        "fingerprint": value.get("fingerprint"),
        "status": value.get("status"),
        "persisted_filename": filename,
        "phase": phase,
        "sequence": sequence,
    }


def _read_index(session_root: str | Path, session_id: str) -> dict[str, Any]:
    try:
        value = read_session_artifact(session_root, session_id, INDEX_FILE)
    except FileNotFoundError:
        return {"entries": []}
    if not isinstance(value, Mapping) or not isinstance(value.get("entries"), list):
        raise FormalPersistenceError("artifact_index_invalid")
    return {"entries": list(value["entries"])}


def _write_index(session_root: str | Path, session_id: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    index = {
        "session_id": session_id,
        "entries": sorted(entries, key=lambda item: (int(item.get("sequence") or 0), str(item.get("logical_key") or ""))),
    }
    write_session_artifact(session_root, session_id, INDEX_FILE, index)
    read_back = read_session_artifact(session_root, session_id, INDEX_FILE)
    if read_back != index:
        raise FormalPersistenceError("artifact_index_readback_mismatch")
    return index


def _persist(
    *,
    session_root: str | Path,
    session_id: str,
    filename: str,
    logical_key: str,
    artifact: Mapping[str, Any],
    validator: Callable[[Any], Any],
    phase: str,
    sequence: int,
) -> dict[str, Any]:
    checked = validator(artifact)
    if not getattr(checked, "valid", False):
        raise FormalPersistenceError(f"{logical_key}_validator_failed:{','.join(getattr(checked, 'errors', ())) or 'invalid'}")

    try:
        existing = read_session_artifact(session_root, session_id, filename)
    except FileNotFoundError:
        existing = None
    if existing is not None and existing != artifact:
        raise FormalPersistenceError(f"{logical_key}_conflict")
    if existing is None:
        write_session_artifact(session_root, session_id, filename, dict(artifact))
    read_back = read_session_artifact(session_root, session_id, filename)
    if read_back != artifact:
        raise FormalPersistenceError(f"{logical_key}_readback_mismatch")

    index = _read_index(session_root, session_id)
    entries = list(index["entries"])
    entry = _artifact_ref(artifact, logical_key=logical_key, filename=filename, phase=phase, sequence=sequence)
    same_slot = [item for item in entries if item.get("logical_key") == logical_key]
    if same_slot and same_slot[0] != entry:
        raise FormalPersistenceError(f"{logical_key}_index_conflict")
    if not same_slot:
        entries.append(entry)
    return _write_index(session_root, session_id, entries)


def _request_text(payload: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    configured = payload.get("formal_engineering_request")
    if isinstance(configured, str) and configured.strip():
        return configured
    request_id = str(request.get("request_id") or "zero-formal-runtime")
    return f"create bounded validation example for {request_id} and validate change"


def _target_path(payload: Mapping[str, Any]) -> str:
    value = payload.get("formal_target_path") or "examples/zero_first_governed_engineering_trial.json"
    text = str(value).strip()
    if text != "examples/zero_first_governed_engineering_trial.json":
        raise FormalPersistenceError("target_path_scope_expansion")
    return text


def _analysis_chain(payload: Mapping[str, Any], request: Mapping[str, Any], workspace_root: str | Path) -> dict[str, Any]:
    intent = parse_developer_intent(_request_text(payload, request))
    bootstrap = bootstrap_engineering_mission(intent)
    analysis_request = prepare_repository_analysis_request(bootstrap)
    scope_values = explicit_scope_values(request, payload)
    scoped_scope = None
    if scope_values is not None:
        try:
            scoped_scope = normalize_scoped_repository_scope(Path(workspace_root), scope_values)
        except ValueError as exc:
            raise FormalPersistenceError(str(exc)) from exc
        payload_map = dict(analysis_request.get("analysis_request_payload") or {})
        payload_map["bounded_scope_paths"] = list(scoped_scope.normalized_scope)
        payload_map["bounded_scope_fingerprint_material"] = dict(scoped_scope.fingerprint_material)
        analysis_request = {**analysis_request, "analysis_request_payload": payload_map}
        from core.engineering.engineering_intake_common import identified
        analysis_request = identified({k: v for k, v in analysis_request.items() if k not in {"repository_analysis_request_id", "fingerprint"}}, "repository_analysis_request_id", "engineering-repository-analysis-request-")
    closure = analyze_repository(analysis_request, workspace_root)
    return {
        "developer_intent": intent,
        "mission_bootstrap": bootstrap,
        "repository_analysis_request": analysis_request,
        "repository_analysis_closure": closure,
    }


def _planning_chain(analysis_closure: Mapping[str, Any]) -> dict[str, Any]:
    context = build_engineering_planning_context(analysis_closure, {}, {})
    goals = extract_engineering_goals(context, {})
    work = build_engineering_work_breakdown(goals)
    dependencies = build_engineering_dependency_ordering(work)
    validation = build_engineering_validation_strategy(goals, work)
    risks = build_engineering_risk_assessment(context, goals, work)
    plan = build_engineering_plan(context, goals, work, dependencies, validation, risks)
    verification = verify_engineering_plan(plan)
    closure = build_engineering_planning_closure(plan, verification)
    return {
        "planning_context": context,
        "goals": goals,
        "work_breakdown": work,
        "dependency_ordering": dependencies,
        "validation_strategy": validation,
        "risk_assessment": risks,
        "engineering_plan": plan,
        "planning_verification": verification,
        "planning_closure": closure,
    }


def _proposal_chain(planning_closure: Mapping[str, Any], target_path: str) -> dict[str, Any]:
    proposal_intent = {
        "requested_scope": [OPAQUE_SCOPE],
        "excluded_scope": [],
        "change_categories": ["documentation_change"],
        "constraints": {
            "allowed_target_path": target_path,
            "executor_invoked": False,
            "git_mutation_performed": False,
            "workspace_mutation_performed": False,
        },
    }
    intake = build_engineering_proposal_intake(planning_closure, proposal_intent)
    scope = build_engineering_proposal_scope(intake, proposal_intent)
    changes = build_engineering_proposed_change_set(scope, proposal_intent)
    dependencies = build_engineering_proposal_dependency_mapping(changes, proposal_intent.get("dependency_edges"))
    validation = build_engineering_proposal_validation_plan(changes, proposal_intent)
    risks = build_engineering_proposal_risk_review(changes, intake["evidence_references"], proposal_intent)
    proposal = build_engineering_proposal(intake, scope, changes, dependencies, validation, risks)
    verification = verify_engineering_proposal(proposal)
    closure = build_engineering_proposal_closure(proposal, verification)
    review_closure = _proposal_review_closure(closure)
    return {
        "proposal_intake": intake,
        "proposal_scope": scope,
        "proposed_change_set": changes,
        "proposal_dependency_mapping": dependencies,
        "proposal_validation_plan": validation,
        "proposal_risk_review": risks,
        "engineering_proposal": proposal,
        "proposal_verification": verification,
        "proposal_closure": closure,
        "proposal_review_closure": review_closure,
    }


def _proposal_review_closure(proposal_closure: Mapping[str, Any]) -> dict[str, Any]:
    if not validate_engineering_proposal_closure(proposal_closure).valid or proposal_closure.get("status") != "closed":
        raise FormalPersistenceError("proposal_closure_invalid")
    body = {
        "schema": "zero.engineering.proposal_review_closure.v1",
        "status": "closed",
        "engineering_proposal_review_id": "engineering-proposal-review-" + str(proposal_closure.get("fingerprint"))[:24],
        "proposal_closure_id": proposal_closure.get("proposal_closure_id"),
        "engineering_proposal_id": proposal_closure.get("engineering_proposal_id"),
        "planning_closure_id": proposal_closure.get("planning_closure_id"),
        "repository_identity": proposal_closure.get("repository_identity"),
        "analyzed_revision": proposal_closure.get("analyzed_revision"),
        "governance_boundary_declaration": {
            "authorization_granted": False,
            "execution_granted": False,
            "mutation_granted": False,
        },
        "next_boundary_declaration": {"foundation": "Engineering Approval Foundation"},
        "boundary": {"sealed": True},
    }
    review = identified(body, "proposal_review_closure_id", "engineering-proposal-review-closure-")
    if not validate_review_closure(review).valid:
        raise FormalPersistenceError("proposal_review_closure_invalid")
    return review


def _approval_chain(review_closure: Mapping[str, Any], operator_input: Mapping[str, Any], target_path: str) -> dict[str, Any]:
    decision = operator_input.get("decision")
    operator_id = str(operator_input.get("operator_id") or "").strip()
    if decision != "approved":
        raise FormalPersistenceError("operator_approval_not_approved")
    if not operator_id:
        raise FormalPersistenceError("operator_identity_required")
    if operator_input.get("automated_decision") is not False:
        raise FormalPersistenceError("automated_approval_rejected")
    approved_scope = operator_input.get("approval_scope") or [target_path]
    if approved_scope != [target_path]:
        raise FormalPersistenceError("approval_scope_expansion")
    intent = {
        "requested_decision": "approve",
        "approval_objective": "approve formal preparation only",
        "constraints": [
            "operator_id:" + operator_id,
            "approved_scope:" + target_path,
            "mutation_execution:not_granted",
            "git_mutation:not_granted",
            "runtime_kernel:not_granted",
        ],
    }
    intake = build_engineering_approval_intake(review_closure, intent)
    eligibility = build_engineering_approval_eligibility(intake, intent)
    policy = build_engineering_approval_policy(intake, eligibility, intent)
    decision_artifact = build_engineering_approval_decision(intake, eligibility, policy)
    conditions = build_engineering_approval_conditions(intake, intent)
    verification = verify_engineering_approval(decision_artifact, conditions)
    closure = build_engineering_approval_closure(intake, eligibility, policy, decision_artifact, conditions, verification)
    return {
        "intake": intake,
        "eligibility": eligibility,
        "policy": policy,
        "decision": decision_artifact,
        "conditions": conditions,
        "verification": verification,
        "closure": closure,
    }


def _authorization_chain(approval_closure: Mapping[str, Any], target_path: str) -> dict[str, Any]:
    intent = {
        "requested_decision": "authorize",
        "authorization_objective": "authorize preparation boundary only",
        "constraints": [
            "preparation_only",
            "target_path:" + target_path,
            "execution_authority:not_granted",
            "mutation_authority:not_granted",
        ],
    }
    intake = build_engineering_authorization_intake(approval_closure, intent)
    eligibility = build_engineering_authorization_eligibility(intake, intent)
    policy = build_engineering_authorization_policy(intake, eligibility, intent)
    decision = build_engineering_authorization_decision(intake, eligibility, policy)
    constraints = build_engineering_authorization_constraints(intake, intent)
    verification = verify_engineering_authorization(decision, constraints)
    closure = build_engineering_authorization_closure(intake, eligibility, policy, decision, constraints, verification)
    return {
        "intake": intake,
        "eligibility": eligibility,
        "policy": policy,
        "decision": decision,
        "constraints": constraints,
        "verification": verification,
        "closure": closure,
    }


def _preparation_chain(authorization_closure: Mapping[str, Any], target_path: str) -> dict[str, Any]:
    intent = {
        "preparation_objective": "prepare formal mutation authorization review package",
        "constraints": [
            "target_path:" + target_path,
            "operation:create_text_file",
            "deterministic_content_source:zero-first-governed-engineering-trial",
            "executor_not_invoked",
            "mutation_not_performed",
            "transaction_not_executed",
        ],
        "preconditions": [
            "target_path:" + target_path,
            "operation:create_text_file",
            "executor_not_invoked",
            "mutation_not_performed",
            "transaction_not_executed",
        ],
    }
    intake = build_engineering_execution_preparation_intake(authorization_closure, intent)
    eligibility = build_engineering_execution_eligibility(intake, intent)
    preconditions = build_engineering_execution_preconditions(intake, eligibility, intent)
    environment = build_engineering_execution_environment_requirements(preconditions, intent)
    resources = build_engineering_execution_resource_plan(environment, intent)
    validation = validate_engineering_execution_preparation(intake, eligibility, preconditions, environment, resources)
    closure = build_engineering_execution_preparation_closure(intake, eligibility, preconditions, environment, resources, validation)
    return {
        "intake": intake,
        "eligibility": eligibility,
        "preconditions": preconditions,
        "environment_requirements": environment,
        "resource_plan": resources,
        "validation": validation,
        "closure": closure,
    }


def _load_formal(session_root: str | Path, session_id: str, filename: str) -> dict[str, Any] | None:
    try:
        value = read_session_artifact(session_root, session_id, filename)
    except FileNotFoundError:
        return None
    if not isinstance(value, dict):
        raise FormalPersistenceError("persisted_artifact_not_object")
    return value


def run_formal_persistence_mainline(
    *,
    payload: Mapping[str, Any],
    request: Mapping[str, Any],
    session: Mapping[str, Any],
    session_root: str | Path | None,
    workspace_root: str | Path | None,
    mode: str,
) -> dict[str, Any]:
    if not session_root:
        return {"status": "disabled", "reason_codes": ["session_root_missing"]}
    if not workspace_root:
        return {"status": "invalid", "reason_codes": ["workspace_root_missing"]}

    session_id = str(session.get("session_id") or "")
    target_path = _target_path(payload)
    persisted: list[dict[str, Any]] = []
    chains: dict[str, Any] = {}
    try:
        analysis_closure = _load_formal(session_root, session_id, FORMAL_ANALYSIS_FILE)
        if analysis_closure is None:
            analysis = _analysis_chain(payload, request, workspace_root)
            analysis_closure = analysis["repository_analysis_closure"]
            index = _persist(session_root=session_root, session_id=session_id, filename=FORMAL_ANALYSIS_FILE,
                             logical_key="formal_analysis", artifact=analysis_closure,
                             validator=validate_repository_analysis_closure, phase="formal_analysis_persisted", sequence=10)
            chains["analysis_chain"] = analysis
        else:
            checked = validate_repository_analysis_closure(analysis_closure)
            if not checked.valid:
                raise FormalPersistenceError("formal_analysis_readback_invalid")
            requested_scope = explicit_scope_values(request, payload)
            if requested_scope is not None:
                expected_scope = list(normalize_scoped_repository_scope(Path(workspace_root), requested_scope).normalized_scope)
                actual_scope = analysis_closure.get("report", {}).get("repository_summary", {}).get("normalized_scope")
                if actual_scope != expected_scope:
                    raise FormalPersistenceError("formal_analysis_scope_conflict")
            index = _read_index(session_root, session_id)
        persisted.append(_artifact_ref(analysis_closure, logical_key="formal_analysis", filename=FORMAL_ANALYSIS_FILE, phase="formal_analysis_persisted", sequence=10))

        if mode == "analyze":
            return _result("formal_analysis_persisted", "formal_analysis_persisted", session_root, session_id, persisted, index, chains)

        planning_closure = _load_formal(session_root, session_id, FORMAL_PLANNING_FILE)
        if planning_closure is None:
            planning = _planning_chain(analysis_closure)
            planning_closure = planning["planning_closure"]
            index = _persist(session_root=session_root, session_id=session_id, filename=FORMAL_PLANNING_FILE,
                             logical_key="formal_planning", artifact=planning_closure,
                             validator=validate_engineering_planning_closure, phase="formal_planning_persisted", sequence=20)
            chains["planning_chain"] = planning
        else:
            checked = validate_engineering_planning_closure(planning_closure)
            if not checked.valid:
                raise FormalPersistenceError("formal_planning_readback_invalid")
        persisted.append(_artifact_ref(planning_closure, logical_key="formal_planning", filename=FORMAL_PLANNING_FILE, phase="formal_planning_persisted", sequence=20))

        proposal_review = _load_formal(session_root, session_id, FORMAL_PROPOSAL_FILE)
        if proposal_review is None:
            proposal = _proposal_chain(planning_closure, target_path)
            proposal_review = proposal["proposal_review_closure"]
            index = _persist(session_root=session_root, session_id=session_id, filename=FORMAL_PROPOSAL_FILE,
                             logical_key="formal_proposal", artifact=proposal_review,
                             validator=validate_review_closure, phase="awaiting_operator_approval", sequence=30)
            chains["proposal_chain"] = proposal
        else:
            checked = validate_review_closure(proposal_review)
            if not checked.valid:
                raise FormalPersistenceError("formal_proposal_readback_invalid")
        persisted.append(_artifact_ref(proposal_review, logical_key="formal_proposal", filename=FORMAL_PROPOSAL_FILE, phase="awaiting_operator_approval", sequence=30))

        operator_input = payload.get("operator_input")
        if not isinstance(operator_input, Mapping):
            return _result("awaiting_operator_approval", "awaiting_operator_approval", session_root, session_id, persisted, index, chains,
                           required_operator_input={"decision_required": True, "operator_identity_required": True, "automated_decision_allowed": False})

        approval_closure = _load_formal(session_root, session_id, FORMAL_APPROVAL_FILE)
        if approval_closure is None:
            approval = _approval_chain(proposal_review, operator_input, target_path)
            approval_closure = approval["closure"]
            index = _persist(session_root=session_root, session_id=session_id, filename=FORMAL_APPROVAL_FILE,
                             logical_key="formal_approval", artifact=approval_closure,
                             validator=validate_engineering_approval_closure,
                             phase="formal_approval_persisted", sequence=40)
            chains["approval_chain"] = approval
        persisted.append(_artifact_ref(approval_closure, logical_key="formal_approval", filename=FORMAL_APPROVAL_FILE, phase="formal_approval_persisted", sequence=40))

        authorization_closure = _load_formal(session_root, session_id, FORMAL_AUTHORIZATION_FILE)
        if authorization_closure is None:
            authorization = _authorization_chain(approval_closure, target_path)
            authorization_closure = authorization["closure"]
            index = _persist(session_root=session_root, session_id=session_id, filename=FORMAL_AUTHORIZATION_FILE,
                             logical_key="formal_authorization", artifact=authorization_closure,
                             validator=validate_engineering_authorization_closure,
                             phase="formal_authorization_persisted", sequence=50)
            chains["authorization_chain"] = authorization
        persisted.append(_artifact_ref(authorization_closure, logical_key="formal_authorization", filename=FORMAL_AUTHORIZATION_FILE, phase="formal_authorization_persisted", sequence=50))

        preparation_closure = _load_formal(session_root, session_id, FORMAL_PREPARATION_FILE)
        if preparation_closure is None:
            preparation = _preparation_chain(authorization_closure, target_path)
            preparation_closure = preparation["closure"]
            index = _persist(session_root=session_root, session_id=session_id, filename=FORMAL_PREPARATION_FILE,
                             logical_key="formal_preparation", artifact=preparation_closure,
                             validator=validate_engineering_execution_preparation_closure, phase="awaiting_mutation_authorization", sequence=60)
            chains["preparation_chain"] = preparation
        persisted.append(_artifact_ref(preparation_closure, logical_key="formal_preparation", filename=FORMAL_PREPARATION_FILE, phase="awaiting_mutation_authorization", sequence=60))
        return _result("awaiting_mutation_authorization", "awaiting_mutation_authorization", session_root, session_id, persisted, index, chains)
    except FormalPersistenceError as exc:
        return _result("invalid", "fail_closed", session_root, session_id, persisted, _read_index(session_root, session_id), chains, reason_codes=[str(exc)])


class _Valid:
    def __init__(self, valid: bool, errors: tuple[str, ...] = ()) -> None:
        self.valid = valid
        self.errors = errors if not valid else ()


def _result(
    status: str,
    phase: str,
    session_root: str | Path,
    session_id: str,
    persisted: list[dict[str, Any]],
    index: Mapping[str, Any],
    chains: Mapping[str, Any],
    *,
    required_operator_input: Mapping[str, Any] | None = None,
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "current_phase": phase,
        "session_root": str(session_root),
        "session_id": session_id,
        "persisted_artifacts": persisted,
        "artifact_index": deepcopy(dict(index)),
        "formal_chains": deepcopy(dict(chains)),
        "required_operator_input": dict(required_operator_input or {}),
        "reason_codes": list(reason_codes or []),
        "execution_enabled": False,
        "executor_invoked": False,
        "workspace_mutation_performed": False,
        "git_mutation_performed": False,
        "scoped_analysis_enabled": bool((chains.get("analysis_chain") or {}).get("repository_analysis_closure", {}).get("report", {}).get("repository_summary", {}).get("scoped_analysis_enabled")),
        "normalized_scope": (chains.get("analysis_chain") or {}).get("repository_analysis_closure", {}).get("report", {}).get("repository_summary", {}).get("normalized_scope", []),
        "analyzed_paths": (chains.get("analysis_chain") or {}).get("repository_analysis_closure", {}).get("report", {}).get("repository_summary", {}).get("analyzed_paths", []),
        "proposed_missing_targets": (chains.get("analysis_chain") or {}).get("repository_analysis_closure", {}).get("report", {}).get("repository_summary", {}).get("proposed_missing_targets", []),
        "analysis_coverage": (chains.get("analysis_chain") or {}).get("repository_analysis_closure", {}).get("report", {}).get("repository_summary", {}).get("analysis_coverage"),
        "analysis_truncated": (chains.get("analysis_chain") or {}).get("repository_analysis_closure", {}).get("report", {}).get("repository_summary", {}).get("snapshot_truncated"),
    }


def resume_formal_persistence_session(session_root: str | Path, session_id: str) -> dict[str, Any]:
    try:
        store = load_session_store(session_root, session_id)
        index = store.get(INDEX_FILE) or _read_index(session_root, session_id)
        entries = index.get("entries", []) if isinstance(index, Mapping) else []
        validators = {
            "formal_analysis": validate_repository_analysis_closure,
            "formal_planning": validate_engineering_planning_closure,
            "formal_proposal": validate_review_closure,
            "formal_approval": validate_engineering_approval_closure,
            "formal_authorization": validate_engineering_authorization_closure,
            "formal_preparation": validate_engineering_execution_preparation_closure,
        }
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise FormalPersistenceError("artifact_index_entry_invalid")
            logical_key = str(entry.get("logical_key") or "")
            filename = str(entry.get("persisted_filename") or "")
            validator = validators.get(logical_key)
            if validator is None:
                raise FormalPersistenceError("artifact_index_unknown_logical_key")
            artifact = read_session_artifact(session_root, session_id, filename)
            checked = validator(artifact)
            if not getattr(checked, "valid", False):
                raise FormalPersistenceError(logical_key + "_resume_validator_failed")
            if artifact.get("fingerprint") != entry.get("fingerprint"):
                raise FormalPersistenceError(logical_key + "_resume_fingerprint_mismatch")
        logical = {entry.get("logical_key") for entry in entries if isinstance(entry, Mapping)}
        if "formal_preparation" in logical:
            phase = "awaiting_mutation_authorization"
            status = "awaiting_mutation_authorization"
        elif "formal_proposal" in logical:
            phase = "awaiting_operator_approval"
            status = "awaiting_operator_approval"
        elif "formal_analysis" in logical:
            phase = "formal_analysis_persisted"
            status = "formal_analysis_persisted"
        else:
            phase = "request_received"
            status = "created"
        return {
            "status": status,
            "current_phase": phase,
            "session_root": str(session_root),
            "session_id": session_id,
            "artifact_index": index,
            "required_operator_input": {"decision_required": True, "operator_identity_required": True, "automated_decision_allowed": False} if phase == "awaiting_operator_approval" else {},
            "execution_enabled": False,
            "executor_invoked": False,
            "workspace_mutation_performed": False,
            "git_mutation_performed": False,
        }
    except Exception as exc:
        return {
            "status": "invalid",
            "current_phase": "fail_closed",
            "session_root": str(session_root),
            "session_id": session_id,
            "reason_codes": [str(exc)],
            "execution_enabled": False,
            "executor_invoked": False,
            "workspace_mutation_performed": False,
            "git_mutation_performed": False,
        }


__all__ = [
    "run_formal_persistence_mainline",
    "resume_formal_persistence_session",
]
