from __future__ import annotations
from typing import Any,Mapping,Sequence
from core.engineering.engineering_proposal_review_common import AUTHORITY,ValidationResult,review_artifact,validate_review_artifact
SCHEMA="zero.engineering.proposal_review_decision.v1";ID_KEY="proposal_review_decision_id";PREFIX="engineering-proposal-review-decision-";FIELDS={"review_intake_id","review_linkages","findings_linkage","decision","decision_rationale","blocking_finding_ids","unresolved_finding_ids","approval_readiness","authorization_readiness","execution_readiness","authority_declarations"}
def build_engineering_proposal_review_decision(intake:Mapping[str,Any],reviews:Mapping[str,Mapping[str,Any]],findings:Sequence[Mapping[str,Any]])->dict[str,Any]:
 statuses={x.get("status") for x in reviews.values()}; blocking=sorted(x.get("review_finding_id") for x in findings if x.get("blocking")); unresolved=sorted(x.get("review_finding_id") for x in findings if x.get("status")!="acknowledged")
 if "invalid" in statuses:decision="invalid"
 elif "blocked" in statuses or "inconsistent" in statuses:decision="blocked"
 elif statuses & {"insufficient","insufficient_evidence","unknown"}:decision="insufficient_evidence"
 elif blocking or "changes_required" in statuses:decision="changes_requested"
 else:decision="ready_for_approval"
 p={"review_intake_id":intake.get("proposal_review_intake_id"),"review_linkages":{k:next((v for n,v in x.items() if n.endswith("_review_id")),None) for k,x in sorted(reviews.items())},"findings_linkage":[x.get("review_finding_id") for x in findings],"decision":decision,"decision_rationale":"deterministic propagation of review findings","blocking_finding_ids":blocking,"unresolved_finding_ids":unresolved,"approval_readiness":"eligible_for_approval_review" if decision=="ready_for_approval" else ("unknown" if decision=="insufficient_evidence" else "not_eligible"),"authorization_readiness":"not_evaluated","execution_readiness":"not_evaluated","authority_declarations":dict(AUTHORITY)};return review_artifact(SCHEMA,decision,p,ID_KEY,PREFIX)
def validate_engineering_proposal_review_decision(v:Any)->ValidationResult:return validate_review_artifact(v,schema=SCHEMA,statuses={"ready_for_approval","changes_requested","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_proposal_review_decision","validate_engineering_proposal_review_decision"]
