from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
SCHEMA='zero.engineering.runtime_adapter_execution_closure.v1'
def build_execution_closure(result:Mapping[str,Any], verification:Mapping[str,Any], evidence:Mapping[str,Any])->dict[str,Any]:
 closed=verification.get('verification_status')=='verified' and result.get('result_status') in {'succeeded','rejected','cancelled','failed'}
 body={'schema':SCHEMA,'closure_status':'closed' if closed else 'not_closed','execution_status':result.get('result_status'),'verification_status':verification.get('verification_status'),'adapter_id':result.get('adapter_id'),'adapter_version':result.get('adapter_version'),'operation':result.get('operation'),'output_failure_disposition':'output' if 'output' in result else 'failure' if 'failure' in result else 'none','external_effect_invariant_status':'confirmed_false','upstream_linkage_status':'linked','result_id':result.get('result_id'),'verification_id':verification.get('verification_id'),'evidence_id':evidence.get('evidence_id')}
 body['fingerprint']=canonical_fingerprint(body); body['closure_id']='cls-'+body['fingerprint'][:24]; return body
