from __future__ import annotations
from typing import Any
from core.engineering.engineering_runtime_adapter_admission_common import *
SCHEMA='zero.engineering.runtime_adapter_admission_policy.v1';ID='policy_id';PREFIX='engineering-runtime-adapter-admission-policy-'
FIELDS={'rules'}
RULES=('exact_handoff_linkage_required','exact_session_linkage_required','exact_governed_admission_linkage_required','adapter_identity_required','adapter_version_required','scope_subset_required','authority_non_transferable','authority_non_reusable','authority_scope_bound','authority_not_perpetual','authority_passive','authority_no_executable_content','terminal_or_closed_authority_rejected','invalid_inputs_fail_closed')
def build_default_runtime_adapter_admission_policy()->dict[str,Any]: return stable_artifact({'schema':SCHEMA,'rules':list(RULES),'boundary':boundary()},ID,PREFIX)
def validate_runtime_adapter_admission_policy(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,statuses=set(),id_key=ID,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
 if isinstance(v,Mapping) and v.get('rules')!=list(RULES): e.append('policy_rules_mismatch')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_admission_policy(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_admission_policy(v); return {'schema':SCHEMA,'valid':r.valid,'reason_codes':list(r.errors)}
