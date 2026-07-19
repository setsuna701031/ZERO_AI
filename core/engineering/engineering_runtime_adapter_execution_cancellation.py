from __future__ import annotations
from typing import Any, Mapping
from core.engineering.engineering_runtime_adapter_execution_integration_common import canonical_fingerprint
SCHEMA='zero.engineering.runtime_adapter_execution_cancellation.v1'
def build_execution_cancellation(submission:Mapping[str,Any], requested=False)->dict[str,Any]:
 state='requested' if requested is True else 'not_requested' if requested is False else 'invalid'
 body={'schema':SCHEMA,'submission_id':submission.get('submission_id'),'cancellation_state':state,'pre_start_only':True,'invocation_started':False,'adapter_invoked':False}
 body['fingerprint']=canonical_fingerprint(body); body['cancellation_id']='can-'+body['fingerprint'][:24]; return body
def acknowledge_cancellation(c:Mapping[str,Any])->dict[str,Any]:
 d=dict(c); d['cancellation_state']='acknowledged' if c.get('cancellation_state')=='requested' else 'invalid'; d.pop('fingerprint',None); d.pop('cancellation_id',None); d['fingerprint']=canonical_fingerprint(d); d['cancellation_id']='can-'+d['fingerprint'][:24]; return d
