from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PATH = REPO_ROOT / "main.py"
SHARED_DIR = REPO_ROOT / "workspace" / "shared"


def run_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def require_ok(result: subprocess.CompletedProcess, label: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"[requirement-demo-smoke] {label} failed\n"
            f"returncode={result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )


def require_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(
            f"[requirement-demo-smoke] missing expected text in {label}: {needle}"
        )


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"[requirement-demo-smoke] missing file for {label}: {path}")


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

    stdout = result.stdout or ""
    print(stdout.rstrip())

    require_contains(stdout, "[requirement-demo] PASS", "requirement-demo stdout")

    require_file(project_summary, "project_summary")
    require_file(implementation_plan, "implementation_plan")
    require_file(acceptance_checklist, "acceptance_checklist")

    project_summary_text = project_summary.read_text(encoding="utf-8", errors="replace")
    implementation_plan_text = implementation_plan.read_text(encoding="utf-8", errors="replace")
    acceptance_checklist_text = acceptance_checklist.read_text(encoding="utf-8", errors="replace")

    if not project_summary_text.strip():
        raise RuntimeError("[requirement-demo-smoke] project_summary.txt is empty")
    if not implementation_plan_text.strip():
        raise RuntimeError("[requirement-demo-smoke] implementation_plan.txt is empty")
    if not acceptance_checklist_text.strip():
        raise RuntimeError("[requirement-demo-smoke] acceptance_checklist.txt is empty")

    require_contains(acceptance_checklist_text, "Acceptance Criteria", "acceptance_checklist.txt")
    require_contains(acceptance_checklist_text, "Verification", "acceptance_checklist.txt")
    require_contains(acceptance_checklist_text, "Deliverable", "acceptance_checklist.txt")

    print("[requirement-demo-smoke] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
