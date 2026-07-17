import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_runtime_activation_admission import admit_capability_runtime_activation
from cli.zero_capability_runtime_activation_eligibility import _finish
def run(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--preparation",required=True);p.add_argument("--admitted-at");p.add_argument("--expires-at");p.add_argument("--ttl-seconds",type=int);p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.preparation).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=admit_capability_runtime_activation(v,admitted_at=a.admitted_at,admission_expires_at=a.expires_at,admission_ttl_seconds=a.ttl_seconds)
 for c in ("invalid_admitted_at","invalid_admission_ttl_seconds","invalid_admission_expiry","ttl_mismatch"):
  if c in r["errors"]:return {"error":c},2
 return _finish(r,a.output)
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
