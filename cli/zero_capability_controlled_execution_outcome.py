import argparse,json
from cli.zero_capability_execution_session_admission import _read,_finish
from core.runtime.runtime_capability_controlled_execution_outcome import build_capability_controlled_execution_outcome
def run(argv=None):
    p=argparse.ArgumentParser(description="Record a caller-observed controlled outcome; this does not execute a request.");p.add_argument("--request","--input",dest="input");p.add_argument("--observed-status",required=True);p.add_argument("--evidence-json",default="[]");p.add_argument("--result-json",default="{}");p.add_argument("--reasons-json",default="[]");p.add_argument("--output")
    try:a=p.parse_args(argv);return _finish(build_capability_controlled_execution_outcome(_read(a.input),observed_status=a.observed_status,evidence_references=json.loads(a.evidence_json),result_summary=json.loads(a.result_json),failure_or_blocked_reasons=json.loads(a.reasons_json)),a.output)
    except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
