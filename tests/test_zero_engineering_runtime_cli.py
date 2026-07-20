import json
import cli.zero_engineering_runtime as cli_module
from cli.zero_engineering_runtime import main
from tests.engineering_runtime_adapter_invocation_mainline_fixtures import mainline_payload
def test_cli_canonical_preview(capsys):
 assert main(["pipeline","--json",json.dumps({"request_id":"r","workspace_id":"w","workspace_root_fingerprint":"f"})])==0; out=capsys.readouterr().out; assert json.loads(out)["result"]["status"]=="previewed"
def test_cli_error_has_no_traceback(capsys):
 assert main(["pipeline","--json","{"])==2; assert "Traceback" not in capsys.readouterr().out
def test_cli_inspects_passive_adapter_invocation(capsys):
 payload=mainline_payload()
 assert main(["adapter-invocation","--json",json.dumps(payload)])==0
 out=json.loads(capsys.readouterr().out)
 assert out["result_status"]=="invoked"
 assert out["adapter_invoked"] is False
 assert out["executor_invoked"] is False
 assert out["mutation_performed"] is False
def test_cli_incomplete_and_foreign_session_fail(capsys):
 payload=mainline_payload(); payload["adapter_invocation"].pop("resource_constraints")
 assert main(["adapter-invocation","--json",json.dumps(payload)])==2
 assert json.loads(capsys.readouterr().out)["status"]=="invalid"
 payload=mainline_payload(); payload["adapter_invocation"]["activation_handoff"]["execution_session_id"]="foreign"
 assert main(["adapter-invocation","--json",json.dumps(payload)])==2
 assert json.loads(capsys.readouterr().out)["status"]=="invalid"
def test_cli_not_closed_is_failure(monkeypatch,capsys):
 monkeypatch.setattr(cli_module,"orchestrate_engineering_runtime",lambda *args,**kwargs:{"result":{"status":"not_closed"}})
 assert main(["adapter-invocation","--json","{}"])==2
 assert json.loads(capsys.readouterr().out)["status"]=="not_closed"
