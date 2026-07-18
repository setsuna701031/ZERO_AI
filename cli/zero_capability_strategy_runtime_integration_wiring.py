from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_strategy_runtime_integration_wiring import SCHEMA, wire_runtime_integration
from core.runtime.runtime_capability_strategy_runtime_integration_wiring_validation import validate_runtime_integration_wiring
def _read(path:str)->Any:return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def _render(value:Any)->str:return json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n"
def build_parser()->argparse.ArgumentParser:
 p=argparse.ArgumentParser(prog="python -m cli.zero_capability_strategy_runtime_integration_wiring");s=p.add_subparsers(dest="command",required=True)
 for c in ("wire","validate","inspect"):s.add_parser(c).add_argument("json_file")
 return p
def run(argv:list[str]|None=None)->tuple[Any,int]:
 a=build_parser().parse_args(argv)
 try:
  value=_read(a.json_file)
  if a.command=="wire":
   out=wire_runtime_integration(value);return out,0 if out["status"] in {"wired","default_compatible"} else 1
  if not isinstance(value,dict) or value.get("schema")!=SCHEMA:return {"valid":False,"errors":["unsupported_schema"]},1
  v=validate_runtime_integration_wiring(value)
  if a.command=="validate":return {"valid":v.valid,"errors":list(v.errors)},0 if v.valid else 1
  return {"valid":v.valid,"schema":value.get("schema"),"status":value.get("status"),"wiring_id":value.get("wiring_id"),"source_decision_id":value.get("source_decision_id"),"wiring_payload_available":value.get("wiring_payload") is not None},0 if v.valid else 1
 except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:return {"error":"input_error","error_type":type(exc).__name__},2
def main(argv:list[str]|None=None)->int:
 try:value,code=run(argv)
 except SystemExit as exc:return int(exc.code or 0)
 sys.stdout.write(_render(value));return code
if __name__=="__main__":raise SystemExit(main())
__all__=["build_parser","main","run"]
