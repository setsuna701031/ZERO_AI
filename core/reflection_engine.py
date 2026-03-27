from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ReflectionEngine:
    """
    ZERO Reflection Engine (lessons v1)

    目標：
    - 把一次 task execution 整理成 lesson
    - 給 memory_manager 保存
    - 讓下一次 planner 能讀到
    """

    def reflect(
        self,
        task_info: Dict[str, Any],
        runtime_result: Dict[str, Any],
        step_results: Optional[List[Dict[str, Any]]] = None,
        planner_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(task_info, dict):
            raise TypeError("task_info must be a dict.")

        if not isinstance(runtime_result, dict):
            raise TypeError("runtime_result must be a dict.")

        task_name = str(task_info.get("task_name", "")).strip()
        goal = str(task_info.get("goal", "")).strip()
        task_type = str(
            runtime_result.get("task_type")
            or task_info.get("task_type")
            or "general"
        ).strip() or "general"

        step_results = step_results or []
        planner_context = planner_context or {}

        success = bool(runtime_result.get("success", False))
        error = runtime_result.get("error")
        tools_used = self._collect_tools_used(step_results, runtime_result)

        what_worked = self._extract_what_worked(
            success=success,
            task_type=task_type,
            step_results=step_results,
            runtime_result=runtime_result,
            planner_context=planner_context,
        )

        what_failed = self._extract_what_failed(
            success=success,
            error=error,
            step_results=step_results,
        )

        suggested_next_time = self._extract_suggestions(
            success=success,
            task_type=task_type,
            error=error,
            step_results=step_results,
            planner_context=planner_context,
            tools_used=tools_used,
        )

        tags = self._build_tags(task_type=task_type, tools_used=tools_used, success=success)

        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "task_name": task_name,
            "goal": goal,
            "goal_summary": goal[:120],
            "task_type": task_type,
            "outcome": "success" if success else "failure",
            "what_worked": what_worked,
            "what_failed": what_failed,
            "suggested_next_time": suggested_next_time,
            "tools_used": tools_used,
            "tags": tags,
            "error": None if error is None else str(error),
        }

    # =========================================================
    # Helpers
    # =========================================================

    def _collect_tools_used(
        self,
        step_results: List[Dict[str, Any]],
        runtime_result: Dict[str, Any],
    ) -> List[str]:
        names: List[str] = []

        runtime_tools = runtime_result.get("tools_used", [])
        if isinstance(runtime_tools, list):
            for item in runtime_tools:
                clean = str(item).strip()
                if clean and clean not in names:
                    names.append(clean)

        for step in step_results:
            if not isinstance(step, dict):
                continue
            clean = str(step.get("tool_name", "")).strip()
            if clean and clean.lower() != "none" and clean not in names:
                names.append(clean)

        return names

    def _extract_what_worked(
        self,
        success: bool,
        task_type: str,
        step_results: List[Dict[str, Any]],
        runtime_result: Dict[str, Any],
        planner_context: Dict[str, Any],
    ) -> List[str]:
        worked: List[str] = []

        if success:
            worked.append("Current execution flow completed successfully.")

        lesson_count = int(planner_context.get("lesson_count", 0))
        if lesson_count > 0:
            worked.append(f"Planner referenced {lesson_count} prior lesson(s).")

        for step in step_results:
            if not isinstance(step, dict):
                continue

            if str(step.get("status", "")).strip().lower() != "finished":
                continue

            step_kind = str(step.get("step_kind", "")).strip().lower()
            step_text = str(step.get("step_text", "")).strip()
            output = step.get("output", {})

            if step_kind == "tool":
                tool_name = str(step.get("tool_name", "")).strip()
                if isinstance(output, dict) and output.get("tool_success") is True:
                    worked.append(f"Tool step succeeded: {tool_name or step_text}")
            else:
                if step_text:
                    worked.append(f"Reason step completed: {step_text}")

        if task_type == "command":
            worked.append("Command-oriented task classification matched runtime flow.")
        elif task_type == "file":
            worked.append("File-oriented task classification matched runtime flow.")

        return self._dedupe(worked)

    def _extract_what_failed(
        self,
        success: bool,
        error: Any,
        step_results: List[Dict[str, Any]],
    ) -> List[str]:
        failed: List[str] = []

        if not success:
            if error:
                failed.append(str(error).strip())

        for step in step_results:
            if not isinstance(step, dict):
                continue

            if str(step.get("status", "")).strip().lower() != "failed":
                continue

            step_text = str(step.get("step_text", "")).strip()
            tool_name = str(step.get("tool_name", "")).strip()
            output = step.get("output", {})

            if isinstance(output, dict):
                output_error = str(output.get("error", "")).strip()
                if output_error:
                    if tool_name:
                        failed.append(f"{tool_name}: {output_error}")
                    elif step_text:
                        failed.append(f"{step_text}: {output_error}")
                    else:
                        failed.append(output_error)

        return self._dedupe(failed)

    def _extract_suggestions(
        self,
        success: bool,
        task_type: str,
        error: Any,
        step_results: List[Dict[str, Any]],
        planner_context: Dict[str, Any],
        tools_used: List[str],
    ) -> List[str]:
        suggestions: List[str] = []

        if success:
            if tools_used:
                suggestions.append("Prefer previously successful tool path first.")
        else:
            suggestions.append("Add explicit precheck before the risky step.")
            suggestions.append("Fail fast when tool step returns unsuccessful result.")

        recalled_actions = planner_context.get("recalled_actions", [])
        if isinstance(recalled_actions, list):
            for item in recalled_actions:
                clean = str(item).strip()
                if clean:
                    suggestions.append(clean)

        error_text = str(error or "").lower()
        if "not found" in error_text:
            suggestions.append("Verify file/path/tool existence before execution.")
        if "permission" in error_text:
            suggestions.append("Check permissions before running the task.")
        if "tool" in error_text and "failed" in error_text:
            suggestions.append("Validate tool availability and input arguments first.")

        if task_type == "file":
            suggestions.append("For file tasks, verify target path before read/write.")
        if task_type == "command":
            suggestions.append("For command tasks, validate command text before execution.")

        for step in step_results:
            if not isinstance(step, dict):
                continue
            if str(step.get("step_kind", "")).strip().lower() != "tool":
                continue

            output = step.get("output", {})
            if isinstance(output, dict) and output.get("tool_success") is False:
                tool_name = str(step.get("tool_name", "")).strip()
                if tool_name:
                    suggestions.append(f"Pre-validate tool '{tool_name}' before execution.")

        return self._dedupe(suggestions)

    def _build_tags(self, task_type: str, tools_used: List[str], success: bool) -> List[str]:
        tags: List[str] = [task_type, "lesson", "success" if success else "failure"]

        for item in tools_used:
            clean = str(item).strip()
            if clean:
                tags.append(clean)

        return self._dedupe(tags)

    def _dedupe(self, items: List[str]) -> List[str]:
        result: List[str] = []
        seen = set()

        for item in items:
            clean = str(item).strip()
            if not clean:
                continue
            if clean in seen:
                continue
            seen.add(clean)
            result.append(clean)

        return result