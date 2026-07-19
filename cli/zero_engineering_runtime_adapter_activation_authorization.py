from __future__ import annotations
import argparse,json,sys,contextlib,io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_adapter_activation_authorization_common import canonical_json
from core.engineering.engineering_runtime_adapter_activation_authorization_request import *
from core.engineering.engineering_runtime_adapter_activation_authorization_policy import *
from core.engineering.engineering_runtime_adapter_activation_authorization_review import *
from core.engineering.engineering_runtime_adapter_activation_authorization import *
from core.engineering.engineering_runtime_adapter_activation_authorization_handoff import *
from core.engineering.engineering_runtime_adapter_activation_authorization_closure import *
VALIDATORS={'request':validate_runtime_adapter_activation_authorization_request,'policy':validate_runtime_adapter_activation_authorization_policy,'review':validate_runtime_adapter_activation_authorization_review,'authorize':validate_runtime_adapter_activation_authorization,'handoff':validate_runtime_adapter_activation_authorization_handoff,'closure':validate_runtime_adapter_activation_authorization_closure}
INSPECTORS={'request':inspect_runtime_adapter_activation_authorization_request,'policy':inspect_runtime_adapter_activation_authorization_policy,'review':inspect_runtime_adapter_activation_authorization_review,'authorize':inspect_runtime_adapter_activation_authorization,'handoff':inspect_runtime_adapter_activation_authorization_handoff,'closure':inspect_runtime_adapter_activation_authorization_closure}
def _read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {}
def build_parser():
 p=argparse.ArgumentParser(); p.add_argument('action',choices=('request','policy','review','authorize','handoff','closure','validate','inspect')); p.add_argument('input_json',nargs='?'); p.add_argument('--kind',choices=tuple(VALIDATORS)); return p
def run(argv=None):
 try:
  with contextlib.redirect_stderr(io.StringIO()): a=build_parser().parse_args(argv)
 except SystemExit as e: return {'error':'argument_error'},int(e.code or 2)
 try:
  data=_read(a.input_json)
  if a.action=='policy': return build_default_runtime_adapter_activation_authorization_policy(),0
  if a.action=='request':
   v=build_runtime_adapter_activation_authorization_request(data['handoff'],data['eligibility_closure'],data['requested_authorized_scope'],data['authorization_constraints'],data['resource_constraints'],data['timeout_constraints'],data['environment_constraints'],data.get('authorization_context',{})); return v,0 if validate_runtime_adapter_activation_authorization_request(v).valid else 1
  if a.action=='review':
   v=evaluate_runtime_adapter_activation_authorization_review(data['request'],data['policy']); return v,0 if v.get('review_status')=='approved' else 1
  if a.action=='authorize':
   v=build_runtime_adapter_activation_authorization(data['request'],data['policy'],data['review']); return v,0 if v.get('authorization_status')=='authorized' else 1
  if a.action=='handoff':
   v=build_runtime_adapter_activation_authorization_handoff(data['authorization']); return v,0 if validate_runtime_adapter_activation_authorization_handoff(v).valid and v.get('eligible_for_activation_token_review') else 1
  if a.action=='closure':
   v=build_runtime_adapter_activation_authorization_closure(data['request'],data['policy'],data['review'],data['authorization'],data['handoff']); return v,0 if v.get('package_status')=='closed' else 1
  kind=a.kind or data.get('kind'); artifact=data.get('artifact',data)
  if kind not in VALIDATORS: return {'error':'kind_required'},2
  if a.action=='validate':
   r=VALIDATORS[kind](artifact); return {'valid':r.valid,'reason_codes':list(r.errors)},0 if r.valid else 1
  return INSPECTORS[kind](artifact),0
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError): return {'error':'input_error'},2
def main(argv=None):
 v,c=run(argv); sys.stdout.write(canonical_json(v)+'\n'); return c
if __name__=='__main__': raise SystemExit(main())
