import argparse,json,sys
from pathlib import Path
from core.runtime.runtime_capability_execution_session_admission import admit_capability_execution_session
def _read(path):return json.loads((sys.stdin.read() if path in (None,"-") else Path(path).read_text(encoding="utf-8-sig")))
def _finish(v,path):
    if path:Path(path).write_text(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False),encoding="utf-8")
    return v,0
def run(argv=None):
    p=argparse.ArgumentParser(description="Build a non-executing execution-session admission artifact.");p.add_argument("--activation-verification-closure","--input",dest="input");p.add_argument("--capability-profile-id",default="");p.add_argument("--capability-strategy-id",default="");p.add_argument("--output")
    try:a=p.parse_args(argv);v=_read(a.input);return _finish(admit_capability_execution_session(v,capability_profile_id=a.capability_profile_id,capability_strategy_id=a.capability_strategy_id),a.output)
    except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
