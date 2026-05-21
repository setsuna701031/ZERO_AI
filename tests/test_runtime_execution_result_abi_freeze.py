from __future__ import annotations

from core.runtime.runtime_execution_result import (
    RuntimeExecutionResult,
    build_runtime_execution_result,
)


def _payload_from(mapping: dict) -> dict:
    return RuntimeExecutionResult.from_runtime_mapping(mapping).to_dict()


def test_legacy_ok_payload_executes_without_failure() -> None:
    payload = _payload_from({"ok": True})

    assert payload["executed"] is True
    assert payload["failed"] is False


def test_blocked_error_type_is_blocked_without_failure() -> None:
    payload = _payload_from({"ok": False, "error_type": "blocked"})

    assert payload["blocked"] is True
    assert payload["failed"] is False


def test_verification_ok_sets_verification_passed() -> None:
    payload = _payload_from({"ok": True, "verification": {"ok": True}})

    assert payload["verification_passed"] is True


def test_changed_files_sync_to_impacted_files() -> None:
    payload = _payload_from({"ok": True, "changed_files": ["core/runtime/a.py"]})

    assert payload["changed_files"] == ["core/runtime/a.py"]
    assert payload["impacted_files"] == ["core/runtime/a.py"]


def test_metadata_changed_files_sync_to_impacted_files() -> None:
    payload = _payload_from(
        {
            "ok": True,
            "metadata": {"changed_files": ["core/runtime/from_metadata.py"]},
        }
    )

    assert payload["changed_files"] == ["core/runtime/from_metadata.py"]
    assert payload["impacted_files"] == ["core/runtime/from_metadata.py"]


def test_evidence_mutation_summary_impacted_files_sync() -> None:
    payload = _payload_from(
        {
            "ok": True,
            "evidence": {
                "mutation_summary": {
                    "impacted_files": ["core/runtime/from_evidence.py"],
                },
            },
        }
    )

    assert payload["changed_files"] == ["core/runtime/from_evidence.py"]
    assert payload["impacted_files"] == ["core/runtime/from_evidence.py"]


def test_target_path_syncs_to_impacted_files() -> None:
    payload = _payload_from({"ok": True, "target_path": "core/runtime/target.py"})

    assert payload["changed_files"] == ["core/runtime/target.py"]
    assert payload["impacted_files"] == ["core/runtime/target.py"]


def test_operations_target_path_syncs_to_impacted_files() -> None:
    payload = _payload_from(
        {
            "ok": True,
            "operations": [
                {"op_type": "write_file", "target_path": "core/runtime/op.py"},
            ],
        }
    )

    assert payload["changed_files"] == ["core/runtime/op.py"]
    assert payload["impacted_files"] == ["core/runtime/op.py"]


def test_build_payload_contains_runtime_execution_result_abi_fields() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "changed_files": ["core/runtime/result.py"],
            "rollback_metadata": {"restore_available": True},
            "metadata": {"summary": "abi freeze"},
        }
    )

    for key in (
        "ok",
        "executed",
        "blocked",
        "failed",
        "verification_passed",
        "evidence",
        "changed_files",
        "impacted_files",
        "rollback_metadata",
        "rollback_snapshot",
        "metadata",
    ):
        assert key in payload

    assert "mutation_summary" in payload["evidence"]
    assert payload["changed_files"] == ["core/runtime/result.py"]
    assert payload["impacted_files"] == ["core/runtime/result.py"]
    assert payload["rollback_snapshot"] == {"restore_available": True}
