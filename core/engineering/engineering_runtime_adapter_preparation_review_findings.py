from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_preparation_review_common import *
from core.engineering.engineering_runtime_adapter_preparation_review_request import validate_runtime_adapter_preparation_review_request
from core.engineering.engineering_runtime_adapter_preparation_review_policy import validate_runtime_adapter_preparation_review_policy
from core.engineering.engineering_runtime_adapter_preparation_review_eligibility import validate_runtime_adapter_preparation_review_eligibility
SCHEMA='zero.engineering.runtime_adapter_preparation_review_findings.v1';ID='review_findings_id';PREFIX='engineering-runtime-adapter-preparation-review-findings-'
FIELDS={'review_request_id','review_request_fingerprint','review_policy_id','review_policy_fingerprint','review_eligibility_id','review_eligibility_fingerprint','invocation_descriptor_id','invocation_descriptor_fingerprint','preparation_id','preparation_fingerprint','preparation_closure_id','preparation_closure_fingerprint','findings','blocking_findings','advisory_findings','linkage_valid','scope_valid','resources_valid','timeout_valid','environment_valid','authority_valid','passive_invariants_valid'}
def build_runtime_adapter_preparation_review_findings(request:Mapping[str,Any],policy:Mapping[str,Any],eligibility:Mapping[str,Any],advisory_findings:Any=())->dict[str,Any]:
 blockers=[]
 if not validate_runtime_adapter_preparation_review_request(request).valid: blockers.append('invalid_review_request')
 if not validate_runtime_adapter_preparation_review_policy(policy).valid: blockers.append('invalid_review_policy')
 if not validate_runtime_adapter_preparation_review_eligibility(eligibility).valid: blockers.append('invalid_review_eligibility')
 blockers.extend(eligibility.get('reason_codes',[]) or [])
 linkage=not any('linkage_mismatch' in r for r in blockers); scope='scope_expansion' not in blockers and 'wildcard_scope' not in blockers; auth=not any(r.endswith('authority') or r=='unrestricted_authority' for r in blockers)
 blocking=normalize_findings(blockers); advisory=normalize_findings(advisory_findings); findings=normalize_findings(blocking+advisory)
 return stable_artifact({'schema':SCHEMA,'review_request_id':request.get('review_request_id'),'review_request_fingerprint':request.get('fingerprint'),'review_policy_id':policy.get('review_policy_id'),'review_policy_fingerprint':policy.get('fingerprint'),'review_eligibility_id':eligibility.get('review_eligibility_id'),'review_eligibility_fingerprint':eligibility.get('fingerprint'),'invocation_descriptor_id':request.get('invocation_descriptor_id'),'invocation_descriptor_fingerprint':request.get('invocation_descriptor_fingerprint'),'preparation_id':request.get('runtime_adapter_preparation_id'),'preparation_fingerprint':request.get('runtime_adapter_preparation_fingerprint'),'preparation_closure_id':request.get('runtime_adapter_preparation_closure_id'),'preparation_closure_fingerprint':request.get('runtime_adapter_preparation_closure_fingerprint'),'findings':findings,'blocking_findings':blocking,'advisory_findings':advisory,'linkage_valid':linkage,'scope_valid':scope,'resources_valid':'unbounded_resources' not in blocking,'timeout_valid':'invalid_timeout' not in blocking,'environment_valid':'invalid_environment_constraints' not in blocking,'authority_valid':auth,'passive_invariants_valid':'passive_invariant_violation' not in blocking and 'executable_payload' not in blocking},ID,PREFIX)
def validate_runtime_adapter_preparation_review_findings(v:Any)->ValidationResult: return validate_artifact(v,schema=SCHEMA,statuses=set(),id_key=ID,prefix=PREFIX,fields=FIELDS)
def inspect_runtime_adapter_preparation_review_findings(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_preparation_review_findings(v); return {'schema':SCHEMA,'valid':r.valid,'blocking_findings':v.get('blocking_findings') if isinstance(v,Mapping) else [],'reason_codes':list(r.errors)}
