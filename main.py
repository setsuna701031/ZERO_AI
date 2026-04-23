from __future__ import annotations

import locale
import subprocess
import sys
from pathlib import Path
from typing import List

from core.capabilities.demo_flows import (
    run_doc_demo,
    run_execution_demo,
    run_requirement_demo,
)
from core.capabilities.full_build_flow import run_full_build_demo, run_mini_build_demo


REPO_ROOT = Path(__file__).resolve().parent
APP_PATH = REPO_ROOT / "app.py"
MAINLINE_SMOKE_PATH = REPO_ROOT / "tests" / "run_mainline_smoke.py"
SHARED_DIR = REPO_ROOT / "workspace" / "shared"


def safe_print(text: str = "") -> None:
    value = str(text or "")
    try:
        print(value)
        return
    except UnicodeEncodeError:
        pass

    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    sanitized = value.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(sanitized)


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


def print_help() -> None:
    safe_print("ZERO unified entry")
    safe_print("")
    safe_print("Usage:")
    safe_print("  python main.py start")
    safe_print("  python main.py runtime")
    safe_print("  python main.py smoke")
    safe_print("  python main.py doc-demo")
    safe_print("  python main.py requirement-demo")
    safe_print("  python main.py execution-demo")
    safe_print("  python main.py mini-build-demo")
    safe_print("  python main.py full-build-demo")
    safe_print("  python main.py health")
    safe_print("  python main.py help")
    safe_print("")
    safe_print("Commands:")
    safe_print("  start             Launch interactive ZERO CLI")
    safe_print("  runtime           Show runtime information")
    safe_print("  smoke             Run stable mainline smoke validation")
    safe_print("  doc-demo          Run end-to-end document demo flow")
    safe_print("  requirement-demo  Run requirement-pack demo flow")
    safe_print("  execution-demo    Run execution-proof demo flow")
    safe_print("  mini-build-demo   Run engineering mini build demo flow")
    safe_print("  full-build-demo   Run requirement -> build -> execute -> verify flow")
    safe_print("  health            Show health information")
    safe_print("  help              Show this help")


def run_process(args: List[str], capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        capture_output=capture,
        text=False,
    )


def stdout_text(result: subprocess.CompletedProcess) -> str:
    return _decode_bytes(result.stdout or b"")


def stderr_text(result: subprocess.CompletedProcess) -> str:
    return _decode_bytes(result.stderr or b"")


def ensure_required_paths() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"app.py not found: {APP_PATH}")
    SHARED_DIR.mkdir(parents=True, exist_ok=True)


def run_app_command(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    return run_process([sys.executable, str(APP_PATH), *args], capture=capture)


def main(argv: List[str]) -> int:
    command = argv[1].strip().lower() if len(argv) >= 2 else "help"

    if command in {"help", "--help", "-h"}:
        print_help()
        return 0

    if command == "start":
        ensure_required_paths()
        result = run_app_command()
        return result.returncode

    if command == "runtime":
        ensure_required_paths()
        result = run_app_command("runtime", capture=False)
        return result.returncode

    if command == "health":
        ensure_required_paths()
        result = run_app_command("health", capture=False)
        return result.returncode

    if command == "smoke":
        if not MAINLINE_SMOKE_PATH.exists():
            raise FileNotFoundError(f"mainline smoke not found: {MAINLINE_SMOKE_PATH}")
        result = run_process([sys.executable, str(MAINLINE_SMOKE_PATH)], capture=False)
        return result.returncode

    if command == "doc-demo":
        return run_doc_demo()

    if command == "requirement-demo":
        return run_requirement_demo()

    if command == "execution-demo":
        return run_execution_demo()

    if command == "mini-build-demo":
        return run_mini_build_demo()

    if command == "full-build-demo":
        return run_full_build_demo()

    safe_print(f"Unknown command: {command}")
    safe_print("")
    print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))