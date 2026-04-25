from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.capability_invoker import execute_resolved_capability


SHARED_DIR = REPO_ROOT / "workspace" / "shared"

INPUT_PATH = SHARED_DIR / "capability_invoker_input.txt"
SUMMARY_OUTPUT_PATH = SHARED_DIR / "capability_invoker_summary.txt"
ACTION_ITEMS_OUTPUT_PATH = SHARED_DIR / "capability_invoker_action_items.txt"


def fail(message: str) -> int:
    print(f"[capability-invoker-execute-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[capability-invoker-execute-smoke] PASS: {message}")


def write_input() -> None:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_PATH.write_text(
        (
            "Engineering Review Notes\n\n"
            "Alice will finish the API draft by Friday.\n"
            "Bob will test the upload flow next week.\n"
            "Carol will prepare the release note before the internal demo.\n"
            "The team agreed that the next milestone should focus on document flow reliability.\n"
            "The operator needs a concise summary and a separate action-items file.\n"
        ),
        encoding="utf-8",
    )


def require_file_nonempty(path: Path, label: str) -> bool:
    if not path.exists():
        print(f"[capability-invoker-execute-smoke] missing {label}: {path}")
        return False

    if not path.is_file():
        print(f"[capability-invoker-execute-smoke] not a file {label}: {path}")
        return False

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"[capability-invoker-execute-smoke] empty {label}: {path}")
        return False

    for marker in ("{{previous_result}}", "{{file_content}}"):
        if marker in text:
            print(f"[capability-invoker-execute-smoke] unresolved marker in {label}: {marker}")
            return False

    pass_step(f"{label} exists and is non-empty")
    return True


def make_route() -> dict:
    return {
        "capability": "document_flow",
        "operation": "summary_and_action_items",
        "capability_registry_hint": {
            "capability": "document_flow",
            "operation": "summary_and_action_items",
            "registry_operation": "run_summary_and_action_items",
            "capability_registered": True,
            "operation_registered": True,
        },
    }


def main() -> int:
    print("[capability-invoker-execute-smoke] START")
    print(f"[capability-invoker-execute-smoke] repo: {REPO_ROOT}")

    write_input()
    pass_step(f"input written: {INPUT_PATH}")

    for output_path in (SUMMARY_OUTPUT_PATH, ACTION_ITEMS_OUTPUT_PATH):
        if output_path.exists():
            output_path.unlink()

    result = execute_resolved_capability(
        route=make_route(),
        input_path=INPUT_PATH,
        summary_output_path=SUMMARY_OUTPUT_PATH,
        action_items_output_path=ACTION_ITEMS_OUTPUT_PATH,
    )

    payload = result.to_dict()
    print("[capability-invoker-execute-smoke] execution result")
    for key, value in payload.items():
        if key == "result":
            continue
        print(f"{key}: {value}")

    if not result.ok:
        return fail(f"execute_resolved_capability returned non-ok: {result.error}")

    checks = [
        require_file_nonempty(INPUT_PATH, "capability invoker input"),
        require_file_nonempty(SUMMARY_OUTPUT_PATH, "capability invoker summary output"),
        require_file_nonempty(ACTION_ITEMS_OUTPUT_PATH, "capability invoker action-items output"),
    ]

    if not all(checks):
        return fail("one or more capability execution artifact checks failed")

    print("[capability-invoker-execute-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())