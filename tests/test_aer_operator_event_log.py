from __future__ import annotations

import inspect
import json
import os

from core.runtime.aer_operator_event_log import (
    AER_OPERATOR_EVENT_CONTRACT,
    OPERATOR_EVENT_LOG_DIR_NAME,
    OPERATOR_EVENT_LOG_FILE_NAME,
    append_operator_event,
    build_operator_event,
    load_operator_events,
    operator_event_log_dir,
    operator_event_log_path,
    validate_operator_event,
)
import core.runtime.aer_operator_event_log as event_log_module
import core.runtime.aer_operator_resume as resume_module


def test_operator_event_log_dir_and_path_are_workspace_local_defaults(tmp_path) -> None:
    log_dir = operator_event_log_dir(str(tmp_path))
    log_path = operator_event_log_path(str(tmp_path))

    assert log_dir == os.path.abspath(os.path.join(str(tmp_path), OPERATOR_EVENT_LOG_DIR_NAME))
    assert log_path == os.path.abspath(
        os.path.join(str(tmp_path), OPERATOR_EVENT_LOG_DIR_NAME, OPERATOR_EVENT_LOG_FILE_NAME)
    )


def test_build_operator_event_contains_required_schema_fields() -> None:
    event = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="checkpoint.created",
        phase="checkpointed",
        message="checkpoint created",
        metadata={"checkpoint_id": "checkpoint-1"},
        sequence=7,
    )

    assert event == {
        "contract": AER_OPERATOR_EVENT_CONTRACT,
        "event_id": "event-1",
        "operator_session_id": "operator-session-1",
        "package_id": "package-86",
        "event_type": "checkpoint.created",
        "phase": "checkpointed",
        "message": "checkpoint created",
        "metadata": {"checkpoint_id": "checkpoint-1"},
        "sequence": 7,
    }
    assert validate_operator_event(event)["ok"] is True


def test_build_operator_event_deep_copies_metadata() -> None:
    metadata = {"nested": {"value": "original"}}

    event = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.started",
        metadata=metadata,
    )
    event["metadata"]["nested"]["value"] = "mutated"

    assert metadata["nested"]["value"] == "original"


def test_validate_operator_event_rejects_invalid_shapes_and_identity() -> None:
    assert "payload must be a dict" in validate_operator_event(None)["errors"]

    event = build_operator_event(
        event_id="",
        operator_session_id="",
        package_id="",
        event_type="",
    )
    event["contract"] = "wrong.contract"
    event["phase"] = "not-a-phase"
    event["metadata"] = []
    event["sequence"] = -1

    result = validate_operator_event(event)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]
    assert "event_id is required" in result["errors"]
    assert "operator_session_id is required" in result["errors"]
    assert "package_id is required" in result["errors"]
    assert "event_type is required" in result["errors"]
    assert "invalid phase: not-a-phase" in result["errors"]
    assert "metadata must be a dict" in result["errors"]
    assert "sequence must be >= 0" in result["errors"]


def test_append_operator_event_writes_jsonl_and_load_round_trips(tmp_path) -> None:
    first = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.admitted",
        phase="admitted",
        message="operator admitted",
        sequence=0,
    )
    second = build_operator_event(
        event_id="event-2",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.running",
        phase="running",
        message="operator running",
        sequence=1,
    )

    first_result = append_operator_event(str(tmp_path), first)
    second_result = append_operator_event(str(tmp_path), second)
    loaded = load_operator_events(str(tmp_path))

    assert first_result["ok"] is True
    assert second_result["ok"] is True
    assert loaded == [first, second]

    with open(operator_event_log_path(str(tmp_path)), "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    assert len(lines) == 2
    assert [json.loads(line) for line in lines] == [first, second]


def test_append_operator_event_rejects_sequence_lower_than_last_event(tmp_path) -> None:
    first = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.running",
        phase="running",
        sequence=3,
    )
    older = build_operator_event(
        event_id="event-2",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.checkpointed",
        phase="checkpointed",
        sequence=2,
    )

    assert append_operator_event(str(tmp_path), first)["ok"] is True
    result = append_operator_event(str(tmp_path), older)

    assert result["ok"] is False
    assert "sequence must be monotonically increasing: 2 < 3" in result["errors"]
    assert load_operator_events(str(tmp_path)) == [first]


def test_append_operator_event_allows_sequence_gaps_without_inference(tmp_path) -> None:
    first = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.running",
        phase="running",
        sequence=1,
    )
    later = build_operator_event(
        event_id="event-2",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.checkpointed",
        phase="checkpointed",
        sequence=5,
    )

    assert append_operator_event(str(tmp_path), first)["ok"] is True
    assert append_operator_event(str(tmp_path), later)["ok"] is True

    assert load_operator_events(str(tmp_path)) == [first, later]


def test_load_operator_events_preserves_append_order_and_never_sorts_by_sequence(tmp_path) -> None:
    log_dir = operator_event_log_dir(str(tmp_path))
    os.makedirs(log_dir, exist_ok=True)
    first = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.running",
        phase="running",
        sequence=10,
    )
    second = build_operator_event(
        event_id="event-2",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.checkpointed",
        phase="checkpointed",
        sequence=4,
    )
    with open(operator_event_log_path(str(tmp_path)), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(first))
        handle.write("\n")
        handle.write(json.dumps(second))
        handle.write("\n")

    assert load_operator_events(str(tmp_path)) == [first, second]


def test_append_operator_event_rejects_invalid_event_without_creating_log(tmp_path) -> None:
    event = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-86",
        event_type="operator.admitted",
    )
    event["package_id"] = ""

    result = append_operator_event(str(tmp_path), event)

    assert result["ok"] is False
    assert "package_id is required" in result["errors"]
    assert os.path.exists(operator_event_log_path(str(tmp_path))) is False


def test_load_operator_events_returns_empty_for_missing_log(tmp_path) -> None:
    assert load_operator_events(str(tmp_path)) == []


def test_load_operator_events_filters_by_operator_session_and_package(tmp_path) -> None:
    events = [
        build_operator_event(
            event_id="event-1",
            operator_session_id="operator-session-1",
            package_id="package-86",
            event_type="operator.admitted",
            phase="admitted",
            sequence=0,
        ),
        build_operator_event(
            event_id="event-2",
            operator_session_id="operator-session-2",
            package_id="package-86",
            event_type="operator.admitted",
            phase="admitted",
            sequence=0,
        ),
        build_operator_event(
            event_id="event-3",
            operator_session_id="operator-session-1",
            package_id="package-other",
            event_type="operator.admitted",
            phase="admitted",
            sequence=0,
        ),
    ]
    for event in events:
        append_operator_event(str(tmp_path), event)

    assert load_operator_events(str(tmp_path), operator_session_id="operator-session-1") == [
        events[0],
        events[2],
    ]
    assert load_operator_events(str(tmp_path), package_id="package-86") == [
        events[0],
        events[1],
    ]
    assert load_operator_events(
        str(tmp_path),
        operator_session_id="operator-session-1",
        package_id="package-86",
    ) == [events[0]]


def test_load_operator_events_reports_invalid_jsonl_lines(tmp_path) -> None:
    log_dir = operator_event_log_dir(str(tmp_path))
    os.makedirs(log_dir, exist_ok=True)
    with open(operator_event_log_path(str(tmp_path)), "w", encoding="utf-8") as handle:
        handle.write("{\n")

    loaded = load_operator_events(str(tmp_path))

    assert len(loaded) == 1
    assert loaded[0]["ok"] is False
    assert loaded[0]["errors"][0].startswith("invalid event log line 1:")


def test_event_log_module_has_no_delete_or_update_api() -> None:
    exported_names = dir(event_log_module)

    assert "delete_operator_event" not in exported_names
    assert "delete_operator_events" not in exported_names
    assert "update_operator_event" not in exported_names
    assert "update_operator_events" not in exported_names


def test_event_log_module_does_not_import_forbidden_runtime_layers() -> None:
    source = inspect.getsource(event_log_module)

    forbidden = (
        "Scheduler",
        "TaskRunner",
        "aer_operator_resume",
        "approval",
        "issue_report",
        "operator_loop",
    )
    for token in forbidden:
        assert token not in source


def test_resume_remains_stateless_and_does_not_write_events_in_this_package() -> None:
    source = inspect.getsource(resume_module)

    forbidden = (
        "aer_operator_event_log",
        "append_operator_event",
        "operator_event_log_path",
        "operator_event_log_dir",
    )
    for token in forbidden:
        assert token not in source
