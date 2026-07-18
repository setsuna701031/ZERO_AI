from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.change_proposal_preparation import SCHEMA,prepare_change_proposal
from core.engineering.change_proposal_preparation_validation import validate_change_proposal_preparation
def _read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def build_parser():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True)
 for c in ("prepare","validate","inspect"):s.add_parser(c).add_argument("json_file")
 return p
def run(argv=None):
 a=build_parser().parse_args(argv)
 try:
  v=_read(a.json_file)
  if a.command=="prepare":o=prepare_change_proposal(v);return o,0 if o["status"] in {"prepared","needs_clarification"} else 1
  if not isinstance(v,dict) or v.get("schema")!=SCHEMA:return {"valid":False,"errors":["unsupported_schema"]},1
  x=validate_change_proposal_preparation(v);return ({"valid":x.valid,"errors":list(x.errors)} if a.command=="validate" else {"valid":x.valid,"schema":v.get("schema"),"status":v.get("status"),"change_proposal_preparation_id":v.get("change_proposal_preparation_id")}),0 if x.valid else 1
 except (OSError,ValueError,TypeError,json.JSONDecodeError) as e:return {"error":"input_error","error_type":type(e).__name__},2
def main(argv=None):
 try:v,c=run(argv)
 except SystemExit as e:return int(e.code or 0)
 sys.stdout.write(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n");return c
if __name__=="__main__":raise SystemExit(main())
__all__=["build_parser","main","run"]
