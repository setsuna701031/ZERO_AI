import os
from typing import Any, Dict, List, Optional

try:
    from core.task_memory import TaskMemory
except ImportError:
    from task_memory import TaskMemory


class ContextManager:
    """
    ZERO Context Manager
    """

    def __init__(self, workspace_root: str, recent_limit: int = 5) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.recent_limit = max(1, int(recent_limit))
        self.task_memory = TaskMemory(self.workspace_root)

    def get_recent_task_records(self, limit: Optional[int] = None) -> Dict[str, Any]:
        safe_limit = self.recent_limit if limit is None else max(1, int(limit))
        return self.task_memory.get_recent_records(limit=safe_limit)

    def build_context_bundle(self, limit: Optional[int] = None) -> Dict[str, Any]:
        recent_result = self.get_recent_task_records(limit=limit)

        if not recent_result.get("ok", False):
            return {
                "ok": False,
                "summary": "Failed to load recent task records.",
                "recent_records": [],
                "context_text": "",
                "context_items": [],
            }

        records = recent_result.get("records", [])
        context_items = self._build_context_items(records)
        context_text = self._build_context_text(context_items)

        return {
            "ok": True,
            "summary": f"Built context from {len(context_items)} task record(s).",
            "recent_records": records,
            "context_items": context_items,
            "context_text": context_text,
        }

    def build_planner_input(self, user_input: str, limit: Optional[int] = None) -> Dict[str, Any]:
        bundle = self.build_context_bundle(limit=limit)

        context_text = bundle.get("context_text", "")
        combined_input = self._combine_user_input_with_context(user_input, context_text)

        return {
            "ok": True,
            "summary": "Planner input prepared.",
            "user_input": user_input,
            "context_text": context_text,
            "combined_input": combined_input,
            "context_items": bundle.get("context_items", []),
        }

    def _build_context_items(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        for record in records:
            steps = record.get("steps", [])
            changed_files = record.get("changed_files", [])
            evidence = record.get("evidence", [])

            items.append({
                "id": record.get("id"),
                "timestamp": record.get("timestamp"),
                "user_input": record.get("user_input"),
                "mode": record.get("mode"),
                "summary": record.get("summary"),
                "success": record.get("success"),
                "step_count": len(steps) if isinstance(steps, list) else 0,
                "changed_files": changed_files if isinstance(changed_files, list) else [],
                "evidence": evidence if isinstance(evidence, list) else [],
            })

        return items

    def _build_context_text(self, context_items: List[Dict[str, Any]]) -> str:
        if not context_items:
            return "No recent task context."

        lines: List[str] = []
        lines.append("Recent task context:")

        for item in context_items:
            lines.append(f"- Task ID: {item.get('id', '')}")
            lines.append(f"  Time: {item.get('timestamp', '')}")
            lines.append(f"  Input: {item.get('user_input', '')}")
            lines.append(f"  Mode: {item.get('mode', '')}")
            lines.append(f"  Summary: {item.get('summary', '')}")
            lines.append(f"  Success: {item.get('success', False)}")
            lines.append(f"  Step count: {item.get('step_count', 0)}")

            changed_files = item.get("changed_files", [])
            if changed_files:
                lines.append(f"  Changed files: {', '.join(changed_files)}")

            evidence = item.get("evidence", [])
            if evidence:
                lines.append(f"  Evidence: {', '.join(evidence)}")

        return "\n".join(lines)

    def _combine_user_input_with_context(self, user_input: str, context_text: str) -> str:
        return (
            f"User request:\n{user_input}\n\n"
            f"{context_text}\n\n"
            f"Please use the recent task context only when relevant."
        )