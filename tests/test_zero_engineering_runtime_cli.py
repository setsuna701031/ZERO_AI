import json
from cli.zero_engineering_runtime import main
def test_cli_canonical_preview(capsys):
 assert main(["pipeline","--json",json.dumps({"request_id":"r","workspace_id":"w","workspace_root_fingerprint":"f"})])==0; out=capsys.readouterr().out; assert json.loads(out)["result"]["status"]=="previewed"
def test_cli_error_has_no_traceback(capsys):
 assert main(["pipeline","--json","{"])==2; assert "Traceback" not in capsys.readouterr().out
