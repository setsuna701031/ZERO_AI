from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_strategy_runtime_integration_verification import SCHEMA,verify_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_verification_validation import validate_runtime_integration_verification
def _read(path:str)->Any:return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def _render(value:Any)->str:return json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n"
def build_parser()->argparse.ArgumentParser:
 p=argparse.ArgumentParser(prog="python -m cli.zero_capability_strategy_runtime_integration_verification");s=p.add_subparsers(dest="command",required=True)
 q=s.add_parser("verify");q.add_argument("configuration_file");q.add_argument("decision_file");q.add_argument("wiring_file")
 for c in ("validate","inspect"):s.add_parser(c).add_argument("json_file")
 return p
def run(argv:list[str]|None=None)->tuple[Any,int]:
 a=build_parser().parse_args(argv)
 try:
  if a.command=="verify":
   out=verify_runtime_integration(_read(a.configuration_file),_read(a.decision_file),_read(a.wiring_file));return out,0 if out["status"]=="verified" else 1
  value=_read(a.json_file)
  if not isinstance(value,dict) or value.get("schema")!=SCHEMA:return {"valid":False,"errors":["unsupported_schema"]},1
  v=validate_runtime_integration_verification(value)
  if a.command=="validate":return {"valid":v.valid,"errors":list(v.errors)},0 if v.valid else 1
  return {"valid":v.valid,"schema":value.get("schema"),"status":value.get("status"),"verification_id":value.get("verification_id"),"source_integration_wiring_id":value.get("source_integration_wiring_id"),"evidence":value.get("evidence")},0 if v.valid else 1
 except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:return {"error":"input_error","error_type":type(exc).__name__},2
def main(argv:list[str]|None=None)->int:
 try:value,code=run(argv)
 except SystemExit as exc:return int(exc.code or 0)
 sys.stdout.write(_render(value));return code
if __name__=="__main__":raise SystemExit(main())
__all__=["build_parser","main","run"]
