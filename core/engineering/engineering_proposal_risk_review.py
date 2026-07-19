from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_common import fingerprint,stable_proposal_id
RISK_CATEGORIES=("approval bypass risk","authorization bypass risk","compatibility risk","dependency risk","evidence insufficiency risk","frozen contract risk","implementation ambiguity risk","mutation boundary risk","operational risk","rollback uncertainty risk","scope expansion risk","validation gap risk")
def build_engineering_proposal_risk_review(changes:list[Mapping[str,Any]],evidence_references:list[str],intent:Mapping[str,Any]|None=None)->list[dict[str,Any]]:
 specs=(intent or {}).get("risks")
 if specs is None:specs=[{"category":"mutation boundary risk","description":"The proposal describes change intent but grants no implementation or mutation authority","evidence_references":evidence_references,"affected_proposed_change_ids":[x["proposed_change_id"] for x in changes],"likelihood":"unknown","impact":"high","severity":"unknown","mitigation_requirements":["require later governed review and authorization"],"residual_risk":"unknown"}]
 out=[];valid_changes={x["proposed_change_id"] for x in changes}
 for spec in specs:
  refs=sorted(set(spec.get("evidence_references",[])));targets=sorted(set(spec.get("affected_proposed_change_ids",[])))
  if spec.get("category") not in RISK_CATEGORIES or not refs or not set(refs)<=set(evidence_references) or not set(targets)<=valid_changes:raise ValueError("unsupported_proposal_risk")
  material={"category":spec["category"],"description":str(spec.get("description","")).strip(),"source_planning_risk_ids":sorted(set(spec.get("source_planning_risk_ids",[]))),"evidence_references":refs,"affected_proposed_change_ids":targets,"likelihood":spec.get("likelihood","unknown"),"impact":spec.get("impact","unknown"),"severity":spec.get("severity","unknown"),"mitigation_requirements":sorted(set(spec.get("mitigation_requirements",[]))),"residual_risk":spec.get("residual_risk","unknown"),"approval_blocking":bool(spec.get("approval_blocking",False)),"authorization_blocking":bool(spec.get("authorization_blocking",False)),"proposal_blocking":bool(spec.get("proposal_blocking",False)),"status":"reviewed"}
  if not material["description"]:raise ValueError("unsupported_proposal_risk")
  value={**material,"proposal_risk_id":stable_proposal_id("engineering-proposal-risk-",material)};value["fingerprint"]=fingerprint(value);out.append(value)
 return sorted(out,key=lambda x:x["proposal_risk_id"])
build_proposal_risk_review=build_engineering_proposal_risk_review
__all__=["RISK_CATEGORIES","build_engineering_proposal_risk_review","build_proposal_risk_review"]
