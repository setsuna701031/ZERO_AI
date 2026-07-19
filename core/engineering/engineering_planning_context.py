from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import ValidationResult, planning_artifact, validate_planning_artifact
from core.engineering.repository_analysis_closure import validate_repository_analysis_closure

SCHEMA="zero.engineering.planning_context.v1"; ID_KEY="planning_context_id"; PREFIX="engineering-planning-context-"
FIELDS={"repository_analysis_closure_id","repository_analysis_closure_fingerprint","repository_identity","analyzed_revision","planning_objective","allowed_scope","excluded_scope","constraints","evidence_references"}

def build_engineering_planning_context(closure:Mapping[str,Any], intent:Mapping[str,Any]|None=None, constraints:Mapping[str,Any]|None=None)->dict[str,Any]:
    checked=validate_repository_analysis_closure(closure)
    if not checked.valid or closure.get("status")!="closed": raise ValueError("repository_analysis_closure_invalid")
    intent={} if intent is None else dict(intent); constraints={} if constraints is None else dict(constraints)
    allowed_keys={"planning_objective","allowed_scope","excluded_scope","goals"}
    if set(intent)-allowed_keys or not isinstance(constraints,dict): raise ValueError("unsupported_planning_intent")
    report=closure["report"]; evidence=list(report.get("evidence_index",[]))
    proven=sorted(k for k,v in report.get("engineering_surface_summary",{}).items() if isinstance(v,int) and v>=0)
    requested=intent.get("allowed_scope",proven)
    if not isinstance(requested,list) or not set(requested)<=set(proven): raise ValueError("scope_expansion")
    excluded=intent.get("excluded_scope",[])
    if not isinstance(excluded,list) or not set(excluded)<=set(proven): raise ValueError("scope_expansion")
    objective=intent.get("planning_objective","Produce a bounded engineering plan from sealed repository analysis evidence")
    if not isinstance(objective,str) or not objective.strip(): raise ValueError("invalid_planning_objective")
    lineage=closure.get("lineage",{}); root=lineage.get("root_admission",{}); snapshot=lineage.get("snapshot",{})
    payload={"repository_analysis_closure_id":closure[ID_KEY.replace("planning_context","repository_analysis_closure")],"repository_analysis_closure_fingerprint":closure["fingerprint"],
             "repository_identity":{"repository_root_admission_id":root.get("source_root_admission_id"),"repository_root_admission_fingerprint":root.get("source_root_admission_fingerprint")},
             "analyzed_revision":{"repository_snapshot_id":snapshot.get("source_snapshot_id"),"repository_snapshot_fingerprint":snapshot.get("source_snapshot_fingerprint")},
             "planning_objective":objective.strip(),"allowed_scope":sorted(set(requested)),"excluded_scope":sorted(set(excluded)),
             "constraints":{k:constraints[k] for k in sorted(constraints)},"evidence_references":sorted(set(evidence))}
    return planning_artifact(SCHEMA,"prepared",payload,ID_KEY,PREFIX)

def validate_engineering_planning_context(v:Any)->ValidationResult:
    r=validate_planning_artifact(v,schema=SCHEMA,statuses={"prepared","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
    if isinstance(v,dict):
        if not v.get("evidence_references"): e.append("missing_evidence")
        if set(v.get("allowed_scope",[])) & set(v.get("excluded_scope",[])): e.append("scope_conflict")
    return ValidationResult(not e,tuple(dict.fromkeys(e)))

build_planning_context=build_engineering_planning_context
__all__=["build_engineering_planning_context","build_planning_context","validate_engineering_planning_context"]
