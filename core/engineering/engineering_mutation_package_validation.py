from __future__ import annotations
from typing import Any
from core.engineering.engineering_mutation_preparation_common import *
def validate_mutation_package(package,proposal,approved_scope,approval_verification,admission):
 rs=[]
 if package.get('status')!='packaged': rs.append('package_not_packaged')
 if package.get('proposal_id')!=proposal.get('proposal_id'): rs.append('proposal_linkage_mismatch')
 if package.get('approved_scope_id')!=approved_scope.get('approved_scope_id'): rs.append('approved_scope_mismatch')
 if approval_verification.get('status')!='verified': rs.append('approval_not_verified')
 if admission.get('status')!='admitted': rs.append('admission_not_admitted')
 ops=package.get('ordered_prepared_operations',[])
 if [o.get('original_proposal_operation_id') for o in ops]!=approved_scope.get('approved_operation_ids',[]): rs.append('operation_order_mismatch')
 rs+=conflict_reasons(ops)+validate_false_invariants(package)+prohibited_payload(package,allow_content=True)
 body={'package_id':package.get('package_id'),'package_fingerprint':package.get('fingerprint'),'proposal_id':package.get('proposal_id'),'approved_scope_id':approved_scope.get('approved_scope_id'),'approval_verification_id':approval_verification.get('approval_verification_id'),'preparation_admission_id':admission.get('preparation_admission_id'),'validation_codes':reasons(rs),'status':'valid' if not rs else 'rejected','reason_codes':reasons(rs),'mutation_authorized':False,'mutation_performed':False}
 return artifact('mpv',SCHEMAS['mutation_package_validation'],body,'package_validation_id')
