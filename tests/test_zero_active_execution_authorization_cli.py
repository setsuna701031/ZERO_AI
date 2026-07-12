from __future__ import annotations
import json
from cli.zero_active_execution_authorization import run_active_execution_authorization_cli
from tests.test_runtime_active_execution_authorization import NOW, records
def write(path,value,bom=False): path.write_text(json.dumps(value),encoding="utf-8-sig" if bom else "utf-8")
def test_authorize_reject_status_bom_and_result(tmp_path):
    controlled,auth=records(tmp_path); cp,ap=tmp_path/"c.json",tmp_path/"a.json"; write(cp,controlled,True); write(ap,auth,True); out=tmp_path/"out.json"
    result,code=run_active_execution_authorization_cli("authorize",cp,ap,now=NOW,result_path=out)
    assert code==0 and result["authorization_status"]=="authorized"
    status,code=run_active_execution_authorization_cli("status",out,result_path=out); assert code==0 and status["authorization_status"]=="authorized"
    auth["decision"]="rejected"; write(ap,auth); result,code=run_active_execution_authorization_cli("authorize",cp,ap,now=NOW,result_path=out)
    assert code==1 and result["authorization_status"]=="rejected"
def test_invalid_json_expiration_and_status(tmp_path):
    controlled,auth=records(tmp_path); cp,ap,out=tmp_path/"c.json",tmp_path/"a.json",tmp_path/"out.json"; write(cp,controlled); ap.write_text("bad")
    _,code=run_active_execution_authorization_cli("authorize",cp,ap,result_path=out); assert code==2
    write(ap,auth); result,code=run_active_execution_authorization_cli("authorize",cp,ap,now="2026-07-10T12:16:00+00:00",result_path=out); assert code==1
    write(out,{"contract":"wrong"}); _,code=run_active_execution_authorization_cli("status",out,result_path=out); assert code==2
