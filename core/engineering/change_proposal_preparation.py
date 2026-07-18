from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.engineering.engineering_intake_common import identified,links,passive_boundary,source_status
from core.engineering.planning_request_validation import validate_engineering_planning_request
SCHEMA="zero.engineering.change_proposal_preparation.v1";STATUSES=frozenset({"prepared","needs_clarification","rejected","invalid"})
def prepare_change_proposal(planning:Any)->dict[str,Any]:
 valid=validate_engineering_planning_request(planning).valid;s={"planned_request":"prepared","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(source_status(planning),"invalid") if valid else "invalid";v=planning if isinstance(planning,Mapping) else {};p=v.get("planning_request_payload") or {}
 payload=None if s!="prepared" else {"proposal_objective":p.get("planning_objective"),"intent_types":deepcopy(p.get("intent_types")),"required_analysis_evidence":deepcopy(p.get("required_inputs")),"required_planning_evidence":deepcopy(p.get("expected_outputs")),"scope_enforcement":deepcopy(p.get("change_scope_policy")),"change_limits":{"bounded":True,"mutation_allowed":False},"required_validation":deepcopy(p.get("validation_policy")),"approval_required":True,"authorization_required":True,"proposal_status":"not_created"}
 return identified({"schema":SCHEMA,"status":s,**links(planning,"planning_request","planning_request_id"),"preparation_payload":payload,"reasons":["change_proposal_preparation_ready" if s=="prepared" else f"planning_request_{s}"],"boundary":passive_boundary("passive_proposal_preparation",execution_plan_created=False,approval_granted=False,authorization_granted=False)},"change_proposal_preparation_id","engineering-change-proposal-preparation-")
build_change_proposal_preparation=prepare_change_proposal
__all__=["SCHEMA","STATUSES","build_change_proposal_preparation","prepare_change_proposal"]
