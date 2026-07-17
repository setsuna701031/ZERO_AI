from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash,_safe
CONTRACT="zero.runtime.capability_observation_evidence_relevance_assessment.v1";SCHEMA_VERSION="1";STATUSES=frozenset({"relevant","not_relevant","blocked","invalid"})
RULES={"target_exists":"existence","target_metadata_available":"metadata","target_text_preview_available":"text_preview","target_digest_available":"sha256","directory_contents_available":"directory_listing","observation_available":"*"};FORBIDDEN=frozenset({"should_mutate","should_execute","should_delete","should_write","should_deploy","business_correctness","security_certified","fully_verified","recursive_workspace_complete"});QUESTION_FIELDS=frozenset({"question_id","question_type","target_reference","required_observation_kinds","decision_scope"})
def build_capability_observation_evidence_relevance_assessment(acceptance:Any,closure:Any,result:Any,observation_request:Any,*,decision_question:Any)->dict[str,Any]:
 a,c,x,q=[deepcopy(dict(v)) if isinstance(v,Mapping) else {} for v in (acceptance,closure,result,observation_request)]
 try:d=_safe(decision_question)
 except (TypeError,ValueError):d={};bad=True
 else:bad=False
 shape=isinstance(d,Mapping) and set(d)==QUESTION_FIELDS and isinstance(d.get("question_id"),str) and bool(d.get("question_id")) and isinstance(d.get("question_type"),str) and isinstance(d.get("target_reference"),Mapping) and bool(d.get("target_reference")) and isinstance(d.get("required_observation_kinds"),list) and bool(d.get("required_observation_kinds")) and all(isinstance(v,str) for v in d.get("required_observation_kinds",[])) and isinstance(d.get("decision_scope"),Mapping) and bool(d.get("decision_scope"))
 kind=x.get("observation_kind","");target={"relative_target":q.get("relative_target","")};links=a.get("observation_closure_id")==c.get("observation_closure_id") and a.get("observation_result_id")==x.get("observation_result_id") and a.get("observation_request_id")==q.get("observation_request_id");scope=d.get("decision_scope")==q.get("limits")
 expected=RULES.get(d.get("question_type"));rule=expected=="*" or expected==kind;required=kind in d.get("required_observation_kinds",[]);target_ok=d.get("target_reference")==target
 if bad or not shape or d.get("question_type") not in set(RULES)|FORBIDDEN:status="invalid";why="malformed_decision_question"
 elif a.get("acceptance_status")!="accepted":status="blocked" if a.get("acceptance_status")=="blocked" else "invalid";why="consumer_not_accepted"
 elif d.get("question_type") in FORBIDDEN or not links or not scope:status="blocked";why="decision_scope_or_question_blocked"
 elif rule and required and target_ok:status="relevant";why="deterministic_relevance_match"
 else:status="not_relevant";why="deterministic_relevance_mismatch"
 rr={"question_type":d.get("question_type",""),"expected_observation_kind":expected or "","deterministic":True}
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"consumer_acceptance_id":a.get("consumer_acceptance_id",""),"consumer_acceptance_fingerprint":a.get("consumer_acceptance_fingerprint",""),"observation_closure_id":c.get("observation_closure_id",""),"observation_closure_fingerprint":c.get("observation_closure_fingerprint",""),"observation_result_id":x.get("observation_result_id",""),"observation_result_fingerprint":x.get("observation_result_fingerprint",""),"decision_question":d,"decision_scope":d.get("decision_scope",{}) if isinstance(d,Mapping) else {},"required_observation_kinds":d.get("required_observation_kinds",[]) if isinstance(d,Mapping) else [],"observed_kind":kind if isinstance(kind,str) else "","target_reference":target,"relevance_rules":rr,"relevance_status":status,"relevant":status=="relevant","reasons":[why],"blocked_reasons":[why] if status=="blocked" else []};f=_hash(b);return {**b,"relevance_assessment_id":"capability-observation-evidence-relevance-assessment-"+f[:24],"relevance_assessment_fingerprint":f}
assess_capability_observation_evidence_relevance=build_capability_observation_evidence_relevance_assessment
