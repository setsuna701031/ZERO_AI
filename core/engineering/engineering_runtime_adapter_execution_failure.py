from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
SCHEMA='zero.engineering.runtime_adapter_execution_failure.v1'
EXC={'ValueError':'value_error','TypeError':'type_error','KeyError':'key_error','RuntimeError':'runtime_error','Exception':'ordinary_exception'}
def normalize_exception(exc:Exception, stage='adapter_invocation')->dict[str,Any]: return build_execution_failure({},'adapter_exception',stage,EXC.get(type(exc).__name__,'ordinary_exception'))
def build_execution_failure(submission:Mapping[str,Any], code:str, stage:str, category:str='policy_rejection')->dict[str,Any]:
 body={'schema':SCHEMA,'submission_id':submission.get('submission_id'),'failure_code':code,'exception_category':category,'execution_stage':stage,'retryable':False,'message_code':'normalized_'+code}
 body['failure_fingerprint']=canonical_fingerprint(body); body['fingerprint']=body['failure_fingerprint']; body['failure_id']='fail-'+body['fingerprint'][:24]; return body
