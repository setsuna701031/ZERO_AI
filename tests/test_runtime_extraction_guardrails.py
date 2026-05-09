from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scheduler_and_agent_loop_still_exist_as_public_entrypoints() -> None:
    assert (REPO_ROOT / "core/tasks/scheduler.py").exists()
    assert (REPO_ROOT / "core/agent/agent_loop.py").exists()


def test_runtime_patch_inventory_tests_exist_before_extraction() -> None:
    required = [
        "tests/test_runtime_patch_tail_inventory.py",
        "tests/test_runtime_patch_tail_assignment_inventory.py",
        "tests/test_runtime_responsibility_inventory.py",
        "tests/test_runtime_boundary_candidates.py",
    ]

    for path in required:
        assert (REPO_ROOT / path).exists(), path


def test_extraction_must_preserve_default_runtime_regression_command() -> None:
    pytest_ini = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")

    assert "testpaths = tests" in pytest_ini