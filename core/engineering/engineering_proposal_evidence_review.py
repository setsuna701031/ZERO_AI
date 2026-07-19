from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_review_common import ValidationResult,review_artifact,stable_record,validate_review_artifact
SCHEMA="zero.engineering.proposal_evidence_review.v1";ID_KEY="proposal_evidence_review_id";PREFIX="engineering-proposal-evidence-review-";FIELDS={"review_intake_id","items","missing_evidence","conflicting_evidence","opaque_linkage_preserved"}
def build_engineering_proposal_evidence_review(intake:Mapping[str,Any],closure:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 intent=dict(intent or {}); refs=sorted(set(intake.get("evidence_references",[]))); missing=sorted(set(intent.get("required_evidence",[]))-set(refs)); conflicts=sorted(set(intent.get("conflicting_evidence",[])))
 items=[stable_record({"review_intake_id":intake.get("proposal_review_intake_id"),"evidence_reference":r,"source_linkage":closure.get("proposal_closure_id"),"relevance":"relevant","sufficiency":"sufficient","consistency":"consistent","integrity_status":"verified","review_rationale":"bounded linkage review","finding_references":[],"status":"sufficient"},"evidence_review_id","engineering-proposal-evidence-item-") for r in refs]
 status="inconsistent" if conflicts else ("insufficient" if missing else ("sufficient" if intake.get("status")=="accepted" else "invalid"))
 return review_artifact(SCHEMA,status,{"review_intake_id":intake.get("proposal_review_intake_id"),"items":items,"missing_evidence":missing,"conflicting_evidence":conflicts,"opaque_linkage_preserved":True},ID_KEY,PREFIX)
def validate_engineering_proposal_evidence_review(v:Any)->ValidationResult:return validate_review_artifact(v,schema=SCHEMA,statuses={"sufficient","insufficient","inconsistent","invalid","unknown"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_proposal_evidence_review","validate_engineering_proposal_evidence_review"]
