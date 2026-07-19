from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from tests.engineering_workspace_mutation_executor_fixtures import handoff
from core.engineering.engineering_governed_workspace_mutation_executor import validate_only, execute_pipeline
from core.engineering.engineering_workspace_mutation_executor_common import sha_bytes, canonical_json

def ws(tmp_path):
    (tmp_path/"sentinel.txt").write_text("sentinel",encoding="utf-8")
    return tmp_path

def test_validation_only_does_not_create_transaction_dir(tmp_path):
    root=ws(tmp_path); out=validate_only(handoff(root),root)
    assert out["executor_admission"]["status"]=="admitted"
    assert not (root/".zero").exists()

def test_execute_create_text_file(tmp_path):
    root=ws(tmp_path); out=execute_pipeline(handoff(root),root,True)
    assert out["result"]["status"]=="succeeded"
    assert (root/"out.txt").read_text(encoding="utf-8")=="hello\n"
    assert "root_path" not in canonical_json(out)

def test_reject_absolute_and_transaction_paths(tmp_path):
    root=ws(tmp_path)
    h=handoff(root,[{"operation_id":"op","operation_type":"create_text_file","target_path":"/x","proposed_content":"x","expected_after_fingerprint":sha_bytes(b"x")}])
    assert validate_only(h,root)["executor_admission"]["status"]!="admitted"
    h=handoff(root,[{"operation_id":"op","operation_type":"create_text_file","target_path":".zero/transactions/x","proposed_content":"x","expected_after_fingerprint":sha_bytes(b"x")}])
    assert validate_only(h,root)["executor_admission"]["status"]!="admitted"
