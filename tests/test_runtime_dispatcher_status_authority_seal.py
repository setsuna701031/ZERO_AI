from __future__ import annotations

import ast
from pathlib import Path

import core.runtime.runtime_dispatcher as runtime_dispatcher_module
from core.runtime.runtime_dispatcher import RuntimeDispatcher


import pytest

pytestmark = [pytest.mark.contract]

ROOT = Path(__file__).resolve().parents[1]

TARGET_FILES = (
    ROOT / "core" / "runtime" / "runtime_dispatcher.py",
    ROOT / "core" / "runtime" / "runtime_session_resume.py",
)


def _status_assignments(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    findings: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue

            slice_node = target.slice

            if not (
                isinstance(slice_node, ast.Constant)
                and slice_node.value == "status"
            ):
                continue

            segment = ast.get_source_segment(source, node) or ""
            findings.append(segment.strip())

    return findings


def test_dispatcher_and_resume_status_writes_are_canonicalized() -> None:
    dispatcher = _status_assignments(
        ROOT / "core/runtime/runtime_dispatcher.py"
    )

    resume = _status_assignments(
        ROOT / "core/runtime/runtime_session_resume.py"
    )

    assert any(
        'normalize_runtime_status("running")' in entry
        for entry in dispatcher
    )

    assert any(
        "normalize_runtime_status(runtime_status)"
        in entry
        for entry in resume
    )


def test_dispatcher_and_resume_use_canonical_status_helper() -> None:
    dispatcher_source = (
        ROOT / "core/runtime/runtime_dispatcher.py"
    ).read_text(encoding="utf-8-sig")

    resume_source = (
        ROOT / "core/runtime/runtime_session_resume.py"
    ).read_text(encoding="utf-8-sig")

    assert "from core.runtime.runtime_status import normalize_runtime_status" in dispatcher_source
    assert "_canonical_runtime_status" not in dispatcher_source
    assert "from core.runtime.runtime_status import normalize_runtime_status" in resume_source
    assert "_canonical_runtime_status" not in resume_source


def test_dispatcher_status_projection_delegates_to_canonical_normalizer(monkeypatch) -> None:
    calls: list[str] = []

    def canonical_status(value):
        calls.append(value)
        return "canonical-running"

    monkeypatch.setattr(runtime_dispatcher_module, "normalize_runtime_status", canonical_status)

    next_task = RuntimeDispatcher._next_task(
        {"status": "queued"},
        {"task": {"status": "active"}},
        {"current_step": 1},
    )
    replanned = RuntimeDispatcher._append_replan_task(
        {"status": "failed", "steps": []},
        [{"id": "repair"}],
        {"current_step": 1},
    )

    assert next_task["status"] == "canonical-running"
    assert replanned["status"] == "canonical-running"
    assert calls == ["running", "running"]
