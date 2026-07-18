from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.engineering.engineering_intake_common import identified,links,passive_boundary,source_status
from core.engineering.repository_analysis_request_validation import validate_repository_analysis_request
SCHEMA="zero.engineering.planning_request.v1";STATUSES=frozenset({"planned_request","needs_clarification","rejected","invalid"})
def build_engineering_planning_request(analysis:Any)->dict[str,Any]:
 valid=validate_repository_analysis_request(analysis).valid;s={"prepared":"planned_request","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(source_status(analysis),"invalid") if valid else "invalid";v=analysis if isinstance(analysis,Mapping) else {};a=v.get("analysis_request_payload") or {}
 payload=None if s!="planned_request" else {"planning_objective":"prepare_bounded_engineering_change_plan","intent_types":deepcopy(a.get("intent_types")),"required_inputs":deepcopy(a.get("evidence_requirements")),"expected_outputs":["repository_findings","root_cause_or_design_analysis","bounded_change_plan","affected_files_projection","test_plan","risk_assessment","rollback_expectation"],"change_scope_policy":{"allowed_scope":deepcopy(a.get("scope_hints")),"scope_expansion":False},"validation_policy":{"requirements":deepcopy(a.get("requested_test_context")),"must_not_weaken":True},"approval_policy":{"approval_required":True,"approval_granted":False},"fallback_policy":"needs_clarification"}
 return identified({"schema":SCHEMA,"status":s,**links(analysis,"repository_analysis_request","repository_analysis_request_id"),"planning_request_payload":payload,"reasons":["passive_planning_request_prepared" if s=="planned_request" else f"analysis_request_{s}"],"boundary":passive_boundary("passive_planning_request")},"planning_request_id","engineering-planning-request-")
prepare_engineering_planning_request=build_engineering_planning_request
__all__=["SCHEMA","STATUSES","build_engineering_planning_request","prepare_engineering_planning_request"]
