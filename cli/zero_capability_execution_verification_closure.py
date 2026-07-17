import argparse,json
from cli.zero_capability_execution_session_admission import _read,_finish
from core.runtime.runtime_capability_execution_verification_closure import close_capability_execution_verification
def run(argv=None):
    p=argparse.ArgumentParser(description="Verify and close a capability execution control-plane chain.");p.add_argument("--session-admission",required=True);p.add_argument("--authority",required=True);p.add_argument("--request",required=True);p.add_argument("--outcome",required=True);p.add_argument("--output")
    try:a=p.parse_args(argv);return _finish(close_capability_execution_verification(_read(a.session_admission),_read(a.authority),_read(a.request),_read(a.outcome)),a.output)
    except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
