from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "app.py"
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


def require_contains(text: str, token: str, label: str) -> None:
    require_true(
        token in text,
        f"[implementation-proof-smoke] missing expected text in {label}: {token}\n\n{text}",
    )


def require_file(path: Path, label: str) -> str:
    require_true(path.exists(), f"[implementation-proof-smoke] missing {label}: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    require_true(text.strip() != "", f"[implementation-proof-smoke] empty {label}: {path}")
    return text


def extract_task_id(create_stdout: str) -> str:
    for line in create_stdout.splitlines():
        stripped = line.strip()
        if '"task_id"' in stripped:
            parts = stripped.split(": ", 1)
            if len(parts) == 2:
                value = parts[1].strip().strip('",')
                if value.startswith("task_"):
                    return value
    raise RuntimeError(
        "[implementation-proof-smoke] failed to extract task_id from create output\n"
        f"{create_stdout}"
    )


def main() -> int:
    require_true(APP_PATH.exists(), f"app.py not found: {APP_PATH}")

    print("[implementation-proof-smoke] creating implementation-proof task...")
    create_result = run_process([sys.executable, str(APP_PATH), "task", "implementation-proof"])
    require_true(
        create_result.returncode == 0,
        "[implementation-proof-smoke] create command failed\n"
        f"returncode={create_result.returncode}\nSTDOUT:\n{create_result.stdout}\nSTDERR:\n{create_result.stderr}",
    )

    task_id = extract_task_id(create_result.stdout)
    require_contains(create_result.stdout, "structured_implementation_proof_v1", "create stdout")
    require_contains(create_result.stdout, '"step_count": 2', "create stdout")

    print(f"[implementation-proof-smoke] created: {task_id}")

    submit_result = run_process([sys.executable, str(APP_PATH), "task", "submit", task_id])
    require_true(
        submit_result.returncode == 0,
        "[implementation-proof-smoke] submit command failed\n"
        f"returncode={submit_result.returncode}\nSTDOUT:\n{submit_result.stdout}\nSTDERR:\n{submit_result.stderr}",
    )
    require_contains(submit_result.stdout, '"ok": true', "submit stdout")

    run_result = run_process([sys.executable, str(APP_PATH), "task", "run", task_id])
    require_true(
        run_result.returncode == 0,
        "[implementation-proof-smoke] run command failed\n"
        f"returncode={run_result.returncode}\nSTDOUT:\n{run_result.stdout}\nSTDERR:\n{run_result.stderr}",
    )

    show_result = run_process([sys.executable, str(APP_PATH), "task", "show", task_id])
    require_true(
        show_result.returncode == 0,
        "[implementation-proof-smoke] show command failed\n"
        f"returncode={show_result.returncode}\nSTDOUT:\n{show_result.stdout}\nSTDERR:\n{show_result.stderr}",
    )
    require_contains(show_result.stdout, "status: finished", "show stdout")
    require_contains(show_result.stdout, "step: 2/2", "show stdout")
    require_contains(show_result.stdout, "goal:", "show stdout")

    result_result = run_process([sys.executable, str(APP_PATH), "task", "result", task_id])
    require_true(
        result_result.returncode == 0,
        "[implementation-proof-smoke] result command failed\n"
        f"returncode={result_result.returncode}\nSTDOUT:\n{result_result.stdout}\nSTDERR:\n{result_result.stderr}",
    )
    require_contains(result_result.stdout, "status: finished", "result stdout")

    script_path = SHARED_DIR / "number_stats.py"
    script_text = require_file(script_path, "number_stats.py")
    require_contains(script_text, "from pathlib import Path", "number_stats.py")
    require_contains(script_text, 'input_path = base / "numbers_input.txt"', "number_stats.py")
    require_contains(script_text, 'output_path = base / "stats_result.txt"', "number_stats.py")
    require_contains(script_text, '"\\n".join(', "number_stats.py")
    require_contains(script_text, 'print(output_path.read_text(encoding="utf-8").rstrip())', "number_stats.py")

    print("[PASS] implementation-proof smoke")
    print("[implementation-proof-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
