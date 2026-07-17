import argparse,json
from cli.zero_capability_execution_session_admission import _read,_finish
from core.runtime.runtime_capability_runtime_outcome_reconciliation import build_capability_runtime_outcome_reconciliation
HELP="dry-run; no external side effects; does not execute the requested operation"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP)
 for n in ("authority","request","adapter-admission","dispatch-plan","dispatch-result"):p.add_argument("--"+n,required=True)
 p.add_argument("--output")
 try:a=p.parse_args(argv);return _finish(build_capability_runtime_outcome_reconciliation(_read(a.authority),_read(a.request),_read(a.adapter_admission),_read(a.dispatch_plan),_read(a.dispatch_result)),a.output)
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
