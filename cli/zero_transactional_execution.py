from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Mapping
from core.runtime.runtime_transactional_active_execution import CONTRACT,execute_transactional_active_plan
def _load(p):
 x=Path(p)
 if not x.is_file(): return {},"file_not_found"
 try:v=json.loads(x.read_text(encoding="utf-8-sig"))
 except Exception:return {},"invalid_json"
 return (dict(v),"") if isinstance(v,Mapping) else ({},"object_required")
def _write(p,v):
 x=Path(p);x.parent.mkdir(parents=True,exist_ok=True);x.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True,default=str),encoding="utf-8")
def build_parser():
 p=argparse.ArgumentParser(prog="python -m cli.zero_transactional_execution");s=p.add_subparsers(dest="command",required=True);r=s.add_parser("run")
 for n in ("authorization_file","invocation_file","bundle_file"):r.add_argument(n)
 r.add_argument("--target-root",required=True);r.add_argument("--workspace-root",required=True);r.add_argument("--now");r.add_argument("--result-path",required=True)
 q=s.add_parser("status");q.add_argument("authorization_file");q.add_argument("--result-path",required=True);return p
def run_transactional_execution_cli(command,authorization_file,invocation_file=None,bundle_file=None,*,target_root=None,workspace_root=None,now=None,result_path):
 if command=="status":
  result,e=_load(authorization_file);code=0
  if e or result.get("contract")!=CONTRACT:result={"contract":CONTRACT,"transaction_status":"input_error","reasons":[e or "invalid_contract"]};code=2
 else:
  vals=[_load(x or "") for x in (authorization_file,invocation_file,bundle_file)];bad=next((i for i,x in enumerate(vals) if x[1]),None)
  if bad is not None or not target_root or not workspace_root:result={"contract":CONTRACT,"transaction_status":"input_error","reasons":["invalid_input"]};code=2
  else:
   result=execute_transactional_active_plan(vals[0][0],vals[1][0],vals[2][0],target_root=target_root,transaction_workspace_root=workspace_root,now=now)
   code=0 if result["transaction_status"]=="committed" else 3 if result["transaction_status"]=="rollback_failed" else 1
 _write(result_path,result);return result,code
def main(argv=None):
 a=build_parser().parse_args(argv);r,c=run_transactional_execution_cli(a.command,a.authorization_file,getattr(a,"invocation_file",None),getattr(a,"bundle_file",None),target_root=getattr(a,"target_root",None),workspace_root=getattr(a,"workspace_root",None),now=getattr(a,"now",None),result_path=a.result_path);print(json.dumps(r,ensure_ascii=False,indent=2,sort_keys=True));return c
if __name__=="__main__":raise SystemExit(main())
