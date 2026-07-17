import json
from cli.zero_capability_activation_authorization_request import run
from tests.test_runtime_capability_activation_authorization_request import allowed_gate
def test_metadata_commands():
    assert run(["modes"])[0]["modes"]==["evaluate_review","prepare_review_handoff","validate_only"]
    for command in ("defaults","reviewer-classes","authorization-classes","future-consumers"):assert run([command])[1]==0
def test_review_validate_explain(tmp_path):
    gate,metadata=allowed_gate();source=tmp_path/"request.json";source.write_text(json.dumps({"gate_decision":gate,"authorization_metadata":metadata,"review_mode":"prepare_review_handoff"}),encoding="utf-8");review,code=run(["review",str(source)]);assert code==0 and review["reviewable"]
    output=tmp_path/"review.json";output.write_text(json.dumps(review),encoding="utf-8");assert run(["validate",str(output)])[0]["valid"] and run(["explain",str(output)])[0]["reviewable"]
def test_invalid_input_sanitized(tmp_path):
    source=tmp_path/"bad.json";source.write_text("bad",encoding="utf-8");value,code=run(["review",str(source)]);assert code!=0 and value=={"error":"invalid_json_input"}
