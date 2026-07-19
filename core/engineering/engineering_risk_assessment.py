from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_planning_common import fingerprint,stable_id
RISK_CATEGORIES=("compatibility risk","contract drift risk","dependency risk","determinism risk","mutation boundary risk","operational risk","repository state risk","scope risk","validation gap risk")
def build_engineering_risk_assessment(context:Mapping[str,Any],goals:list[Mapping[str,Any]],work_items:list[Mapping[str,Any]],risks:list[Mapping[str,Any]]|None=None)->list[dict[str,Any]]:
 specs=risks if risks is not None else [{"category":"mutation boundary risk","description":"Implementation may require repository mutation that this planning artifact cannot authorize","likelihood":"unknown","impact":"high","severity":"unknown","blocking_status":"non_blocking","mitigation_strategy":"Require a later governed authorization boundary","residual_risk":"unknown","evidence_references":context["evidence_references"]}]
 out=[];valid_targets={x["goal_id"] for x in goals}|{x["work_item_id"] for x in work_items}
 for spec in specs:
  category=spec.get("category");refs=sorted(set(spec.get("evidence_references",[])));targets=sorted(set(spec.get("affected_ids",[])))
  if category not in RISK_CATEGORIES or not refs or not set(refs)<=set(context["evidence_references"]) or not set(targets)<=valid_targets:raise ValueError("unsupported_risk")
  material={"category":category,"description":str(spec.get("description","")).strip(),"likelihood":spec.get("likelihood","unknown"),"impact":spec.get("impact","unknown"),"severity":spec.get("severity","unknown"),"evidence_references":refs,"affected_ids":targets,"mitigation_strategy":str(spec.get("mitigation_strategy","Preserve as unknown pending evidence")),"residual_risk":spec.get("residual_risk","unknown"),"blocking_status":spec.get("blocking_status","non_blocking")}
  if not material["description"] or material["blocking_status"] not in {"blocking","non_blocking"}:raise ValueError("unsupported_risk")
  value={**material,"risk_id":stable_id("engineering-risk-",material)};value["fingerprint"]=fingerprint(value);out.append(value)
 return sorted(out,key=lambda x:x["risk_id"])
build_risk_assessment=build_engineering_risk_assessment
__all__=["RISK_CATEGORIES","build_engineering_risk_assessment","build_risk_assessment"]
