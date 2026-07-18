from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.engineering.engineering_intake_common import identified,links,passive_boundary,source_status
from core.engineering.change_proposal_preparation_validation import validate_change_proposal_preparation
SCHEMA="zero.engineering.controlled_coding_handoff.v1";STATUSES=frozenset({"handed_off","needs_clarification","rejected","invalid"})
def build_controlled_coding_handoff(preparation:Any)->dict[str,Any]:
 valid=validate_change_proposal_preparation(preparation).valid;s={"prepared":"handed_off","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(source_status(preparation),"invalid") if valid else "invalid";v=preparation if isinstance(preparation,Mapping) else {};p=v.get("preparation_payload") or {}
 payload=None if s!="handed_off" else {"engineering_objective":p.get("proposal_objective"),"intent_types":deepcopy(p.get("intent_types")),"allowed_scope":deepcopy((p.get("scope_enforcement") or {}).get("allowed_scope")),"forbidden_scope":["scope_expansion","active_execution"],"analysis_requirements":deepcopy(p.get("required_analysis_evidence")),"planning_requirements":deepcopy(p.get("required_planning_evidence")),"proposal_requirements":{"proposal_status":"not_created"},"validation_requirements":deepcopy(p.get("required_validation")),"governance_requirements":{"approval_required":True,"authorization_required":True,"approval_granted":False,"authorization_granted":False},"next_stage":"repository_analysis_pending"}
 b=passive_boundary("passive_handoff",developer_intake_complete=s=="handed_off",repository_analysis_started=False,approval_granted=False,authorization_granted=False)
 return identified({"schema":SCHEMA,"status":s,**links(preparation,"change_proposal_preparation","change_proposal_preparation_id"),"handoff_payload":payload,"reasons":["developer_intake_handed_off" if s=="handed_off" else f"proposal_preparation_{s}"],"boundary":b},"controlled_coding_handoff_id","engineering-controlled-coding-handoff-")
handoff_controlled_coding=build_controlled_coding_handoff
__all__=["SCHEMA","STATUSES","build_controlled_coding_handoff","handoff_controlled_coding"]
