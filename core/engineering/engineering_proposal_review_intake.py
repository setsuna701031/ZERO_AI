from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_proposal_closure import validate_engineering_proposal_closure
from core.engineering.engineering_proposal_review_common import ValidationResult,authority_absent,review_artifact,validate_review_artifact
SCHEMA="zero.engineering.proposal_review_intake.v1";ID_KEY="proposal_review_intake_id";PREFIX="engineering-proposal-review-intake-"
FIELDS={"proposal_closure_id","proposal_closure_fingerprint","engineering_proposal_id","proposal_verification_id","planning_closure_id","repository_identity","analyzed_revision","review_objective","review_scope","review_constraints","evidence_references","governance_declarations"}
GOVERNANCE={"approved":False,"authorized":False,"executable":False,"mutation_granted":False,"review_only":True}
def build_engineering_proposal_review_intake(closure:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 intent=dict(intent or {}); valid=validate_engineering_proposal_closure(closure).valid and closure.get("status")=="closed" and authority_absent(intent)
 allowed=set(closure.get("proposal_summary",{}).get("repository_areas",[])); requested=sorted(set(intent.get("review_scope",[])))
 expanded=bool(allowed and not set(requested)<=allowed); status="accepted" if valid and not expanded else ("blocked" if expanded or closure.get("status")=="blocked" else "invalid")
 payload={"proposal_closure_id":closure.get("proposal_closure_id"),"proposal_closure_fingerprint":closure.get("fingerprint"),"engineering_proposal_id":closure.get("engineering_proposal_id"),"proposal_verification_id":closure.get("proposal_verification_id"),"planning_closure_id":closure.get("planning_closure_id"),"repository_identity":closure.get("repository_identity"),"analyzed_revision":closure.get("analyzed_revision"),"review_objective":intent.get("review_objective","review sealed engineering proposal"),"review_scope":requested,"review_constraints":sorted(set(intent.get("review_constraints",[]))),"evidence_references":sorted(set(intent.get("evidence_references",[]))),"governance_declarations":dict(GOVERNANCE)}
 return review_artifact(SCHEMA,status,payload,ID_KEY,PREFIX)
def validate_engineering_proposal_review_intake(v:Any)->ValidationResult:return validate_review_artifact(v,schema=SCHEMA,statuses={"accepted","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_proposal_review_intake","validate_engineering_proposal_review_intake"]
