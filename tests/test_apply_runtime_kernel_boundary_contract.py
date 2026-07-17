from __future__ import annotations

import re
from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




STEP_EXECUTOR_PATH = Path("core/runtime/step_executor.py")


def _source() -> str:
    return STEP_EXECUTOR_PATH.read_text(encoding="utf-8")


def _function_body(source: str, function_name: str) -> str:
    marker = f"def {function_name}("
    start = source.find(marker)
    assert start >= 0

    next_def = source.find("\n    def ", start + 1)
    return source[start : next_def if next_def >= 0 else len(source)]


def test_apply_runtime_has_single_registered_override_pair() -> None:
    source = _source()

    assert source.count('self.register_handler("apply_patch",') == 2
    assert source.count('self.register_handler("apply_unified_diff",') == 2

    assert source.count(
        'self.register_handler("apply_patch", _zero_v734_handle_apply_step.__get__(self, StepExecutor))'
    ) == 1
    assert source.count(
        'self.register_handler("apply_unified_diff", _zero_v734_handle_apply_step.__get__(self, StepExecutor))'
    ) == 1


def test_apply_runtime_keeps_single_original_handler_reference() -> None:
    source = _source()

    assert source.count(
        "_ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP = StepExecutor._handle_apply_unified_diff_step"
    ) == 1
    assert source.count("_ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP(") >= 1


def test_apply_runtime_does_not_define_extra_apply_handler_generations() -> None:
    source = _source()

    forbidden_patterns = [
        r"def\s+_zero_v736_.*apply",
        r"def\s+_zero_v737_.*apply",
        r"def\s+_zero_v738_.*apply",
        r"def\s+_zero_v739_.*apply",
        r"def\s+_zero_v740_.*apply",
        r"_ZERO_V736_ORIGINAL_APPLY",
        r"_ZERO_V737_ORIGINAL_APPLY",
        r"_ZERO_V738_ORIGINAL_APPLY",
        r"_ZERO_V739_ORIGINAL_APPLY",
        r"_ZERO_V740_ORIGINAL_APPLY",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, source) is None


def test_apply_runtime_transaction_helpers_remain_single_core_api_set() -> None:
    source = _source()

    required_singleton_defs = [
        "def _build_apply_patch_transaction(",
        "def _mark_apply_patch_transaction(",
        "def _run_apply_patch_verify_boundary(",
        "def _build_apply_patch_rollback_result(",
        "def _verify_apply_patch_target(",
        "def _rollback_apply_patch_target(",
    ]

    for symbol in required_singleton_defs:
        assert source.count(symbol) == 1


def test_apply_runtime_write_path_uses_governed_write_boundary() -> None:
    source = _source()
    apply_body = _function_body(source, "_handle_apply_unified_diff_step")

    assert "self._governed_write_text(" in apply_body
    assert "provenance=" in apply_body
    assert "metadata=" in apply_body

    direct_apply_writes = [
        "target_path.write_text(",
        "full_target_path.write_text(",
        "Path(full_target_path).write_text(",
    ]

    for token in direct_apply_writes:
        assert token not in apply_body


def test_apply_runtime_has_single_rollback_helper() -> None:
    source = _source()
    rollback_body = _function_body(source, "_rollback_apply_patch_target")

    assert source.count("def _rollback_apply_patch_target(") == 1
    assert "backup_path" in rollback_body
    assert "full_target_path" in rollback_body
    assert "return True" in rollback_body
    assert "return False" in rollback_body


def test_apply_runtime_multi_patch_wraps_not_replaces_original_runtime() -> None:
    source = _source()

    assert "def _zero_v735_atomic_multi_patch_step(" in source
    assert "patch_result = _ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP(" in source
    assert "def _zero_v734_handle_apply_step(" in source
    assert "return _zero_v735_atomic_multi_patch_step(" in source