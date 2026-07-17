import argparse,json
from cli.zero_capability_execution_session_admission import _read,_finish
from core.runtime.runtime_capability_execution_authority import issue_capability_execution_authority
def run(argv=None):
    p=argparse.ArgumentParser(description="Issue bounded, non-executing capability authority.");p.add_argument("--session-admission","--input",dest="input");p.add_argument("--scope-json",default="{}");p.add_argument("--constraints-json",default="{}");p.add_argument("--issued-at");p.add_argument("--expires-at");p.add_argument("--output")
    try:a=p.parse_args(argv);return _finish(issue_capability_execution_authority(_read(a.input),issued_scope=json.loads(a.scope_json),authority_constraints=json.loads(a.constraints_json),issued_at=a.issued_at,expires_at=a.expires_at),a.output)
    except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
