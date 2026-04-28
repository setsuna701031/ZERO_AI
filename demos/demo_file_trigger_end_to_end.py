# demos/demo_file_trigger_end_to_end.py
"""
End-to-end helper for the watcher + trigger path.

Usage:
    python -m demos.demo_file_trigger_end_to_end

Then run these in separate terminals:
    python -m core.watch.file_watcher --debug
    python -m core.watch.file_trigger_handler --debug

This helper creates/updates workspace/inbox/watcher_task_input.txt.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def main() -> None:
    inbox = Path("workspace/inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    path = inbox / "watcher_task_input.txt"
    path.write_text(
        "ZERO file watcher end-to-end test\n"
        f"timestamp={datetime.utcnow().isoformat()}Z\n"
        "Goal: summarize this file into a generated summary artifact.\n",
        encoding="utf-8",
    )

    print(f"wrote: {path}")
    print("Expected:")
    print("1. file_watcher emits file_detected event")
    print("2. file_trigger_handler submits ZERO task")
    print("3. task appears in task list")


if __name__ == "__main__":
    main()
