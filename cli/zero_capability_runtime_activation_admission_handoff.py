import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_runtime_activation_admission_handoff import create_capability_runtime_activation_admission_handoff
from cli.zero_capability_runtime_activation_eligibility import _finish
def run(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--admission",required=True);p.add_argument("--handed-off-at");p.add_argument("--recipient-id",default="runtime-activation-consumer");p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.admission).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=create_capability_runtime_activation_admission_handoff(v,handed_off_at=a.handed_off_at,recipient_id=a.recipient_id)
 for c in ("invalid_handed_off_at","invalid_recipient_id"):
  if c in r["errors"]:return {"error":c},2
 return _finish(r,a.output)
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
