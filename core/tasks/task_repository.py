from __future__ import annotations

import copy
import json
import os
import time
from typing import Any, Dict, List, Optional, Set

from core.tasks.task_paths import TaskPathManager


class TaskRepository:
    """
    ZERO Task Repository (DAG Enabled)

    這版重點：
    1. 保留外部傳進來的 status，不再強制洗成 queued
    2. 保留 depends_on，不再在 create_task 時被舊邏輯覆蓋
    3. 若沒有顯式 status，才根據 depends_on 自動推導：
       - 有依賴 => blocked
       - 無依賴 => queued
    4. DAG 解鎖時同時接受 done / finished
    """

    COMPLETED_STATUSES: Set[str] = {
        "done",
        "finished",
    }

    def __init__(self, db_path: str = "workspace/tasks.json") -> None:
        self.db_path = os.path.abspath(db_path)
        self.workspace_root = os.path.dirname(self.db_path)
        self.path_manager = TaskPathManager(workspace_root=self.workspace_root)
        self.path_manager.ensure_workspace()

        self.tasks: List[Dict[str, Any]] = []
        self.load()

    # ============================================================
    # file io
    # ============================================================

    def load(self) -> None:
        if not os.path.exists(self.db_path):
            self.tasks = []
            self.save()
            return

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self.tasks = []
            return

        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            raw_tasks = data["tasks"]
        elif isinstance(data, list):
            raw_tasks = data
        else:
            raw_tasks = []

        normalized: List[Dict[str, Any]] = []
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            try:
                normalized.append(self._normalize_task(item))
            except Exception:
                continue

        self.tasks = normalized

    def reload(self) -> None:
        self.load()

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        normalized: List[Dict[str, Any]] = []
        for task in self.tasks:
            if not isinstance(task, dict):
                continue
            try:
                normalized.append(self._normalize_task(task))
            except Exception:
                continue

        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(
                {"tasks": normalized},
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ============================================================
    # DAG helpers
    # ============================================================

    def _build_graph(self) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {}
        for task in self.tasks:
            tid = str(task.get("task_id") or "").strip()
            if not tid:
                continue
            deps = self._normalize_depends_on(task.get("depends_on", []))
            graph[tid] = deps
        return graph

    def _detect_cycle(self, graph: Dict[str, List[str]]) -> bool:
        visited: Set[str] = set()
        stack: Set[str] = set()

        def visit(node: str) -> bool:
            if node in stack:
                return True
            if node in visited:
                return False

            visited.add(node)
            stack.add(node)

            for dep in graph.get(node, []):
                if dep not in graph:
                    continue
                if visit(dep):
                    return True

            stack.remove(node)
            return False

        for node in graph:
            if visit(node):
                return True
        return False

    def _check_dependencies_exist(self, depends_on: List[str]) -> bool:
        ids = {str(t.get("task_id")) for t in self.tasks if t.get("task_id")}
        for dep in depends_on:
            if dep not in ids:
                return False
        return True

    def _normalize_depends_on(self, depends_on: Any) -> List[str]:
        if not isinstance(depends_on, list):
            return []

        result: List[str] = []
        seen: Set[str] = set()

        for dep in depends_on:
            dep_id = str(dep).strip()
            if not dep_id:
                continue
            if dep_id in seen:
                continue
            seen.add(dep_id)
            result.append(dep_id)

        return result

    def _resolve_default_status(self, explicit_status: Any, depends_on: List[str]) -> str:
        status = str(explicit_status or "").strip().lower()
        if status:
            return status

        if depends_on:
            return "blocked"

        return "queued"

    def _normalize_history(self, history: Any, status: str) -> List[str]:
        if isinstance(history, list):
            cleaned = [str(x).strip() for x in history if str(x).strip()]
        else:
            cleaned = []

        if not cleaned:
            return [status]

        return cleaned

    def _is_dependency_completed(self, status: Any) -> bool:
        return str(status or "").strip().lower() in self.COMPLETED_STATUSES

    def _refresh_blocked_status(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        只在 status 為 queued / blocked 時，自動和 depends_on 對齊。
        done / finished / running / failed 之類的狀態不主動改。
        """
        result = copy.deepcopy(task)
        task_map = {t["task_id"]: t for t in self.tasks if "task_id" in t}

        deps = self._normalize_depends_on(result.get("depends_on", []))
        current_status = str(result.get("status", "")).strip().lower()

        if current_status not in {"queued", "blocked"}:
            return result

        if not deps:
            result["status"] = "queued"
            return result

        all_done = True
        for dep in deps:
            dep_task = task_map.get(dep)
            if not dep_task:
                all_done = False
                break
            if not self._is_dependency_completed(dep_task.get("status")):
                all_done = False
                break

        result["status"] = "queued" if all_done else "blocked"
        return result

    # ============================================================
    # basic repo api
    # ============================================================

    def list_tasks(self) -> List[Dict[str, Any]]:
        self.reload()

        refreshed: List[Dict[str, Any]] = []
        changed = False

        for task in self.tasks:
            updated = self._refresh_blocked_status(task)
            refreshed.append(updated)
            if updated.get("status") != task.get("status"):
                changed = True

        if changed:
            self.tasks = refreshed
            self.save()

        return copy.deepcopy(refreshed)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        self.reload()

        for task in self.tasks:
            if task.get("task_id") == task_id:
                updated = self._refresh_blocked_status(task)
                if updated.get("status") != task.get("status"):
                    for i, item in enumerate(self.tasks):
                        if item.get("task_id") == task_id:
                            self.tasks[i] = updated
                            self.save()
                            break
                return copy.deepcopy(updated)

        return None

    def add_task(self, task: Dict[str, Any]) -> bool:
        self.reload()

        normalized = self._normalize_task(task)
        task_id = normalized["task_id"]

        if self._find_task_ref(task_id):
            return False

        depends_on = self._normalize_depends_on(normalized.get("depends_on", []))
        normalized["depends_on"] = depends_on

        if not self._check_dependencies_exist(depends_on):
            raise ValueError("depends_on task not found")

        self.tasks.append(normalized)
        graph = self._build_graph()
        if self._detect_cycle(graph):
            self.tasks.pop()
            raise ValueError("DAG cycle detected")

        normalized = self._refresh_blocked_status(normalized)
        self.tasks[-1] = normalized

        self.save()
        return True

    def create_task(
        self,
        task: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        self.reload()

        if isinstance(task, dict):
            return self.add_task(task)

        goal = str(kwargs.get("goal") or "").strip()
        if not goal:
            return False

        task_id = str(
            kwargs.get("task_id")
            or f"task_{int(time.time() * 1000)}"
        ).strip()

        depends_on = self._normalize_depends_on(kwargs.get("depends_on", []))
        status = self._resolve_default_status(kwargs.get("status"), depends_on)
        history = self._normalize_history(kwargs.get("history"), status)

        raw_task: Dict[str, Any] = {
            "task_id": task_id,
            "title": str(kwargs.get("title") or goal),
            "goal": goal,
            "status": status,
            "priority": int(kwargs.get("priority", 0)),
            "depends_on": depends_on,
            "history": history,
        }

        return self.add_task(raw_task)

    def upsert_task(self, task: Dict[str, Any]) -> bool:
        self.reload()

        normalized = self._normalize_task(task)
        task_id = normalized["task_id"]

        depends_on = self._normalize_depends_on(normalized.get("depends_on", []))
        normalized["depends_on"] = depends_on

        if depends_on and not self._check_dependencies_exist(depends_on):
            own_id_only = [dep for dep in depends_on if dep != task_id]
            if not self._check_dependencies_exist(own_id_only):
                raise ValueError("depends_on task not found")

        existing_index = None
        for i, existing in enumerate(self.tasks):
            if existing.get("task_id") == task_id:
                existing_index = i
                break

        if existing_index is not None:
            old_task = self.tasks[existing_index]
            self.tasks[existing_index] = normalized

            graph = self._build_graph()
            if self._detect_cycle(graph):
                self.tasks[existing_index] = old_task
                raise ValueError("DAG cycle detected")

            self.tasks[existing_index] = self._refresh_blocked_status(normalized)
            self.save()
            return True

        self.tasks.append(normalized)
        graph = self._build_graph()
        if self._detect_cycle(graph):
            self.tasks.pop()
            raise ValueError("DAG cycle detected")

        self.tasks[-1] = self._refresh_blocked_status(normalized)
        self.save()
        return True

    def delete_task(self, task_id: str) -> bool:
        self.reload()

        self.tasks = [t for t in self.tasks if t.get("task_id") != task_id]
        self.save()
        return True

    # ============================================================
    # scheduler api
    # ============================================================

    def get_ready_tasks(self) -> List[Dict[str, Any]]:
        """
        只回傳依賴已完成且可進入執行的任務
        """
        self.reload()

        refreshed: List[Dict[str, Any]] = []
        changed = False
        for i, task in enumerate(self.tasks):
            updated = self._refresh_blocked_status(task)
            refreshed.append(updated)
            if updated.get("status") != task.get("status"):
                self.tasks[i] = updated
                changed = True

        if changed:
            self.save()

        ready: List[Dict[str, Any]] = []
        for task in refreshed:
            if str(task.get("status", "")).strip().lower() != "queued":
                continue
            ready.append(copy.deepcopy(task))

        return ready

    # ============================================================
    # normalization
    # ============================================================

    def _normalize_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            raise TypeError("task must be dict")

        task_id = str(task.get("task_id") or "").strip()
        if not task_id:
            raise ValueError("task missing task_id")

        depends_on = self._normalize_depends_on(task.get("depends_on", []))
        status = self._resolve_default_status(task.get("status"), depends_on)
        history = self._normalize_history(task.get("history"), status)

        enriched = self.path_manager.enrich_task(copy.deepcopy(task))

        normalized = {
            "task_id": task_id,
            "title": str(enriched.get("title", task.get("title", ""))),
            "goal": str(enriched.get("goal", task.get("goal", ""))),
            "status": status,
            "priority": int(enriched.get("priority", task.get("priority", 0))),
            "depends_on": copy.deepcopy(depends_on),
            "history": copy.deepcopy(history),
            "workspace_dir": str(enriched.get("workspace_dir", "")),
            "task_dir": str(enriched.get("task_dir", "")),
        }

        return normalized

    # ============================================================
    # internal helpers
    # ============================================================

    def _find_task_ref(self, task_id: str) -> Optional[Dict[str, Any]]:
        for task in self.tasks:
            if task.get("task_id") == task_id:
                return task
        return None