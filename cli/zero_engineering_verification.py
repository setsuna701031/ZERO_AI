from __future__ import annotations
import argparse,json,sys
from pathlib import Path

def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8')) if path else json.load(sys.stdin)
def _dump(obj):
    sys.stdout.write(json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n')
def main(argv=None):
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    for c in ('validate-plan','build-admission','validate-admission','validate-run','build-continuation','validate-continuation','inspect-run','resume-verification','build-report','build-plan','run-verification'):
        sp=sub.add_parser(c); sp.add_argument('--input'); sp.add_argument('--repo-root',default='.')
    ns=ap.parse_args(argv)
    try:
        data=_load(ns.input)
        if ns.cmd=='validate-plan':
            from core.engineering.engineering_verification_plan_validation import validate_verification_plan as f; r=f(data); _dump({'valid':r.valid,'errors':list(r.errors)})
        elif ns.cmd=='build-admission':
            from core.engineering.engineering_verification_admission import build_verification_admission as f; _dump(f(data))
        elif ns.cmd=='validate-admission':
            from core.engineering.engineering_verification_admission_validation import validate_verification_admission as f; r=f(data.get('admission',data),data.get('plan')); _dump({'valid':r.valid,'errors':list(r.errors)})
        elif ns.cmd=='validate-run':
            from core.engineering.engineering_verification_run_validation import validate_verification_run as f; r=f(data); _dump({'valid':r.valid,'errors':list(r.errors)})
        elif ns.cmd=='build-continuation':
            from core.engineering.engineering_runtime_continuation import build_runtime_continuation as f; _dump(f(session=data['session'],execution_result=data['execution_result'],verification_result=data['verification_result'],verification_run=data.get('verification_run')))
        elif ns.cmd=='validate-continuation':
            from core.engineering.engineering_runtime_continuation_validation import validate_runtime_continuation as f; r=f(data); _dump({'valid':r.valid,'errors':list(r.errors)})
        elif ns.cmd=='inspect-run': _dump({'verification_run':data,'step_count':len(data.get('step_results',[]))})
        elif ns.cmd=='resume-verification': _dump({'resumed':True,'rerun':False,'state':data})
        elif ns.cmd=='build-report':
            from core.engineering.engineering_execution_session_report import build_execution_session_report as f; _dump(f(data))
        elif ns.cmd=='build-plan':
            from core.engineering.engineering_verification_plan import build_verification_plan as f; _dump(f(session=data['session'],proposal=data['proposal'],repair_plan=data['repair_plan'],execution_result=data['execution_result'],**data.get('options',{})))
        elif ns.cmd=='run-verification':
            from core.engineering.engineering_governed_verification_runner import run_governed_verification as f; _dump(f(repository_root=ns.repo_root,session=data['session'],proposal=data['proposal'],repair_plan=data['repair_plan'],execution_result=data['execution_result'],verification_plan=data['verification_plan'],verification_admission=data['verification_admission'],replay_state=data.get('replay_state')))
        return 0
    except Exception as exc:
        print(str(exc),file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
