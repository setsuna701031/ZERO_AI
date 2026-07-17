import json
from pathlib import Path

import pytest

from core.runtime.runtime_mission_execution_approval_flow import (
    ensure_pending_execution_plan, execute_approved_mission,
    review_mission_execution_plan, validate_mission_execution_plan,
)
from core.runtime.runtime_natural_language_mission_bootstrap import run_natural_language_mission

NOW="2026-07-13T00:00:00+00:00"


def prepared(tmp_path):
    return run_natural_language_mission("create hello.txt with content hello zero",workspace_root=tmp_path,now=NOW)


def test_pending_plan_is_persisted_bound_and_sealed(tmp_path):
    artifact=prepared(tmp_path);plan=ensure_pending_execution_plan(artifact["artifact_path"],now=NOW)
    assert not validate_mission_execution_plan(plan)
    assert plan["mission_id"]==artifact["mission_reference"]["mission_id"]
    assert plan["required_approval_scope"]==["hello.txt"] and plan["risk_classification"]=="mutation"


def test_scope_expansion_empty_operator_and_tamper_fail(tmp_path):
    artifact=prepared(tmp_path)
    with pytest.raises(ValueError,match="operator_id"): review_mission_execution_plan(artifact["artifact_path"],decision="approve",operator_id="",now=NOW)
    with pytest.raises(ValueError,match="scope_expansion"): review_mission_execution_plan(artifact["artifact_path"],decision="approve",operator_id="op",approved_scope=["other.txt"],now=NOW)
    plan_path=Path(artifact["execution_plan_reference"]["path"]);raw=json.loads(plan_path.read_text());raw["target_paths"]=["evil.txt"];plan_path.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match="fingerprint"): ensure_pending_execution_plan(artifact["artifact_path"],now=NOW)


def test_approval_is_idempotent_and_executes_existing_chain(tmp_path):
    artifact=prepared(tmp_path);first=review_mission_execution_plan(artifact["artifact_path"],decision="approve",operator_id="op",now=NOW);second=review_mission_execution_plan(artifact["artifact_path"],decision="approve",operator_id="op",now=NOW)
    assert first==second and first["execution_authority_granted"] is False
    result=execute_approved_mission(artifact["artifact_path"],operator_id="op",now=NOW)
    assert result["mission_status"]=="completed" and (tmp_path/"hello.txt").read_text()=="hello zero"
    again=execute_approved_mission(artifact["artifact_path"],operator_id="op",now=NOW)
    assert again["mission_status"]=="completed" and (tmp_path/"hello.txt").read_text()=="hello zero"


def test_denial_blocks_without_effect(tmp_path):
    artifact=prepared(tmp_path);approval=review_mission_execution_plan(artifact["artifact_path"],decision="deny",operator_id="op",reason="test denial",now=NOW)
    assert approval["approval_status"]=="denied" and not (tmp_path/"hello.txt").exists()
    with pytest.raises(ValueError,match="not_approved"): execute_approved_mission(artifact["artifact_path"],operator_id="op",now=NOW)
