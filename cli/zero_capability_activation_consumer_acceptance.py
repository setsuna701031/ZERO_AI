import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_activation_consumer_acceptance import accept_capability_activation_consumer_handoff
from cli.zero_capability_runtime_activation_eligibility import _finish
def run(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--handoff",required=True);p.add_argument("--accepted-at");p.add_argument("--consumer-id",required=True);p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.handoff).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=accept_capability_activation_consumer_handoff(v,accepted_at=a.accepted_at,consumer_id=a.consumer_id)
 for c in ("invalid_accepted_at","invalid_consumer_id"):
  if c in r["errors"]:return {"error":c},2
 return _finish(r,a.output)
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
