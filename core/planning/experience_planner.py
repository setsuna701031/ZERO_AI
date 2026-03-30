from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.memory_manager import MemoryManager


class ExperiencePlanner:
    """
    經驗型 Planner（第二版）
    - 先讀 memory
    - 找相似任務的成功步驟
    - 把成功步驟抽成模板
    - 再用目前 goal 重新實例化
    - 避免直接複製舊任務文字污染新任務
    """

    def __init__(self, memory_manager: Optional[MemoryManager] = None) -> None:
        self.memory_manager = memory_manager

    def plan(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> List[str]:
        goal = (user_input or "").strip()
        if not goal:
            return []

        planning_context = self._build_memory_context(goal)
        reused_steps = self._select_reusable_steps(goal, planning_context)

        if reused_steps:
            return reused_steps

        return self._build_default_plan(goal)

    def preview_context(self, user_input: str) -> Dict[str, Any]:
        goal = (user_input or "").strip()
        return self._build_memory_context(goal)

    # -------------------------------------------------------------------------
    # internal
    # -------------------------------------------------------------------------
    def _build_memory_context(self, goal: str) -> Dict[str, Any]:
        if self.memory_manager is None:
            return {
                "goal": goal,
                "similar_goals": [],
                "successful_steps": [],
                "lessons": [],
                "failed_notes": [],
                "source_count": 0,
                "source_memories": [],
            }

        return self.memory_manager.build_planning_context(goal=goal, limit=8)

    def _select_reusable_steps(
        self,
        goal: str,
        planning_context: Dict[str, Any],
    ) -> List[str]:
        successful_steps = planning_context.get("successful_steps", []) or []
        failed_notes = planning_context.get("failed_notes", []) or []

        cleaned_steps = self._normalize_step_list(successful_steps)
        if not cleaned_steps:
            return []

        # 先把舊步驟抽成「模板類型」
        step_templates = self._extract_step_templates(cleaned_steps)

        if not step_templates:
            return []

        filtered_templates: List[str] = []
        for template in step_templates:
            instantiated = self._render_step_template(template, goal)
            if self._looks_like_bad_step(instantiated, failed_notes):
                continue
            filtered_templates.append(template)

        if not filtered_templates:
            return []

        # 用目前的新 goal 重新生成步驟
        rendered_steps = [self._render_step_template(template, goal) for template in filtered_templates]

        if not self._has_validation_step(rendered_steps):
            rendered_steps.append(f"驗證結果：{goal}")

        return self._normalize_step_list(rendered_steps)[:8]

    def _build_default_plan(self, goal: str) -> List[str]:
        return [
            f"分析需求：{goal}",
            f"規劃執行步驟：{goal}",
            f"實作主要內容：{goal}",
            f"驗證結果：{goal}",
        ]

    # -------------------------------------------------------------------------
    # step template handling
    # -------------------------------------------------------------------------
    def _extract_step_templates(self, steps: List[str]) -> List[str]:
        """
        把歷史成功步驟轉成模板。
        例如：
            分析需求：幫我做一個簡單網站
        轉成：
            分析需求：{goal}
        """
        templates: List[str] = []

        for step in steps:
            category = self._detect_step_category(step)
            template = self._category_to_template(category)
            templates.append(template)

        templates = self._normalize_step_list(templates)

        # 若歷史資料太亂，至少保留基本流程
        if not templates:
            return []

        # 確保順序穩定：分析 -> 規劃 -> 實作 -> 驗證
        ordered = self._sort_templates(templates)
        return ordered

    def _detect_step_category(self, step: str) -> str:
        text = (step or "").strip()

        if not text:
            return "generic"

        if "分析" in text or "需求" in text:
            return "analyze"

        if "規劃" in text or "計畫" in text or "步驟" in text:
            return "plan"

        if "實作" in text or "建立" in text or "撰寫" in text or "生成" in text:
            return "implement"

        if "驗證" in text or "測試" in text or "確認" in text or "檢查" in text:
            return "verify"

        return "generic"

    def _category_to_template(self, category: str) -> str:
        mapping = {
            "analyze": "分析需求：{goal}",
            "plan": "規劃執行步驟：{goal}",
            "implement": "實作主要內容：{goal}",
            "verify": "驗證結果：{goal}",
            "generic": "執行任務：{goal}",
        }
        return mapping.get(category, "執行任務：{goal}")

    def _render_step_template(self, template: str, goal: str) -> str:
        return template.replace("{goal}", goal)

    def _sort_templates(self, templates: List[str]) -> List[str]:
        priority = {
            "分析需求：{goal}": 10,
            "規劃執行步驟：{goal}": 20,
            "實作主要內容：{goal}": 30,
            "驗證結果：{goal}": 40,
            "執行任務：{goal}": 50,
        }
        return sorted(templates, key=lambda item: priority.get(item, 999))

    # -------------------------------------------------------------------------
    # utilities
    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_step_list(steps: List[str]) -> List[str]:
        seen = set()
        result: List[str] = []

        for step in steps:
            text = str(step).strip()
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            result.append(text)

        return result

    @staticmethod
    def _has_validation_step(steps: List[str]) -> bool:
        keywords = ["驗證", "測試", "確認", "檢查"]
        for step in steps:
            if any(keyword in step for keyword in keywords):
                return True
        return False

    @staticmethod
    def _looks_like_bad_step(step: str, failed_notes: List[str]) -> bool:
        step_text = step.strip().lower()
        if not step_text:
            return True

        for note in failed_notes:
            note_text = str(note).lower()
            if step_text and step_text in note_text:
                return True

        return False