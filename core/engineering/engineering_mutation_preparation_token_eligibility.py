from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def evaluate_mutation_preparation_token_eligibility(package,package_validation,approval_verification,approved_scope,admission,consumed_token_record=None):
 rs=[]
 if package.get('status')!='packaged': rs.append('package_invalid')
 if package_validation.get('status')!='valid': rs.append('package_validation_invalid')
 if approval_verification.get('status')!='verified': rs.append('approval_not_verified')
 if approved_scope.get('status')!='sealed': rs.append('approved_scope_invalid')
 if admission.get('status')!='admitted': rs.append('admission_invalid')
 if not package.get('ordered_prepared_operations'): rs.append('empty_prepared_operations')
 if consumed_token_record: rs.append('token_already_consumed')
 rs+=validate_false_invariants(package,package_validation,approval_verification,admission)
 body={'package_id':package.get('package_id'),'package_fingerprint':package.get('fingerprint'),'package_validation_id':package_validation.get('package_validation_id'),'package_validation_fingerprint':package_validation.get('fingerprint'),'approval_verification_id':approval_verification.get('approval_verification_id'),'approved_scope_id':approved_scope.get('approved_scope_id'),'preparation_admission_id':admission.get('preparation_admission_id'),'workspace_id':package.get('workspace_id'),'workspace_root_fingerprint':package.get('workspace_root_fingerprint'),'token_use_limit':1,'status':'eligible' if not rs else 'not_eligible','reason_codes':reasons(rs),'mutation_authorized':False,'mutation_performed':False}
 return artifact('mpte',SCHEMAS['mutation_preparation_token_eligibility'],body,'token_eligibility_id')
