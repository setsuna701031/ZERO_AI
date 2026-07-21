from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.engineering.engineering_runtime_session_v3 import RuntimeSessionError, _ref, _seal, _verify_seal
from core.engineering.engineering_runtime_orchestrator_common import fingerprint

OBJECTIVE_SCHEMA = "zero.engineering.runtime_session_objective.v1"
ASSIGNMENT_SCHEMA = "zero.engineering.runtime_cycle_objective_assignment.v1"
PROGRESS_SCHEMA = "zero.engineering.runtime_objective_progress.v1"
READINESS_SCHEMA = "zero.engineering.runtime_completion_readiness.v1"
REVIEW_REQUEST_SCHEMA = "zero.engineering.runtime_completion_review_request.v1"
COMPLETION_DECISION_SCHEMA = "zero.engineering.runtime_completion_decision.v1"
ITERATION_DECISION_SCHEMA = "zero.engineering.runtime_iteration_decision.v1"
ITERATION_HEALTH_SCHEMA = "zero.engineering.runtime_iteration_health.v1"
NEXT_CANDIDATE_SCHEMA = "zero.engineering.runtime_next_iteration_objective_candidate.v1"

OBJECTIVE_STATUSES = {"defined", "active", "partially_satisfied", "satisfied", "blocked", "failed", "invalid", "superseded"}
CRITERION_STATUSES = {"defined", "satisfied", "partially_satisfied", "not_satisfied", "blocked", "failed", "not_evaluated", "invalid"}
PROGRESS_STATUSES = {"progressing", "partial", "no_progress", "blocked", "failed", "invalid"}
READINESS_ACTIONS = {"continue_iteration", "prepare_completion_review", "require_human_review", "block_session", "stop_failed", "no_action_closed", "invalid"}
COMPLETION_DECISIONS = {"approved_complete", "rejected_incomplete", "returned_for_iteration", "blocked", "invalid"}
ITERATION_DECISIONS = {"continue_required", "completion_review_ready", "human_reassessment_required", "blocked", "failed", "closed", "invalid"}
HEALTH_STATUSES = {"progressing", "slow_progress", "stalled", "repeating_failure", "blocked", "invalid"}
NO_PROGRESS_THRESHOLD = 3


def _ensure_scope(scope: Sequence[str], name: str) -> list[str]:
    if not isinstance(scope, Sequence) or isinstance(scope, (str, bytes)) or not scope:
        raise RuntimeSessionError(f"{name}_scope_required")
    out = sorted({str(v) for v in scope if str(v)})
    if not out or any(v.startswith("/") or ".." in v.split("/") for v in out):
        raise RuntimeSessionError(f"{name}_scope_invalid")
    return out


def _scope_subset(child: Sequence[str], parent: Sequence[str]) -> bool:
    parent_set = set(parent)
    return all(c in parent_set or any(c.startswith(p.rstrip("/") + "/") for p in parent_set) for c in child)


def _artifact_ref(value: Mapping[str, Any], id_key: str, fp_key: str) -> dict[str, Any]:
    if str(value.get("schema", "")).startswith("zero.test."):
        raise RuntimeSessionError("fake_artifact_reference")
    if not value.get(id_key) or not value.get(fp_key):
        raise RuntimeSessionError("artifact_reference_missing_identity")
    return {"schema": str(value["schema"]), "artifact_identity": str(value[id_key]), "artifact_fingerprint": str(value[fp_key])}


def validate_evidence_reference(ref: Mapping[str, Any], session_id: str | None = None) -> dict[str, Any]:
    r = _ref(ref, "evidence", True)
    if str(r["schema"]).startswith("zero.test."):
        raise RuntimeSessionError("fake_evidence_reference")
    if session_id and ref.get("session_id") not in (None, session_id):
        raise RuntimeSessionError("evidence_session_mismatch")
    return r


def build_session_objective(session: Mapping[str, Any], *, source_task_identity: Mapping[str, Any], source_planning_reference: Mapping[str, Any] | None, objective_statement: str, bounded_scope: Sequence[str], acceptance_criteria: Sequence[Mapping[str, Any]], required_evidence: Sequence[Mapping[str, Any]], priority: str = "required", objective_status: str = "defined", parent_objective: Mapping[str, Any] | None = None, dependencies: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    if not objective_statement or not objective_statement.strip():
        raise RuntimeSessionError("empty_objective")
    if objective_status not in OBJECTIVE_STATUSES:
        raise RuntimeSessionError("invalid_objective_status")
    scope = _ensure_scope(bounded_scope, "objective")
    if parent_objective and not _scope_subset(scope, parent_objective.get("bounded_scope", [])):
        raise RuntimeSessionError("child_scope_expansion")
    criteria = []
    seen = set()
    for c in acceptance_criteria:
        cid = str(c.get("criterion_id", ""))
        if not cid or cid in seen:
            raise RuntimeSessionError("duplicate_or_missing_criterion")
        seen.add(cid)
        status = str(c.get("status", "defined"))
        if status not in CRITERION_STATUSES:
            raise RuntimeSessionError("invalid_criterion_status")
        refs = [validate_evidence_reference(r, session.get("session_id")) for r in c.get("evidence_references", [])]
        if status == "satisfied" and not refs:
            raise RuntimeSessionError("satisfied_criterion_missing_evidence")
        criteria.append({"criterion_id": cid, "description": str(c.get("description", "")), "required": bool(c.get("required", True)), "evidence_type": str(c.get("evidence_type", "artifact")), "verification_method": str(c.get("verification_method", "formal_evidence")), "status": status, "evidence_references": refs})
    criteria = sorted(criteria, key=lambda x: x["criterion_id"])
    if not criteria or (priority == "required" and not any(c["required"] for c in criteria)):
        raise RuntimeSessionError("missing_acceptance_criteria")
    req_evidence = [validate_evidence_reference(r, session.get("session_id")) for r in required_evidence]
    body = {"schema": OBJECTIVE_SCHEMA, "session_id": session["session_id"], "source_task_identity": dict(source_task_identity), "source_planning_reference": _ref(source_planning_reference, "source_planning_reference") if source_planning_reference else None, "objective_statement": objective_statement.strip(), "bounded_scope": scope, "acceptance_criteria": criteria, "required_evidence": req_evidence, "priority": priority, "objective_status": objective_status, "parent_objective_id": parent_objective.get("objective_id") if parent_objective else None, "dependencies": list(dependencies)}
    out = _seal(body, "objective_fingerprint", "objective_id", "engineering-runtime-objective-")
    validate_session_objective(out, session)
    return out


def validate_session_objective(obj: Mapping[str, Any], session: Mapping[str, Any] | None = None) -> None:
    _verify_seal(obj, "objective_fingerprint", "objective_id", "engineering-runtime-objective-")
    if obj.get("schema") != OBJECTIVE_SCHEMA:
        raise RuntimeSessionError("invalid_objective_schema")
    if session and obj.get("session_id") != session.get("session_id"):
        raise RuntimeSessionError("objective_session_mismatch")
    if not obj.get("objective_statement") or not obj.get("acceptance_criteria"):
        raise RuntimeSessionError("objective_contract_incomplete")


def build_cycle_objective_assignment(session: Mapping[str, Any], cycle: Mapping[str, Any], objectives: Sequence[Mapping[str, Any]], *, target_criteria: Sequence[Mapping[str, Any]], declared_scope: Sequence[str], excluded_scope: Sequence[str], expected_evidence: Sequence[Mapping[str, Any]], previous_progress: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if session.get("status") in {"completed", "closed", "failed", "invalid"}:
        raise RuntimeSessionError("terminal_session_assignment")
    obj_by_id = {}
    parent_scope = []
    criteria_by_obj = {}
    for o in objectives:
        validate_session_objective(o, session)
        obj_by_id[o["objective_id"]] = o
        parent_scope.extend(o["bounded_scope"])
        criteria_by_obj[o["objective_id"]] = {c["criterion_id"] for c in o["acceptance_criteria"]}
    scope = _ensure_scope(declared_scope, "assignment")
    if not _scope_subset(scope, sorted(set(parent_scope))):
        raise RuntimeSessionError("assignment_scope_expansion")
    targets = []
    for t in target_criteria:
        oid, cid = str(t.get("objective_id", "")), str(t.get("criterion_id", ""))
        if oid not in obj_by_id:
            raise RuntimeSessionError("unknown_objective")
        if cid not in criteria_by_obj[oid]:
            raise RuntimeSessionError("unknown_criterion")
        targets.append({"objective_id": oid, "criterion_id": cid})
    if len({(t["objective_id"], t["criterion_id"]) for t in targets}) != len(targets):
        raise RuntimeSessionError("duplicate_assignment")
    body = {"schema": ASSIGNMENT_SCHEMA, "session_id": session["session_id"], "cycle_id": cycle["cycle_id"], "cycle_number": cycle["cycle_number"], "objective_references": [_artifact_ref(o, "objective_id", "objective_fingerprint") for o in objectives], "target_criteria": sorted(targets, key=lambda x: (x["objective_id"], x["criterion_id"])), "declared_scope": scope, "excluded_scope": sorted(set(excluded_scope)), "expected_evidence": [validate_evidence_reference(e, session["session_id"]) for e in expected_evidence], "previous_progress_reference": _artifact_ref(previous_progress, "progress_id", "progress_fingerprint") if previous_progress else None, "assignment_status": "assigned"}
    return _seal(body, "assignment_fingerprint", "assignment_id", "engineering-runtime-assignment-")


def evaluate_objective_progress(session: Mapping[str, Any], objectives: Sequence[Mapping[str, Any]], assignment: Mapping[str, Any], *, satisfied_evidence: Sequence[Mapping[str, Any]] = (), partial_criteria: Sequence[Mapping[str, str]] = (), blocked_criteria: Sequence[Mapping[str, str]] = (), failed_criteria: Sequence[Mapping[str, str]] = (), feedback: Mapping[str, Any] | None = None, scope_observations: Sequence[str] = (), verification_failures: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    if assignment.get("schema") != ASSIGNMENT_SCHEMA or assignment.get("session_id") != session.get("session_id"):
        raise RuntimeSessionError("assignment_session_mismatch")
    ev = [validate_evidence_reference(e, session["session_id"]) for e in satisfied_evidence]
    ev_keys = {e["artifact_identity"] for e in ev}
    unresolved = set(feedback.get("unresolved_criteria", []) if feedback else [])
    blocked = {(x["objective_id"], x["criterion_id"]) for x in blocked_criteria} | {(x.split(":",1)[0], x.split(":",1)[1]) for x in unresolved if ":" in x}
    failed = {(x["objective_id"], x["criterion_id"]) for x in failed_criteria}
    partial = {(x["objective_id"], x["criterion_id"]) for x in partial_criteria}
    scope_dev = [s for s in scope_observations if not _scope_subset([s], assignment.get("declared_scope", []))]
    criteria_results = []
    newly = []
    remaining = []
    for t in assignment.get("target_criteria", []):
        key = (t["objective_id"], t["criterion_id"])
        status = "satisfied" if ev_keys and key not in blocked and key not in failed and not scope_dev else "not_satisfied"
        if key in partial: status = "partially_satisfied"
        if key in blocked: status = "blocked"
        if key in failed: status = "failed"
        refs = ev if status == "satisfied" else []
        if status == "satisfied": newly.append(dict(t))
        else: remaining.append(dict(t))
        criteria_results.append({**dict(t), "status": status, "evidence_references": refs})
    objective_results = []
    for o in objectives:
        related = [r for r in criteria_results if r["objective_id"] == o["objective_id"]]
        if related and all(r["status"] == "satisfied" for r in related): st = "satisfied"
        elif any(r["status"] == "failed" for r in related): st = "failed"
        elif any(r["status"] == "blocked" for r in related): st = "blocked"
        elif any(r["status"] in {"satisfied", "partially_satisfied"} for r in related): st = "partially_satisfied"
        else: st = "not_satisfied"
        objective_results.append({"objective_id": o["objective_id"], "status": st})
    unsupported = [] if not ev else [r for r in criteria_results if r["status"] != "satisfied" and ev]
    pstatus = "failed" if failed else "blocked" if blocked else "progressing" if newly else "partial" if partial else "no_progress"
    body = {"schema": PROGRESS_SCHEMA, "session_id": session["session_id"], "cycle_id": assignment["cycle_id"], "cycle_number": assignment["cycle_number"], "assignment_reference": _artifact_ref(assignment, "assignment_id", "assignment_fingerprint"), "objective_results": objective_results, "criteria_results": criteria_results, "newly_satisfied_criteria": newly, "remaining_criteria": remaining, "blocked_criteria": [dict(objective_id=o, criterion_id=c) for o, c in sorted(blocked)], "failed_criteria": [dict(objective_id=o, criterion_id=c) for o, c in sorted(failed)], "unsupported_claims": unsupported, "evidence_coverage": {"evidence_count": len(ev), "covered_criteria_count": len(newly)}, "scope_deviation": scope_dev, "verification_failure_references": list(verification_failures), "unresolved_feedback": sorted(unresolved), "progress_status": pstatus}
    return _seal(body, "progress_fingerprint", "progress_id", "engineering-runtime-progress-")


def evaluate_completion_readiness(session: Mapping[str, Any], objectives: Sequence[Mapping[str, Any]], progresses: Sequence[Mapping[str, Any]], cycles: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    required = [o for o in objectives if o.get("priority") == "required"]
    latest = {}
    blockers = []
    for p in progresses:
        _verify_seal(p, "progress_fingerprint", "progress_id", "engineering-runtime-progress-")
        if p.get("session_id") != session.get("session_id"): blockers.append("invalid_lineage")
        for r in p.get("criteria_results", []): latest[(r["objective_id"], r["criterion_id"])] = r
        if p.get("scope_deviation"): blockers.append("scope_deviation")
        if p.get("unresolved_feedback"): blockers.append("unresolved_feedback")
    satisfied_obj = 0; remaining_obj = 0; blocked_obj = 0; failed_obj = 0
    for o in required:
        statuses = [latest.get((o["objective_id"], c["criterion_id"]), {}).get("status", "not_satisfied") for c in o["acceptance_criteria"] if c["required"]]
        if statuses and all(s == "satisfied" for s in statuses): satisfied_obj += 1
        elif any(s == "failed" for s in statuses): failed_obj += 1
        elif any(s == "blocked" for s in statuses): blocked_obj += 1
        else: remaining_obj += 1
    if any(c.get("cycle_status") == "failed" for c in cycles): blockers.append("failed_cycle")
    evidence_complete = bool(latest) and all(r.get("status") != "satisfied" or r.get("evidence_references") for r in latest.values()) and all(r.get("status") == "satisfied" for r in latest.values() if r.get("objective_id"))
    if not evidence_complete: blockers.append("missing_evidence")
    candidate = bool(required) and satisfied_obj == len(required) and not blockers
    action = "prepare_completion_review" if candidate else "stop_failed" if failed_obj else "block_session" if blocked_obj else "continue_iteration"
    body = {"schema": READINESS_SCHEMA, "session_id": session["session_id"], "evaluated_cycle_count": len(progresses), "required_objective_count": len(required), "satisfied_objective_count": satisfied_obj, "remaining_objective_count": remaining_obj, "blocked_objective_count": blocked_obj, "failed_objective_count": failed_obj, "evidence_completeness": evidence_complete, "scope_consistency": "scope_deviation" not in blockers, "lineage_validity": "invalid_lineage" not in blockers, "completion_candidate": candidate, "completion_blockers": sorted(set(blockers)), "human_review_required": candidate or bool(blockers), "recommended_action": action, "session_completed": False}
    return _seal(body, "readiness_fingerprint", "readiness_id", "engineering-runtime-readiness-")


def request_completion_review(session, readiness):
    if not readiness.get("completion_candidate"):
        raise RuntimeSessionError("completion_not_ready")
    body={"schema":REVIEW_REQUEST_SCHEMA,"session_id":session["session_id"],"completion_readiness_reference":_artifact_ref(readiness,"readiness_id","readiness_fingerprint"),"objective_summary":{"satisfied_objectives":readiness["satisfied_objective_count"]},"evidence_summary":{"evidence_completeness":readiness["evidence_completeness"]},"remaining_risks":readiness.get("completion_blockers",[]),"scope_summary":{"scope_consistency":readiness["scope_consistency"]},"requested_decision":"human_completion_decision","authority_state":"not_granted","session_completed":False}
    return _seal(body,"review_request_fingerprint","review_request_id","engineering-runtime-review-request-")


def record_completion_decision(session, review_request, *, decision: str, human_actor_reference: Mapping[str, Any], decision_conditions=(), decision_evidence=()):
    if session.get("status") == "closed": raise RuntimeSessionError("closed_session_completion_decision")
    if decision not in COMPLETION_DECISIONS: raise RuntimeSessionError("invalid_completion_decision")
    if not human_actor_reference or not human_actor_reference.get("actor_id"): raise RuntimeSessionError("missing_human_actor")
    body={"schema":COMPLETION_DECISION_SCHEMA,"session_id":session["session_id"],"review_request_reference":_artifact_ref(review_request,"review_request_id","review_request_fingerprint"),"decision":decision,"human_actor_reference":dict(human_actor_reference),"decision_conditions":list(decision_conditions),"decision_evidence":[validate_evidence_reference(e,session["session_id"]) for e in decision_evidence],"permits_completed_transition":decision=="approved_complete","not_proposal_approval":True,"not_authorization":True}
    return _seal(body,"decision_fingerprint","decision_id","engineering-runtime-completion-decision-")


def apply_completion_decision(session, decision_artifact):
    _verify_seal(decision_artifact,"decision_fingerprint","decision_id","engineering-runtime-completion-decision-")
    if decision_artifact.get("decision") != "approved_complete": raise RuntimeSessionError("completion_not_approved")
    from core.engineering.engineering_runtime_session_v3 import complete_session
    return complete_session(session)


def evaluate_iteration_health(session, progresses: Sequence[Mapping[str, Any]]):
    deltas=[]; last_e=set(); stalled=0; repeated_fail=[]; repeated_gap=[]
    seen_fail=set(); seen_gap=set(); novel=0
    for p in progresses:
        ev={e["artifact_identity"] for r in p.get("criteria_results",[]) for e in r.get("evidence_references",[])}
        new_sat=len(p.get("newly_satisfied_criteria",[])); new_ev=len(ev-last_e); novel+=new_ev
        if new_sat: stalled=0
        else: stalled+=1
        for f in p.get("verification_failure_references",[]):
            fid=f.get("artifact_identity") or f.get("finding_id")
            if fid in seen_fail: repeated_fail.append(fid)
            seen_fail.add(fid)
        for g in p.get("remaining_criteria",[]):
            gid=f"{g['objective_id']}:{g['criterion_id']}"
            if gid in seen_gap: repeated_gap.append(gid)
            seen_gap.add(gid)
        deltas.append({"cycle_number":p.get("cycle_number"),"newly_satisfied_count":new_sat,"novel_evidence_count":new_ev})
        last_e |= ev
    status="progressing" if deltas and deltas[-1]["newly_satisfied_count"] else "slow_progress" if deltas and deltas[-1]["novel_evidence_count"] else "stalled" if stalled>=NO_PROGRESS_THRESHOLD else "slow_progress"
    if repeated_fail: status="repeating_failure"
    action="human_reassessment_required" if status in {"stalled","repeating_failure"} else "continue_iteration"
    body={"schema":ITERATION_HEALTH_SCHEMA,"session_id":session["session_id"],"evaluated_cycles":len(progresses),"progress_deltas":deltas,"stalled_cycle_count":stalled,"repeated_gap_references":sorted(set(repeated_gap)),"repeated_failure_references":sorted(set(repeated_fail)),"novel_evidence_count":novel,"health_status":status,"recommended_action":action,"bounded_no_progress_threshold":NO_PROGRESS_THRESHOLD}
    return _seal(body,"health_fingerprint","health_id","engineering-runtime-health-")


def decide_iteration(session, progress, readiness, health=None):
    if session.get("status") == "closed": d="closed"
    elif health and health.get("recommended_action") == "human_reassessment_required": d="human_reassessment_required"
    elif readiness.get("completion_candidate"): d="completion_review_ready"
    elif readiness.get("failed_objective_count"): d="failed"
    elif readiness.get("blocked_objective_count"): d="blocked"
    else: d="continue_required"
    body={"schema":ITERATION_DECISION_SCHEMA,"session_id":session["session_id"],"current_cycle":progress.get("cycle_number"),"objective_progress_reference":_artifact_ref(progress,"progress_id","progress_fingerprint"),"completion_readiness_reference":_artifact_ref(readiness,"readiness_id","readiness_fingerprint"),"decision":d,"reason_codes":readiness.get("completion_blockers",[]) + ([health.get("health_status")] if health else []),"remaining_objectives":progress.get("remaining_criteria",[]),"next_objective_candidates":[],"human_review_required":d in {"completion_review_ready","human_reassessment_required","blocked","failed"}}
    return _seal(body,"iteration_decision_fingerprint","iteration_decision_id","engineering-runtime-iteration-decision-")


def create_next_iteration_objective_candidate(session, progress, objectives, *, health=None):
    if health and health.get("recommended_action") == "human_reassessment_required":
        raise RuntimeSessionError("human_reassessment_required")
    remaining=progress.get("remaining_criteria",[])
    known={o["objective_id"]:o for o in objectives}
    scope=[]
    for r in remaining:
        if r["objective_id"] not in known: raise RuntimeSessionError("unknown_objective")
        scope.extend(known[r["objective_id"]]["bounded_scope"])
    body={"schema":NEXT_CANDIDATE_SCHEMA,"session_id":session["session_id"],"source_cycle":progress.get("cycle_number"),"source_progress_reference":_artifact_ref(progress,"progress_id","progress_fingerprint"),"remaining_objective_references":[_artifact_ref(known[r["objective_id"]],"objective_id","objective_fingerprint") for r in remaining],"target_criteria":remaining,"bounded_scope":sorted(set(scope)),"expected_evidence":[],"candidate_status":"candidate_only","candidate_only":True,"not_a_proposal":True,"not_approved":True,"not_authorized":True,"not_executable":True}
    return _seal(body,"candidate_fingerprint","candidate_id","engineering-runtime-next-objective-")
