from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




STEP_EXECUTOR_PATH = Path("core/runtime/step_executor.py")


def _source() -> str:
    return STEP_EXECUTOR_PATH.read_text(encoding="utf-8")


def test_apply_patch_and_apply_unified_diff_share_one_registered_handler() -> None:
    source = _source()

    assert 'self.register_handler("apply_unified_diff", _zero_v734_handle_apply_step.__get__(self, StepExecutor))' in source
    assert 'self.register_handler("apply_patch", _zero_v734_handle_apply_step.__get__(self, StepExecutor))' in source

    assert source.count('self.register_handler("apply_patch",') == 2
    assert source.count('self.register_handler("apply_unified_diff",') == 2


def test_apply_runtime_original_handler_is_preserved_as_single_baseline() -> None:
    source = _source()

    assert source.count("_ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP = StepExecutor._handle_apply_unified_diff_step") == 1
    assert "_ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP(" in source


def test_apply_runtime_does_not_add_new_apply_handler_override_after_v735() -> None:
    source = _source()

    forbidden_apply_override_tokens = [
        "_zero_v736_handle_apply",
        "_zero_v737_handle_apply",
        "_zero_v738_handle_apply",
        "_zero_v739_handle_apply",
        "_zero_v740_handle_apply",
        "_zero_v736_atomic_multi_patch",
        "_zero_v737_atomic_multi_patch",
        "_zero_v738_atomic_multi_patch",
        "_zero_v739_atomic_multi_patch",
        "_zero_v740_atomic_multi_patch",
    ]

    for token in forbidden_apply_override_tokens:
        assert token not in source


def test_v735_atomic_multi_patch_wraps_original_apply_handler() -> None:
    source = _source()

    assert "_zero_v735_atomic_multi_patch_step" in source
    assert "patch_result = _ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP(" in source


def test_step_executor_apply_runtime_kernel_is_explicitly_named() -> None:
    source = _source()

    required_symbols = [
        "_handle_apply_unified_diff_step",
        "_rollback_apply_patch_target",
        "_build_apply_patch_transaction",
        "_run_apply_patch_verify_boundary",
        "_build_apply_patch_rollback_result",
        "_verify_apply_patch_target",
        "_zero_v734_handle_apply_step",
        "_zero_v735_atomic_multi_patch_step",
    ]

    for symbol in required_symbols:
        assert symbol in source