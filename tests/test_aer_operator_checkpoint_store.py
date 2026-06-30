from __future__ import annotations

import json
import os

from core.runtime.aer_operator_checkpoint import (
    build_operator_checkpoint,
    compute_checkpoint_integrity_hash,
)
from core.runtime.aer_operator_checkpoint_store import (
    CHECKPOINT_STORE_DIR_NAME,
    checkpoint_exists,
    checkpoint_path,
    checkpoint_store_dir,
    delete_checkpoint,
    latest_checkpoint_for_identity,
    list_checkpoints,
    load_checkpoints_for_identity,
    load_checkpoint,
    save_checkpoint,
)


def test_checkpoint_store_dir_uses_workspace_local_default(tmp_path) -> None:
    store_dir = checkpoint_store_dir(str(tmp_path))

    assert store_dir == os.path.abspath(os.path.join(str(tmp_path), CHECKPOINT_STORE_DIR_NAME))


def test_checkpoint_path_rejects_empty_and_traversal_ids(tmp_path) -> None:
    for checkpoint_id in ("", "../escape", "..", "nested/checkpoint"):
        try:
            checkpoint_path(str(tmp_path), checkpoint_id)
        except ValueError as exc:
            assert "checkpoint_id" in str(exc)
        else:
            raise AssertionError(f"checkpoint_id should be rejected: {checkpoint_id}")


def test_save_checkpoint_writes_json_and_load_checkpoint_round_trips(tmp_path) -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-83",
        phase="checkpointed",
        completed_phases=("initialized", "admitted"),
        pending_phases=("running",),
        metadata={"source": "store-test"},
    )

    saved = save_checkpoint(str(tmp_path), checkpoint)
    loaded = load_checkpoint(str(tmp_path), "checkpoint-1")

    assert saved["ok"] is True
    assert saved["checkpoint_id"] == "checkpoint-1"
    assert checkpoint_exists(str(tmp_path), "checkpoint-1") is True
    assert loaded["ok"] is True
    assert loaded["checkpoint"] == checkpoint
    with open(saved["path"], "r", encoding="utf-8") as handle:
        assert json.loads(handle.read()) == checkpoint


def test_save_checkpoint_rejects_invalid_payload(tmp_path) -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    checkpoint["package_id"] = ""

    result = save_checkpoint(str(tmp_path), checkpoint)

    assert result["ok"] is False
    assert "package_id is required" in result["errors"]
    assert checkpoint_exists(str(tmp_path), "checkpoint-1") is False


def test_save_checkpoint_rejects_traversal_checkpoint_id_from_payload(tmp_path) -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    checkpoint["checkpoint_id"] = "../escape"
    checkpoint["integrity_hash"] = compute_checkpoint_integrity_hash(checkpoint)

    result = save_checkpoint(str(tmp_path), checkpoint)

    assert result["ok"] is False
    assert "checkpoint_id must not contain path separators" in result["errors"]


def test_load_checkpoint_rejects_missing_invalid_json_and_invalid_payload(tmp_path) -> None:
    missing = load_checkpoint(str(tmp_path), "missing")
    assert missing["ok"] is False
    assert "checkpoint not found" in missing["errors"]

    store_dir = checkpoint_store_dir(str(tmp_path))
    os.makedirs(store_dir, exist_ok=True)

    invalid_json_path = checkpoint_path(str(tmp_path), "invalid-json")
    with open(invalid_json_path, "w", encoding="utf-8") as handle:
        handle.write("{")

    invalid_json = load_checkpoint(str(tmp_path), "invalid-json")
    assert invalid_json["ok"] is False
    assert invalid_json["errors"][0].startswith("invalid checkpoint file:")

    invalid_payload = build_operator_checkpoint(
        checkpoint_id="invalid-payload",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    invalid_payload["phase"] = "bad-phase"
    invalid_payload["integrity_hash"] = compute_checkpoint_integrity_hash(invalid_payload)
    with open(checkpoint_path(str(tmp_path), "invalid-payload"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(invalid_payload))

    loaded = load_checkpoint(str(tmp_path), "invalid-payload")
    assert loaded["ok"] is False
    assert "invalid phase: bad-phase" in loaded["errors"]


def test_delete_checkpoint_is_idempotent(tmp_path) -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    save_checkpoint(str(tmp_path), checkpoint)

    first = delete_checkpoint(str(tmp_path), "checkpoint-1")
    second = delete_checkpoint(str(tmp_path), "checkpoint-1")

    assert first["ok"] is True
    assert first["deleted"] is True
    assert second["ok"] is True
    assert second["deleted"] is False
    assert checkpoint_exists(str(tmp_path), "checkpoint-1") is False


def test_list_checkpoints_returns_valid_payloads_and_reports_invalid_files(tmp_path) -> None:
    checkpoint_a = build_operator_checkpoint(
        checkpoint_id="checkpoint-a",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    checkpoint_b = build_operator_checkpoint(
        checkpoint_id="checkpoint-b",
        operator_session_id="operator-session-1",
        package_id="package-83",
        phase="running",
    )
    save_checkpoint(str(tmp_path), checkpoint_b)
    save_checkpoint(str(tmp_path), checkpoint_a)

    with open(checkpoint_path(str(tmp_path), "broken"), "w", encoding="utf-8") as handle:
        handle.write("{")
    with open(os.path.join(checkpoint_store_dir(str(tmp_path)), "ignored.txt"), "w", encoding="utf-8") as handle:
        handle.write("ignored")

    records = list_checkpoints(str(tmp_path))

    valid_ids = [record["checkpoint_id"] for record in records if record.get("contract")]
    invalid = [record for record in records if record.get("ok") is False]

    assert valid_ids == ["checkpoint-a", "checkpoint-b"]
    assert len(invalid) == 1
    assert invalid[0]["checkpoint_id"] == "broken"
    assert invalid[0]["errors"][0].startswith("invalid checkpoint file:")


def test_load_checkpoints_for_identity_filters_by_session_and_package_in_store_order(tmp_path) -> None:
    checkpoint_a = build_operator_checkpoint(
        checkpoint_id="checkpoint-a",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    checkpoint_b = build_operator_checkpoint(
        checkpoint_id="checkpoint-b",
        operator_session_id="operator-session-2",
        package_id="package-83",
    )
    checkpoint_c = build_operator_checkpoint(
        checkpoint_id="checkpoint-c",
        operator_session_id="operator-session-1",
        package_id="package-84",
    )
    save_checkpoint(str(tmp_path), checkpoint_c)
    save_checkpoint(str(tmp_path), checkpoint_b)
    save_checkpoint(str(tmp_path), checkpoint_a)

    by_session = load_checkpoints_for_identity(str(tmp_path), operator_session_id="operator-session-1")
    by_package = load_checkpoints_for_identity(str(tmp_path), package_id="package-83")
    by_both = load_checkpoints_for_identity(
        str(tmp_path),
        operator_session_id="operator-session-1",
        package_id="package-83",
    )

    assert [checkpoint["checkpoint_id"] for checkpoint in by_session] == ["checkpoint-a", "checkpoint-c"]
    assert [checkpoint["checkpoint_id"] for checkpoint in by_package] == ["checkpoint-a", "checkpoint-b"]
    assert by_both == [checkpoint_a]


def test_load_checkpoints_for_identity_ignores_invalid_files_without_crashing(tmp_path) -> None:
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-a",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    save_checkpoint(str(tmp_path), checkpoint)
    with open(checkpoint_path(str(tmp_path), "broken"), "w", encoding="utf-8") as handle:
        handle.write("{")

    records = load_checkpoints_for_identity(str(tmp_path), operator_session_id="operator-session-1")

    assert records == [checkpoint]


def test_latest_checkpoint_for_identity_uses_last_matching_store_order(tmp_path) -> None:
    checkpoint_a = build_operator_checkpoint(
        checkpoint_id="checkpoint-a",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    checkpoint_b = build_operator_checkpoint(
        checkpoint_id="checkpoint-b",
        operator_session_id="operator-session-1",
        package_id="package-84",
    )
    checkpoint_c = build_operator_checkpoint(
        checkpoint_id="checkpoint-c",
        operator_session_id="operator-session-1",
        package_id="package-83",
    )
    save_checkpoint(str(tmp_path), checkpoint_c)
    save_checkpoint(str(tmp_path), checkpoint_b)
    save_checkpoint(str(tmp_path), checkpoint_a)

    latest = latest_checkpoint_for_identity(
        str(tmp_path),
        operator_session_id="operator-session-1",
        package_id="package-83",
    )

    assert latest["ok"] is True
    assert latest["found"] is True
    assert latest["checkpoint_id"] == "checkpoint-c"
    assert latest["checkpoint"] == checkpoint_c


def test_latest_checkpoint_for_identity_returns_structured_empty_result(tmp_path) -> None:
    latest = latest_checkpoint_for_identity(str(tmp_path), operator_session_id="missing")

    assert latest["ok"] is True
    assert latest["found"] is False
    assert latest["checkpoint_id"] == ""
    assert "checkpoint" not in latest
    assert latest["errors"] == []


def test_checkpoint_exists_returns_false_for_invalid_ids(tmp_path) -> None:
    assert checkpoint_exists(str(tmp_path), "../escape") is False
