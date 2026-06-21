from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
SCHEDULER = ROOT / "core" / "tasks" / "scheduler.py"
REPORT_DIR = ROOT / "docs" / "architecture" / "runtime_patch_consolidation"
REPORT = REPORT_DIR / "stage3c_scheduler_authority_report.md"
BACKUP_DIR = ROOT / ".zero_patch_consolidation_backup" / "stage3c_scheduler_authority"

START_MARKER = "# ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V1"
STOP_MARKER = "# ZERO_PATCH_SCHEDULER_OPERATOR_SESSION_COMPLETION_V7"
REMOVE_MARKERS = [
    "ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V1",
    "ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V2",
    "ZERO_PATCH_SCHEDULER_RUNTIME_GATE_FALLBACK_V3",
    "ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_FALLBACK_V4",
    "ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_DIRECT_HANDLER_V5",
    "ZERO_PATCH_SCHEDULER_EXPLICIT_AUTHORITY_RESULT_SHAPE_V6",
]
VERIFY_COMMANDS = [
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_evidence_freeze.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_execution_ownership_migration_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mainline_freeze_contract.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runtime_mode_propagation.py"],
    [sys.executable, "-m", "pytest", "-q", "tests/test_runner_scheduler_boundary_survival.py"],
    [sys.executable, "-m", "compileall", "core"],
]


def count_zero_patch() -> int:
    count = 0
    for path in (ROOT / "core").rglob("*.py"):
        try:
            count += path.read_text(encoding="utf-8", errors="ignore").count("ZERO_PATCH_")
        except OSError:
            pass
    return count


def backup_file(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, target)
    return target


def remove_scheduler_authority_blocks() -> dict[str, object]:
    text = SCHEDULER.read_text(encoding="utf-8")
    before_markers = {m: text.count(m) for m in REMOVE_MARKERS}
    start = text.find(START_MARKER)
    if start == -1:
        return {"changed": False, "removed": {}, "reason": f"start marker not found: {START_MARKER}"}
    stop = text.find(STOP_MARKER, start)
    if stop == -1:
        return {"changed": False, "removed": {}, "reason": f"stop marker not found: {STOP_MARKER}"}

    new_text = text[:start].rstrip() + "\n\n" + text[stop:].lstrip()
    SCHEDULER.write_text(new_text, encoding="utf-8")
    after_text = SCHEDULER.read_text(encoding="utf-8")
    removed = {m: before_markers[m] - after_text.count(m) for m in REMOVE_MARKERS}
    return {"changed": True, "removed": removed, "reason": "removed contiguous scheduler authority fallback block"}


def run_verify() -> tuple[bool, list[dict[str, object]]]:
    results: list[dict[str, object]] = []
    ok = True
    for cmd in VERIFY_COMMANDS:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        passed = proc.returncode == 0
        ok = ok and passed
        results.append({
            "cmd": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "passed": passed,
        })
        if not passed:
            break
    return ok, results


def write_report(before: int, after: int, patch_result: dict[str, object], verify_ok: bool, results: list[dict[str, object]], rolled_back: bool) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Runtime Patch Consolidation Stage 3C - Scheduler Authority",
        "",
        f"- before ZERO_PATCH markers: {before}",
        f"- after ZERO_PATCH markers: {after}",
        f"- verification passed: {verify_ok}",
        f"- rolled back: {rolled_back}",
        "",
        "## Patch result",
        "",
        "```json",
        json.dumps(patch_result, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Verification",
        "",
    ]
    for item in results:
        lines.extend([
            "```text",
            f"$ {item['cmd']}",
            str(item.get("stdout") or "").rstrip(),
            str(item.get("stderr") or "").rstrip(),
            "```",
            "",
        ])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if not SCHEDULER.exists():
        raise SystemExit(f"missing file: {SCHEDULER}")
    before = count_zero_patch()
    backup = backup_file(SCHEDULER)
    patch_result = remove_scheduler_authority_blocks()
    verify_ok, results = run_verify()
    rolled_back = False
    if not verify_ok:
        shutil.copy2(backup, SCHEDULER)
        rolled_back = True
    after = count_zero_patch()
    write_report(before, after, patch_result, verify_ok, results, rolled_back)
    print("stage3c removed:", patch_result.get("removed", {}))
    print("remaining ZERO_PATCH markers:", after)
    print("report:", REPORT)
    print("verification", "passed" if verify_ok else "failed; rolled back")
    return 0 if verify_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
