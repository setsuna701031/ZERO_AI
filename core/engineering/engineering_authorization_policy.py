from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_authorization_common import ValidationResult,authorization_artifact,stable_record,validate_authorization_artifact
SCHEMA="zero.engineering.authorization_policy.v1";ID_KEY="authorization_policy_id";PREFIX="engineering-authorization-policy-";FIELDS={"authorization_intake_id","authorization_eligibility_id","policy_rules","policy_findings","policy_outcome"}
RULES=("approval_closure_verified","approval_authority_granted","eligible_for_authorization","no_execution_grant","no_mutation_grant","no_repository_mutation","constraints_bounded","execution_preparation_only")
def build_engineering_authorization_policy(i:Mapping[str,Any],e:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 x=dict(intent or {});violations=sorted(set(x.get("policy_violations",[])));rules=[stable_record({"name":n,"passed":n not in violations},"authorization_policy_rule_id","engineering-authorization-policy-rule-") for n in RULES];outcome="satisfied" if e.get("status")=="eligible" and not violations else "not_satisfied";return authorization_artifact(SCHEMA,outcome,{"authorization_intake_id":i.get("authorization_intake_id"),"authorization_eligibility_id":e.get("authorization_eligibility_id"),"policy_rules":rules,"policy_findings":violations,"policy_outcome":outcome},ID_KEY,PREFIX)
def validate_engineering_authorization_policy(v:Any)->ValidationResult:return validate_authorization_artifact(v,schema=SCHEMA,statuses={"satisfied","not_satisfied","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["RULES","build_engineering_authorization_policy","validate_engineering_authorization_policy"]
