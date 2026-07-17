import argparse,json
from cli.zero_capability_execution_session_admission import _read,_finish
from core.runtime.runtime_capability_executor_bridge_verification_closure import close_capability_executor_bridge_verification
HELP="dry-run; no external side effects; does not execute the requested operation"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP)
 for n in ("authority","request","adapter-admission","dispatch-plan","dispatch-result","reconciliation"):p.add_argument("--"+n,required=True)
 p.add_argument("--controlled-execution-outcome");p.add_argument("--execution-verification-closure");p.add_argument("--output")
 try:a=p.parse_args(argv);return _finish(close_capability_executor_bridge_verification(_read(a.authority),_read(a.request),_read(a.adapter_admission),_read(a.dispatch_plan),_read(a.dispatch_result),_read(a.reconciliation),controlled_execution_outcome=_read(a.controlled_execution_outcome) if a.controlled_execution_outcome else None,execution_verification_closure=_read(a.execution_verification_closure) if a.execution_verification_closure else None),a.output)
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
