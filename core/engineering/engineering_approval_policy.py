from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_approval_common import ValidationResult,approval_artifact,stable_record,validate_approval_artifact
SCHEMA="zero.engineering.approval_policy.v1";ID_KEY="approval_policy_id";PREFIX="engineering-approval-policy-";FIELDS={"approval_intake_id","approval_eligibility_id","policy_rules","policy_findings","policy_outcome"}
RULES=("review_closure_verified","eligible_for_approval","no_authorization_grant","no_execution_grant","no_mutation_grant","no_repository_mutation","conditions_bounded")
def build_engineering_approval_policy(i:Mapping[str,Any],e:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 x=dict(intent or {});violations=sorted(set(x.get("policy_violations",[])));rules=[stable_record({"name":n,"passed":n not in violations},"approval_policy_rule_id","engineering-approval-policy-rule-") for n in RULES];outcome="satisfied" if e.get("status")=="eligible" and not violations else "not_satisfied";p={"approval_intake_id":i.get("approval_intake_id"),"approval_eligibility_id":e.get("approval_eligibility_id"),"policy_rules":rules,"policy_findings":violations,"policy_outcome":outcome};return approval_artifact(SCHEMA,outcome,p,ID_KEY,PREFIX)
def validate_engineering_approval_policy(v:Any)->ValidationResult:return validate_approval_artifact(v,schema=SCHEMA,statuses={"satisfied","not_satisfied","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["RULES","build_engineering_approval_policy","validate_engineering_approval_policy"]
