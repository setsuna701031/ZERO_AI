# core/watch/file_watcher.py
"""
ZERO File Watcher

Purpose:
- Provide a simple product-facing event source.
- Watch a folder for new/updated files.
- Inject file events into ZERO world_state through control_api.
- Keep this outside AgentLoop / Scheduler / Planner.

Default flow:
    workspace/inbox/*.txt
        -> world_state["file_watcher"]
        -> app.py L5 background loop can react later

This first version only emits events. It does not hard-code summary behavior yet.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

from core.control.control_api import Zero


DEFAULT_WATCH_DIR = "workspace/inbox"
DEFAULT_OUTPUT_DIR = "workspace/shared"
DEFAULT_SOURCE_NAME = "file_watcher"


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def ensure_dir(path: str) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def is_supported_file(path: Path, extensions: Iterable[str]) -> bool:
    if not path.is_file():
        return False
    suffixes = {ext.lower().strip() for ext in extensions if str(ext).strip()}
    if not suffixes:
        return True
    return path.suffix.lower() in suffixes


def snapshot_files(watch_dir: Path, extensions: Iterable[str]) -> Dict[str, float]:
    result: Dict[str, float] = {}
    if not watch_dir.exists():
        return result

    for path in watch_dir.iterdir():
        if not is_supported_file(path, extensions):
            continue
        try:
            result[str(path.resolve())] = path.stat().st_mtime
        except OSError:
            continue
    return result


def build_file_event(path: Path, watch_dir: Path, output_dir: Path) -> Dict[str, object]:
    resolved = path.resolve()
    output_name = f"{path.stem}_summary.txt"
    output_path = output_dir / output_name

    return {
        "event_type": "file_detected",
        "created_at": utc_now(),
        "path": str(resolved),
        "logical_path": str(path).replace("\\", "/"),
        "name": path.name,
        "stem": path.stem,
        "suffix": path.suffix,
        "watch_dir": str(watch_dir.resolve()),
        "output_path": str(output_path).replace("\\", "/"),
        "suggested_task_goal": (
            f"Summarize {str(path).replace(chr(92), '/')} "
            f"into {str(output_path).replace(chr(92), '/')}"
        ),
    }


class ZeroFileWatcher:
    def __init__(
        self,
        *,
        watch_dir: str = DEFAULT_WATCH_DIR,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        source_name: str = DEFAULT_SOURCE_NAME,
        poll_seconds: float = 2.0,
        extensions: Optional[Iterable[str]] = None,
        emit_existing: bool = False,
        debug: bool = False,
    ) -> None:
        self.watch_dir = ensure_dir(watch_dir)
        self.output_dir = ensure_dir(output_dir)
        self.source_name = str(source_name or DEFAULT_SOURCE_NAME).strip() or DEFAULT_SOURCE_NAME
        self.poll_seconds = max(0.2, float(poll_seconds))
        self.extensions = list(extensions or [".txt", ".md"])
        self.emit_existing = bool(emit_existing)
        self.debug = bool(debug)
        self.zero = Zero()
        self.seen: Dict[str, float] = {}

    def initialize(self) -> None:
        current = snapshot_files(self.watch_dir, self.extensions)

        if self.emit_existing:
            self.seen = {}
            return

        self.seen = current

    def scan_once(self) -> Dict[str, object]:
        current = snapshot_files(self.watch_dir, self.extensions)
        emitted = []

        for path_text, mtime in current.items():
            previous_mtime = self.seen.get(path_text)
            if previous_mtime is not None and mtime <= previous_mtime:
                continue

            path = Path(path_text)
            event = build_file_event(path, self.watch_dir, self.output_dir)

            result = self.zero.inject_world(self.source_name, event)
            emitted.append(
                {
                    "path": path_text,
                    "mtime": mtime,
                    "event": event,
                    "inject_result_ok": bool(result.get("ok", False)) if isinstance(result, dict) else False,
                }
            )

            if self.debug:
                print("[watcher] emitted:", event)
                print("[watcher] inject_result:", result)

        self.seen = current

        return {
            "ok": True,
            "mode": "file_watcher_scan_once",
            "watch_dir": str(self.watch_dir),
            "source_name": self.source_name,
            "emitted_count": len(emitted),
            "emitted": emitted,
        }

    def run_forever(self) -> None:
        self.initialize()
        print(f"[watcher] watching: {self.watch_dir}")
        print(f"[watcher] output_dir: {self.output_dir}")
        print(f"[watcher] source: {self.source_name}")
        print("[watcher] press Ctrl+C to stop")

        while True:
            result = self.scan_once()
            if self.debug or int(result.get("emitted_count", 0)) > 0:
                print("[watcher] scan:", result)
            time.sleep(self.poll_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZERO file watcher event source")
    parser.add_argument("--watch-dir", default=DEFAULT_WATCH_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--extensions", default=".txt,.md")
    parser.add_argument("--emit-existing", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    extensions = [part.strip() for part in str(args.extensions or "").split(",") if part.strip()]

    watcher = ZeroFileWatcher(
        watch_dir=args.watch_dir,
        output_dir=args.output_dir,
        source_name=args.source_name,
        poll_seconds=args.poll_seconds,
        extensions=extensions,
        emit_existing=args.emit_existing,
        debug=args.debug,
    )

    if args.once:
        watcher.initialize()
        print(watcher.scan_once())
        return

    watcher.run_forever()


if __name__ == "__main__":
    main()
