import argparse,json
from cli.zero_capability_execution_session_admission import _read,_finish
from core.runtime.runtime_capability_dry_run_dispatch_result import build_capability_dry_run_dispatch_result
HELP="dry-run; no external side effects; does not execute the requested operation"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);p.add_argument("--dispatch-plan",required=True);p.add_argument("--observed-status",required=True);p.add_argument("--output")
 try:a=p.parse_args(argv);return _finish(build_capability_dry_run_dispatch_result(_read(a.dispatch_plan),observed_status=a.observed_status,observation_summary={"dry_run_simulation_generated":True}),a.output)
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
