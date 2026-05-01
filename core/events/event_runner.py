from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from core.events.event_schema import EventRecord
from core.events.event_to_task import event_to_task
from core.events.file_event_source import FileEventSource
from core.runtime.step_executor import StepExecutor
from core.runtime.task_step_executor_adapter import TaskStepExecutorAdapter
from core.tools.tool_registry import ToolRegistry


class EventRunner:
    def __init__(self, repo_root: str | None = None, workspace_dir: str | None = None) -> None:
        self.repo_root = Path(repo_root or ".").resolve(strict=False)
        self.workspace_dir = _resolve_workspace_dir(workspace_dir or str(self.repo_root))
        self.outbox_dir = self.workspace_dir / "events_outbox"
        self.results_path = self.outbox_dir / "event_results.jsonl"
        self.event_source = FileEventSource(str(self.workspace_dir))

    def poll_once(self) -> List[Dict[str, Any]]:
        events = self.event_source.poll_once()
        results: List[Dict[str, Any]] = []
        for event in events:
            task = event_to_task(event)
            try:
                task_result = self._build_adapter().execute_task(task)
            except Exception as exc:
                task_result = {
                    "ok": False,
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                    "results": [],
                }
            record = self._build_result_record(event=event, task=task, task_result=task_result)
            self._append_result(record)
            results.append(record)
        return results

    def _build_adapter(self) -> TaskStepExecutorAdapter:
        registry = ToolRegistry(workspace_dir=str(self.repo_root))
        executor = StepExecutor(
            tool_registry=registry,
            workspace_root=str(self.workspace_dir),
        )
        return TaskStepExecutorAdapter(
            step_executor=executor,
            tool_registry=registry,
            workspace=str(self.workspace_dir),
        )

    def _build_result_record(
        self,
        *,
        event: EventRecord,
        task: Dict[str, Any],
        task_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        first_result = {}
        if isinstance(task_result.get("results"), list) and task_result["results"]:
            first = task_result["results"][0]
            if isinstance(first, dict):
                first_result = first.get("result") if isinstance(first.get("result"), dict) else first

        output = first_result.get("output") if isinstance(first_result.get("output"), dict) else {}
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": asdict(event),
            "task": {
                "id": task.get("id"),
                "type": task.get("type"),
                "title": task.get("title"),
                "event_id": task.get("event_id"),
                "source_path": task.get("source_path"),
            },
            "ok": bool(task_result.get("ok", False)),
            "error": _error_summary(task_result),
            "tool_result": _tool_result_summary(first_result),
            "forbidden_mutations": {
                "git_commit": bool(output.get("git_commit") or first_result.get("git_commit") or _find_deep(first_result, "git_commit")),
                "git_push": bool(output.get("git_push") or first_result.get("git_push") or _find_deep(first_result, "git_push")),
                "github_create_pr": bool(output.get("github_create_pr") or first_result.get("github_create_pr") or _find_deep(first_result, "github_create_pr")),
            },
        }

    def _append_result(self, record: Dict[str, Any]) -> None:
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        (self.outbox_dir / ".gitkeep").touch()
        with self.results_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def poll_once(repo_root: str | None = None, workspace_dir: str | None = None) -> List[Dict[str, Any]]:
    return EventRunner(repo_root=repo_root, workspace_dir=workspace_dir).poll_once()


def _resolve_workspace_dir(path_text: str) -> Path:
    path = Path(path_text).resolve(strict=False)
    if path.name != "workspace":
        path = path / "workspace"
    return path


def _error_summary(task_result: Dict[str, Any]) -> Any:
    if task_result.get("ok"):
        return None
    error = task_result.get("error") or task_result.get("message") or "event task failed"
    return str(error)[:300]


def _tool_result_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    output = result.get("output") if isinstance(result.get("output"), dict) else {}
    changed_files = output.get("changed_files") or _find_deep(result, "changed_files") or []
    return {
        "request_id": result.get("request_id") or _find_deep(result, "request_id"),
        "tool": result.get("tool") or output.get("tool") or _find_deep(result, "tool"),
        "ok": bool(result.get("ok", output.get("ok", False))),
        "side_effect_level": result.get("side_effect_level") or output.get("side_effect_level") or _find_deep(result, "side_effect_level"),
        "changed_files": changed_files if isinstance(changed_files, list) else [],
    }


def _find_deep(value: Any, key: str, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if isinstance(value, dict):
        found = value.get(key)
        if found is not None:
            return found
        for nested in value.values():
            found = _find_deep(nested, key, depth + 1)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_deep(item, key, depth + 1)
            if found is not None:
                return found
    return None
