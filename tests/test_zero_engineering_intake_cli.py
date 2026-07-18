import json,subprocess,sys
from cli.zero_engineering_intake import build_engineering_intake,run
def test_aggregate_intake_deterministic_complete_lineage_and_passive():
 request="分析這個 repository，找出 pytest 卡住的原因，提出安全修正方案並準備受控修改。";a=build_engineering_intake(request);b=build_engineering_intake(request)
 assert a==b and a["status"]=="handed_off" and len([k for k in a if k.startswith("source_") and k.endswith("_id")])==5
 assert a["handoff_payload"]["next_stage"]=="repository_analysis_pending" and not any(a["boundary"][k] for k in ("repository_analysis_started","planning_started","proposal_created","coding_started","execution_started","approval_granted","authorization_granted","authority_granted"))
def test_aggregate_validate_inspect_and_no_traceback(tmp_path):
 v,c=run(["intake","inspect repository and fix bug"]);assert c==0
 p=tmp_path/"h.json";p.write_text(json.dumps(v),encoding="utf-8");assert run(["validate",str(p)])[1]==0 and run(["inspect",str(p)])[1]==0
 bad=tmp_path/"bad";bad.write_text("{",encoding="utf-8");done=subprocess.run([sys.executable,"-m","cli.zero_engineering_intake","validate",str(bad)],capture_output=True,text=True);assert done.returncode and "Traceback" not in done.stderr
