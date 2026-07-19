from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_review_common import FINDING_CATEGORIES,SEVERITIES,stable_record
def build_engineering_proposal_review_findings(reviews:Mapping[str,Mapping[str,Any]])->list[dict[str,Any]]:
 out=[]
 for category,review in sorted(reviews.items()):
  status=review.get("status"); normal={"sufficient","contained","consistent","acceptable_for_review","compliant"}
  if status in normal:continue
  severity="critical" if status in {"invalid","blocked","inconsistent"} else ("high" if status in {"changes_required","insufficient","insufficient_evidence"} else "unknown")
  payload={"category":category if category in FINDING_CATEGORIES else "integrity","severity":severity,"title":f"{category} review {status}","description":"review artifact requires governed resolution","source_review_artifact_ids":sorted(v for k,v in review.items() if k.endswith("_review_id")),"evidence_references":[],"affected_proposal_linkage":review.get("review_intake_id"),"affected_governance_boundary":"proposal review","recommended_resolution":"resolve finding through governed proposal review intake","blocking":severity in {"critical","high"},"approval_gate_relevant":True,"authorization_gate_relevant":False,"status":"blocking" if severity in {"critical","high"} else "open"}
  out.append(stable_record(payload,"review_finding_id","engineering-proposal-review-finding-"))
 return sorted(out,key=lambda x:(SEVERITIES.index(x["severity"]),x["review_finding_id"]))
def validate_engineering_proposal_review_findings(v:Any)->bool:return isinstance(v,list) and all(x.get("category") in FINDING_CATEGORIES and x.get("severity") in SEVERITIES for x in v)
__all__=["build_engineering_proposal_review_findings","validate_engineering_proposal_review_findings"]
