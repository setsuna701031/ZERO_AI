from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PATH = REPO_ROOT / "main.py"


def require_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    result = subprocess.run(
        [sys.executable, str(MAIN_PATH), "persona-chat"],
        input="exit\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
    )

    require_true(result.returncode == 0, f"persona-chat entry failed\n{result.stdout}\n{result.stderr}")

    stdout = result.stdout or ""
    require_true("ZERO online. What are we building today?" in stdout, "missing greeting")
    require_true("Type 'exit' to leave." in stdout, "missing exit hint")
    require_true("ZERO offline." in stdout, "missing offline message")

    print("[PASS] persona main entry smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())