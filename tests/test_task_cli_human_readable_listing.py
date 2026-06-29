from __future__ import annotations

from cli.task_cli import _print_task_table
import pytest

pytestmark = [pytest.mark.llm]




def test_task_list_default_hides_runtime_fingerprints_and_limits(capsys) -> None:
    long_id = "agent-runtime-abcdef1234567890-runtime-deadbeef12345678"
    _print_task_table(
        [
            {"task_id": "task_old", "status": "finished", "goal": "old task", "created_at": 1},
            {"task_id": long_id, "status": "queued", "goal": "run runtime task", "created_at": 2},
        ],
        limit=1,
    )

    out = capsys.readouterr().out
    assert "Showing latest 1 of 2 tasks" in out
    assert long_id not in out
    assert "agent-abcdef12…12345678" in out
    assert "run runtime task" in out


def test_task_list_verbose_preserves_full_ids(capsys) -> None:
    long_id = "planner_prt_12345678-runtime-abcdef1234567890"
    _print_task_table(
        [
            {
                "task_id": long_id,
                "status": "queued",
                "goal": "inspect full runtime lineage",
                "created_at": 1,
                "runtime_session_id": "runtime-deadbeef12345678",
            }
        ],
        verbose=True,
        limit=None,
    )

    out = capsys.readouterr().out
    assert long_id in out
    assert "runtime" in out
    assert "inspect full runtime lineage" in out


def test_task_list_raw_preserves_machine_readable_payload(capsys) -> None:
    long_id = "agent-runtime-abcdef1234567890-runtime-deadbeef12345678"
    _print_task_table(
        [{"task_id": long_id, "status": "queued", "goal": "raw payload", "created_at": 1}],
        raw=True,
    )

    out = capsys.readouterr().out
    assert long_id in out
    assert '"goal": "raw payload"' in out

from cli.task_cli import (
    _print_artifact_graph_edges,
    _print_artifact_graph_nodes,
    _print_artifact_graph_summary,
)


def _sample_artifact_graph() -> dict:
    return {
        "nodes": [
            {"artifact": "workspace/shared/input.txt", "type": "input", "first_seen_at": 1},
            {
                "artifact": "workspace/shared/summary_graph.txt",
                "type": "summary",
                "artifact_type": "summary_text",
                "producer_task_id": "task_1",
                "first_seen_at": 2,
            },
            {"artifact": "[['fail']]", "type": "input", "first_seen_at": 3},
        ],
        "edges": [
            {
                "from": "workspace/shared/input.txt",
                "to": "workspace/shared/summary_graph.txt",
                "operation": "summary_text",
                "task_id": "task_1",
                "created_at": 2,
            },
            {
                "from": "[['fail']]",
                "to": "workspace/shared/task_failure.json",
                "operation": "persistent_runtime_session",
                "task_id": "task_2",
                "created_at": 3,
            },
        ],
        "events": [{"task_id": "task_1"}, {"task_id": "task_2"}],
    }


def test_artifact_graph_summary_is_limited_and_human_readable(capsys) -> None:
    _print_artifact_graph_summary(_sample_artifact_graph(), limit=1)

    out = capsys.readouterr().out
    assert "ZERO Artifact Graph" in out
    assert "nodes: 3" in out
    assert "edges: 2" in out
    assert "latest edges: showing 1 of 2" in out
    assert "<compound-plan>" not in out
    assert "[['fail']]" not in out
    assert "workspace/shared/input.txt ->" not in out
    assert "Use `task graph nodes`" in out


def test_artifact_graph_edges_table_can_show_all(capsys) -> None:
    _print_artifact_graph_edges(_sample_artifact_graph(), limit=None)

    out = capsys.readouterr().out
    assert "ZERO Artifact Graph edges: 2" in out
    assert "shared/input.txt" in out
    assert "shared/summary_graph.txt" in out
    assert "persistent_runtime_session" in out


def test_artifact_graph_nodes_table_hides_non_artifact_noise(capsys) -> None:
    _print_artifact_graph_nodes(_sample_artifact_graph(), limit=None)

    out = capsys.readouterr().out
    assert "ZERO Artifact Graph nodes: 3" in out
    assert "shared/summary_graph.txt" in out
    assert "<compound-plan>" not in out
    assert "<non-artifact>" not in out

from cli.task_cli import _reorder_selected_task_first, _select_fast_runnable_task


def test_select_fast_runnable_task_supports_latest_next_and_task_id() -> None:
    tasks = [
        {"task_id": "task_old", "status": "queued", "goal": "old", "created_at": 1, "fast_cli_path": True},
        {"task_id": "task_done", "status": "finished", "goal": "done", "created_at": 2, "fast_cli_path": True},
        {"task_id": "task_new", "status": "queued", "goal": "new", "created_at": 3, "fast_cli_path": True},
        {"task_id": "task_legacy", "status": "queued", "goal": "legacy", "created_at": 4},
    ]

    assert _select_fast_runnable_task(tasks, "next")["task_id"] == "task_old"
    assert _select_fast_runnable_task(tasks, "latest")["task_id"] == "task_new"
    assert _select_fast_runnable_task(tasks, "task_old")["task_id"] == "task_old"
    assert _select_fast_runnable_task(tasks, "task_done") is None
    assert _select_fast_runnable_task(tasks, "task_legacy") is None


def test_reorder_selected_task_first_preserves_remaining_order() -> None:
    tasks = [
        {"task_id": "task_a"},
        {"task_id": "task_b"},
        {"task_id": "task_c"},
    ]

    reordered = _reorder_selected_task_first(tasks, "task_c")
    assert [task["task_id"] for task in reordered] == ["task_c", "task_a", "task_b"]


from cli.task_cli import _print_selected_task_run_result, _task_run_wants_json


def test_selected_task_run_result_is_human_readable_by_default(capsys) -> None:
    _print_selected_task_run_result(
        {
            "ok": True,
            "selector": "latest",
            "selected_task_id": "task_123",
            "result": {
                "executed_count": 1,
                "blocked_count": 0,
                "executed_results": [
                    {
                        "goal": "generate a markdown report from workspace/shared/summary.txt into workspace/shared/report.md",
                        "artifact": {
                            "artifact_path": "E:/zero_ai/workspace/shared/report.md",
                            "artifact_type": "markdown_report",
                        },
                        "runtime_ownership": {"very": "large"},
                    }
                ],
            },
        }
    )

    out = capsys.readouterr().out
    assert "ZERO Task Run" in out
    assert "ok: true" in out
    assert "selector: latest" in out
    assert "selected: task_123" in out
    assert "artifact_type: markdown_report" in out
    assert "shared/report.md" in out
    assert "runtime_ownership" not in out
    assert "--json" in out


def test_selected_task_run_error_is_human_readable(capsys) -> None:
    _print_selected_task_run_result(
        {
            "ok": False,
            "selector": "task_done",
            "error": "no matching queued fast task",
            "hint": "Use task list",
        }
    )

    out = capsys.readouterr().out
    assert "ok: false" in out
    assert "selector: task_done" in out
    assert "error: no matching queued fast task" in out
    assert "hint: Use task list" in out


def test_task_run_json_flag_detection() -> None:
    assert _task_run_wants_json(["task", "run", "latest", "--json"])
    assert _task_run_wants_json(["task", "run", "next", "raw"])
    assert not _task_run_wants_json(["task", "run", "latest"])

from cli.task_cli import _display_task_status, _queued_invalid_reason, _is_fast_runnable_task


def _zombie_task() -> dict:
    return {
        "task_id": "task_zombie",
        "status": "queued",
        "goal": "Task name:",
        "created_at": 10,
        "steps": [{"type": "llm", "prompt": "Task name:"}],
        "route": {
            "ok": False,
            "component_contract_mismatch": True,
            "error": "router contract mismatch",
        },
        "result_exists": True,
        "results": [],
        "step_results": [],
        "execution_log": [],
    }


def test_queued_invalid_task_is_marked_in_task_list(capsys) -> None:
    _print_task_table([_zombie_task()], limit=None)

    out = capsys.readouterr().out
    assert "task_zombie" in out
    assert "queued_invalid" in out
    assert "queued  " not in out


def test_zombie_queued_task_is_not_fast_runnable() -> None:
    task = _zombie_task()

    assert _queued_invalid_reason(task)
    assert _display_task_status(task) == "queued_invalid"
    assert not _is_fast_runnable_task({**task, "fast_cli_path": True})


def test_select_fast_runnable_task_skips_zombie_for_latest_next() -> None:
    tasks = [
        {**_zombie_task(), "fast_cli_path": True, "created_at": 99},
        {"task_id": "task_valid", "status": "queued", "goal": "valid", "created_at": 1, "fast_cli_path": True, "steps": [{"type": "llm", "prompt": "valid"}]},
    ]

    assert _select_fast_runnable_task(tasks, "latest")["task_id"] == "task_valid"
    assert _select_fast_runnable_task(tasks, "next")["task_id"] == "task_valid"
    assert _select_fast_runnable_task(tasks, "task_zombie") is None

from cli.task_cli import (
    _apply_task_cleanup,
    _print_task_audit,
    _print_task_cleanup,
    _task_cleanup_payload,
    _task_inventory_audit,
)


def test_task_inventory_audit_reports_invalid_and_stale_queued(capsys) -> None:
    tasks = [
        {"task_id": "task_done", "status": "finished", "goal": "done", "created_at": 1},
        {
            "task_id": "task_bad_route",
            "status": "queued",
            "goal": "Task name:",
            "created_at": 2,
            "route": {"ok": False, "error": "router contract mismatch"},
        },
        {"task_id": "task_stale", "status": "queued", "goal": "legacy scheduler task", "created_at": 3},
        {"task_id": "task_fast", "status": "queued", "goal": "fast task", "created_at": 4, "fast_cli_path": True},
    ]

    payload = _task_inventory_audit(tasks)
    assert payload["total_count"] == 4
    assert payload["status_counts"]["finished"] == 1
    assert payload["status_counts"]["queued_invalid"] == 1
    assert payload["status_counts"]["queued"] == 2
    assert payload["queued_invalid_count"] == 1
    assert payload["stale_queued_count"] == 1
    assert payload["runnable_fast_queued_count"] == 1

    _print_task_audit(payload)
    out = capsys.readouterr().out
    assert "ZERO Task Inventory Audit" in out
    assert "queued_invalid: 1" in out
    assert "task_bad_route" in out
    assert "task_stale" in out
    assert "task cleanup --dry-run" in out


def test_task_cleanup_dry_run_targets_invalid_only_by_default(capsys) -> None:
    tasks = [
        {"task_id": "task_invalid", "status": "queued", "goal": "Task name:"},
        {"task_id": "task_stale", "status": "queued", "goal": "legacy scheduler task"},
        {"task_id": "task_fast", "status": "queued", "goal": "fast task", "fast_cli_path": True},
    ]

    payload = _task_cleanup_payload(tasks, include_stale=False, apply=False)
    assert payload["target_count"] == 1
    assert payload["targets"][0]["task_id"] == "task_invalid"
    assert payload["targets"][0]["to_status"] == "archived_invalid"

    _print_task_cleanup(payload)
    out = capsys.readouterr().out
    assert "ZERO Task Cleanup" in out
    assert "apply: false" in out
    assert "task_invalid" in out
    assert "task_stale" not in out


def test_apply_task_cleanup_archives_invalid_without_deleting_records() -> None:
    tasks = [
        {"task_id": "task_invalid", "status": "queued", "goal": "Task name:", "history": ["created", "queued"]},
        {"task_id": "task_keep", "status": "finished", "goal": "done"},
    ]

    updated, payload = _apply_task_cleanup(tasks, include_stale=False)
    assert payload["changed_count"] == 1
    assert updated[0]["task_id"] == "task_invalid"
    assert updated[0]["status"] == "archived_invalid"
    assert updated[0]["history"][-1] == "archived_invalid"
    assert updated[0]["cleanup"]["previous_status"] == "queued"
    assert updated[1]["status"] == "finished"


def test_apply_task_cleanup_can_include_stale_when_requested() -> None:
    tasks = [
        {"task_id": "task_stale", "status": "queued", "goal": "legacy scheduler task"},
        {"task_id": "task_fast", "status": "queued", "goal": "fast task", "fast_cli_path": True},
    ]

    updated, payload = _apply_task_cleanup(tasks, include_stale=True)
    assert payload["changed_count"] == 1
    assert updated[0]["status"] == "archived_stale"
    assert updated[1]["status"] == "queued"
