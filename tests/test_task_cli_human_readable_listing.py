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
