from __future__ import annotations
import argparse,json,sys,contextlib,io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_adapter_activation_eligibility_common import canonical_json
from core.engineering.engineering_runtime_adapter_activation_eligibility_request import *
from core.engineering.engineering_runtime_adapter_activation_eligibility_policy import *
from core.engineering.engineering_runtime_adapter_activation_constraint_profile import *
from core.engineering.engineering_runtime_adapter_activation_eligibility_evaluation import *
from core.engineering.engineering_runtime_adapter_activation_eligibility import *
from core.engineering.engineering_runtime_adapter_activation_eligibility_handoff import *
from core.engineering.engineering_runtime_adapter_activation_eligibility_closure import *
VALIDATORS={'request':validate_runtime_adapter_activation_eligibility_request,'policy':validate_runtime_adapter_activation_eligibility_policy,'profile':validate_runtime_adapter_activation_constraint_profile,'evaluate':validate_runtime_adapter_activation_eligibility_evaluation,'eligibility':validate_runtime_adapter_activation_eligibility,'handoff':validate_runtime_adapter_activation_eligibility_handoff,'closure':validate_runtime_adapter_activation_eligibility_closure}
INSPECTORS={'request':inspect_runtime_adapter_activation_eligibility_request,'policy':inspect_runtime_adapter_activation_eligibility_policy,'profile':inspect_runtime_adapter_activation_constraint_profile,'evaluate':inspect_runtime_adapter_activation_eligibility_evaluation,'eligibility':inspect_runtime_adapter_activation_eligibility,'handoff':inspect_runtime_adapter_activation_eligibility_handoff,'closure':inspect_runtime_adapter_activation_eligibility_closure}
def _read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {}
def build_parser():
 p=argparse.ArgumentParser(); p.add_argument('action',choices=('request','policy','profile','evaluate','eligibility','handoff','closure','validate','inspect')); p.add_argument('input_json',nargs='?'); p.add_argument('--kind',choices=tuple(VALIDATORS)); return p
def run(argv=None):
 try:
  with contextlib.redirect_stderr(io.StringIO()): a=build_parser().parse_args(argv)
 except SystemExit as e: return {'error':'argument_error'},int(e.code or 2)
 try:
  data=_read(a.input_json)
  if a.action=='policy': return build_default_runtime_adapter_activation_eligibility_policy(),0
  if a.action=='request':
   v=build_runtime_adapter_activation_eligibility_request(data['handoff'],data['review_closure'],data['requested_activation_scope'],data['activation_constraints'],data['resource_constraints'],data['timeout_constraints'],data['environment_constraints'],data.get('request_context',{})); return v,0 if validate_runtime_adapter_activation_eligibility_request(v).valid else 1
  if a.action=='profile':
   v=build_runtime_adapter_activation_constraint_profile(data['request']); return v,0 if validate_runtime_adapter_activation_constraint_profile(v).valid else 1
  if a.action=='evaluate':
   v=evaluate_runtime_adapter_activation_eligibility(data['request'],data['policy'],data['profile']); return v,0 if v.get('eligibility_status')=='eligible' else 1
  if a.action=='eligibility':
   v=build_runtime_adapter_activation_eligibility(data['request'],data['policy'],data['profile'],data['evaluation']); return v,0 if v.get('eligibility_status')=='eligible' else 1
  if a.action=='handoff':
   v=build_runtime_adapter_activation_eligibility_handoff(data['eligibility']); return v,0 if validate_runtime_adapter_activation_eligibility_handoff(v).valid else 1
  if a.action=='closure':
   v=build_runtime_adapter_activation_eligibility_closure(data['request'],data['policy'],data['profile'],data['evaluation'],data['eligibility'],data['handoff']); return v,0 if v.get('package_status')=='closed' else 1
  kind=a.kind or data.get('kind'); artifact=data.get('artifact',data)
  if kind not in VALIDATORS: return {'error':'kind_required'},2
  if a.action=='validate':
   r=VALIDATORS[kind](artifact); return {'valid':r.valid,'reason_codes':list(r.errors)},0 if r.valid else 1
  return INSPECTORS[kind](artifact),0
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError): return {'error':'input_error'},2
def main(argv=None):
 v,c=run(argv); sys.stdout.write(canonical_json(v)+'\n'); return c
if __name__=='__main__': raise SystemExit(main())
