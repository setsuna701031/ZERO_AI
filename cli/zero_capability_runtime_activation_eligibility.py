import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_runtime_activation_eligibility import evaluate_capability_runtime_activation_eligibility
def run(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--handoff",required=True);p.add_argument("--evaluated-at");p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.handoff).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=evaluate_capability_runtime_activation_eligibility(v,evaluated_at=a.evaluated_at)
 if "invalid_evaluated_at" in r["errors"]:return {"error":"invalid_evaluated_at"},2
 return _finish(r,a.output)
def _finish(r,o):
 t=json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False)
 if o:
  try:Path(o).write_text(t+"\n",encoding="utf-8")
  except OSError:return {"error":"output_write_failed"},2
 return r,0
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
