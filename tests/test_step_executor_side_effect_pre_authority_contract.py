from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any


SIDE_EFFECT_STEPS = {
    "write_file": "mutation",
    "append_file": "mutation",
    "workspace_append": "mutation",
    "apply_patch": "mutation",
    "apply_unified_diff": "mutation",
    "run_python": "execute",
    "command": "execute",
}

READ_ONLY_OR_NON_SIDE_EFFECT_STEPS = [
    "read_file",
    "verify",
    "verify_file",
    "respond",
    "final_answer",
    "llm",
    "llm_generate",
]

PUBLIC_INTERNAL_KEYS = {
    "evidence",
    "evidence_adapter",
    "evidence_events",
    "boundary",
    "boundary_fingerprint",
    "adapter_fingerprint",
    "hook",
    "hook_fingerprint",
}


def test_step_executor_classifies_side_effect_steps_for_pre_authority(
    tmp_path: Path,
) -> None:
    executor = _make_step_executor(tmp_path)

    for step_type, action_type in SIDE_EFFECT_STEPS.items():
        classification = executor._classify_step_authority_requirement(
            step_type,
            {"type": step_type},
        )

        assert classification["authority_required"] is True
        assert classification["action_type"] == action_type
        assert classification["step_type"] == step_type
        assert classification["authority_policy"] == "legacy_step_executor_policy"
        assert classification["sealed"] is False
        assert classification["status"] == "authority_unsealed"


def test_step_executor_does_not_classify_read_only_steps_as_mutation(
    tmp_path: Path,
) -> None:
    executor = _make_step_executor(tmp_path)

    for step_type in READ_ONLY_OR_NON_SIDE_EFFECT_STEPS:
        decision = executor._build_pre_execution_authority_decision(
            step_type,
            {"type": step_type},
            {},
            {},
        )

        assert decision["authority_phase"] == "pre_execution"
        assert decision["authority_required"] is False
        assert decision["action_type"] in {"read", "respond", "generate"}
        assert decision["action_type"] != "mutation"
        assert decision["decision"] == "read_only"
        assert decision["sealed"] is False


def test_side_effect_public_result_keeps_pre_authority_summary(
    tmp_path: Path,
) -> None:
    executor = _make_step_executor(tmp_path)

    result = executor.execute_step(
        {
            "type": "write_file",
            "path": "workspace/shared/pre_authority.txt",
            "content": "PRE_AUTHORITY",
        },
    )

    assert result["ok"] is True
    _assert_public_authority_decision(
        result,
        step_type="write_file",
        action_type="mutation",
    )
    _assert_no_public_internal_keys(result["authority_decision"])


def test_execute_authority_steps_are_legacy_unsealed_not_fake_sealed(
    tmp_path: Path,
) -> None:
    executor = _make_step_executor(tmp_path)

    for step_type in ("command", "run_python"):
        decision = executor._build_pre_execution_authority_decision(
            step_type,
            {"type": step_type},
            {},
            {},
        )

        assert decision["authority_phase"] == "pre_execution"
        assert decision["authority_required"] is True
        assert decision["action_type"] == "execute"
        assert decision["decision"] == "allowed_with_legacy_policy"
        assert decision["sealed"] is False
        assert decision["authority_source"] == "legacy_step_executor_policy"
        assert decision["status"] == "authority_unsealed"
        assert "legacy" in decision["reason"]


def test_attach_pre_execution_authority_preserves_public_shape(
    tmp_path: Path,
) -> None:
    executor = _make_step_executor(tmp_path)
    decision = executor._build_pre_execution_authority_decision(
        "append_file",
        {"type": "append_file"},
        {},
        {},
    )
    result = executor._attach_pre_execution_authority(
        {
            "ok": True,
            "step_type": "append_file",
            "runtime_execution_result": {"metadata": {}},
            "evidence_adapter": {"internal": True},
        },
        decision,
    )

    _assert_public_authority_decision(
        result,
        step_type="append_file",
        action_type="mutation",
    )
    assert result["runtime_execution_result"]["metadata"]["authority_decision"] == (
        result["authority_decision"]
    )
    assert result["authority_decision"]["authority_phase"] == "pre_execution"


def _make_step_executor(workspace_root: Path) -> Any:
    from core.runtime.step_executor import StepExecutor

    signature = inspect.signature(StepExecutor)
    kwargs: dict[str, Any] = {}

    if "workspace_root" in signature.parameters:
        kwargs["workspace_root"] = str(workspace_root)
    if "workspace_dir" in signature.parameters:
        kwargs["workspace_dir"] = str(workspace_root)
    if "runtime_store" in signature.parameters:
        kwargs["runtime_store"] = None
    if "tool_registry" in signature.parameters:
        kwargs["tool_registry"] = None
    if "llm_client" in signature.parameters:
        kwargs["llm_client"] = None
    if "debug" in signature.parameters:
        kwargs["debug"] = False

    return StepExecutor(**kwargs)


def _assert_public_authority_decision(
    result: dict[str, Any],
    *,
    step_type: str,
    action_type: str,
) -> None:
    decision = result.get("authority_decision")
    assert isinstance(decision, dict)
    assert decision["authority_phase"] == "pre_execution"
    assert decision["authority_required"] is True
    assert decision["action_type"] == action_type
    assert decision["step_type"] == step_type
    assert decision["decision"] == "allowed_with_legacy_policy"
    assert decision["authority_source"] == "legacy_step_executor_policy"
    assert decision["authority_policy"] == "legacy_step_executor_policy"
    assert decision["sealed"] is False
    assert decision["status"] == "authority_unsealed"
    assert decision["reason"] == "legacy_step_executor_policy_unsealed"

    runtime_payload = result.get("runtime_execution_result")
    assert isinstance(runtime_payload, dict)
    runtime_metadata = runtime_payload.get("metadata")
    assert isinstance(runtime_metadata, dict)
    assert runtime_metadata.get("authority_decision") == decision


def _assert_no_public_internal_keys(value: Any) -> None:
    if isinstance(value, dict):
        assert not (set(value) & PUBLIC_INTERNAL_KEYS)
        for item in value.values():
            _assert_no_public_internal_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_public_internal_keys(item)
