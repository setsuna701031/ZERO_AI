from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any
from core.engineering.developer_intent import SCHEMA,parse_developer_intent
from core.engineering.developer_intent_validation import validate_developer_intent
def _read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def _render(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n"
def build_parser():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True);q=s.add_parser("parse");q.add_argument("request",nargs="+")
 for c in ("validate","inspect"):s.add_parser(c).add_argument("json_file")
 return p
def run(argv=None):
 a=build_parser().parse_args(argv)
 try:
  if a.command=="parse":
   v=parse_developer_intent(" ".join(a.request));return v,0 if v["status"] in {"accepted","needs_clarification"} else 1
  v=_read(a.json_file)
  if not isinstance(v,dict) or v.get("schema")!=SCHEMA:return {"valid":False,"errors":["unsupported_schema"]},1
  x=validate_developer_intent(v)
  if a.command=="validate":return {"valid":x.valid,"errors":list(x.errors)},0 if x.valid else 1
  return {"valid":x.valid,"schema":v.get("schema"),"status":v.get("status"),"developer_intent_id":v.get("developer_intent_id"),"intent_types":v.get("intent_types")},0 if x.valid else 1
 except (OSError,ValueError,TypeError,json.JSONDecodeError) as e:return {"error":"input_error","error_type":type(e).__name__},2
def main(argv=None):
 try:v,c=run(argv)
 except SystemExit as e:return int(e.code or 0)
 sys.stdout.write(_render(v));return c
if __name__=="__main__":raise SystemExit(main())
__all__=["build_parser","main","run"]
