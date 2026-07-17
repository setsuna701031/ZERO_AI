from pathlib import Path

from core.runtime.runtime_mission_execution_approval_flow import execute_approved_mission,review_mission_execution_plan
from core.runtime.runtime_natural_language_mission_bootstrap import run_natural_language_mission

NOW="2026-07-13T00:00:00+00:00"


def test_read_only_completes_with_evidence_and_no_mutation(tmp_path):
    source=tmp_path/"README.md";source.write_text("hello",encoding="utf-8");before=source.read_bytes()
    result=run_natural_language_mission("read README.md",workspace_root=tmp_path,now=NOW)
    assert result["bootstrap_status"]=="completed" and result["runtime_result"]["mutation_performed"] is False
    assert source.read_bytes()==before and result["runtime_result"]["evidence"]


def test_create_verify_approval_completion_and_replay(tmp_path):
    artifact=run_natural_language_mission("create hello.txt with content hello zero and then verify it",workspace_root=tmp_path,now=NOW)
    assert artifact["bootstrap_status"]=="waiting_for_plan_confirmation" and not (tmp_path/"hello.txt").exists()
    review_mission_execution_plan(artifact["artifact_path"],decision="approve",operator_id="operator",now=NOW)
    result=execute_approved_mission(artifact["artifact_path"],operator_id="operator",now=NOW)
    assert result["mission_status"]=="completed" and (tmp_path/"hello.txt").read_text()=="hello zero"
    mtime=(tmp_path/"hello.txt").stat().st_mtime_ns
    replay=execute_approved_mission(artifact["artifact_path"],operator_id="operator",now=NOW)
    assert replay["mission_status"]=="completed" and (tmp_path/"hello.txt").stat().st_mtime_ns==mtime
