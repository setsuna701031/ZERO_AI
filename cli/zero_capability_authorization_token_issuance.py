import argparse,json
from pathlib import Path
from core.runtime.runtime_capability_authorization_token_issuance import issue_capability_authorization_token
def run(argv=None):
 p=argparse.ArgumentParser(prog="zero-capability-authorization-token-issuance");p.add_argument("--preparation",required=True);p.add_argument("--issued-at");p.add_argument("--expires-at");p.add_argument("--ttl-seconds",type=int);p.add_argument("--output")
 try:a=p.parse_args(argv)
 except SystemExit as x:return {"error":"invalid_arguments"},int(x.code)
 try:v=json.loads(Path(a.preparation).read_text(encoding="utf-8-sig"))
 except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
 r=issue_capability_authorization_token(v,issued_at=a.issued_at,issuance_expires_at=a.expires_at,issuance_ttl_seconds=a.ttl_seconds)
 for c in ("invalid_issued_at","invalid_issuance_expires_at","invalid_issuance_ttl","ttl_mismatch"):
  if c in r["errors"]:return {"error":c},2
 text=json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False)
 if a.output:
  try:Path(a.output).write_text(text+"\n",encoding="utf-8")
  except OSError:return {"error":"output_write_failed"},2
 return r,0
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
