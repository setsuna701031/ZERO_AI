from __future__ import annotations
from copy import deepcopy
import string
from typing import Any,Mapping
from core.runtime.runtime_capability_execution_session_admission import _hash,_safe
CONTRACT="zero.runtime.capability_observation_evidence_sufficiency_assessment.v1";SCHEMA_VERSION="1";STATUSES=frozenset({"sufficient","insufficient","blocked","invalid"});REQUIREMENT_FIELDS=frozenset({"require_observed","require_not_truncated","require_target_type","require_nonempty_evidence"})
def build_capability_observation_evidence_sufficiency_assessment(relevance:Any,acceptance:Any,closure:Any,result:Any,*,sufficiency_requirements:Any)->dict[str,Any]:
 r,a,c,x=[deepcopy(dict(v)) if isinstance(v,Mapping) else {} for v in (relevance,acceptance,closure,result)]
 try:req=_safe(sufficiency_requirements)
 except (TypeError,ValueError):req={};bad=True
 else:bad=False
 shape=isinstance(req,Mapping) and set(req)==REQUIREMENT_FIELDS and all(isinstance(req.get(n),bool) for n in REQUIREMENT_FIELDS);obs=x.get("observation") if isinstance(x.get("observation"),Mapping) else {};kind=x.get("observation_kind");question=r.get("decision_question",{});qtype=question.get("question_type") if isinstance(question,Mapping) else "";limitations=[]
 links=r.get("consumer_acceptance_id")==a.get("consumer_acceptance_id") and r.get("observation_closure_id")==c.get("observation_closure_id") and r.get("observation_result_id")==x.get("observation_result_id")
 valid=False
 if kind=="existence":valid=qtype in {"target_exists","observation_available"} and isinstance(obs.get("exists"),bool) and obs.get("target_type") in {"regular_file","directory","other","missing"}
 elif kind=="metadata":valid=qtype in {"target_metadata_available","observation_available"} and obs.get("target_type") in {"regular_file","directory","other"} and isinstance(obs.get("size_bytes"),int) and not isinstance(obs.get("size_bytes"),bool) and isinstance(obs.get("read_only_metadata"),Mapping)
 elif kind=="text_preview":valid=qtype in {"target_text_preview_available","observation_available"} and obs.get("encoding")=="utf-8" and isinstance(obs.get("preview"),str) and isinstance(obs.get("preview_bytes"),int) and not isinstance(obs.get("preview_bytes"),bool) and obs.get("preview_bytes")<=x.get("bytes_read",-1);limitations.append("bounded_text_preview" if x.get("truncated") else "text_preview_only")
 elif kind=="sha256":valid=qtype in {"target_digest_available","observation_available"} and obs.get("algorithm")=="sha256" and isinstance(obs.get("digest"),str) and len(obs.get("digest"))==64 and all(ch in string.hexdigits for ch in obs.get("digest")) and isinstance(obs.get("file_size_bytes"),int) and not isinstance(obs.get("file_size_bytes"),bool);limitations.append("digest_does_not_prove_content_correctness")
 elif kind=="directory_listing":
  entries=obs.get("entries");valid=qtype in {"directory_contents_available","observation_available"} and isinstance(entries,list) and len(entries)==x.get("entries_observed") and all(isinstance(e,Mapping) and set(e)=={"name","entry_type"} and isinstance(e.get("name"),str) and isinstance(e.get("entry_type"),str) for e in entries);limitations.append("bounded_non_recursive_directory_listing")
 if x.get("truncated"):limitations.append("evidence_truncated")
 requirements_ok=(not req.get("require_observed") or x.get("result_status")=="observed") and (not req.get("require_not_truncated") or x.get("truncated") is False) and (not req.get("require_nonempty_evidence") or bool(obs)) and (not req.get("require_target_type") or isinstance(obs.get("target_type"),str) and bool(obs.get("target_type")))
 if bad or not shape:status="invalid";why="malformed_sufficiency_requirements"
 elif r.get("relevance_status")=="blocked" or a.get("acceptance_status")=="blocked":status="blocked";why="upstream_blocked"
 elif r.get("relevance_status") not in {"relevant","not_relevant"} or not links or x.get("result_status") not in {"observed","not_observed","blocked","failed","invalid"}:status="invalid";why="invalid_sufficiency_chain"
 elif r.get("relevance_status")!="relevant" or not valid or not requirements_ok:status="insufficient";why="evidence_insufficient"
 else:status="sufficient";why="evidence_sufficient"
 chars={"observation_kind":kind if isinstance(kind,str) else "","observed":x.get("result_status")=="observed","truncated":x.get("truncated") is True,"nonempty":bool(obs)}
 b={"contract":CONTRACT,"schema_version":SCHEMA_VERSION,"relevance_assessment_id":r.get("relevance_assessment_id",""),"relevance_assessment_fingerprint":r.get("relevance_assessment_fingerprint",""),"consumer_acceptance_id":a.get("consumer_acceptance_id",""),"consumer_acceptance_fingerprint":a.get("consumer_acceptance_fingerprint",""),"observation_closure_id":c.get("observation_closure_id",""),"observation_closure_fingerprint":c.get("observation_closure_fingerprint",""),"observation_result_id":x.get("observation_result_id",""),"observation_result_fingerprint":x.get("observation_result_fingerprint",""),"decision_question":deepcopy(question) if isinstance(question,Mapping) else {},"sufficiency_requirements":req,"evidence_characteristics":chars,"sufficiency_status":status,"sufficient":status=="sufficient","limitations":sorted(set(limitations)),"reasons":[why],"blocked_reasons":[why] if status=="blocked" else []};f=_hash(b);return {**b,"sufficiency_assessment_id":"capability-observation-evidence-sufficiency-assessment-"+f[:24],"sufficiency_assessment_fingerprint":f}
assess_capability_observation_evidence_sufficiency=build_capability_observation_evidence_sufficiency_assessment
