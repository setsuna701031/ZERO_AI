import json
from cli.zero_capability_activation_gate import run
from tests.test_runtime_capability_activation_gate import admitted_chain

def test_catalog_commands_do_not_invoke_other_layers():
    assert run(["modes"])[0]["modes"]==["evaluate_gate","prepare_authorization_request","validate_only"]
    assert run(["defaults"])[1]==0 and run(["authorization-classes"])[1]==0 and run(["future-consumers"])[1]==0
def test_gate_validate_and_explain(tmp_path):
    values=admitted_chain(); payload={"admission_decision":values[0],"activation_handoff":values[1],"consumption_result":values[2],"lease":values[3],"integration":values[4],"runtime_context":values[5],"gate_mode":"prepare_authorization_request"}; source=tmp_path/"gate.json";source.write_text(json.dumps(payload),encoding="utf-8")
    decision,code=run(["gate",str(source)]);assert code==0 and decision["gate_status"]=="allowed"
    output=tmp_path/"decision.json";output.write_text(json.dumps(decision),encoding="utf-8");assert run(["validate",str(output)])[0]["valid"] and run(["explain",str(output)])[0]["allowed"]
def test_invalid_json_is_sanitized(tmp_path):
    source=tmp_path/"bad.json";source.write_text("not json",encoding="utf-8");value,code=run(["gate",str(source)]);assert code!=0 and value=={"error":"invalid_json_input"}
