from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "runtime" / "task_runner.py"
REPORT = ROOT / "taskrunner_legacy_reference_audit_report.txt"

CANDIDATES = [
    "_stage3b_run_task",
    "_stage3b_run_task_tick",
    "_taskrunner_consolidated_run_task",
    "_taskrunner_consolidated_run_task_tick",
    "_zero_stage3b_run_task_tick_v2",
    "_zero_stage3b_run_task_tick_v3",
    "_zero_stage3b_run_task_tick_v4",
    "_zero_stage3b_run_task_v2",
    "_zero_stage3b_run_task_v3",
    "_zero_stage3b_run_task_v4",
    "_zero_v702_task_runner_run_one_step",
    "_zero_v800_task_runner_run_one_step",
    "_zero_v801_task_runner_finalize_public_result",
    "_zero_v810_finalize_public_result",
    "_zero_v810_persist_step_result_to_runtime_state",
    "_zero_v810_taskrunner_init",
]

SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "__pycache__",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "workspace",
    "htmlcov",
    "dist",
    "build",
}

TEXT_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".ps1",
    ".bat",
    ".sh",
}


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def _iter_files() -> Iterable[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if _is_skipped(path):
            continue
        if not _is_text_file(path):
            continue
        yield path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _line_hits(path: Path, text: str, needle: str) -> List[Tuple[int, str]]:
    hits: List[Tuple[int, str]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            hits.append((index, line.strip()))
    return hits


def _is_definition_line(candidate: str, line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith(f"def {candidate}(")
        or stripped.startswith(f"async def {candidate}(")
        or stripped.startswith(f"{candidate} =")
        or stripped.startswith(f"{candidate}:")
    )


def _bucket_for_path(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith("tests/") or "/tests/" in rel:
        return "test"
    if rel.startswith("tools/") or "/tools/" in rel:
        return "tool"
    if rel == REPORT.name:
        return "self_report"
    return "production"


def _classify_candidate(
    candidate: str,
    refs: List[Dict[str, object]],
) -> str:
    non_definition_refs = [ref for ref in refs if not ref["is_definition"]]
    if not non_definition_refs:
        return "A"

    buckets = {str(ref["bucket"]) for ref in non_definition_refs}

    if buckets <= {"test"}:
        return "B"

    if buckets <= {"test", "tool", "self_report"}:
        return "B"

    return "C"


def _explanation(label: str) -> str:
    if label == "A":
        return "A = no non-definition references found; deletion candidate after targeted tests"
    if label == "B":
        return "B = only tests/tools references found; update references before deletion"
    return "C = production reference exists; do not delete yet"


def _find_references() -> Dict[str, List[Dict[str, object]]]:
    refs: Dict[str, List[Dict[str, object]]] = {candidate: [] for candidate in CANDIDATES}

    for path in _iter_files():
        try:
            text = _read_text(path)
        except Exception as exc:
            rel = path.relative_to(ROOT).as_posix()
            for candidate in CANDIDATES:
                refs[candidate].append(
                    {
                        "path": rel,
                        "line": 0,
                        "text": f"<read_error: {exc}>",
                        "bucket": "read_error",
                        "is_definition": False,
                    }
                )
            continue

        for candidate in CANDIDATES:
            if candidate not in text:
                continue
            for line_no, line in _line_hits(path, text, candidate):
                rel = path.relative_to(ROOT).as_posix()
                refs[candidate].append(
                    {
                        "path": rel,
                        "line": line_no,
                        "text": line,
                        "bucket": _bucket_for_path(path),
                        "is_definition": _is_definition_line(candidate, line),
                    }
                )

    return refs


def _write_report(refs: Dict[str, List[Dict[str, object]]]) -> None:
    lines: List[str] = []

    lines.append("TaskRunner Legacy Reference Audit")
    lines.append("")
    lines.append(f"repo_root: {ROOT}")
    lines.append(f"target: {TARGET.relative_to(ROOT)}")
    lines.append(f"candidates: {len(CANDIDATES)}")
    lines.append("")

    groups = {"A": [], "B": [], "C": []}

    for candidate in CANDIDATES:
        label = _classify_candidate(candidate, refs[candidate])
        groups[label].append(candidate)

    lines.append("=" * 80)
    lines.append("Summary")
    lines.append("=" * 80)
    lines.append(f"A_no_non_definition_references: {len(groups['A'])}")
    lines.append(f"B_tests_or_tools_only: {len(groups['B'])}")
    lines.append(f"C_production_references_exist: {len(groups['C'])}")
    lines.append("")

    for label in ("A", "B", "C"):
        lines.append(f"{label}: {_explanation(label)}")
        for candidate in groups[label]:
            lines.append(f"- {candidate}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("Candidate Details")
    lines.append("=" * 80)

    for candidate in CANDIDATES:
        candidate_refs = refs[candidate]
        label = _classify_candidate(candidate, candidate_refs)
        non_definition_refs = [ref for ref in candidate_refs if not ref["is_definition"]]

        lines.append("")
        lines.append(f"- {candidate}")
        lines.append(f"  classification: {label}")
        lines.append(f"  explanation: {_explanation(label)}")
        lines.append(f"  total_refs: {len(candidate_refs)}")
        lines.append(f"  non_definition_refs: {len(non_definition_refs)}")

        if not candidate_refs:
            lines.append("  references:")
            lines.append("    - <none>")
            continue

        lines.append("  references:")
        for ref in candidate_refs:
            marker = "definition" if ref["is_definition"] else "reference"
            lines.append(
                f"    - {ref['path']}:{ref['line']} "
                f"[{ref['bucket']}; {marker}] {ref['text']}"
            )

    lines.append("")
    lines.append("=" * 80)
    lines.append("Suggested Package 35 Plan")
    lines.append("=" * 80)
    lines.append("- Remove only A-class candidates first.")
    lines.append("- Do not remove B-class candidates until tests/tools references are updated or confirmed archival.")
    lines.append("- Do not remove C-class candidates.")
    lines.append("- After cleanup, run targeted py_compile and TaskRunner/AER seal tests.")
    lines.append("")

    lines.append("=" * 80)
    lines.append("Validation")
    lines.append("=" * 80)
    lines.append("- This package only scans references. No runtime behavior was changed.")
    lines.append("- Long validation remains local-only.")
    lines.append("- Non-mainline issues must be reported explicitly.")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    refs = _find_references()
    _write_report(refs)
    print(str(REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())