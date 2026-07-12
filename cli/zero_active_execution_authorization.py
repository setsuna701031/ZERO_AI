from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Mapping, Sequence
from core.runtime.runtime_active_execution_authorization import RUNTIME_ACTIVE_EXECUTION_AUTHORIZATION_CONTRACT, authorize_active_execution

DEFAULT_RESULT_PATH = Path("workspace/operator_active_authorizations/active_execution_authorization_result.json")
def build_parser():
    p=argparse.ArgumentParser(prog="python -m cli.zero_active_execution_authorization"); s=p.add_subparsers(dest="command",required=True)
    a=s.add_parser("authorize"); a.add_argument("controlled_result_file"); a.add_argument("authorization_file"); a.add_argument("--now"); a.add_argument("--result-path",default=str(DEFAULT_RESULT_PATH))
    q=s.add_parser("status"); q.add_argument("controlled_result_file"); q.add_argument("--result-path",default=str(DEFAULT_RESULT_PATH)); return p
def _load(path):
    x=Path(path)
    if not x.is_file(): return {},"file_not_found"
    try: v=json.loads(x.read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeError,json.JSONDecodeError): return {},"invalid_json"
    return (dict(v),"") if isinstance(v,Mapping) else ({},"json_object_required")
def _write(path,value):
    x=Path(path); x.parent.mkdir(parents=True,exist_ok=True); x.write_text(json.dumps(dict(value),ensure_ascii=False,indent=2,sort_keys=True,default=str),encoding="utf-8")
def run_active_execution_authorization_cli(command,controlled_result_file,authorization_file=None,*,now=None,result_path=DEFAULT_RESULT_PATH):
    if command=="status":
        result,error=_load(controlled_result_file)
        if error or result.get("contract")!=RUNTIME_ACTIVE_EXECUTION_AUTHORIZATION_CONTRACT: result={"contract":RUNTIME_ACTIVE_EXECUTION_AUTHORIZATION_CONTRACT,"authorization_status":"input_error","active_execution_prepared":False,"execution_allowed":False,"reasons":[error or "invalid_authorization_result_contract"]}; code=2
        else: code=0
    elif command=="authorize":
        controlled,e1=_load(controlled_result_file); auth,e2=_load(authorization_file or "")
        if e1 or e2: result={"contract":RUNTIME_ACTIVE_EXECUTION_AUTHORIZATION_CONTRACT,"authorization_status":"input_error","active_execution_prepared":False,"execution_allowed":False,"reasons":[f"controlled_{e1}" if e1 else f"authorization_{e2}"]}; code=2
        else: result=authorize_active_execution(controlled,auth,now=now); code=0 if result["authorization_status"]=="authorized" else 1
    else: result={"contract":RUNTIME_ACTIVE_EXECUTION_AUTHORIZATION_CONTRACT,"authorization_status":"input_error","execution_allowed":False,"reasons":["invalid_command"]}; code=2
    _write(result_path,result); return result,code
def main(argv:Sequence[str]|None=None):
    a=build_parser().parse_args(argv); result,code=run_active_execution_authorization_cli(a.command,a.controlled_result_file,getattr(a,"authorization_file",None),now=getattr(a,"now",None),result_path=a.result_path); print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True,default=str)); return code
if __name__=="__main__": raise SystemExit(main())
__all__=["DEFAULT_RESULT_PATH","build_parser","main","run_active_execution_authorization_cli"]
