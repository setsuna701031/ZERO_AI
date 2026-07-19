from __future__ import annotations
import argparse,json,sys,contextlib,io
from pathlib import Path
from core.engineering.engineering_runtime_adapter_preparation_review_common import canonical_json
from core.engineering.engineering_runtime_adapter_preparation_review_request import build_runtime_adapter_preparation_review_request,validate_runtime_adapter_preparation_review_request,inspect_runtime_adapter_preparation_review_request
from core.engineering.engineering_runtime_adapter_preparation_review_policy import build_default_runtime_adapter_preparation_review_policy,validate_runtime_adapter_preparation_review_policy,inspect_runtime_adapter_preparation_review_policy
from core.engineering.engineering_runtime_adapter_preparation_review_eligibility import evaluate_runtime_adapter_preparation_review_eligibility,validate_runtime_adapter_preparation_review_eligibility,inspect_runtime_adapter_preparation_review_eligibility
from core.engineering.engineering_runtime_adapter_preparation_review_findings import build_runtime_adapter_preparation_review_findings,validate_runtime_adapter_preparation_review_findings,inspect_runtime_adapter_preparation_review_findings
from core.engineering.engineering_runtime_adapter_preparation_review import build_runtime_adapter_preparation_review,validate_runtime_adapter_preparation_review,inspect_runtime_adapter_preparation_review
from core.engineering.engineering_runtime_adapter_preparation_review_handoff import build_runtime_adapter_preparation_review_handoff,validate_runtime_adapter_preparation_review_handoff,inspect_runtime_adapter_preparation_review_handoff
from core.engineering.engineering_runtime_adapter_preparation_review_closure import build_runtime_adapter_preparation_review_closure,validate_runtime_adapter_preparation_review_closure,inspect_runtime_adapter_preparation_review_closure
VALIDATORS={'request':validate_runtime_adapter_preparation_review_request,'policy':validate_runtime_adapter_preparation_review_policy,'eligibility':validate_runtime_adapter_preparation_review_eligibility,'findings':validate_runtime_adapter_preparation_review_findings,'review':validate_runtime_adapter_preparation_review,'handoff':validate_runtime_adapter_preparation_review_handoff,'closure':validate_runtime_adapter_preparation_review_closure}
INSPECTORS={'request':inspect_runtime_adapter_preparation_review_request,'policy':inspect_runtime_adapter_preparation_review_policy,'eligibility':inspect_runtime_adapter_preparation_review_eligibility,'findings':inspect_runtime_adapter_preparation_review_findings,'review':inspect_runtime_adapter_preparation_review,'handoff':inspect_runtime_adapter_preparation_review_handoff,'closure':inspect_runtime_adapter_preparation_review_closure}
def _read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else {}
def build_parser():
 p=argparse.ArgumentParser(); p.add_argument('action',choices=('request','policy','eligibility','findings','review','handoff','closure','validate','inspect')); p.add_argument('input_json',nargs='?'); p.add_argument('--kind',choices=tuple(VALIDATORS)); return p
def run(argv=None):
 try:
  with contextlib.redirect_stderr(io.StringIO()): a=build_parser().parse_args(argv)
 except SystemExit as e: return {'error':'argument_error'},int(e.code or 2)
 try:
  data=_read(a.input_json)
  if a.action=='policy': return build_default_runtime_adapter_preparation_review_policy(),0
  if a.action=='request':
   v=build_runtime_adapter_preparation_review_request(data['preparation'],data['closure'],data['descriptor'],data.get('review_context',{})); return v,0 if validate_runtime_adapter_preparation_review_request(v).valid else 1
  if a.action=='eligibility':
   v=evaluate_runtime_adapter_preparation_review_eligibility(data['request'],data['policy']); return v,0 if v.get('eligibility_status')=='eligible' else 1
  if a.action=='findings':
   v=build_runtime_adapter_preparation_review_findings(data['request'],data['policy'],data['eligibility'],data.get('advisory_findings',[])); return v,0 if not v.get('blocking_findings') else 1
  if a.action=='review':
   v=build_runtime_adapter_preparation_review(data['request'],data['policy'],data['eligibility'],data['findings']); return v,0 if v.get('review_status')=='approved' else 1
  if a.action=='handoff':
   v=build_runtime_adapter_preparation_review_handoff(data['review'],data['request']); return v,0 if validate_runtime_adapter_preparation_review_handoff(v).valid else 1
  if a.action=='closure':
   v=build_runtime_adapter_preparation_review_closure(data['request'],data['policy'],data['eligibility'],data['findings'],data['review'],data['handoff']); return v,0 if v.get('package_status')=='closed' else 1
  kind=a.kind or data.get('kind'); artifact=data.get('artifact',data)
  if kind not in VALIDATORS: return {'error':'kind_required'},2
  if a.action=='validate':
   r=VALIDATORS[kind](artifact); return {'valid':r.valid,'reason_codes':list(r.errors)},0 if r.valid else 1
  return INSPECTORS[kind](artifact),0
 except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError): return {'error':'input_error'},2
def main(argv=None):
 v,c=run(argv); sys.stdout.write(canonical_json(v)+'\n'); return c
if __name__=='__main__': raise SystemExit(main())
