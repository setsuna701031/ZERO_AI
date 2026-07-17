from __future__ import annotations

import inspect
import json
from pathlib import Path

from core.runtime.runtime_evidence_surface import (
    evidence_index_path,
    list_evidence,
    load_evidence_index,
    register_evidence,
)


def test_register_evidence_writes_task_index(tmp_path: Path) -> None:
    artifact = tmp_path / "workspace" / "evidence" / "code_chain_repair" / "task_a_repair_result_report.json"
    index = register_evidence(
        "task a",
        "code_chain_repair_result_report",
        artifact,
        {"schema": "code_chain_repair_result_report_v1", "source": "code_chain"},
        repo_root=tmp_path,
    )

    index_path = evidence_index_path("task a", repo_root=tmp_path)
    on_disk = json.loads(index_path.read_text(encoding="utf-8"))

    assert index_path == tmp_path / "workspace" / "evidence" / "index" / "task_a_evidence_index.json"
    assert index == on_disk
    assert on_disk["schema"] == "runtime_evidence_index_v1"
    assert on_disk["task_id"] == "task a"
    assert on_disk["evidence_count"] == 1
    assert on_disk["evidence"][0]["evidence_type"] == "code_chain_repair_report"
    assert on_disk["evidence"][0]["path"] == str(artifact)
    assert on_disk["evidence"][0]["metadata"]["source"] == "code_chain"


def test_list_evidence_reads_registered_items(tmp_path: Path) -> None:
    first = tmp_path / "workspace" / "evidence" / "code_chain_repair" / "task_b_repair_result_report.json"
    second = tmp_path / "workspace" / "evidence" / "task_reports" / "task_b_report.json"

    register_evidence(
        "task-b",
        "code_chain_repair_result_report",
        first,
        {"schema": "code_chain_repair_result_report_v1"},
        repo_root=tmp_path,
    )
    register_evidence(
        "task-b",
        "task_report",
        second,
        {"format": "json"},
        repo_root=tmp_path,
    )

    listed = list_evidence("task-b", repo_root=tmp_path)
    loaded = load_evidence_index("task-b", repo_root=tmp_path)

    assert loaded["evidence_count"] == 2
    assert [item["evidence_type"] for item in listed] == [
        "code_chain_repair_report",
        "task_report",
    ]
    assert [item["path"] for item in listed] == [str(first), str(second)]


def test_register_evidence_updates_existing_type_and_path(tmp_path: Path) -> None:
    artifact = tmp_path / "workspace" / "evidence" / "recovery" / "task_c.json"

    register_evidence("task-c", "future_recovery_evidence", artifact, {"version": 1}, repo_root=tmp_path)
    register_evidence("task-c", "future_recovery_evidence", artifact, {"version": 2}, repo_root=tmp_path)

    listed = list_evidence("task-c", repo_root=tmp_path)

    assert len(listed) == 1
    assert listed[0]["metadata"] == {"version": 2}


def test_evidence_surface_is_indexing_only_not_execution() -> None:
    import core.runtime.runtime_evidence_surface as surface
    from core.agent import agent_loop
    from core.tasks import scheduler

    source = inspect.getsource(surface)
    agent_loop_source = inspect.getsource(agent_loop)
    scheduler_source = inspect.getsource(scheduler)

    assert "StepExecutor" not in source
    assert "AgentLoop" not in source
    assert "execute_code_chain_attempt" not in source
    assert "autonomous_repair_loop" not in source
    assert "status = \"ok\"" not in source
    assert "runtime_evidence_surface" not in agent_loop_source
    assert "runtime_evidence_surface" not in scheduler_source
