from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_cursor_advance_authority import evaluate_cursor_advance


ROOT = Path(__file__).resolve().parents[1]


def _progress_apply(**overrides):
    record = {
        "schema": "zero.runtime.progress_apply_gate.v1",
        "progress_apply_record_id": "runtime-progress-apply::session-1521::read",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_step_commit_result_id": "runtime-step-commit-result::session-1521::read",
        "progress_apply_allowed": True,
        "progress_record_created": True,
        "progress_apply_denied": False,
        "denial_reason": "none",
        "result_kind": "read_result",
        "summary": "caller supplied read evidence",
        "failure_reason": "none",
        "recovery_required": False,
    }
    record.update(overrides)
    return record


def _current_cursor():
    return {
        "cursor_id": "runtime-cursor::session-1521::step-1",
        "step_index": 1,
        "state": "CONTINUE",
    }


def _next_candidate():
    return {
        "cursor_id": "runtime-cursor::session-1521::step-2",
        "step_index": 2,
        "state": "CONTINUE",
    }


def test_1521_valid_progress_apply_authorizes_cursor_advance():
    previous = _current_cursor()
    candidate = _next_candidate()

    record = evaluate_cursor_advance(_progress_apply(), previous, candidate)

    assert record["cursor_advance_authorized"] is True
    assert record["previous_cursor"] == previous
    assert record["next_cursor"] == candidate
    assert record["source_progress_id"] == "runtime-progress-apply::session-1521::read"
    assert record["denial_reason"] == "none"
    assert record["runtime_state_mutated"] is False


def test_1522_missing_apply_authority_denies():
    record = evaluate_cursor_advance(None, _current_cursor(), _next_candidate())

    assert record["cursor_advance_authorized"] is False
    assert record["source_progress_id"] is None
    assert record["denial_reason"] == "missing_progress_apply_record"
    assert record["runtime_state_mutated"] is False


def test_1523_failed_progress_apply_denies_deterministically():
    apply_record = _progress_apply(
        progress_apply_allowed=False,
        progress_record_created=False,
        progress_apply_denied=True,
        denial_reason="commit_not_completed",
    )

    first = evaluate_cursor_advance(apply_record, _current_cursor(), _next_candidate())
    second = evaluate_cursor_advance(apply_record, _current_cursor(), _next_candidate())

    assert first == second
    assert first["cursor_advance_authorized"] is False
    assert first["next_cursor"] == {}
    assert first["denial_reason"] == "commit_not_completed"


def test_1524_missing_next_candidate_denies():
    record = evaluate_cursor_advance(_progress_apply(), _current_cursor(), None)

    assert record["cursor_advance_authorized"] is False
    assert record["denial_reason"] == "missing_next_candidate"
    assert record["previous_cursor"] == _current_cursor()
    assert record["next_cursor"] == {}


def test_1525_boundary_does_not_import_execution_surfaces():
    source = (ROOT / "core/runtime/runtime_cursor_advance_authority.py").read_text()

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert "task_runner" not in source
    assert "agent_loop" not in source
    assert "progress_memory" not in source
    assert "writer" not in source


def test_1526_boundary_does_not_trigger_execution_or_next_tick():
    record = evaluate_cursor_advance(_progress_apply(), _current_cursor(), _next_candidate())

    assert record["execution_admission_called"] is False
    assert record["worker_called"] is False
    assert record["task_executed"] is False
    assert record["runtime_queue_mutated"] is False
    assert record["loop_continued"] is False
    assert record["next_tick_requested"] is False


def test_1527_result_is_record_only_cursor_authority():
    record = evaluate_cursor_advance(_progress_apply(), _current_cursor(), _next_candidate())

    assert record["record_only"] is True
    assert record["cursor_authority_only"] is True
    assert record["cursor_advance_record_id"].startswith("runtime-cursor-advance::")


def test_1528_inputs_are_not_mutated():
    apply_record = _progress_apply()
    previous = _current_cursor()
    candidate = _next_candidate()

    evaluate_cursor_advance(apply_record, previous, candidate)

    assert apply_record == _progress_apply()
    assert previous == _current_cursor()
    assert candidate == _next_candidate()
