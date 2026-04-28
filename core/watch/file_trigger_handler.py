# core/watch/file_trigger_handler.py
"""
ZERO File Trigger Handler

Purpose:
- Convert file_watcher events into ZERO tasks.
- Keep trigger rules outside AgentLoop / Scheduler / Planner.
- Provide the next platform layer:
    file detected -> trigger handler -> control_api.submit(task goal)

Product-facing behavior:
- workspace/inbox is the external drop zone.
- This handler copies detected files into workspace/shared.
- ZERO tasks only read/write under workspace/shared to avoid sandbox/path problems.
- The handler chooses a task route by file extension.

Current smart routing:
- .txt -> summary
- .md  -> markdown summary / cleanup
- .log -> log analysis summary
- .json -> JSON structure summary / validation notes
- fallback -> generic summary

Important:
- ZERO task execution guards reject unsafe absolute paths.
- This handler normalizes paths like:
    E:/zero_ai/workspace/inbox/a.txt
  into:
    workspace/inbox/a.txt
- The task itself uses:
    workspace/shared/a.txt
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.control.control_api import Zero
from core.world.world_state import world_state


DEFAULT_SOURCE_NAME = "file_watcher"
DEFAULT_HANDLER_NAME = "file_trigger_handler"

WORKSPACE_DIR = Path("workspace")
INBOX_DIR = WORKSPACE_DIR / "inbox"
SHARED_DIR = WORKSPACE_DIR / "shared"

WORKSPACE_PREFIX = "workspace/"


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_slashes(path: Any) -> str:
    return _safe_str(path).replace("\\", "/")


def _to_logical_workspace_path(path: Any) -> str:
    """
    Convert absolute/local paths into ZERO logical workspace paths.

    Examples:
        E:\\zero_ai\\workspace\\inbox\\a.txt
        E:/zero_ai/workspace/inbox/a.txt
            -> workspace/inbox/a.txt

        workspace\\inbox\\a.txt
            -> workspace/inbox/a.txt
    """
    text = _normalize_slashes(path)
    if not text:
        return ""

    lowered = text.lower()

    if lowered.startswith(WORKSPACE_PREFIX):
        return text

    marker = "/workspace/"
    idx = lowered.find(marker)
    if idx >= 0:
        return WORKSPACE_PREFIX + text[idx + len(marker):]

    marker_no_leading = "workspace/"
    idx = lowered.find(marker_no_leading)
    if idx >= 0:
        return WORKSPACE_PREFIX + text[idx + len(marker_no_leading):]

    return text


def _logical_to_local_path(logical_path: str) -> Path:
    """
    Convert a logical workspace path to a local Path relative to project root.
    """
    normalized = _to_logical_workspace_path(logical_path)
    return Path(normalized.replace("/", "\\"))


def _is_file_detected_event(event: Any) -> bool:
    return isinstance(event, dict) and _safe_str(event.get("event_type")) == "file_detected"


def _normalize_event_paths(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a copied event with safe logical paths added/overwritten.

    We keep absolute_path for evidence/debug, but task goals must use logical paths.
    """
    normalized = dict(event)

    raw_path = _safe_str(event.get("path"))
    raw_logical_path = _safe_str(event.get("logical_path"))
    raw_output_path = _safe_str(event.get("output_path"))

    input_candidate = raw_logical_path or raw_path
    logical_input = _to_logical_workspace_path(input_candidate)
    logical_output = _to_logical_workspace_path(raw_output_path)

    if raw_path:
        normalized["absolute_path"] = raw_path

    if logical_input:
        normalized["logical_path"] = logical_input
        normalized["path"] = logical_input

    if logical_output:
        normalized["output_path"] = logical_output

    return normalized


def _event_fingerprint(event: Dict[str, Any]) -> str:
    normalized_event = _normalize_event_paths(event)
    path = _safe_str(normalized_event.get("logical_path")) or _safe_str(normalized_event.get("path"))
    created_at = _safe_str(normalized_event.get("created_at"))
    output_path = _safe_str(normalized_event.get("output_path"))
    raw = f"{path}|{created_at}|{output_path}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _copy_input_to_shared(event: Dict[str, Any]) -> Tuple[bool, str, str, str]:
    """
    Copy detected inbox file into workspace/shared.

    Returns:
        ok, shared_input_path, original_input_path, error
    """
    normalized_event = _normalize_event_paths(event)

    input_path = _safe_str(normalized_event.get("logical_path")) or _safe_str(normalized_event.get("path"))
    if not input_path:
        return False, "", "", "input path is empty"

    local_input = _logical_to_local_path(input_path)

    if not local_input.exists():
        return False, "", input_path, f"source file not found: {input_path}"

    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    shared_local_path = SHARED_DIR / local_input.name
    shutil.copy(local_input, shared_local_path)

    shared_logical_path = _normalize_slashes(str(shared_local_path))
    return True, shared_logical_path, input_path, ""


def _output_path_for_route(shared_input_path: str, route_name: str) -> str:
    path = Path(shared_input_path.replace("/", "\\"))
    stem = path.stem

    if route_name == "summary":
        name = f"{stem}_summary.txt"
    elif route_name == "markdown_summary":
        name = f"{stem}_md_summary.txt"
    elif route_name == "log_analysis":
        name = f"{stem}_log_analysis.txt"
    elif route_name == "json_validation":
        name = f"{stem}_json_validation.txt"
    else:
        name = f"{stem}_summary.txt"

    return _normalize_slashes(str(SHARED_DIR / name))


def _detect_route(shared_input_path: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic routing by file extension.

    Keep goals compatible with the current summary/document pipeline by retaining
    a clear "Summarize <input> into <output>" structure.
    """
    suffix = Path(shared_input_path).suffix.lower()

    if suffix == ".txt":
        route_name = "summary"
        output_path = _output_path_for_route(shared_input_path, route_name)
        goal = f"Summarize {shared_input_path} into {output_path}"
        return {
            "route": route_name,
            "input_path": shared_input_path,
            "output_path": output_path,
            "goal": goal,
            "reason": ".txt file uses summary route",
        }

    if suffix == ".md":
        route_name = "markdown_summary"
        output_path = _output_path_for_route(shared_input_path, route_name)
        goal = (
            f"Summarize {shared_input_path} into {output_path}. "
            "Focus on headings, decisions, action items, and key technical notes."
        )
        return {
            "route": route_name,
            "input_path": shared_input_path,
            "output_path": output_path,
            "goal": goal,
            "reason": ".md file uses markdown summary route",
        }

    if suffix == ".log":
        route_name = "log_analysis"
        output_path = _output_path_for_route(shared_input_path, route_name)
        goal = (
            f"Summarize {shared_input_path} into {output_path}. "
            "Focus on errors, warnings, failure causes, and likely next debugging steps."
        )
        return {
            "route": route_name,
            "input_path": shared_input_path,
            "output_path": output_path,
            "goal": goal,
            "reason": ".log file uses log analysis route",
        }

    if suffix == ".json":
        route_name = "json_validation"
        output_path = _output_path_for_route(shared_input_path, route_name)
        goal = (
            f"Summarize {shared_input_path} into {output_path}. "
            "Focus on JSON structure, important fields, missing fields, and potential data issues."
        )
        return {
            "route": route_name,
            "input_path": shared_input_path,
            "output_path": output_path,
            "goal": goal,
            "reason": ".json file uses JSON validation route",
        }

    route_name = "summary"
    output_path = _output_path_for_route(shared_input_path, route_name)
    goal = f"Summarize {shared_input_path} into {output_path}"
    return {
        "route": route_name,
        "input_path": shared_input_path,
        "output_path": output_path,
        "goal": goal,
        "reason": "fallback summary route",
    }


def _get_event_from_world(source_name: str) -> Optional[Dict[str, Any]]:
    state = world_state.get(reload=True)
    data = state.get("data")
    if not isinstance(data, dict):
        return None

    event = data.get(source_name)
    if isinstance(event, dict):
        return event

    return None


def _mark_event_handled(
    *,
    source_name: str,
    event: Dict[str, Any],
    route: Dict[str, Any],
    submit_result: Dict[str, Any],
    fingerprint: str,
    shared_path: str,
    original_path: str,
) -> Dict[str, Any]:
    handled_payload = _normalize_event_paths(event)
    handled_payload["handled"] = True
    handled_payload["handled_at"] = utc_now()
    handled_payload["handled_by"] = DEFAULT_HANDLER_NAME
    handled_payload["fingerprint"] = fingerprint
    handled_payload["original_path"] = original_path
    handled_payload["shared_path"] = shared_path
    handled_payload["route"] = route
    handled_payload["submitted_task_goal"] = _safe_str(route.get("goal"))
    handled_payload["submit_result"] = submit_result

    return world_state.update(source_name, handled_payload)


class ZeroFileTriggerHandler:
    def __init__(
        self,
        *,
        source_name: str = DEFAULT_SOURCE_NAME,
        poll_seconds: float = 2.0,
        debug: bool = False,
    ) -> None:
        self.source_name = _safe_str(source_name) or DEFAULT_SOURCE_NAME
        self.poll_seconds = max(0.2, float(poll_seconds))
        self.debug = bool(debug)
        self.zero = Zero()
        self.last_handled_fingerprint = ""

    def handle_once(self) -> Dict[str, Any]:
        raw_event = _get_event_from_world(self.source_name)

        if not _is_file_detected_event(raw_event):
            return {
                "ok": True,
                "mode": "file_trigger_handler_once",
                "action": "idle",
                "reason": "no file_detected event",
                "source_name": self.source_name,
            }

        event = _normalize_event_paths(raw_event)

        if bool(event.get("handled")):
            return {
                "ok": True,
                "mode": "file_trigger_handler_once",
                "action": "idle",
                "reason": "event already handled",
                "source_name": self.source_name,
                "event": event,
            }

        fingerprint = _event_fingerprint(event)
        if fingerprint and fingerprint == self.last_handled_fingerprint:
            return {
                "ok": True,
                "mode": "file_trigger_handler_once",
                "action": "idle",
                "reason": "event fingerprint already handled in this process",
                "source_name": self.source_name,
                "fingerprint": fingerprint,
                "event": event,
            }

        copied, shared_path, original_path, copy_error = _copy_input_to_shared(event)
        if not copied:
            return {
                "ok": False,
                "mode": "file_trigger_handler_once",
                "action": "copy_failed",
                "reason": copy_error,
                "source_name": self.source_name,
                "event": event,
            }

        route = _detect_route(shared_path, event)
        task_goal = _safe_str(route.get("goal"))
        if not task_goal:
            return {
                "ok": False,
                "mode": "file_trigger_handler_once",
                "action": "invalid_route",
                "reason": "route did not produce task goal",
                "source_name": self.source_name,
                "event": event,
                "route": route,
            }

        submit_result = self.zero.submit(task_goal)

        if not isinstance(submit_result, dict):
            submit_result = {
                "ok": False,
                "error": "control_api.submit returned non-dict result",
                "raw_result": submit_result,
            }

        if bool(submit_result.get("ok", False)):
            self.last_handled_fingerprint = fingerprint
            handled_state = _mark_event_handled(
                source_name=self.source_name,
                event=event,
                route=route,
                submit_result=submit_result,
                fingerprint=fingerprint,
                shared_path=shared_path,
                original_path=original_path,
            )
        else:
            handled_state = world_state.get(reload=True)

        result = {
            "ok": bool(submit_result.get("ok", False)),
            "mode": "file_trigger_handler_once",
            "action": "submitted_task" if bool(submit_result.get("ok", False)) else "submit_failed",
            "source_name": self.source_name,
            "fingerprint": fingerprint,
            "shared_path": shared_path,
            "original_path": original_path,
            "route": route,
            "task_goal": task_goal,
            "submit_result": submit_result,
            "world_state": handled_state,
        }

        if self.debug:
            print("[trigger] result:", result)

        return result

    def run_forever(self) -> None:
        print(f"[trigger] watching world_state source: {self.source_name}")
        print("[trigger] press Ctrl+C to stop")

        while True:
            result = self.handle_once()
            action = _safe_str(result.get("action")) if isinstance(result, dict) else ""
            if self.debug or action not in {"idle", ""}:
                print("[trigger] scan:", result)
            time.sleep(self.poll_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZERO file watcher trigger handler")
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    handler = ZeroFileTriggerHandler(
        source_name=args.source_name,
        poll_seconds=args.poll_seconds,
        debug=args.debug,
    )

    if args.once:
        print(handler.handle_once())
        return

    handler.run_forever()


if __name__ == "__main__":
    main()
