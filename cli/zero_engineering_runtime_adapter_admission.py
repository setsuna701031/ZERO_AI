from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.engineering_runtime_adapter_admission_request import build_runtime_adapter_admission_request,validate_runtime_adapter_admission_request,inspect_runtime_adapter_admission_request
from core.engineering.engineering_runtime_adapter_admission_policy import build_default_runtime_adapter_admission_policy,validate_runtime_adapter_admission_policy,inspect_runtime_adapter_admission_policy
from core.engineering.engineering_runtime_adapter_admission_eligibility import evaluate_runtime_adapter_admission_eligibility,validate_runtime_adapter_admission_eligibility,inspect_runtime_adapter_admission_eligibility
from core.engineering.engineering_runtime_adapter_admission import build_runtime_adapter_admission,validate_runtime_adapter_admission,inspect_runtime_adapter_admission
from core.engineering.engineering_runtime_adapter_admission_closure import build_runtime_adapter_admission_closure,validate_runtime_adapter_admission_closure,inspect_runtime_adapter_admission_closure
from core.engineering.engineering_runtime_adapter_admission_common import canonical_json
VALIDATORS={'request':validate_runtime_adapter_admission_request,'policy':validate_runtime_adapter_admission_policy,'eligibility':validate_runtime_adapter_admission_eligibility,'admission':validate_runtime_adapter_admission,'closure':validate_runtime_adapter_admission_closure}
INSPECTORS={'request':inspect_runtime_adapter_admission_request,'policy':inspect_runtime_adapter_admission_policy,'eligibility':inspect_runtime_adapter_admission_eligibility,'admission':inspect_runtime_adapter_admission,'closure':inspect_runtime_adapter_admission_closure}
def _read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def build_parser():
 p=argparse.ArgumentParser(); p.add_argument('action',choices=('request','policy','eligibility','admit','closure','validate','inspect')); p.add_argument('input_json',nargs='?'); p.add_argument('--kind',choices=tuple(VALIDATORS)); return p
def run(argv=None):
 try: a=build_parser().parse_args(argv)
 except SystemExit as e: return {'error':'argument_error'},int(e.code or 2)
 try:
  data=_read(a.input_json) if a.input_json else {}
  if a.action=='policy': return build_default_runtime_adapter_admission_policy(),0
  if a.action=='request':
   v=build_runtime_adapter_admission_request(data['handoff'],data['session'],data['admission'],data['requested_adapter_id'],data['requested_adapter_version'],data['requested_scope'],data.get('authority_reference'),data['authority_constraints']); return v,0 if validate_runtime_adapter_admission_request(v).valid else 1
  if a.action=='eligibility':
   v=evaluate_runtime_adapter_admission_eligibility(data['request'],data['handoff'],data['session'],data['admission']); return v,0 if v.get('eligibility_status')=='eligible' else 1
  if a.action=='admit':
   v=build_runtime_adapter_admission(data['request'],data['eligibility'],data['policy']); return v,0 if v.get('admission_status')=='admitted' else 1
  if a.action=='closure':
   v=build_runtime_adapter_admission_closure(data['request'],data['policy'],data['eligibility'],data['admission']); return v,0 if v.get('package_status')=='closed' else 1
  kind=a.kind or data.get('kind'); artifact=data.get('artifact',data)
  if kind not in VALIDATORS: return {'error':'kind_required'},2
  if a.action=='validate':
   r=VALIDATORS[kind](artifact); return {'valid':r.valid,'reason_codes':list(r.errors)},0 if r.valid else 1
  return INSPECTORS[kind](artifact),0
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError): return {'error':'input_error'},2
def main(argv=None):
 v,c=run(argv); sys.stdout.write(canonical_json(v)+'\n'); return c
if __name__=='__main__': raise SystemExit(main())
