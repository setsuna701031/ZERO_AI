from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR_PATH = REPO_ROOT / "core" / "capabilities" / "document_flow_orchestrator.py"

INPUT_PATH = REPO_ROOT / "workspace" / "shared" / "document_flow_orchestrator_input.txt"
SUMMARY_PATH = REPO_ROOT / "workspace" / "shared" / "document_flow_orchestrator_summary.txt"
ACTION_ITEMS_PATH = REPO_ROOT / "workspace" / "shared" / "document_flow_orchestrator_action_items.txt"


def fail(message: str) -> int:
    print(f"[document-flow-orchestrator-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[document-flow-orchestrator-smoke] PASS: {message}")


def decode_process_text(data: bytes) -> str:
    if not data:
        return ""

    for encoding in ("utf-8", "cp950", "cp936", "cp1252"):
        try:
            return data.decode(encoding)
        except Exception:
            pass

    return data.decode("utf-8", errors="replace")


def require_stdout_contains(stdout: str, markers: list[str]) -> bool:
    ok = True

    for marker in markers:
        if marker not in stdout:
            print(f"[document-flow-orchestrator-smoke] missing stdout marker: {marker}")
            ok = False
        else:
            pass_step(f"stdout contains: {marker}")

    return ok


def require_file_nonempty(path: Path, label: str) -> bool:
    if not path.exists():
        print(f"[document-flow-orchestrator-smoke] missing {label}: {path}")
        return False

    if not path.is_file():
        print(f"[document-flow-orchestrator-smoke] not a file {label}: {path}")
        return False

    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        print(f"[document-flow-orchestrator-smoke] cannot read {label}: {path}")
        print(f"[document-flow-orchestrator-smoke] error: {exc}")
        return False

    if not text:
        print(f"[document-flow-orchestrator-smoke] empty {label}: {path}")
        return False

    forbidden_markers = [
        "{{previous_result}}",
        "{{file_content}}",
    ]

    for marker in forbidden_markers:
        if marker in text:
            print(f"[document-flow-orchestrator-smoke] unresolved marker in {label}: {marker}")
            return False

    pass_step(f"{label} exists and is non-empty")
    return True


def main() -> int:
    print("[document-flow-orchestrator-smoke] START")
    print(f"[document-flow-orchestrator-smoke] repo: {REPO_ROOT}")

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
        print("[document-flow-orchestrator-smoke] orchestrator stdout:")
        print(stdout.strip())

    if stderr.strip():
        print("[document-flow-orchestrator-smoke] orchestrator stderr:")
        print(stderr.strip())

    if result.returncode != 0:
        return fail(f"orchestrator returned non-zero code: {result.returncode}")

    checks = [
        require_stdout_contains(
            stdout,
            [
                "[document-flow-orchestrator] task lifecycle",
                "summary_task_id: task_",
                "action_items_task_id: task_",
                "[document-flow-orchestrator] PASS",
            ],
        ),
        require_file_nonempty(INPUT_PATH, "document flow orchestrator input"),
        require_file_nonempty(SUMMARY_PATH, "document flow orchestrator summary output"),
        require_file_nonempty(ACTION_ITEMS_PATH, "document flow orchestrator action-items output"),
    ]

    if not all(checks):
        return fail("one or more document-flow orchestrator checks failed")

    print("[document-flow-orchestrator-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())