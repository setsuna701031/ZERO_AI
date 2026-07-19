from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
SCHEMA='zero.engineering.runtime_adapter_execution_evidence.v1'
def build_execution_evidence(result:Mapping[str,Any], verification:Mapping[str,Any])->dict[str,Any]:
 body={'schema':SCHEMA,'stage_code':'reference_adapter_execution','decision_code':verification.get('verification_status'),'result_id':result.get('result_id'),'result_fingerprint':result.get('fingerprint'),'verification_id':verification.get('verification_id'),'status_mapping':result.get('result_status'),'adapter_id':result.get('adapter_id'),'adapter_version':result.get('adapter_version'),'invariant_codes':['external_effects_false','upstream_linkage_preserved']}
 body['fingerprint']=canonical_fingerprint(body); body['evidence_id']='evd-'+body['fingerprint'][:24]; return body
