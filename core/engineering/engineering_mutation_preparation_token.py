from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def issue_mutation_preparation_token(eligibility,package,package_validation,approval_verification,approved_scope,preparation_sequence=0):
 rs=[]
 if eligibility.get('status')!='eligible': rs.append('token_not_eligible')
 body={'token_schema':SCHEMAS['mutation_preparation_token'],'package_id':package.get('package_id'),'package_fingerprint':package.get('fingerprint'),'package_validation_id':package_validation.get('package_validation_id'),'package_validation_fingerprint':package_validation.get('fingerprint'),'approval_verification_id':approval_verification.get('approval_verification_id'),'approval_verification_fingerprint':approval_verification.get('fingerprint'),'approved_scope_id':approved_scope.get('approved_scope_id'),'approved_scope_fingerprint':approved_scope.get('fingerprint'),'workspace_id':package.get('workspace_id'),'workspace_root_fingerprint':package.get('workspace_root_fingerprint'),'operation_fingerprints':[o.get('original_proposal_operation_fingerprint') for o in package.get('ordered_prepared_operations',[])],'preparation_sequence':preparation_sequence,'token_use_limit':1,'token_purpose':'mutation_preparation_handoff','token_state':'issued' if not rs else 'not_issued','mutation_authorized':False,'token_consumed':False,'mutation_performed':False,'status':'issued' if not rs else 'not_issued','reason_codes':reasons(rs)}
 return artifact('mpt',SCHEMAS['mutation_preparation_token'],body,'token_id')
