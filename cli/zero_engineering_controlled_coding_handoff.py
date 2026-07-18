from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from core.engineering.controlled_coding_handoff import SCHEMA,build_controlled_coding_handoff
from core.engineering.controlled_coding_handoff_validation import validate_controlled_coding_handoff
def _read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def build_parser():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True)
 for c in ("handoff","validate","inspect"):s.add_parser(c).add_argument("json_file")
 return p
def run(argv=None):
 a=build_parser().parse_args(argv)
 try:
  v=_read(a.json_file)
  if a.command=="handoff":o=build_controlled_coding_handoff(v);return o,0 if o["status"] in {"handed_off","needs_clarification"} else 1
  if not isinstance(v,dict) or v.get("schema")!=SCHEMA:return {"valid":False,"errors":["unsupported_schema"]},1
  x=validate_controlled_coding_handoff(v);return ({"valid":x.valid,"errors":list(x.errors)} if a.command=="validate" else {"valid":x.valid,"schema":v.get("schema"),"status":v.get("status"),"controlled_coding_handoff_id":v.get("controlled_coding_handoff_id"),"next_stage":(v.get("handoff_payload") or {}).get("next_stage")}),0 if x.valid else 1
 except (OSError,ValueError,TypeError,json.JSONDecodeError) as e:return {"error":"input_error","error_type":type(e).__name__},2
def main(argv=None):
 try:v,c=run(argv)
 except SystemExit as e:return int(e.code or 0)
 sys.stdout.write(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n");return c
if __name__=="__main__":raise SystemExit(main())
__all__=["build_parser","main","run"]
