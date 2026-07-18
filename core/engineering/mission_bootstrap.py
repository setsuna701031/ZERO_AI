from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.engineering.engineering_intake_common import identified,links,passive_boundary,source_status
from core.engineering.developer_intent_validation import validate_developer_intent
SCHEMA="zero.engineering.mission_bootstrap.v1";STATUSES=frozenset({"bootstrapped","needs_clarification","rejected","invalid"})
def bootstrap_engineering_mission(intent:Any)->dict[str,Any]:
 valid=validate_developer_intent(intent).valid; s={"accepted":"bootstrapped","needs_clarification":"needs_clarification","rejected":"rejected","invalid":"invalid"}.get(source_status(intent),"invalid") if valid else "invalid";v=intent if isinstance(intent,Mapping) else {}
 payload=None if s!="bootstrapped" else {"mission_kind":"engineering","mission_objective":v.get("normalized_request"),"intent_types":deepcopy(v.get("intent_types")),"allowed_scope":deepcopy(v.get("scope_hints")),"forbidden_scope":["scope_expansion","active_execution"],"explicit_constraints":deepcopy(v.get("explicit_constraints")),"requested_validation":deepcopy(v.get("requested_validation")),"risk_flags":deepcopy(v.get("risk_flags")),"required_stages":["repository_analysis","engineering_planning","change_proposal_preparation","controlled_coding_handoff"],"required_evidence":["repository_findings","bounded_change_plan","risk_assessment","test_plan"],"approval_required":True,"authorization_required":True,"mutation_allowed":False}
 return identified({"schema":SCHEMA,"status":s,**links(intent,"developer_intent","developer_intent_id"),"bootstrap_payload":payload,"reasons":["engineering_mission_bootstrapped" if s=="bootstrapped" else f"developer_intent_{s}"],"boundary":passive_boundary("passive_mission_bootstrap")},"mission_bootstrap_id","engineering-mission-bootstrap-")
build_engineering_mission_bootstrap=bootstrap_engineering_mission
__all__=["SCHEMA","STATUSES","build_engineering_mission_bootstrap","bootstrap_engineering_mission"]
