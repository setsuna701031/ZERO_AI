from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PATH = REPO_ROOT / "workspace" / "shared" / "document_flow_summary.txt"
ACTION_ITEMS_PATH = REPO_ROOT / "workspace" / "shared" / "document_flow_action_items.txt"
INPUT_PATH = REPO_ROOT / "workspace" / "shared" / "document_flow_input.txt"


def fail(message: str) -> int:
    print(f"[document-flow-showcase-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[document-flow-showcase-smoke] PASS: {message}")


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
        print(f"[document-flow-showcase-smoke] missing {label}: {path}")
        return False

    if not path.is_file():
        print(f"[document-flow-showcase-smoke] not a file {label}: {path}")
        return False

    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        print(f"[document-flow-showcase-smoke] cannot read {label}: {path}")
        print(f"[document-flow-showcase-smoke] error: {exc}")
        return False

    if not text:
        print(f"[document-flow-showcase-smoke] empty {label}: {path}")
        return False

    forbidden_markers = [
        "{{previous_result}}",
        "{{file_content}}",
    ]

    for marker in forbidden_markers:
        if marker in text:
            print(f"[document-flow-showcase-smoke] unresolved marker in {label}: {marker}")
            return False

    pass_step(f"{label} exists and is non-empty")
    return True


def require_stdout_contains(stdout: str, markers: list[str]) -> bool:
    ok = True
    for marker in markers:
        if marker not in stdout:
            print(f"[document-flow-showcase-smoke] missing stdout marker: {marker}")
            ok = False
        else:
            pass_step(f"stdout contains: {marker}")
    return ok


def main() -> int:
    print("[document-flow-showcase-smoke] START")
    print(f"[document-flow-showcase-smoke] repo: {REPO_ROOT}")

    result = subprocess.run(
        [sys.executable, "main.py", "document-flow-demo"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=False,
    )

    stdout = decode_process_text(result.stdout or b"")
    stderr = decode_process_text(result.stderr or b"")

    if stdout.strip():
        print("[document-flow-showcase-smoke] command stdout:")
        print(stdout.strip())

    if stderr.strip():
        print("[document-flow-showcase-smoke] command stderr:")
        print(stderr.strip())

    if result.returncode != 0:
        return fail(f"document-flow-demo returned non-zero code: {result.returncode}")

    checks = [
        require_stdout_contains(
            stdout,
            [
                "[document-flow-demo] task lifecycle",
                "[document-flow-demo] PASS",
                "summary_task_id: task_",
                "action_items_task_id: task_",
            ],
        ),
        require_file_nonempty(INPUT_PATH, "document flow input"),
        require_file_nonempty(SUMMARY_PATH, "document flow summary output"),
        require_file_nonempty(ACTION_ITEMS_PATH, "document flow action-items output"),
    ]

    if not all(checks):
        return fail("one or more document-flow showcase checks failed")

    print("[document-flow-showcase-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())