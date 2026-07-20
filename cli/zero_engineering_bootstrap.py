from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.engineering_bootstrap_request import build_engineering_bootstrap_request
from core.engineering.engineering_bootstrap_request_validation import validate_engineering_bootstrap_request
from core.engineering.engineering_bootstrap_pipeline import bootstrap_engineering_task, validate_engineering_bootstrap_result

def _read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def _emit(obj): print(json.dumps(obj,sort_keys=True,separators=(',',':')))
def main(argv=None):
    p=argparse.ArgumentParser(prog='python -m cli.zero_engineering_bootstrap')
    s=p.add_subparsers(dest='command',required=True)
    b=s.add_parser('build-bootstrap-request'); b.add_argument('--json',required=True)
    v=s.add_parser('validate-bootstrap-request'); v.add_argument('--request',required=True)
    r=s.add_parser('run-bootstrap'); r.add_argument('--request',required=True); r.add_argument('--analysis-input',required=True); r.add_argument('--state-root',required=True)
    o=s.add_parser('validate-bootstrap-result'); o.add_argument('--result',required=True)
    a=p.parse_args(argv)
    try:
        if a.command=='build-bootstrap-request':
            payload=json.loads(a.json); out=build_engineering_bootstrap_request(**payload); _emit(out); return 0
        if a.command=='validate-bootstrap-request':
            vr=validate_engineering_bootstrap_request(_read(a.request)); _emit({'valid':vr.valid,'errors':list(vr.errors)}); return 0 if vr.valid else 2
        if a.command=='run-bootstrap':
            out=bootstrap_engineering_task(repo_root=a.state_root, bootstrap_request=_read(a.request), repository_analysis=_read(a.analysis_input)); _emit(out); return 0 if out.get('bootstrap_status')=='proposal_ready' else 1
        vr=validate_engineering_bootstrap_result(_read(a.result)); _emit({'valid':vr.valid,'errors':list(vr.errors)}); return 0 if vr.valid else 2
    except Exception as exc:
        print(str(exc),file=sys.stderr); _emit({'valid':False,'errors':[type(exc).__name__]}); return 2
if __name__=='__main__': raise SystemExit(main())
