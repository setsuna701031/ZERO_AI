from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.engineering.engineering_intake_common import identified,links,passive_boundary,source_status
from core.engineering.mission_bootstrap_validation import validate_engineering_mission_bootstrap
SCHEMA="zero.engineering.repository_analysis_request.v1";STATUSES=frozenset({"prepared","needs_clarification","rejected","invalid"})
def prepare_repository_analysis_request(bootstrap:Any)->dict[str,Any]:
 valid=validate_engineering_mission_bootstrap(bootstrap).valid;s={"bootstrapped":"prepared","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(source_status(bootstrap),"invalid") if valid else "invalid";v=bootstrap if isinstance(bootstrap,Mapping) else {};b=v.get("bootstrap_payload") or {}
 payload=None if s!="prepared" else {"analysis_objectives":deepcopy(b.get("intent_types")),"intent_types":deepcopy(b.get("intent_types")),"repository_scope":"current_repository","scope_hints":deepcopy(b.get("allowed_scope")),"evidence_requirements":["repository_findings","root_cause_or_design_analysis"],"requested_file_categories":[],"requested_test_context":deepcopy(b.get("requested_validation")),"safety_constraints":deepcopy(b.get("explicit_constraints")),"maximum_result_items":200,"maximum_preview_bytes":16384}
 return identified({"schema":SCHEMA,"status":s,**links(bootstrap,"mission_bootstrap","mission_bootstrap_id"),"analysis_request_payload":payload,"reasons":["passive_repository_analysis_prepared" if s=="prepared" else f"mission_bootstrap_{s}"],"boundary":passive_boundary("passive_analysis_request")},"repository_analysis_request_id","engineering-repository-analysis-request-")
build_repository_analysis_request=prepare_repository_analysis_request
__all__=["SCHEMA","STATUSES","build_repository_analysis_request","prepare_repository_analysis_request"]
