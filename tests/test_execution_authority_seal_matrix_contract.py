from __future__ import annotations

from pathlib import Path


MATRIX_PATH = Path("docs/execution_authority_seal_matrix.md")

REQUIRED_SECTIONS = [
    "Current Authority Model",
    "Entry Point Matrix",
    "Known Bypass Risks",
    "Required P0 Contracts",
    "Recommended Next Implementation Package",
    "What NOT To Change Yet",
]

P0_ENTRY_POINTS = [
    "StepExecutor.execute_step",
    "StepExecutor.execute_steps",
    "write_file",
    "append_file",
    "apply_patch",
    "apply_unified_diff",
    "run_python",
    "command",
    "TaskRunner._run_one_step",
    "rollback",
    "retry",
    "TaskRuntime read-only command gate",
    "Scheduler.tick",
    "Scheduler.run_one_step",
    "scheduler execution gateway",
    "AgentLoop.run",
    "AgentLoop tool path",
    "AgentLoop repo-edit",
    "AgentLoop code-chain",
    "governed mutation runtime",
    "repair transaction execution bridge",
    "recovery commit gate",
    "ZeroSystem.tick",
    "app.py task run/tick command",
    "runtime_public_surface.py",
]

REQUIRED_POSITIONING = [
    "Execution authority is not sealed yet",
    "authority metadata is not enforcement",
    "inventory-only contract",
    "pre-execution authority",
    "public output sanitizer",
    "recovery ABI",
]


def test_execution_authority_seal_matrix_document_exists() -> None:
    assert MATRIX_PATH.is_file()


def test_execution_authority_seal_matrix_has_required_sections() -> None:
    text = _matrix_text()

    missing = [
        section for section in REQUIRED_SECTIONS if f"## {section}" not in text
    ]

    assert missing == []


def test_execution_authority_seal_matrix_lists_p0_entry_points() -> None:
    text = _normalized_matrix_text()

    missing = [
        entry_point
        for entry_point in P0_ENTRY_POINTS
        if _normalize_text(entry_point) not in text
    ]

    assert missing == []


def test_execution_authority_seal_matrix_declares_inventory_only_scope() -> None:
    text = _normalized_matrix_text()

    missing = [
        phrase
        for phrase in REQUIRED_POSITIONING
        if _normalize_text(phrase) not in text
    ]

    assert missing == []
    assert "sanitizer do not mix into this package" in text
    assert "recovery abi do not mix into this package" in text


def _matrix_text() -> str:
    return MATRIX_PATH.read_text(encoding="utf-8")


def _normalized_matrix_text() -> str:
    return _normalize_text(_matrix_text())


def _normalize_text(value: str) -> str:
    text = value.lower()
    for marker in ("`", "*", "_", "-", "/", "\n", "."):
        text = text.replace(marker, " ")
    return " ".join(text.split())
