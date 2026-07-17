import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_decision_transaction_preparation import prepare_capability_decision_transaction as build
HELP="prepares a zero-side-effect transactional handoff; does not execute, mutate, validate by subprocess, commit, or rollback; does not create a transaction workspace or snapshot"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);p.add_argument("--bundle",required=True)
 try:
  a=p.parse_args(argv);b=_read(a.bundle);return build(**b),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
