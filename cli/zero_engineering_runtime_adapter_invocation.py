from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_adapter_invocation_common import canonical_fingerprint
from core.engineering.engineering_runtime_adapter_invocation_intake import *
from core.engineering.engineering_runtime_adapter_invocation_admission import *
from core.engineering.engineering_runtime_adapter_invocation_preparation import *
from core.engineering.engineering_runtime_adapter_invocation_review import *
from core.engineering.engineering_runtime_adapter_invocation_authorization import *
from core.engineering.engineering_runtime_adapter_controlled_invocation import *
from core.engineering.engineering_runtime_adapter_invocation_observation import *
from core.engineering.engineering_runtime_adapter_invocation_evidence import *
from core.engineering.engineering_runtime_adapter_invocation_result import *
from core.engineering.engineering_runtime_adapter_invocation_verification import *
from core.engineering.engineering_runtime_adapter_invocation_handoff import *
from core.engineering.engineering_runtime_adapter_invocation_closure import *
def _emit(obj, code=0):
 sys.stdout.write(json.dumps(obj, sort_keys=True, separators=(',',':'))+'\n'); return code
def _error(code, reason): return _emit({'error':{'code':code,'reason_code':reason}},1)
def _read(args):
 data=sys.stdin.read() if not args.input_file else Path(args.input_file).read_text(encoding='utf-8')
 return json.loads(data or '{}')
def main(argv=None):
 p=argparse.ArgumentParser(add_help=True); p.add_argument('action'); p.add_argument('--input-file'); a=p.parse_args(argv)
 try: payload=_read(a)
 except json.JSONDecodeError: return _error('invalid_json','malformed_json')
 except OSError: return _error('input_error','input_unavailable')
 try:
  x=payload if isinstance(payload,dict) else {}
  act=a.action
  if act=='admission-policy': return _emit(build_default_runtime_adapter_invocation_admission_policy())
  if act=='preparation-policy': return _emit(build_default_runtime_adapter_invocation_preparation_policy())
  if act=='authorization-policy': return _emit(build_default_runtime_adapter_invocation_authorization_policy())
  if act=='intake-request': return _emit(build_runtime_adapter_invocation_intake_request(x.get('activation_handoff',{}),x.get('requested_invocation_scope'),x.get('requested_operation'),x.get('input_bindings'),x.get('expected_output_contract'),x.get('invocation_constraints'),x.get('resource_constraints'),x.get('timeout_constraints'),x.get('environment_constraints'),x.get('intake_context')))
  if act=='intake': return _emit(build_runtime_adapter_invocation_intake(x.get('request',{}),x.get('activation_handoff',{})))
  if act=='admit': return _emit(build_runtime_adapter_invocation_admission(x.get('intake',{}),x.get('policy')))
  if act=='prepare': return _emit(build_runtime_adapter_invocation_preparation(x.get('admission',{}),x.get('policy')))
  if act=='review-request': return _emit(build_runtime_adapter_invocation_review_request(x.get('preparation',{}),x.get('admission',{}),x.get('intake',{})))
  if act=='review': return _emit(evaluate_runtime_adapter_invocation_review(x.get('request',{}),x.get('preparation',{}),x.get('admission',{}),x.get('intake',{})))
  if act=='authorize': return _emit(build_runtime_adapter_invocation_authorization(x.get('review',{}),x.get('policy')))
  if act=='invoke': return _emit(build_runtime_adapter_controlled_invocation(x.get('authorization',{}),x.get('preparation',{})))
  if act=='observe': return _emit(build_runtime_adapter_invocation_observation(x.get('controlled_invocation',{})))
  if act=='evidence': return _emit(build_runtime_adapter_invocation_evidence(x.get('observation',{}),x.get('controlled_invocation',{})))
  if act=='result': return _emit(build_runtime_adapter_invocation_result(x.get('controlled_invocation',{}),x.get('observation',{}),x.get('evidence',{})))
  if act=='verify': return _emit(verify_runtime_adapter_invocation_governance(x.get('intake',{}),x.get('admission',{}),x.get('preparation',{}),x.get('review',{}),x.get('authorization',{}),x.get('controlled_invocation',{}),x.get('observation',{}),x.get('evidence',{}),x.get('result',{})))
  if act=='handoff': return _emit(build_runtime_adapter_invocation_handoff(x.get('result',{}),x.get('verification',{}),x.get('controlled_invocation',{})))
  if act=='closure': return _emit(build_runtime_adapter_invocation_governance_closure(x.get('intake_request',{}),x.get('intake',{}),x.get('admission_policy',{}),x.get('admission',{}),x.get('preparation_policy',{}),x.get('preparation',{}),x.get('review_request',{}),x.get('review',{}),x.get('authorization_policy',{}),x.get('authorization',{}),x.get('controlled_invocation',{}),x.get('observation',{}),x.get('evidence',{}),x.get('result',{}),x.get('verification',{}),x.get('handoff',{})))
  if act in {'validate','inspect'}:
   obj=x.get('artifact',x); schema=obj.get('schema') if isinstance(obj,dict) else None
   validators={
    'zero.engineering.runtime_adapter_invocation_intake_request.v1':inspect_runtime_adapter_invocation_intake_request,'zero.engineering.runtime_adapter_invocation_intake.v1':inspect_runtime_adapter_invocation_intake,'zero.engineering.runtime_adapter_invocation_admission_policy.v1':inspect_runtime_adapter_invocation_admission_policy,'zero.engineering.runtime_adapter_invocation_admission.v1':inspect_runtime_adapter_invocation_admission,'zero.engineering.runtime_adapter_invocation_preparation_policy.v1':inspect_runtime_adapter_invocation_preparation_policy,'zero.engineering.runtime_adapter_invocation_preparation.v1':inspect_runtime_adapter_invocation_preparation,'zero.engineering.runtime_adapter_invocation_review_request.v1':inspect_runtime_adapter_invocation_review_request,'zero.engineering.runtime_adapter_invocation_review.v1':inspect_runtime_adapter_invocation_review,'zero.engineering.runtime_adapter_invocation_authorization_policy.v1':inspect_runtime_adapter_invocation_authorization_policy,'zero.engineering.runtime_adapter_invocation_authorization.v1':inspect_runtime_adapter_invocation_authorization,'zero.engineering.runtime_adapter_controlled_invocation.v1':inspect_runtime_adapter_controlled_invocation,'zero.engineering.runtime_adapter_invocation_observation.v1':inspect_runtime_adapter_invocation_observation,'zero.engineering.runtime_adapter_invocation_evidence.v1':inspect_runtime_adapter_invocation_evidence,'zero.engineering.runtime_adapter_invocation_result.v1':inspect_runtime_adapter_invocation_result,'zero.engineering.runtime_adapter_invocation_verification.v1':inspect_runtime_adapter_invocation_verification,'zero.engineering.runtime_adapter_invocation_handoff.v1':inspect_runtime_adapter_invocation_handoff,'zero.engineering.runtime_adapter_invocation_governance_closure.v1':inspect_runtime_adapter_invocation_governance_closure}
   out=validators.get(schema,lambda z:{'valid':False,'reason_codes':['unsupported_schema']})(obj); return _emit(out,0 if out.get('valid') else 1)
  return _error('unsupported_action','unsupported_action')
 except Exception: return _error('execution_error','canonical_error')
if __name__=='__main__': raise SystemExit(main())
