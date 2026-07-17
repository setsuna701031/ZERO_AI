import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_authorization_token_issuance_handoff_preparation import prepare_capability_authorization_token_issuance_handoff
def run(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--issuance",required=True);p.add_argument("--prepared-at");p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.issuance).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=prepare_capability_authorization_token_issuance_handoff(v,prepared_at=a.prepared_at)
 if a.prepared_at is not None and "invalid_prepared_at" in r["errors"]:return {"error":"invalid_prepared_at"},2
 text=json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False)
 if a.output:
  try:Path(a.output).write_text(text+"\n",encoding="utf-8")
  except OSError:return {"error":"output_write_failed"},2
 return r,0
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
