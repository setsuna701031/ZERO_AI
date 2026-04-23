from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"


@dataclass
class SmokeEntry:
    label: str
    relative_path: str
    required: bool = True


CORE_SMOKES: List[SmokeEntry] = [
    SmokeEntry("tool layer smoke", "run_tool_layer_smoke.py", required=False),
    SmokeEntry("scheduler smoke", "run_scheduler_smoke.py", required=True),
    SmokeEntry("runtime smoke", "run_runtime_smoke.py", required=False),
    SmokeEntry("document task smoke", "run_document_task_smoke.py", required=True),
    SmokeEntry("document pipeline identity smoke", "run_document_pipeline_identity_smoke.py", required=True),
    SmokeEntry("requirement demo smoke", "run_requirement_demo_smoke.py", required=False),
    SmokeEntry("execution demo smoke", "run_execution_demo_smoke.py", required=False),
    SmokeEntry("semantic task smoke", "run_semantic_task_smoke.py", required=False),
]


def safe_print(text: str = "") -> None:
    value = str(text or "")
    try:
        print(value)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sanitized = value.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(sanitized)


def run_script(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding=getattr(sys.stdout, "encoding", None) or "utf-8",
        errors="replace",
    )


def main() -> int:
    safe_print("[mainline-smoke] starting")
    safe_print(f"[repo] {REPO_ROOT}")

    missing_required: List[str] = []
    failures: List[str] = []
    passes: List[str] = []
    skipped: List[str] = []

    for entry in CORE_SMOKES:
        script_path = TESTS_DIR / entry.relative_path
        if not script_path.exists():
            if entry.required:
                missing_required.append(entry.relative_path)
                safe_print(f"[FAIL] missing required smoke: {entry.relative_path}")
            else:
                skipped.append(entry.relative_path)
                safe_print(f"[SKIP] optional smoke not found: {entry.relative_path}")
            continue

        safe_print(f"[RUN] {entry.label}: {entry.relative_path}")
        result = run_script(script_path)
        if result.returncode == 0:
            passes.append(entry.relative_path)
            safe_print(f"[PASS] {entry.label}")
            continue

        failures.append(entry.relative_path)
        safe_print(f"[FAIL] {entry.label}")
        if result.stdout.strip():
            safe_print("STDOUT:")
            safe_print(result.stdout.rstrip())
        if result.stderr.strip():
            safe_print("STDERR:")
            safe_print(result.stderr.rstrip())

    safe_print("")
    safe_print("[summary]")
    safe_print(f"pass: {len(passes)}")
    safe_print(f"fail: {len(failures)}")
    safe_print(f"missing_required: {len(missing_required)}")
    safe_print(f"skip_optional: {len(skipped)}")

    if missing_required:
        safe_print("missing required scripts:")
        for item in missing_required:
            safe_print(f"  - {item}")

    if failures:
        safe_print("failed scripts:")
        for item in failures:
            safe_print(f"  - {item}")

    if skipped:
        safe_print("skipped optional scripts:")
        for item in skipped:
            safe_print(f"  - {item}")

    if missing_required or failures:
        safe_print("[mainline-smoke] FAIL")
        return 1

    safe_print("[mainline-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
