from __future__ import annotations

"""Stage-1 consolidation guard for ZERO_PATCH_* runtime hotfixes.

Run from repo root. This script intentionally does NOT rewrite runtime logic yet.
It freezes the currently-green hotfix state, classifies every ZERO_PATCH_* block,
and writes a consolidation plan that can be used for the next mechanical rewrite.

Why stage-1 exists:
- The current repo has many monkey patches layered on top of one another.
- Removing them before the tests are frozen risks losing the proven green state.
- This script creates an auditable snapshot and makes the next consolidation step deterministic.
"""

import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

ROOT = Path.cwd()
REPORT_DIR = ROOT / "docs" / "architecture" / "runtime_patch_consolidation"
BACKUP_DIR = ROOT / ".zero_patch_consolidation_backup"
TARGET_GLOBS = ["core/**/*.py"]
TEST_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
]

PATCH_RE = re.compile(r"ZERO_PATCH_[A-Z0-9_]+")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\.]*\s*=\s*_zero", re.MULTILINE)
DEF_RE = re.compile(r"^def\s+(_zero[^\(]*)", re.MULTILINE)
CLASS_RE = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


@dataclass
class PatchHit:
    path: str
    line: int
    marker: str
    category: str


def iter_core_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in TARGET_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def category_for(path: Path, marker: str) -> str:
    text = f"{path.as_posix()} {marker}".lower()
    if "authority" in text or "gate" in text:
        return "authority"
    if "scheduler" in text:
        return "scheduler"
    if "taskrunner" in text or "task_runner" in text:
        return "task_runner"
    if "step_executor" in text:
        return "step_executor"
    if "recovery" in text:
        return "recovery"
    if "replay" in text or "evidence" in text:
        return "replay_evidence"
    if "operator" in text or "session" in text or "checkpoint" in text:
        return "operator_session"
    return "misc"


def scan() -> list[PatchHit]:
    hits: list[PatchHit] = []
    for path in iter_core_files():
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, start=1):
            for match in PATCH_RE.finditer(line):
                marker = match.group(0)
                hits.append(PatchHit(str(path.relative_to(ROOT)), i, marker, category_for(path, marker)))
    return hits


def backup_touched_files(hits: list[PatchHit]) -> None:
    BACKUP_DIR.mkdir(exist_ok=True)
    for rel in sorted({hit.path for hit in hits}):
        src = ROOT / rel
        dst = BACKUP_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def run_cmd(cmd: list[str]) -> dict[str, object]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {"cmd": cmd, "returncode": proc.returncode, "output": proc.stdout[-12000:]}


def build_report(hits: list[PatchHit], test_results: list[dict[str, object]]) -> str:
    by_cat: dict[str, list[PatchHit]] = defaultdict(list)
    by_file: dict[str, list[PatchHit]] = defaultdict(list)
    for hit in hits:
        by_cat[hit.category].append(hit)
        by_file[hit.path].append(hit)

    lines: list[str] = []
    lines.append("# Runtime Patch Consolidation Stage 1")
    lines.append("")
    lines.append("## Current status")
    lines.append("")
    lines.append(f"- ZERO_PATCH markers: {len(hits)}")
    lines.append(f"- touched files: {len(by_file)}")
    lines.append(f"- backup directory: `{BACKUP_DIR}`")
    lines.append("")
    lines.append("## Category map")
    lines.append("")
    for category, items in sorted(by_cat.items()):
        lines.append(f"- `{category}`: {len(items)}")
    lines.append("")
    lines.append("## File map")
    lines.append("")
    for path, items in sorted(by_file.items()):
        lines.append(f"### `{path}`")
        for item in items:
            lines.append(f"- L{item.line}: `{item.marker}` ({item.category})")
        lines.append("")

    lines.append("## Required consolidation order")
    lines.append("")
    lines.append("1. Freeze current green state and keep `.zero_patch_consolidation_backup/` until all tests pass.")
    lines.append("2. Consolidate `PersistentOperatorRuntime` first: session readback, failed checkpoint, recovery payload, replay evidence.")
    lines.append("3. Consolidate `Scheduler` and `TaskRunner` authority handoff next.")
    lines.append("4. Consolidate `StepExecutor` entry authority after runner/scheduler are stable.")
    lines.append("5. Consolidate `execution_authority.py` compatibility policy last.")
    lines.append("6. Remove every `ZERO_PATCH_*`, `_zero_patch_*`, and runtime `Class.method = wrapped` assignment.")
    lines.append("")
    lines.append("## Verification results")
    lines.append("")
    for result in test_results:
        status = "PASS" if result["returncode"] == 0 else "FAIL"
        lines.append(f"### {status}: `{' '.join(result['cmd'])}`")
        lines.append("```text")
        lines.append(str(result["output"]).strip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    hits = scan()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    backup_touched_files(hits)

    test_results = [run_cmd(cmd) for cmd in TEST_COMMANDS]

    report = build_report(hits, test_results)
    (REPORT_DIR / "stage1_report.md").write_text(report, encoding="utf-8")
    (REPORT_DIR / "stage1_patch_inventory.json").write_text(
        json.dumps([asdict(hit) for hit in hits], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (REPORT_DIR / "stage1_test_results.json").write_text(
        json.dumps(test_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"ZERO_PATCH markers: {len(hits)}")
    print(f"report: {REPORT_DIR / 'stage1_report.md'}")
    print(f"inventory: {REPORT_DIR / 'stage1_patch_inventory.json'}")
    print(f"backup: {BACKUP_DIR}")
    failed = [r for r in test_results if r["returncode"] != 0]
    if failed:
        print(f"verification failed: {len(failed)} command(s)")
        return 1
    print("verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
