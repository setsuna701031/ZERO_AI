from __future__ import annotations

from typing import Any, Dict, List, Optional


class Planner:
    """
    ZERO Planner (memory-aware rules v1)

    先不碰複雜 LLM planner。
    先把：
    - task classification
    - lessons injection
    - precheck insertion
    - fallback preference
    做進來。
    """

    def plan(
        self,
        goal: str,
        lessons: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        goal_text = str(goal or "").strip()
        lowered = goal_text.lower()
        task_type = self._classify_task_type(goal_text)
        lessons = lessons or []

        memory_hints = self._build_memory_hints(lessons)
        recalled_actions = memory_hints["suggested_actions"]

        steps: List[Dict[str, Any]] = []

        steps.append(
            {
                "name": "analyze goal",
                "kind": "reason",
            }
        )

        for action in recalled_actions:
            steps.append(
                {
                    "name": f"memory precheck: {action}",
                    "kind": "reason",
                }
            )

        if task_type == "command":
            command_text = self._extract_command_from_goal(goal_text)

            steps.append(
                {
                    "name": "validate command target",
                    "kind": "reason",
                }
            )

            if memory_hints["prefer_command_tool"]:
                steps.append(
                    {
                        "name": "execute command tool",
                        "kind": "tool",
                        "tool_name": "command_tool",
                        "tool_args": {
                            "command": command_text,
                        },
                    }
                )
            else:
                steps.append(
                    {
                        "name": "execute command tool",
                        "kind": "tool",
                        "tool_name": "command_tool",
                        "tool_args": {
                            "command": command_text,
                        },
                    }
                )

            steps.append(
                {
                    "name": "collect command result",
                    "kind": "reason",
                }
            )

        elif task_type == "file":
            target_path = self._extract_file_target(goal_text)

            steps.append(
                {
                    "name": "verify file path",
                    "kind": "reason",
                }
            )
            steps.append(
                {
                    "name": "read file with workspace tool",
                    "kind": "tool",
                    "tool_name": "workspace_tool",
                    "tool_args": {
                        "action": "read_file",
                        "path": target_path,
                    },
                }
            )
            steps.append(
                {
                    "name": "summarize file handling",
                    "kind": "reason",
                }
            )

        else:
            steps.append(
                {
                    "name": "plan response",
                    "kind": "reason",
                }
            )
            steps.append(
                {
                    "name": "summarize outcome",
                    "kind": "reason",
                }
            )

        steps.append(
            {
                "name": "save result",
                "kind": "reason",
            }
        )

        return {
            "goal": goal_text,
            "task_type": task_type,
            "planner_version": "memory_aware_rules_v1",
            "steps": steps,
            "memory_context": {
                "lesson_count": len(lessons),
                "recalled_lesson_ids": [
                    str(item.get("lesson_id", "")).strip()
                    for item in lessons
                    if isinstance(item, dict)
                ],
                "recalled_actions": recalled_actions,
                "avoid_patterns": memory_hints["avoid_patterns"],
                "prefer_patterns": memory_hints["prefer_patterns"],
            },
            "signals": {
                "length": len(goal_text),
                "contains_path_hint": any(
                    x in lowered for x in ["\\", "/", ".py", ".json", ".txt", ".md"]
                ),
                "contains_command_hint": any(
                    x in lowered
                    for x in [
                        "cmd",
                        "command",
                        "執行",
                        "run ",
                        "echo ",
                        "dir ",
                        "copy ",
                        "move ",
                    ]
                ),
                "memory_lesson_count": len(lessons),
            },
        }

    # =========================================================
    # Memory Hints
    # =========================================================

    def _build_memory_hints(self, lessons: List[Dict[str, Any]]) -> Dict[str, Any]:
        suggested_actions: List[str] = []
        avoid_patterns: List[str] = []
        prefer_patterns: List[str] = []

        prefer_command_tool = False

        for lesson in lessons:
            if not isinstance(lesson, dict):
                continue

            outcome = str(lesson.get("outcome", "")).strip().lower()

            for item in lesson.get("suggested_next_time", []):
                clean = str(item).strip()
                if clean:
                    suggested_actions.append(clean)

            for item in lesson.get("what_failed", []):
                clean = str(item).strip()
                if clean:
                    avoid_patterns.append(clean)

            for item in lesson.get("what_worked", []):
                clean = str(item).strip()
                if clean:
                    prefer_patterns.append(clean)

            tools_used = lesson.get("tools_used", [])
            if outcome == "success" and isinstance(tools_used, list):
                if "command_tool" in [str(x).strip() for x in tools_used]:
                    prefer_command_tool = True

        return {
            "suggested_actions": self._dedupe(suggested_actions)[:5],
            "avoid_patterns": self._dedupe(avoid_patterns)[:5],
            "prefer_patterns": self._dedupe(prefer_patterns)[:5],
            "prefer_command_tool": prefer_command_tool,
        }

    # =========================================================
    # Task Type
    # =========================================================

    def _classify_task_type(self, goal: str) -> str:
        lowered = goal.lower()

        command_keywords = [
            "cmd",
            "command",
            "execute",
            "run ",
            "shell",
            "terminal",
            "powershell",
            "執行",
            "指令",
            "命令",
            "echo ",
            "dir ",
            "copy ",
            "move ",
        ]

        file_keywords = [
            ".py",
            ".json",
            ".txt",
            ".md",
            "file",
            "folder",
            "workspace",
            "path",
            "檔案",
            "資料夾",
            "路徑",
            "讀取",
            "讀檔",
        ]

        if any(keyword in lowered for keyword in command_keywords):
            return "command"

        if any(keyword in lowered for keyword in file_keywords):
            return "file"

        return "general"

    # =========================================================
    # Parsing
    # =========================================================

    def _extract_command_from_goal(self, goal: str) -> str:
        text = str(goal).strip()

        prefixes = [
            "execute command ",
            "run command ",
            "cmd:",
            "執行指令 ",
            "執行命令 ",
        ]

        lowered = text.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                return text[len(prefix):].strip() or "echo placeholder"

        return text

    def _extract_file_target(self, goal: str) -> str:
        tokens = str(goal).replace("\\", " \\ ").replace("/", " / ").split()

        for token in tokens:
            clean = token.strip().strip("\"'")
            if clean.endswith((".py", ".json", ".txt", ".md")):
                return clean

        return "task_memory.json"

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