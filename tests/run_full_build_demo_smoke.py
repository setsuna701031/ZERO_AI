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
        raise AssertionError(message)


def require_file(path: Path, label: str) -> str:
    require_true(path.exists(), f"{label} missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    require_true(text.strip() != "", f"{label} is empty: {path}")
    return text


def require_contains(text: str, tokens: list[str], label: str) -> None:
    missing = [token for token in tokens if token not in text]
    require_true(not missing, f"{label} missing tokens: {missing}\n{text}")


def main() -> int:
    require_true(MAIN_PATH.exists(), f"main.py not found: {MAIN_PATH}")

    result = run_process([sys.executable, str(MAIN_PATH), "full-build-demo"])

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    require_true(
        result.returncode == 0,
        f"[full-build-demo-smoke] python main.py full-build-demo failed\n"
        f"returncode={result.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}",
    )

    require_contains(
        stdout,
        [
            "[full-build-demo] requirement-pack result",
            "[full-build-demo] requirement-pack show",
            "[full-build-demo] verified planning artifacts",
            "[full-build-demo] script stdout",
            "[full-build-demo] verified stats_result.txt",
            "[full-build-demo] PASS",
        ],
        "full-build-demo stdout",
    )

    project_summary_path = SHARED_DIR / "project_summary.txt"
    implementation_plan_path = SHARED_DIR / "implementation_plan.txt"
    acceptance_checklist_path = SHARED_DIR / "acceptance_checklist.txt"
    script_path = SHARED_DIR / "number_stats.py"
    stats_result_path = SHARED_DIR / "stats_result.txt"

    project_summary_text = require_file(project_summary_path, "project summary")
    implementation_plan_text = require_file(implementation_plan_path, "implementation plan")
    acceptance_checklist_text = require_file(acceptance_checklist_path, "acceptance checklist")
    require_file(script_path, "number_stats.py")
    stats_text = require_file(stats_result_path, "stats_result.txt")

    require_contains(
        project_summary_text,
        ["project_summary.txt", "implementation_plan.txt", "acceptance_checklist.txt"],
        "project summary",
    )
    require_contains(
        implementation_plan_text,
        ["Implementation Plan"],
        "implementation plan",
    )
    require_contains(
        acceptance_checklist_text,
        ["Acceptance Criteria", "Verification", "Deliverable"],
        "acceptance checklist",
    )
    require_contains(
        stats_text,
        ["sum: 100", "average: 25", "max: 40", "min: 10"],
        "stats result",
    )

    print("[PASS] full-build-demo smoke")
    print("[full-build-demo-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
