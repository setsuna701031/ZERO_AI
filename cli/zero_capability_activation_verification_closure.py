import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_activation_verification_closure import close_capability_activation_verification
from cli.zero_capability_runtime_activation_eligibility import _finish
def run(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--outcome-record",required=True);p.add_argument("--verified-at");p.add_argument("--verifier-id",required=True);p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.outcome_record).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=close_capability_activation_verification(v,verified_at=a.verified_at,verifier_id=a.verifier_id)
 for c in ("invalid_verified_at","invalid_verifier_id"):
  if c in r["errors"]:return {"error":c},2
 return _finish(r,a.output)
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
