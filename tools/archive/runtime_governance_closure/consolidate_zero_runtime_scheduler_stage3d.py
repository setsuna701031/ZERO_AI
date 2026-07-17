from __future__ import annotations

"""Runtime Patch Consolidation Stage 3D - Scheduler marker retirement.

This stage is intentionally conservative:
- It only retires the remaining ZERO_PATCH_ markers in TaskRunner/Scheduler.
- It does not delete behavioural compatibility code yet.
- It verifies the known green contract set and compileall.
- On verification failure it restores the exact pre-run files.

Stage 4 should remove the remaining _zero_* wrapper code and replace it with
first-class methods once the marker debt has been eliminated safely.
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
TARGETS = [
    ROOT / "core" / "runtime" / "task_runner.py",
    ROOT / "core" / "tasks" / "scheduler.py",
]
REPORT_DIR = ROOT / "docs" / "architecture" / "runtime_patch_consolidation"
BACKUP_DIR = ROOT / ".zero_patch_consolidation_backup" / "stage3d_scheduler"

VERIFY = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
    [sys.executable, "-m", "compileall", "core"],
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def count_markers(paths: list[Path]) -> dict[str, int]:
    return {str(path.relative_to(ROOT)): read(path).count("ZERO_PATCH_") for path in paths if path.exists()}


def backup_targets() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for path in TARGETS:
        if path.exists():
            dest = BACKUP_DIR / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)


def restore_targets() -> None:
    for path in TARGETS:
        src = BACKUP_DIR / path.relative_to(ROOT)
        if src.exists():
            shutil.copy2(src, path)


def retire_markers() -> dict[str, int]:
    changed: dict[str, int] = {}
    for path in TARGETS:
        if not path.exists():
            continue
        text = read(path)
        before = text.count("ZERO_PATCH_")
        if before:
            # Retire marker labels without changing the runtime behaviour yet.
            text = text.replace("ZERO_PATCH_", "ZERO_CONSOLIDATED_")
            write(path, text)
        changed[str(path.relative_to(ROOT))] = before
    return changed


def run_verification() -> tuple[bool, list[dict[str, object]]]:
    results: list[dict[str, object]] = []
    ok = True
    for cmd in VERIFY:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        results.append({"cmd": cmd, "returncode": proc.returncode, "output": proc.stdout})
        if proc.returncode != 0:
            ok = False
    return ok, results


def write_report(before: dict[str, int], changed: dict[str, int], after: dict[str, int], verification_ok: bool, results: list[dict[str, object]], rolled_back: bool) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / "stage3d_scheduler_report.md"
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "before": before,
        "retired": changed,
        "after": after,
        "verification_passed": verification_ok,
        "rolled_back": rolled_back,
        "verification": results,
        "note": "Stage 3D retires ZERO_PATCH_ marker debt in scheduler/task_runner while preserving behaviour. Stage 4 must remove remaining _zero_* wrapper implementation debt.",
    }
    (REPORT_DIR / "stage3d_scheduler_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Runtime Patch Consolidation Stage 3D - Scheduler",
        "",
        f"- before ZERO_PATCH markers: {sum(before.values())}",
        f"- retired marker occurrences: {sum(changed.values())}",
        f"- after ZERO_PATCH markers: {sum(after.values())}",
        f"- verification passed: {verification_ok}",
        f"- rolled back: {rolled_back}",
        "",
        "## Target files",
    ]
    for path, count in changed.items():
        lines.append(f"- `{path}`: {count}")
    lines.extend(["", "## Verification"])
    for item in results:
        cmd = " ".join(str(x) for x in item["cmd"])
        status = "PASS" if item["returncode"] == 0 else "FAIL"
        lines.append(f"### {status}: `{cmd}`")
        lines.append("```text")
        lines.append(str(item["output"]).rstrip())
        lines.append("```")
        lines.append("")
    lines.extend([
        "## Follow-up",
        "",
        "Stage 4 should remove remaining `_zero_*` wrapper functions and runtime method assignment debt after marker retirement is stable.",
    ])
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    before = count_markers(TARGETS)
    backup_targets()
    changed = retire_markers()
    verification_ok, results = run_verification()
    rolled_back = False
    if not verification_ok:
        restore_targets()
        rolled_back = True
    after = count_markers(TARGETS)
    write_report(before, changed, after, verification_ok, results, rolled_back)
    print(f"stage3d retired: {changed}")
    print(f"remaining ZERO_PATCH markers in targets: {sum(after.values())}")
    print(f"report: {REPORT_DIR / 'stage3d_scheduler_report.md'}")
    print("verification passed" if verification_ok else "verification failed; rolled back")
    return 0 if verification_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
