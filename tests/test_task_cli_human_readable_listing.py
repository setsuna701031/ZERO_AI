from __future__ import annotations

from cli.task_cli import _print_task_table


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
