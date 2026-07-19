from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_planning_common import fingerprint, stable_id
from core.engineering.engineering_planning_context import validate_engineering_planning_context

def extract_engineering_goals(context:Mapping[str,Any], intent:Mapping[str,Any]|None=None)->list[dict[str,Any]]:
    if not validate_engineering_planning_context(context).valid: raise ValueError("planning_context_invalid")
    refs=context["evidence_references"]; specs=(intent or {}).get("goals") if isinstance(intent,Mapping) else None
    if specs is None: specs=[{"title":"Plan verified repository engineering work","description":context["planning_objective"],"evidence_references":refs,"affected_components":context["allowed_scope"]}]
    if not isinstance(specs,list) or not specs: raise ValueError("unsupported_goal")
    out=[]
    for spec in specs:
        if not isinstance(spec,Mapping): raise ValueError("unsupported_goal")
        evidence=sorted(set(spec.get("evidence_references",[])))
        components=sorted(set(spec.get("affected_components",context["allowed_scope"])))
        if not evidence or not set(evidence)<=set(refs): raise ValueError("unsupported_goal")
        if not set(components)<=set(context["allowed_scope"]): raise ValueError("scope_expansion")
        material={"title":str(spec.get("title","")).strip(),"description":str(spec.get("description","")).strip(),"rationale":"Supported by sealed repository analysis evidence","source_evidence_references":evidence,"affected_components":components,"desired_outcome":str(spec.get("desired_outcome","A bounded, verifiable engineering outcome")),"constraints":context["constraints"],"validation_expectations":sorted(set(spec.get("validation_expectations",["deterministic output verification","read-only boundary verification"]))),"priority":spec.get("priority","normal"),"confidence":spec.get("confidence","evidence_backed"),"status":"bounded"}
        if not material["title"] or not material["description"]: raise ValueError("unsupported_goal")
        item={**material,"goal_id":stable_id("engineering-goal-",material)}; item["fingerprint"]=fingerprint(item); out.append(item)
    return sorted(out,key=lambda x:x["goal_id"])

build_engineering_goals=extract_engineering_goals
__all__=["build_engineering_goals","extract_engineering_goals"]
