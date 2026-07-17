from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_bootstrap_admission import FUTURE_CONSUMERS,MODES,admit_capability_bootstrap,default_policy
from core.runtime.runtime_capability_bootstrap_admission_validation import validate_admission_decision
def _read(p:str)->Any:return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def run(argv:list[str]|None=None)->tuple[Any,int]:
 p=argparse.ArgumentParser(prog="python -m cli.zero_capability_bootstrap_admit");s=p.add_subparsers(dest="command",required=True)
 for x in ("modes","defaults","future-consumers"):s.add_parser(x)
 for x in ("admit","validate","explain"):q=s.add_parser(x);q.add_argument("json_file")
 a=p.parse_args(argv)
 try:
  if a.command=="modes":return {"modes":sorted(MODES)},0
  if a.command=="defaults":return {"mode":"evaluate_admission","future_consumer":sorted(FUTURE_CONSUMERS)[0],"policy":default_policy()},0
  if a.command=="future-consumers":return {"future_consumers":sorted(FUTURE_CONSUMERS)},0
  v=_read(a.json_file)
  if a.command=="admit":
   d=admit_capability_bootstrap(v["request"],consumption_result=v["consumption_result"],lease=v.get("lease"),integration=v["integration"],runtime_context=v["runtime_context"]);return d,0 if d["admission_status"] in {"validated","admitted","blocked","rejected"} else 1
  z=validate_admission_decision(v)
  if a.command=="validate":return {"valid":z.valid,"errors":list(z.errors)},0 if z.valid else 1
  return {"valid":z.valid,"admission_status":v.get("admission_status"),"admitted":v.get("admitted"),"blockers":v.get("blockers",[]),"runtime_started":v.get("runtime_started"),"authorization_issued":v.get("authorization_issued"),"token_issued":v.get("token_issued")},0 if z.valid else 1
 except (OSError,KeyError,ValueError,TypeError,json.JSONDecodeError) as e:return {"error":"input_error","error_type":type(e).__name__},2
def main(argv:list[str]|None=None)->int:
 try:v,c=run(argv)
 except SystemExit as e:return int(e.code or 0)
 sys.stdout.write(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n");return c
if __name__=="__main__":raise SystemExit(main())
