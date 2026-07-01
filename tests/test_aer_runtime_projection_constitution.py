from __future__ import annotations

from pathlib import Path


DOC = Path("docs/aer_runtime_projection_constitution.md")


def test_runtime_projection_constitution_doc_exists() -> None:
    assert DOC.exists()


def test_runtime_projection_constitution_defines_required_rules() -> None:
    text = DOC.read_text(encoding="utf-8")

    required_sections = (
        "## Core Principle",
        "## Success Projection Rule",
        "## Error Projection Rule",
        "## Fixed Contract Rule",
        "## Object Independence Rule",
        "## Allowed vs Forbidden",
        "## Future Layer Requirement",
    )
    for section in required_sections:
        assert section in text


def test_runtime_projection_constitution_seals_required_terms() -> None:
    text = DOC.read_text(encoding="utf-8")

    required_terms = (
        "runtime_checkpoint",
        "runtime_recovery_marker",
        "invalid upstream contract",
        "no passthrough",
        "no recursive wrapper leak",
        "copied upstream errors",
        "source_valid",
        "source_outcome",
    )
    for term in required_terms:
        assert term in text


def test_runtime_projection_constitution_extends_to_future_runtime_layers() -> None:
    text = DOC.read_text(encoding="utf-8")

    for layer in ("Snapshot", "Replay", "Journal", "Persistence", "Audit"):
        assert layer in text
