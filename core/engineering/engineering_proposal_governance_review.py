from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_common import contains_forbidden_payload
from core.engineering.engineering_proposal_review_common import ValidationResult,authority_absent,review_artifact,validate_review_artifact
SCHEMA="zero.engineering.proposal_governance_review.v1";ID_KEY="proposal_governance_review_id";PREFIX="engineering-proposal-governance-review-";FIELDS={"review_intake_id","no_patch_check","no_diff_check","no_source_payload_check","no_repository_mutation_check","no_execution_authority_check","no_mutation_authority_check","no_approval_authority_check","no_authorization_authority_check","review_authority_limitation_check","next_boundary_compliance_check","governance_findings"}
def build_engineering_proposal_governance_review(intake:Mapping[str,Any],closure:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 i=dict(intent or {}); forbidden=contains_forbidden_payload(i); authority=authority_absent(i); next_ok=i.get("next_boundary","Engineering Approval Foundation") in {"Engineering Approval Foundation","governed approval intake boundary"}; findings=[]
 if forbidden:findings.append("forbidden_payload")
 if not authority:findings.append("authority_violation")
 if not next_ok:findings.append("invalid_next_boundary")
 ok=not findings;p={"review_intake_id":intake.get("proposal_review_intake_id"),"no_patch_check":not forbidden,"no_diff_check":not forbidden,"no_source_payload_check":not forbidden,"no_repository_mutation_check":True,"no_execution_authority_check":authority,"no_mutation_authority_check":authority,"no_approval_authority_check":authority,"no_authorization_authority_check":authority,"review_authority_limitation_check":authority,"next_boundary_compliance_check":next_ok,"governance_findings":findings};return review_artifact(SCHEMA,"compliant" if ok else "invalid",p,ID_KEY,PREFIX)
def validate_engineering_proposal_governance_review(v:Any)->ValidationResult:return validate_review_artifact(v,schema=SCHEMA,statuses={"compliant","changes_required","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_proposal_governance_review","validate_engineering_proposal_governance_review"]
