import json
from cli.zero_capability_activation_authorization_review_decision import run
from tests.test_runtime_capability_activation_authorization_review_decision import request, NOW

def test_cli_stdout_contract_and_output_file(tmp_path):
    source=tmp_path/"request.json"; source.write_text(json.dumps(request()),encoding="utf-8")
    output=tmp_path/"decision.json"
    value,code=run(["--request",str(source),"--decision","approved","--reviewer-id","reviewer","--reason","reviewed","--reviewed-at",NOW,"--output",str(output)])
    assert code==0 and value["approved"] and json.loads(output.read_text(encoding="utf-8"))==value
    assert not any(value[k] for k in ("active_authorization_created","token_issued","runtime_activated","execution_authority_granted"))

def test_cli_invalid_inputs_are_sanitized(tmp_path):
    missing,code=run(["--request",str(tmp_path/"missing.json"),"--decision","approved","--reviewer-id","r","--reason","x"])
    assert code==2 and missing=={"error":"invalid_json_input"}
    bad=tmp_path/"bad.json";bad.write_text("not json",encoding="utf-8")
    assert run(["--request",str(bad),"--decision","approved","--reviewer-id","r","--reason","x"])[1]==2
