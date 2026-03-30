from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskSummary:
    """
    Task Summary / Experience Memory

    任務完成後產生 summary.json
    """

    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    # =========================================================
    # Public
    # =========================================================

    def build_summary(
        self,
        task_name: str,
        goal: str,
        plan: Dict[str, Any],
        step_results: List[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        important_steps = self._extract_important_steps(step_results)
        lessons = self._extract_lessons(step_results)

        summary = {
            "task_name": task_name,
            "goal": goal,
            "task_type": result.get("task_type"),
            "status": result.get("status"),
            "step_count": result.get("step_count"),
            "important_steps": important_steps,
            "lessons": lessons,
        }

        return summary

    def save_summary(
        self,
        task_name: str,
        summary: Dict[str, Any],
    ) -> None:
        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        summary_file = task_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    # =========================================================
    # Internal
    # =========================================================

    def _extract_important_steps(
        self,
        step_results: List[Dict[str, Any]],
    ) -> List[str]:
        important = []

        for step in step_results:
            text = step.get("step_text")
            status = step.get("status")

            if status == "finished" and text:
                important.append(text)

        return important[:10]

    def _extract_lessons(
        self,
        step_results: List[Dict[str, Any]],
    ) -> List[str]:
        lessons = []

        for step in step_results:
            output = step.get("output")

            if isinstance(output, dict):
                if "error" in output:
                    lessons.append(f"Error occurred: {output.get('error')}")

                if output.get("llm_used"):
                    lessons.append("LLM reasoning was used for analysis step.")

        if not lessons:
            lessons.append("Task completed without major errors.")

        return lessons