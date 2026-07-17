import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_controlled_activation_outcome import record_capability_controlled_activation_outcome
from cli.zero_capability_runtime_activation_eligibility import _finish
def run(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--preparation",required=True);p.add_argument("--outcome",required=True);p.add_argument("--observed-at");p.add_argument("--consumer-id",required=True);p.add_argument("--evidence-code",required=True);p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.preparation).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=record_capability_controlled_activation_outcome(v,outcome=a.outcome,observed_at=a.observed_at,consumer_id=a.consumer_id,evidence_code=a.evidence_code)
 for c in ("invalid_observed_at","invalid_outcome","invalid_consumer_id","invalid_evidence_code"):
  if c in r["errors"]:return {"error":c},2
 return _finish(r,a.output)
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
