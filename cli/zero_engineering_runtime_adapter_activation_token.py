from __future__ import annotations
import argparse,json,sys,contextlib,io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.engineering.engineering_runtime_adapter_activation_token_common import canonical_json
from core.engineering.engineering_runtime_adapter_activation_token_eligibility import *
from core.engineering.engineering_runtime_adapter_activation_token_preparation import *
from core.engineering.engineering_runtime_adapter_activation_token_review import *
from core.engineering.engineering_runtime_adapter_activation_token_authorization import *
from core.engineering.engineering_runtime_adapter_activation_token_issuance import *
from core.engineering.engineering_runtime_adapter_activation_token_verification import *
from core.engineering.engineering_runtime_adapter_activation_token_handoff import *
from core.engineering.engineering_runtime_adapter_activation_token_closure import *
VALIDATORS={'eligibility-request':validate_runtime_adapter_activation_token_eligibility_request,'eligibility':validate_runtime_adapter_activation_token_eligibility,'preparation-policy':validate_runtime_adapter_activation_token_preparation_policy,'prepare':validate_runtime_adapter_activation_token_preparation,'review-request':validate_runtime_adapter_activation_token_review_request,'review':validate_runtime_adapter_activation_token_review,'authorization-policy':validate_runtime_adapter_activation_token_authorization_policy,'authorize':validate_runtime_adapter_activation_token_authorization,'issue':validate_runtime_adapter_activation_token_issuance,'verify':validate_runtime_adapter_activation_token_verification,'handoff':validate_runtime_adapter_activation_token_handoff,'closure':validate_runtime_adapter_activation_token_governance_closure}
INSPECTORS={'eligibility-request':inspect_runtime_adapter_activation_token_eligibility_request,'eligibility':inspect_runtime_adapter_activation_token_eligibility,'preparation-policy':inspect_runtime_adapter_activation_token_preparation_policy,'prepare':inspect_runtime_adapter_activation_token_preparation,'review-request':inspect_runtime_adapter_activation_token_review_request,'review':inspect_runtime_adapter_activation_token_review,'authorization-policy':inspect_runtime_adapter_activation_token_authorization_policy,'authorize':inspect_runtime_adapter_activation_token_authorization,'issue':inspect_runtime_adapter_activation_token_issuance,'verify':inspect_runtime_adapter_activation_token_verification,'handoff':inspect_runtime_adapter_activation_token_handoff,'closure':inspect_runtime_adapter_activation_token_governance_closure}
def _read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {}
def build_parser():
 p=argparse.ArgumentParser(); p.add_argument('action',choices=('eligibility-request','eligibility','preparation-policy','prepare','review-request','review','authorization-policy','authorize','issue','verify','handoff','closure','validate','inspect')); p.add_argument('input_json',nargs='?'); p.add_argument('--kind',choices=tuple(VALIDATORS)); return p
def run(argv=None):
 try:
  with contextlib.redirect_stderr(io.StringIO()): a=build_parser().parse_args(argv)
 except SystemExit as e: return {'error':'argument_error'},int(e.code or 2)
 try:
  data=_read(a.input_json)
  if a.action=='eligibility-request': v=build_runtime_adapter_activation_token_eligibility_request(data['handoff'],data['closure'],data['requested_token_scope'],data['requested_max_uses'],data['token_constraints'],data['authority_reference'],data['authority_constraints'],data.get('request_context',{})); return v,0 if validate_runtime_adapter_activation_token_eligibility_request(v).valid else 1
  if a.action=='eligibility': v=evaluate_runtime_adapter_activation_token_eligibility(data['request'],data.get('handoff'),data.get('closure')); return v,0 if v.get('eligibility_status')=='eligible' else 1
  if a.action=='preparation-policy': return build_default_runtime_adapter_activation_token_preparation_policy(),0
  if a.action=='prepare': v=build_runtime_adapter_activation_token_preparation(data['request'],data['eligibility'],data['policy']); return v,0 if v.get('preparation_status')=='prepared' else 1
  if a.action=='review-request': v=build_runtime_adapter_activation_token_review_request(data['preparation'],data['eligibility']); return v,0 if validate_runtime_adapter_activation_token_review_request(v).valid else 1
  if a.action=='review': v=evaluate_runtime_adapter_activation_token_review(data['request'],data['preparation'],data['eligibility']); return v,0 if v.get('review_status')=='approved' else 1
  if a.action=='authorization-policy': return build_default_runtime_adapter_activation_token_authorization_policy(),0
  if a.action=='authorize': v=build_runtime_adapter_activation_token_authorization(data['review_request'],data['review'],data['preparation'],data['eligibility'],data['policy']); return v,0 if v.get('authorization_status')=='authorized' else 1
  if a.action=='issue': v=build_runtime_adapter_activation_token_issuance(data['authorization'],data.get('review_request')); return v,0 if v.get('issuance_status')=='issued' else 1
  if a.action=='verify': v=verify_runtime_adapter_activation_token(data['token'],data['authorization']); return v,0 if v.get('verification_status')=='verified' else 1
  if a.action=='handoff': v=build_runtime_adapter_activation_token_handoff(data['token'],data['verification']); return v,0 if v.get('eligible_for_adapter_activation_admission') else 1
  if a.action=='closure': v=build_runtime_adapter_activation_token_governance_closure(data['eligibility_request'],data['eligibility'],data['preparation_policy'],data['preparation'],data['review_request'],data['review'],data['authorization_policy'],data['authorization'],data['issuance'],data['verification'],data['handoff']); return v,0 if v.get('package_status')=='closed' else 1
  kind=a.kind or data.get('kind'); artifact=data.get('artifact',data)
  if kind not in VALIDATORS: return {'error':'kind_required'},2
  if a.action=='validate':
   r=VALIDATORS[kind](artifact); return {'valid':r.valid,'reason_codes':list(r.errors)},0 if r.valid else 1
  return INSPECTORS[kind](artifact),0
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError): return {'error':'input_error'},2
def main(argv=None):
 v,c=run(argv); sys.stdout.write(canonical_json(v)+'\n'); return c
if __name__=='__main__': raise SystemExit(main())
