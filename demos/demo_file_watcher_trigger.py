# demos/demo_file_watcher_trigger.py
"""
Small helper for manually testing the file watcher path.

Usage:
    python -m demos.demo_file_watcher_trigger

This writes a test file into workspace/inbox/.
The watcher should detect it and inject a file_watcher event into world_state.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def main() -> None:
    inbox = Path("workspace/inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    path = inbox / "watcher_test_input.txt"
    path.write_text(
        "ZERO file watcher test\n"
        f"timestamp={datetime.utcnow().isoformat()}Z\n"
        "Please summarize this file.\n",
        encoding="utf-8",
    )

    print(f"wrote: {path}")


if __name__ == "__main__":
    main()
