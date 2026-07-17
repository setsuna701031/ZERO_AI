import json
import pytest
from core.runtime.runtime_candidate_authoring_engine import *

NOW="2026-07-12T00:00:00+00:00"
def request():
 return create_authoring_request(goal={"goal_id":"g","mission_id":"m","goal_type":"modify","target_scope":["a.py"],"acceptance_criteria":["a"],"validation_requirements":["v"]},session={"session_id":"s"},authoring_instruction={"authoring_strategy":"append_text","append_text":"# x"},repository_context_references=[],inspect_evidence_references=[],now=NOW)
def test_bom_atomic_reload_fingerprint_and_identity(tmp_path):
 path=tmp_path/"request.json";original=request();save_authoring_artifact(original,path)
 assert path.read_bytes().startswith(b"\xef\xbb\xbf") and load_authoring_artifact(path,expected_contract=REQUEST_CONTRACT,expected_identity=original["request_id"],now=NOW)==original
 with pytest.raises(ValueError,match="identity"):load_authoring_artifact(path,expected_identity="wrong",now=NOW)
 data=json.loads(path.read_text(encoding="utf-8-sig"));data["goal_id"]="tampered";path.write_text(json.dumps(data),encoding="utf-8")
 with pytest.raises(ValueError,match="fingerprint"):load_authoring_artifact(path,now=NOW)
def test_expiration_and_symlink(tmp_path):
 path=tmp_path/"request.json";save_authoring_artifact(request(),path)
 with pytest.raises(ValueError,match="expired"):load_authoring_artifact(path,now="2026-07-13T00:00:00+00:00")
 link=tmp_path/"link.json"
 try:link.symlink_to(path)
 except OSError:pytest.skip("symlink unavailable")
 with pytest.raises(ValueError,match="unsafe"):load_authoring_artifact(link,now=NOW)
