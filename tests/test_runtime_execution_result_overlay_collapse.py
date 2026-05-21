from __future__ import annotations

from dataclasses import is_dataclass

from core.runtime.runtime_execution_result import (
    RuntimeExecutionResult,
    attach_runtime_execution_result,
    build_runtime_execution_result,
)


LEGACY_INPUT = {
    "ok": True,
    "verification": {"ok": True},
    "changed_files": ["core/runtime/demo.py"],
    "rollback_metadata": {"restore_available": True},
}


MUTATION_LIKE_INPUT = {
    "ok": True,
    "operations": [{"target_path": "project/example.py"}],
    "metadata": {
        "evidence": {
            "mutation_summary": {
                "impacted_files": ["project/example.py"],
            },
        },
    },
}


def _assert_canonical(payload: dict, expected_files: list[str]) -> None:
    for key in (
        "ok",
        "executed",
        "blocked",
        "failed",
        "verification_passed",
        "metadata",
        "evidence",
        "changed_files",
        "impacted_files",
        "rollback_metadata",
        "rollback_snapshot",
    ):
        assert key in payload

    assert payload["executed"] is True
    assert payload["blocked"] is False
    assert payload["failed"] is False
    assert payload["verification_passed"] is True
    assert payload["changed_files"] == expected_files
    assert payload["impacted_files"] == expected_files
    assert "mutation_summary" in payload["evidence"]


def test_runtime_execution_result_to_dict_uses_single_canonical_path() -> None:
    assert is_dataclass(RuntimeExecutionResult)

    payload = RuntimeExecutionResult.from_runtime_mapping(LEGACY_INPUT).to_dict()

    _assert_canonical(payload, ["core/runtime/demo.py"])


def test_from_runtime_mapping_supports_legacy_call_shapes() -> None:
    call_results = [
        RuntimeExecutionResult.from_runtime_mapping(mapping=LEGACY_INPUT),
        RuntimeExecutionResult.from_runtime_mapping(execution_result=LEGACY_INPUT),
        RuntimeExecutionResult.from_runtime_mapping(payload=LEGACY_INPUT),
        RuntimeExecutionResult.from_runtime_mapping(result=LEGACY_INPUT),
        RuntimeExecutionResult.from_runtime_mapping(
            result=LEGACY_INPUT,
            step={"type": "write_file"},
            task={"task_id": "task-1"},
        ),
        RuntimeExecutionResult.from_runtime_mapping(
            ok=True,
            verification={"ok": True},
            changed_files=["core/runtime/demo.py"],
            rollback_metadata={"restore_available": True},
        ),
    ]

    for result in call_results:
        assert isinstance(result, RuntimeExecutionResult)
        _assert_canonical(result.to_dict(), ["core/runtime/demo.py"])

    assert call_results[4].task_id == "task-1"
    assert call_results[4].step_type == "write_file"


def test_from_governed_mutation_result_still_exists() -> None:
    result = RuntimeExecutionResult.from_governed_mutation_result(MUTATION_LIKE_INPUT)

    assert isinstance(result, RuntimeExecutionResult)
    _assert_canonical(result.to_dict(), ["project/example.py"])


def test_build_runtime_execution_result_outputs_canonical_fields() -> None:
    payload = build_runtime_execution_result(LEGACY_INPUT)

    _assert_canonical(payload, ["core/runtime/demo.py"])
    assert payload["rollback_snapshot"] == {"restore_available": True}


def test_build_runtime_execution_result_handles_mutation_like_input() -> None:
    payload = build_runtime_execution_result(MUTATION_LIKE_INPUT)

    _assert_canonical(payload, ["project/example.py"])


def test_attach_runtime_execution_result_preserves_payload_identity_and_keys() -> None:
    payload = {
        "ok": True,
        "custom": "keep-me",
        "changed_files": ["core/runtime/demo.py"],
    }

    attached = attach_runtime_execution_result(payload)

    assert attached is payload
    assert attached["custom"] == "keep-me"
    assert "runtime_execution_result" in attached
    _assert_canonical(attached["runtime_execution_result"], ["core/runtime/demo.py"])
