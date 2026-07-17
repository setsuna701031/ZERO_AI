from __future__ import annotations

import inspect
import json
from pathlib import Path

from core.agent.code_chain_repair_presentation import (
    code_chain_repair_evidence_path,
    format_code_chain_repair_evidence,
    format_code_chain_repair_evidence_for_task,
    load_code_chain_repair_evidence,
)


def test_format_code_chain_repair_evidence_renders_human_readable_summary() -> None:
    report = {
        "schema": "code_chain_repair_result_report_v1",
        "final_status": "ok",
        "original_failure": {
            "ok": False,
            "message": "verify_contains failed: expected return fixed",
        },
        "attempt_count": 2,
        "attempt_history": [
            {
                "attempt_index": 1,
                "attempt_kind": "initial",
                "ok": False,
                "failure_reason": "verify_contains failed",
            },
            {
                "attempt_index": 2,
                "attempt_kind": "repair",
                "ok": True,
            },
        ],
        "verification_history": [
            {
                "attempt_index": 1,
                "attempt_kind": "initial",
                "ok": False,
                "failure_reason": "verify_contains failed",
            },
            {
                "attempt_index": 2,
                "attempt_kind": "repair",
                "ok": True,
                "verification_command": "python -m py_compile target.py",
            },
        ],
        "repair_attempted": True,
        "repair_succeeded": True,
        "evidence_path": "workspace/evidence/code_chain_repair/task_a_repair_result_report.json",
    }

    text = format_code_chain_repair_evidence(report)

    assert "Code Chain Repair Evidence:" in text
    assert "- final_status: ok" in text
    assert "- original_failure: verify_contains failed: expected return fixed" in text
    assert "- attempt_count: 2" in text
    assert "- attempt_1_failed_reason: verify_contains failed" in text
    assert "- repair_attempted: true" in text
    assert "- repair_succeeded: true" in text
    assert "- verification_result: passed (attempt #2; repair; python -m py_compile target.py)" in text
    assert "- evidence_path: workspace/evidence/code_chain_repair/task_a_repair_result_report.json" in text


def test_format_code_chain_repair_evidence_reads_exported_task_report(tmp_path: Path) -> None:
    evidence_path = code_chain_repair_evidence_path(
        repo_root=tmp_path,
        task_id="task with spaces",
    )
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(
        json.dumps(
            {
                "schema": "code_chain_repair_result_report_v1",
                "final_status": "failed",
                "original_failure": {"final_answer": "command failed"},
                "attempt_count": 1,
                "attempt_history": [
                    {
                        "attempt_index": 1,
                        "attempt_kind": "initial",
                        "ok": False,
                        "message": "command failed",
                    }
                ],
                "verification_history": [
                    {
                        "attempt_index": 1,
                        "attempt_kind": "initial",
                        "ok": False,
                        "failure_reason": "command failed",
                    }
                ],
                "repair_attempted": False,
                "repair_succeeded": False,
            }
        ),
        encoding="utf-8",
    )

    loaded = load_code_chain_repair_evidence(
        repo_root=tmp_path,
        task_id="task with spaces",
    )
    text = format_code_chain_repair_evidence_for_task(
        repo_root=tmp_path,
        task_id="task with spaces",
    )

    assert evidence_path == tmp_path / "workspace" / "evidence" / "code_chain_repair" / "task_with_spaces_repair_result_report.json"
    assert loaded["final_status"] == "failed"
    assert "- final_status: failed" in text
    assert "- original_failure: command failed" in text
    assert "- attempt_count: 1" in text
    assert "- attempt_1_failed_reason: command failed" in text
    assert "- repair_attempted: false" in text
    assert "- repair_succeeded: false" in text
    assert "- verification_result: failed (attempt #1; initial; command failed)" in text
    assert f"- evidence_path: {evidence_path}" in text


def test_missing_or_malformed_evidence_is_display_only_and_non_fatal(tmp_path: Path) -> None:
    malformed_path = code_chain_repair_evidence_path(repo_root=tmp_path, task_id="bad")
    malformed_path.parent.mkdir(parents=True)
    malformed_path.write_text("{not json", encoding="utf-8")

    assert load_code_chain_repair_evidence(repo_root=tmp_path, task_id="missing") == {}
    assert load_code_chain_repair_evidence(repo_root=tmp_path, task_id="bad") == {}

    text = format_code_chain_repair_evidence_for_task(repo_root=tmp_path, task_id="missing")

    assert "- final_status: <none>" in text
    assert "- original_failure: <none>" in text
    assert "- attempt_count: <none>" in text
    assert "- repair_attempted: <none>" in text
    assert "- verification_result: not recorded" in text
    assert "missing_repair_result_report.json" in text


def test_repair_presentation_does_not_own_execution_or_mutation() -> None:
    import core.agent.code_chain_repair_presentation as presentation
    from core.agent import agent_loop
    from core.tasks import scheduler

    source = inspect.getsource(presentation)
    agent_loop_source = inspect.getsource(agent_loop)
    scheduler_source = inspect.getsource(scheduler)

    assert "StepExecutor" not in source
    assert "AgentLoop" not in source
    assert "execute_code_chain_attempt" not in source
    assert "autonomous_repair_loop" not in source
    assert "write_text" not in source
    assert "code_chain_repair_presentation" not in agent_loop_source
    assert "code_chain_repair_presentation" not in scheduler_source
