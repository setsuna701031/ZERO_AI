from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PATH = REPO_ROOT / "main.py"
SHARED_DIR = REPO_ROOT / "workspace" / "shared"


def run_process(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def require_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def require_file(path: Path, label: str) -> str:
    require_true(path.exists(), f"[requirement-demo-smoke] missing {label}: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    require_true(text.strip() != "", f"[requirement-demo-smoke] empty {label}: {path}")
    return text


def require_contains(text: str, token: str, label: str) -> None:
    require_true(
        token in text,
        f"[requirement-demo-smoke] missing expected text in {label}: {token}\n\n{text}",
    )


def main() -> int:
    require_true(MAIN_PATH.exists(), f"main.py not found: {MAIN_PATH}")

    print("[requirement-demo-smoke] running requirement-demo...")
    result = run_process([sys.executable, str(MAIN_PATH), "requirement-demo"])

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    require_true(
        result.returncode == 0,
        f"[requirement-demo-smoke] python main.py requirement-demo failed\n"
        f"returncode={result.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}",
    )

    require_contains(stdout, "[requirement-demo] task result", "stdout")
    require_contains(stdout, "[requirement-demo] task show", "stdout")
    require_contains(stdout, "[requirement-demo] outputs", "stdout")
    require_contains(stdout, "[requirement-demo] PASS", "stdout")

    project_summary_path = SHARED_DIR / "project_summary.txt"
    implementation_plan_path = SHARED_DIR / "implementation_plan.txt"
    acceptance_checklist_path = SHARED_DIR / "acceptance_checklist.txt"

    project_summary_text = require_file(project_summary_path, "project_summary.txt")
    implementation_plan_text = require_file(implementation_plan_path, "implementation_plan.txt")
    acceptance_checklist_text = require_file(acceptance_checklist_path, "acceptance_checklist.txt")

    # Stable artifact checks: verify core sections and non-empty outputs,
    # without overfitting to a single exact wording like "Deliverable".
    require_contains(project_summary_text, "project_summary", "project_summary.txt")
    require_contains(project_summary_text, "implementation_plan", "project_summary.txt")
    require_contains(project_summary_text, "acceptance_checklist", "project_summary.txt")

    require_contains(implementation_plan_text, "Implementation Plan", "implementation_plan.txt")

    require_contains(acceptance_checklist_text, "Acceptance", "acceptance_checklist.txt")
    require_contains(acceptance_checklist_text, "Verification", "acceptance_checklist.txt")

    print("[PASS] requirement demo smoke")
    print("[requirement-demo-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
