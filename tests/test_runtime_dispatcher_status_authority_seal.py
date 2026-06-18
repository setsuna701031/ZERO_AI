from __future__ import annotations

import ast
from pathlib import Path


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
        '_canonical_runtime_status("running")' in entry
        for entry in dispatcher
    )

    assert any(
        "_canonical_runtime_status(runtime_status)"
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

    assert "_canonical_runtime_status" in dispatcher_source
    assert "_canonical_runtime_status" in resume_source