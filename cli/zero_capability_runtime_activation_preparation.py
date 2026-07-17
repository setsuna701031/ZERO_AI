import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_runtime_activation_preparation import prepare_capability_runtime_activation
from cli.zero_capability_runtime_activation_eligibility import _finish
def run(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--eligibility",required=True);p.add_argument("--prepared-at");p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.eligibility).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=prepare_capability_runtime_activation(v,prepared_at=a.prepared_at)
 if "invalid_prepared_at" in r["errors"]:return {"error":"invalid_prepared_at"},2
 return _finish(r,a.output)
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
