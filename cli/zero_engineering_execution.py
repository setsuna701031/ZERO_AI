from __future__ import annotations
import argparse, json, sys
from core.engineering.engineering_execution_controller import *
from core.engineering.engineering_execution_session_persistence import load_execution_session, persist_execution_session, resume_persisted_execution_session
from core.engineering.engineering_execution_session import validate_engineering_execution_session
from core.engineering.engineering_execution_session_report import build_execution_session_report, validate_execution_session_report

def _read(path):
    with open(path, encoding='utf-8') as f: return json.load(f)
def _emit(x): print(json.dumps(x, sort_keys=True, separators=(',', ':')))
def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('command'); p.add_argument('--input'); p.add_argument('--session'); p.add_argument('--output'); p.add_argument('--workspace-root')
    a=p.parse_args(argv)
    try:
        x=_read(a.input) if a.input else {}
        if a.command=='create-session': out=create_execution_session(task=x['task'], proposal=x['proposal'], proposal_linkage=x['proposal_linkage'])
        elif a.command=='inspect-session': out=load_execution_session(a.session) if a.session else inspect_execution_session(x['session'])
        elif a.command=='resume-session': out=resume_persisted_execution_session(a.session) if a.session else resume_execution_session(x['session'])
        elif a.command=='attach-approval': out=attach_approval(x['session'], x['approval'])
        elif a.command=='attach-authorization': out=attach_authorization(x['session'], x['authorization'])
        elif a.command=='attach-preparation': out=attach_preparation(x['session'], x['preparation'])
        elif a.command=='attach-token': out=attach_token(x['session'], x['token'])
        elif a.command=='execute': out=execute_authorized_mutation(x['session'], handoff=x['handoff'], workspace_root=a.workspace_root or x.get('workspace_root','.'), execute_confirmed=True)[0]
        elif a.command=='attach-verification': out=attach_verification_result(x['session'], x['verification_result'])
        elif a.command=='complete': out=complete_execution_session(x['session'], completion=x['completion'])
        elif a.command=='close': out=close_execution_session(x['session'], x['closure'])
        elif a.command=='build-report': out=build_execution_session_report(x['session'])
        elif a.command=='validate-session': out=validate_engineering_execution_session(x['session'])
        elif a.command=='validate-report': out=validate_execution_session_report(x['report'])
        else: raise ValueError('invalid_command')
        if a.output: persist_execution_session(out, a.output)
        _emit(out); return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr); _emit({'ok':False,'error':str(exc)}); return 2
if __name__=='__main__': raise SystemExit(main())
