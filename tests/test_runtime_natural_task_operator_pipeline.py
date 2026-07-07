from __future__ import annotations

import inspect
from pathlib import Path

from core.runtime import runtime_natural_task_operator_pipeline as pipeline
from core.runtime.runtime_natural_task_operator_pipeline import (
    RUNTIME_NATURAL_TASK_OPERATOR_PIPELINE_SCHEMA,
    run_natural_task_operator_pipeline,
)
from core.runtime.runtime_operator_config import RuntimeOperatorConfig


def _config(tmp_path: Path) -> RuntimeOperatorConfig:
    return RuntimeOperatorConfig(
        checkpoint_path=tmp_path / "checkpoint.json",
        runtime_mode="controlled",
        max_tick_limit=3,
        emergency_stop_enabled=True,
    )


def test_pipeline_generates_package_and_runs_operator_service(tmp_path: Path) -> None:
    result = run_natural_task_operator_pipeline(
        "create a file and run validation",
        _config(tmp_path),
        target_root=".",
        explicit_manual_mode=True,
    )

    assert result["schema"] == RUNTIME_NATURAL_TASK_OPERATOR_PIPELINE_SCHEMA
    assert result["ok"] is True
    assert result["package_generated"] is True
    assert result["package"]["schema"] == "zero.runtime.operator_package.v1"
    assert result["requested_mode"] == "controlled"
    assert result["package_dispatch_bound"] is True
    assert result["operator_result"]["ok"] is True


def test_pipeline_preserves_controlled_safety_flags(tmp_path: Path) -> None:
    result = run_natural_task_operator_pipeline(
        "update docs without bypassing validation",
        _config(tmp_path),
        target_root="E:/zero_ai",
        explicit_manual_mode=True,
    )

    package = result["package"]

    assert package["validation_required"] is True
    assert package["rollback_required"] is True
    assert package["requested_mode"] == "controlled"
    assert result["validation_passed"] is True
    assert result["rollback_available"] is True
    assert result["commit_allowed"] is True


def test_pipeline_exposes_lifecycle_chain(tmp_path: Path) -> None:
    result = run_natural_task_operator_pipeline(
        "prepare a deterministic package",
        _config(tmp_path),
        explicit_manual_mode=True,
    )

    chain = result["chain"]

    assert chain["intake"] in {"accepted", "rejected"}
    assert chain["gate"] in {"opened", "unknown", "rejected"}
    assert chain["dispatch"] in {"dispatch_bound", "unknown", "rejected"}
    assert "executor" in chain
    assert "validation" in chain
    assert "closure" in chain


def test_pipeline_has_no_direct_console_or_shell_bridge() -> None:
    source = inspect.getsource(pipeline)
    forbidden_terms = (
        "subprocess",
        "open(",
        "Path(",
        "os.",
        "requests",
        "zero_operator_console",
        "run_goal(",
        "commit(",
        "git ",
    )

    for term in forbidden_terms:
        assert term not in source


def test_public_exports_are_stable() -> None:
    assert pipeline.__all__ == [
        "RUNTIME_NATURAL_TASK_OPERATOR_PIPELINE_SCHEMA",
        "run_natural_task_operator_pipeline",
    ]
