from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_runtime_adapter_activation_token_common import *
from core.engineering.engineering_runtime_adapter_activation_token_issuance import validate_runtime_adapter_activation_token_issuance
from core.engineering.engineering_runtime_adapter_activation_token_verification import validate_runtime_adapter_activation_token_verification
SCHEMA='zero.engineering.runtime_adapter_activation_token_handoff.v1';ID='token_handoff_id';PREFIX='engineering-runtime-adapter-activation-token-handoff-'
FIELDS={'token_id','token_fingerprint','token_issuance_id','token_verification_id','token_verification_fingerprint','token_authorization_id','activation_authorization_handoff_id','activation_authorization_id','adapter_id','adapter_version','execution_session_id','invocation_descriptor_id','activation_scope','max_uses','current_uses','authority_reference','authority_constraints','eligible_for_adapter_activation_admission','activation_authorized','token_issued','token_verified','token_consumed','token_material_present','adapter_loaded','adapter_activated','adapter_invoked','runtime_invoked','authority_consumed','mutation_performed'}
def build_runtime_adapter_activation_token_handoff(token:Mapping[str,Any],verification:Mapping[str,Any])->dict[str,Any]:
 tv=validate_runtime_adapter_activation_token_issuance(token).valid; vv=validate_runtime_adapter_activation_token_verification(verification).valid
 linked=verification.get('token_id')==token.get('token_id') and verification.get('token_fingerprint')==token.get('fingerprint')
 ok=tv and vv and linked and token.get('issuance_status')=='issued' and verification.get('verification_status')=='verified' and token.get('token_state')=='issued_unconsumed' and token.get('current_uses')==0 and token.get('max_uses')==1 and token.get('consumed') is False
 return stable_artifact({'schema':SCHEMA,'token_id':token.get('token_id'),'token_fingerprint':token.get('fingerprint'),'token_issuance_id':token.get('token_issuance_id'),'token_verification_id':verification.get('token_verification_id'),'token_verification_fingerprint':verification.get('fingerprint'),'token_authorization_id':token.get('token_authorization_id'),'activation_authorization_handoff_id':token.get('activation_authorization_handoff_id'),'activation_authorization_id':token.get('activation_authorization_id'),'adapter_id':token.get('adapter_id'),'adapter_version':token.get('adapter_version'),'execution_session_id':token.get('execution_session_id'),'invocation_descriptor_id':token.get('invocation_descriptor_id'),'activation_scope':token.get('issued_scope') if ok else {},'max_uses':token.get('max_uses'),'current_uses':token.get('current_uses'),'authority_reference':token.get('authority_reference'),'authority_constraints':token.get('authority_constraints'),'eligible_for_adapter_activation_admission':ok,'activation_authorized':ok,'token_issued':ok,'token_verified':ok,'token_consumed':False,'token_material_present':False,'adapter_loaded':False,'adapter_activated':False,'adapter_invoked':False,'runtime_invoked':False,'authority_consumed':False,'mutation_performed':False},ID,PREFIX)
def validate_runtime_adapter_activation_token_handoff(v:Any)->ValidationResult:
 r=validate_artifact(v,schema=SCHEMA,id_key=ID,prefix=PREFIX,fields=FIELDS); e=list(r.errors)
 if isinstance(v,Mapping):
  ok=v.get('eligible_for_adapter_activation_admission') is True
  if ok and not (v.get('activation_authorized') is True and v.get('token_issued') is True and v.get('token_verified') is True and v.get('token_consumed') is False and v.get('max_uses')==1 and v.get('current_uses')==0): e.append('invalid_handoff_invariants')
  if not passive_invariants_valid(v): e.append('passive_invariant_violation')
 return ValidationResult(not e,tuple(dict.fromkeys(e)))
def inspect_runtime_adapter_activation_token_handoff(v:Any)->dict[str,Any]:
 r=validate_runtime_adapter_activation_token_handoff(v); return {'schema':SCHEMA,'valid':r.valid,'eligible_for_adapter_activation_admission':v.get('eligible_for_adapter_activation_admission') if isinstance(v,Mapping) else False,'reason_codes':list(r.errors)}
