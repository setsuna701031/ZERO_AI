from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR_PATH = REPO_ROOT / "core" / "persona" / "persona_agent_orchestrator.py"
SUMMARY_PATH = REPO_ROOT / "workspace" / "shared" / "persona_agent_summary.txt"
ACTION_ITEMS_PATH = REPO_ROOT / "workspace" / "shared" / "persona_agent_action_items.txt"


def fail(message: str) -> int:
    print(f"[persona-agent-demo-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[persona-agent-demo-smoke] PASS: {message}")


def decode_process_text(data: bytes) -> str:
    if not data:
        return ""

    for encoding in ("utf-8", "cp950", "cp936", "cp1252"):
        try:
            return data.decode(encoding)
        except Exception:
            pass

    return data.decode("utf-8", errors="replace")


def require_file_nonempty(path: Path, label: str) -> bool:
    if not path.exists():
        print(f"[persona-agent-demo-smoke] missing {label}: {path}")
        return False

    if not path.is_file():
        print(f"[persona-agent-demo-smoke] not a file {label}: {path}")
        return False

    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        print(f"[persona-agent-demo-smoke] cannot read {label}: {path}")
        print(f"[persona-agent-demo-smoke] error: {exc}")
        return False

    if not text:
        print(f"[persona-agent-demo-smoke] empty {label}: {path}")
        return False

    forbidden_markers = [
        "{{previous_result}}",
        "{{file_content}}",
    ]

    for marker in forbidden_markers:
        if marker in text:
            print(f"[persona-agent-demo-smoke] unresolved marker in {label}: {marker}")
            return False

    pass_step(f"{label} exists and is non-empty")
    return True


def require_stdout_contains(stdout: str, markers: list[str]) -> bool:
    ok = True
    for marker in markers:
        if marker not in stdout:
            print(f"[persona-agent-demo-smoke] missing stdout marker: {marker}")
            ok = False
        else:
            pass_step(f"stdout contains: {marker}")
    return ok


def main() -> int:
    print("[persona-agent-demo-smoke] START")
    print(f"[persona-agent-demo-smoke] repo: {REPO_ROOT}")

    if not ORCHESTRATOR_PATH.exists():
        return fail(f"orchestrator not found: {ORCHESTRATOR_PATH}")

    result = subprocess.run(
        [sys.executable, str(ORCHESTRATOR_PATH)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=False,
    )

    stdout = decode_process_text(result.stdout or b"")
    stderr = decode_process_text(result.stderr or b"")

    if stdout.strip():
        print("[persona-agent-demo-smoke] orchestrator stdout:")
        print(stdout.strip())

    if stderr.strip():
        print("[persona-agent-demo-smoke] orchestrator stderr:")
        print(stderr.strip())

    if result.returncode != 0:
        return fail(f"orchestrator returned non-zero code: {result.returncode}")

    checks = [
        require_stdout_contains(
            stdout,
            [
                "selected_plan: document_summary_and_action_items",
                "[agent-demo] task lifecycle",
                "[agent-demo] PASS",
            ],
        ),
        require_file_nonempty(SUMMARY_PATH, "persona agent summary artifact"),
        require_file_nonempty(ACTION_ITEMS_PATH, "persona agent action-items artifact"),
    ]

    if not all(checks):
        return fail("one or more persona agent demo checks failed")

    print("[persona-agent-demo-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())