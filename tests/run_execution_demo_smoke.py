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
            f"[execution-demo-smoke] {label} failed\n"
            f"returncode={result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )


def require_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(
            f"[execution-demo-smoke] missing expected text in {label}: {needle}"
        )


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"[execution-demo-smoke] missing file for {label}: {path}")


def main() -> int:
    if not MAIN_PATH.exists():
        raise FileNotFoundError(f"main.py not found: {MAIN_PATH}")

    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    hello_path = SHARED_DIR / "hello.py"
    if hello_path.exists():
        hello_path.unlink()

    print("[execution-demo-smoke] running execution-demo...")
    result = run_command([sys.executable, str(MAIN_PATH), "execution-demo"])
    require_ok(result, "python main.py execution-demo")

    stdout = result.stdout or ""
    print(stdout.rstrip())

    require_contains(stdout, "[execution-demo] PASS", "execution-demo stdout")

    require_file(hello_path, "hello.py")
    hello_text = hello_path.read_text(encoding="utf-8", errors="replace")

    if not hello_text.strip():
        raise RuntimeError("[execution-demo-smoke] hello.py is empty")

    require_contains(hello_text, 'print("ok")', "hello.py")

    print("[execution-demo-smoke] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
