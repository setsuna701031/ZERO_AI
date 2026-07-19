from __future__ import annotations
import argparse,json,sys,contextlib,io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_adapter_activation_common import canonical_json
from core.engineering.engineering_runtime_adapter_activation_admission import *
from core.engineering.engineering_runtime_adapter_activation_preparation import *
from core.engineering.engineering_runtime_adapter_controlled_activation import *
from core.engineering.engineering_runtime_adapter_activation_token_consumption import *
from core.engineering.engineering_runtime_adapter_activation_result import *
from core.engineering.engineering_runtime_adapter_activation_verification import *
from core.engineering.engineering_runtime_adapter_activation_handoff import *
from core.engineering.engineering_runtime_adapter_activation_closure import *
VALIDATORS={'admission-request':validate_runtime_adapter_activation_admission_request,'admission-policy':validate_runtime_adapter_activation_admission_policy,'admit':validate_runtime_adapter_activation_admission,'preparation-policy':validate_runtime_adapter_activation_preparation_policy,'prepare':validate_runtime_adapter_activation_preparation,'activate':validate_runtime_adapter_controlled_activation,'consume-token':validate_runtime_adapter_activation_token_consumption,'result':validate_runtime_adapter_activation_result,'verify':validate_runtime_adapter_activation_verification,'handoff':validate_runtime_adapter_activation_handoff,'closure':validate_runtime_adapter_activation_boundary_closure}
INSPECTORS={'admission-request':inspect_runtime_adapter_activation_admission_request,'admission-policy':inspect_runtime_adapter_activation_admission_policy,'admit':inspect_runtime_adapter_activation_admission,'preparation-policy':inspect_runtime_adapter_activation_preparation_policy,'prepare':inspect_runtime_adapter_activation_preparation,'activate':inspect_runtime_adapter_controlled_activation,'consume-token':inspect_runtime_adapter_activation_token_consumption,'result':inspect_runtime_adapter_activation_result,'verify':inspect_runtime_adapter_activation_verification,'handoff':inspect_runtime_adapter_activation_handoff,'closure':inspect_runtime_adapter_activation_boundary_closure}
def _read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else json.load(sys.stdin)
def run(argv=None):
 try:
  with contextlib.redirect_stderr(io.StringIO()): a=argparse.ArgumentParser(); a.add_argument('action'); a.add_argument('input_json',nargs='?'); a.add_argument('--kind'); ns=a.parse_args(argv)
  d=_read(ns.input_json)
  act=ns.action
  if act=='admission-request': v=build_runtime_adapter_activation_admission_request(d['token_handoff'],d.get('activation_scope'),d.get('admission_context')); return v,0
  if act=='admission-policy': return build_default_runtime_adapter_activation_admission_policy(),0
  if act=='admit': v=build_runtime_adapter_activation_admission(d['request'],d.get('policy'),d.get('token_handoff')); return v,0 if v.get('admission_status')=='admitted' else 1
  if act=='preparation-policy': return build_default_runtime_adapter_activation_preparation_policy(),0
  if act=='prepare': v=build_runtime_adapter_activation_preparation(d['admission'],d['policy'],d.get('activation_configuration'),d.get('resource_constraints'),d.get('timeout_constraints'),d.get('environment_constraints')); return v,0 if v.get('preparation_status')=='prepared' else 1
  if act=='activate': v=build_runtime_adapter_controlled_activation(d['preparation'],d['admission']); return v,0 if v.get('activation_status')=='activated' else 1
  if act=='consume-token': v=build_runtime_adapter_activation_token_consumption(d['controlled_activation']); return v,0 if v.get('consumption_status')=='consumed' else 1
  if act=='result': v=build_runtime_adapter_activation_result(d['controlled_activation'],d['token_consumption']); return v,0 if v.get('result_status')=='activated' else 1
  if act=='verify': v=verify_runtime_adapter_activation_boundary(d['admission'],d['preparation'],d['controlled_activation'],d['token_consumption'],d['activation_result']); return v,0 if v.get('verification_status')=='verified' else 1
  if act=='handoff': v=build_runtime_adapter_activation_handoff(d['activation_result'],d['activation_verification'],d.get('token_consumption'),d.get('controlled_activation')); return v,0 if v.get('eligible_for_invocation_governance') else 1
  if act=='closure': v=build_runtime_adapter_activation_boundary_closure(d['admission_request'],d['admission_policy'],d['admission'],d['preparation_policy'],d['preparation'],d['controlled_activation'],d['token_consumption'],d['activation_result'],d['activation_verification'],d['activation_handoff']); return v,0 if v.get('package_status')=='closed' else 1
  if act in {'validate','inspect'}:
   kind=ns.kind or d.get('kind'); art=d.get('artifact',d)
   if kind not in VALIDATORS: return {'error':'kind_required'},2
   if act=='validate': r=VALIDATORS[kind](art); return {'valid':r.valid,'reason_codes':list(r.errors)},0 if r.valid else 1
   return INSPECTORS[kind](art),0
  return {'error':'unsupported_action'},2
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError): return {'error':'input_error'},2
def main(argv=None):
 v,c=run(argv); sys.stdout.write(canonical_json(v)+'\n'); return c
if __name__=='__main__': raise SystemExit(main())
