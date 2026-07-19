from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_adapter_execution_request import *
from core.engineering.engineering_runtime_adapter_execution_capability import *
from core.engineering.engineering_runtime_adapter_binding_resolution import *
from core.engineering.engineering_runtime_adapter_execution_environment_admission import *
from core.engineering.engineering_runtime_adapter_execution_isolation_policy import *
from core.engineering.engineering_runtime_adapter_execution_resource_budget import *
from core.engineering.engineering_runtime_adapter_execution_timeout_policy import *
from core.engineering.engineering_runtime_adapter_execution_preparation import *
from core.engineering.engineering_runtime_adapter_execution_review import *
from core.engineering.engineering_runtime_adapter_execution_authorization import *
from core.engineering.engineering_runtime_adapter_execution_envelope import *
from core.engineering.engineering_runtime_adapter_execution_readiness_verification import *
from core.engineering.engineering_runtime_adapter_executor_handoff import *
from core.engineering.engineering_runtime_adapter_execution_integration_closure import *

def emit(o,code=0): sys.stdout.write(json.dumps(o,sort_keys=True,separators=(',',':'))+'\n'); return code
def err(c,r): return emit({'error':{'code':c,'reason_code':r}},1)
def read(args):
 data=sys.stdin.read() if not args.input_file else Path(args.input_file).read_text(encoding='utf-8')
 return json.loads(data or '{}')
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('action'); p.add_argument('--input-file'); a=p.parse_args(argv)
 try: x=read(a)
 except json.JSONDecodeError: return err('invalid_json','malformed_json')
 except OSError: return err('input_error','input_unavailable')
 if not isinstance(x,dict): return err('invalid_input','object_required')
 try:
  actions={
   'execution-request':lambda:build_runtime_adapter_execution_request(x.get('invocation_handoff',{}),x.get('invocation_closure',{})),
   'capability':lambda:build_runtime_adapter_execution_capability(**x),
   'binding-resolution':lambda:build_runtime_adapter_binding_resolution(x.get('request',{}),x.get('capability',{})),
   'environment-admission':lambda:build_runtime_adapter_execution_environment_admission(environment_profile=x.get('environment_profile',{}),requirements=x.get('requirements',{})),
   'isolation-policy':lambda:build_runtime_adapter_execution_isolation_policy(**x),
   'resource-budget':lambda:build_runtime_adapter_execution_resource_budget(**x),
   'timeout-policy':lambda:build_runtime_adapter_execution_timeout_policy(**x),
   'prepare':lambda:build_runtime_adapter_execution_preparation(**x),
   'review':lambda:build_runtime_adapter_execution_review(**x),
   'authorize':lambda:build_runtime_adapter_execution_authorization(**x),
   'envelope':lambda:build_runtime_adapter_execution_envelope(**x),
   'verify-readiness':lambda:build_runtime_adapter_execution_readiness_verification(**x),
   'executor-handoff':lambda:build_runtime_adapter_executor_handoff(**x),
   'closure':lambda:build_runtime_adapter_execution_integration_closure(**x)}
  if a.action in actions: return emit(actions[a.action]())
  if a.action in {'validate','inspect'}:
   obj=x.get('artifact',x); schema=obj.get('schema') if isinstance(obj,dict) else None
   vals={
'zero.engineering.runtime_adapter_execution_request.v1':inspect_runtime_adapter_execution_request,'zero.engineering.runtime_adapter_execution_capability.v1':inspect_runtime_adapter_execution_capability,'zero.engineering.runtime_adapter_binding_resolution.v1':inspect_runtime_adapter_binding_resolution,'zero.engineering.runtime_adapter_execution_environment_admission.v1':inspect_runtime_adapter_execution_environment_admission,'zero.engineering.runtime_adapter_execution_isolation_policy.v1':inspect_runtime_adapter_execution_isolation_policy,'zero.engineering.runtime_adapter_execution_resource_budget.v1':inspect_runtime_adapter_execution_resource_budget,'zero.engineering.runtime_adapter_execution_timeout_policy.v1':inspect_runtime_adapter_execution_timeout_policy,'zero.engineering.runtime_adapter_execution_preparation.v1':inspect_runtime_adapter_execution_preparation,'zero.engineering.runtime_adapter_execution_review.v1':inspect_runtime_adapter_execution_review,'zero.engineering.runtime_adapter_execution_authorization.v1':inspect_runtime_adapter_execution_authorization,'zero.engineering.runtime_adapter_execution_envelope.v1':inspect_runtime_adapter_execution_envelope,'zero.engineering.runtime_adapter_execution_readiness_verification.v1':inspect_runtime_adapter_execution_readiness_verification,'zero.engineering.runtime_adapter_executor_handoff.v1':inspect_runtime_adapter_executor_handoff,'zero.engineering.runtime_adapter_execution_integration_closure.v1':inspect_runtime_adapter_execution_integration_closure}
   out=vals.get(schema,lambda z:{'valid':False,'reason_codes':['unsupported_schema']})(obj); return emit(out,0 if out.get('valid') else 1)
  return err('unsupported_action','unsupported_action')
 except Exception: return err('execution_error','canonical_error')
if __name__=='__main__': raise SystemExit(main())
