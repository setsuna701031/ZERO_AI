from __future__ import annotations

import locale
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PATH = REPO_ROOT / "main.py"
SHARED_DIR = REPO_ROOT / "workspace" / "shared"


def _decode_bytes(data: bytes) -> str:
    encoding_candidates = [
        "utf-8",
        locale.getpreferredencoding(False) or "",
        "cp950",
        "cp936",
        "cp1252",
    ]
    for enc in encoding_candidates:
        if not enc:
            continue
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")


def run_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=False,
    )


def stdout_text(result: subprocess.CompletedProcess) -> str:
    return _decode_bytes(result.stdout or b"")


def stderr_text(result: subprocess.CompletedProcess) -> str:
    return _decode_bytes(result.stderr or b"")


def require_ok(result: subprocess.CompletedProcess, label: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"[requirement-demo-smoke] {label} failed\n"
            f"returncode={result.returncode}\n\n"
            f"STDOUT:\n{stdout_text(result)}\n\n"
            f"STDERR:\n{stderr_text(result)}"
        )


def require_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(
            f"[requirement-demo-smoke] missing expected text in {label}: {needle}\n\n{text}"
        )


def require_file(path: Path, label: str, wait_seconds: float = 3.0) -> None:
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if path.exists() and path.is_file():
            return
        time.sleep(0.2)
    raise RuntimeError(f"[requirement-demo-smoke] missing file for {label}: {path}")


def require_non_empty_text(path: Path, label: str) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise RuntimeError(f"[requirement-demo-smoke] {label} is empty: {path}")
    return text


def main() -> int:
    if not MAIN_PATH.exists():
        raise FileNotFoundError(f"main.py not found: {MAIN_PATH}")

    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    project_summary = SHARED_DIR / "project_summary.txt"
    implementation_plan = SHARED_DIR / "implementation_plan.txt"
    acceptance_checklist = SHARED_DIR / "acceptance_checklist.txt"

    for path in [project_summary, implementation_plan, acceptance_checklist]:
        if path.exists():
            path.unlink()

    print("[requirement-demo-smoke] running requirement-demo...")
    result = run_command([sys.executable, str(MAIN_PATH), "requirement-demo"])
    require_ok(result, "python main.py requirement-demo")

    stdout = stdout_text(result)
    stderr = stderr_text(result)

    if stdout.strip():
        print(stdout.rstrip())
    if stderr.strip():
        print("[requirement-demo-smoke] stderr:")
        print(stderr.rstrip())

    require_contains(stdout, "[requirement-demo] PASS", "requirement-demo stdout")

    require_file(project_summary, "project_summary")
    require_file(implementation_plan, "implementation_plan")
    require_file(acceptance_checklist, "acceptance_checklist")

    project_summary_text = require_non_empty_text(project_summary, "project_summary.txt")
    implementation_plan_text = require_non_empty_text(implementation_plan, "implementation_plan.txt")
    acceptance_checklist_text = require_non_empty_text(acceptance_checklist, "acceptance_checklist.txt")

    require_contains(project_summary_text, "Project Summary", "project_summary.txt")
    require_contains(implementation_plan_text, "Implementation Plan", "implementation_plan.txt")
    require_contains(acceptance_checklist_text, "Acceptance Criteria", "acceptance_checklist.txt")
    require_contains(acceptance_checklist_text, "Verification", "acceptance_checklist.txt")
    require_contains(acceptance_checklist_text, "Deliverable", "acceptance_checklist.txt")

    print("[requirement-demo-smoke] outputs:")
    print(f"  project summary: {project_summary}")
    print(f"  implementation plan: {implementation_plan}")
    print(f"  acceptance checklist: {acceptance_checklist}")
    print("[requirement-demo-smoke] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
