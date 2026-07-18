import json,subprocess,sys
from cli.zero_engineering_developer_intent import run
def test_parse_validate_inspect_and_errors(tmp_path):
 v,c=run(["parse","分析","repository","並修正 bug"]);assert c==0
 p=tmp_path/"v.json";p.write_text(json.dumps(v),encoding="utf-8");assert run(["validate",str(p)])[1]==0 and run(["inspect",str(p)])[0]["intent_types"]
 bad=tmp_path/"bad";bad.write_text("{",encoding="utf-8");assert run(["validate",str(bad)])[1]==2
 done=subprocess.run([sys.executable,"-m","cli.zero_engineering_developer_intent","validate",str(bad)],capture_output=True,text=True);assert "Traceback" not in done.stderr
