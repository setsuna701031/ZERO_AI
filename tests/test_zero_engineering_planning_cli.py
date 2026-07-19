import json
from cli.zero_engineering_planning import run
from tests.test_engineering_planning_context import planning_fixture
def test_cli_success_and_failure(tmp_path):
 path=tmp_path/"closure.json";path.write_text(json.dumps(planning_fixture(tmp_path/"repo")),encoding="utf-8")
 value,code=run([str(path)]);assert code==0 and value["status"]=="closed"
 bad=tmp_path/"bad.json";bad.write_text("{",encoding="utf-8");assert run([str(bad)])[1]==2
