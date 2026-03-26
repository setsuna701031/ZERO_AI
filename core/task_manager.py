from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_BLOCKED = "blocked"

VALID_TASK_STATUSES = {
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_BLOCKED,
}


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _make_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:8]}"


@dataclass
class Task:
    id: str
    title: str
    status: str = TASK_STATUS_PENDING
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskManager:
    """
    第一版 Task Tree 管理器

    設計原則：
    - root task 承載整體任務
    - 真正執行的是 leaf task（沒有 children 的 task）
    - 順序執行，不做並行
    - 父節點完成狀態由子節點收斂推導
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}
        self._root_order: List[str] = []

    # -------------------------------------------------------------------------
    # 建立 / 查詢
    # -------------------------------------------------------------------------
    def create_root_task(
        self,
        title: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        task_id = _make_task_id()
        task = Task(
            id=task_id,
            title=title,
            status=TASK_STATUS_PENDING,
            parent_id=None,
            meta=meta or {},
        )
        self._tasks[task_id] = task
        self._root_order.append(task_id)
        return task_id

    def add_subtask(
        self,
        parent_id: str,
        title: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        parent = self._require_task(parent_id)

        task_id = _make_task_id()
        task = Task(
            id=task_id,
            title=title,
            status=TASK_STATUS_PENDING,
            parent_id=parent_id,
            meta=meta or {},
        )

        self._tasks[task_id] = task
        parent.children.append(task_id)
        parent.updated_at = _utc_now_iso()

        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    def get_task_obj(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_children(self, task_id: str) -> List[Dict[str, Any]]:
        task = self._require_task(task_id)
        return [self._tasks[child_id].to_dict() for child_id in task.children]

    def get_parent(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._require_task(task_id)
        if task.parent_id is None:
            return None
        return self._tasks[task.parent_id].to_dict()

    def list_root_tasks(self) -> List[Dict[str, Any]]:
        return [self._tasks[root_id].to_dict() for root_id in self._root_order]

    def has_subtasks(self, task_id: str) -> bool:
        task = self._require_task(task_id)
        return len(task.children) > 0

    def is_leaf_task(self, task_id: str) -> bool:
        task = self._require_task(task_id)
        return len(task.children) == 0

    def count_tasks(self) -> int:
        return len(self._tasks)

    # -------------------------------------------------------------------------
    # 狀態更新
    # -------------------------------------------------------------------------
    def mark_task_pending(self, task_id: str) -> None:
        task = self._require_task(task_id)
        task.status = TASK_STATUS_PENDING
        task.updated_at = _utc_now_iso()

    def mark_task_running(self, task_id: str) -> None:
        task = self._require_task(task_id)
        task.status = TASK_STATUS_RUNNING
        task.updated_at = _utc_now_iso()

    def mark_task_completed(self, task_id: str, result: Optional[str] = None) -> None:
        task = self._require_task(task_id)
        task.status = TASK_STATUS_COMPLETED
        task.result = result
        task.error = None
        task.updated_at = _utc_now_iso()
        self._refresh_parent_chain(task_id)

    def mark_task_failed(self, task_id: str, error: Optional[str] = None) -> None:
        task = self._require_task(task_id)
        task.status = TASK_STATUS_FAILED
        task.error = error
        task.updated_at = _utc_now_iso()
        self._refresh_parent_chain(task_id)

    def mark_task_blocked(self, task_id: str, error: Optional[str] = None) -> None:
        task = self._require_task(task_id)
        task.status = TASK_STATUS_BLOCKED
        task.error = error
        task.updated_at = _utc_now_iso()
        self._refresh_parent_chain(task_id)

    def set_task_result(self, task_id: str, result: Optional[str]) -> None:
        task = self._require_task(task_id)
        task.result = result
        task.updated_at = _utc_now_iso()

    def set_task_error(self, task_id: str, error: Optional[str]) -> None:
        task = self._require_task(task_id)
        task.error = error
        task.updated_at = _utc_now_iso()

    # -------------------------------------------------------------------------
    # 可執行任務挑選
    # -------------------------------------------------------------------------
    def get_next_runnable_task(self, root_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        第一版規則：
        - 只挑 leaf task
        - 狀態必須是 pending
        - 依建立順序深度優先掃描
        """
        task_ids = self._collect_scan_order(root_id=root_id)
        for task_id in task_ids:
            task = self._tasks[task_id]
            if task.status != TASK_STATUS_PENDING:
                continue
            if not self._is_runnable_leaf(task):
                continue
            return task.to_dict()
        return None

    def get_all_leaf_tasks(self, root_id: Optional[str] = None) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        task_ids = self._collect_scan_order(root_id=root_id)
        for task_id in task_ids:
            task = self._tasks[task_id]
            if len(task.children) == 0:
                result.append(task.to_dict())
        return result

    # -------------------------------------------------------------------------
    # 樹狀狀態判定
    # -------------------------------------------------------------------------
    def is_task_tree_completed(self, root_id: str) -> bool:
        root = self._require_task(root_id)
        if root.status == TASK_STATUS_COMPLETED:
            return True

        descendants = self._collect_descendants(root_id)
        if not descendants:
            return root.status == TASK_STATUS_COMPLETED

        for task_id in descendants:
            task = self._tasks[task_id]
            if task.status != TASK_STATUS_COMPLETED:
                return False
        return True

    def is_task_tree_failed(self, root_id: str) -> bool:
        root = self._require_task(root_id)
        if root.status == TASK_STATUS_FAILED:
            return True

        descendants = self._collect_descendants(root_id)
        for task_id in descendants:
            if self._tasks[task_id].status == TASK_STATUS_FAILED:
                return True
        return False

    def get_root_id(self, task_id: str) -> str:
        current = self._require_task(task_id)
        while current.parent_id is not None:
            current = self._require_task(current.parent_id)
        return current.id

    def get_tree_snapshot(self, root_id: str) -> Dict[str, Any]:
        root = self._require_task(root_id)

        def build_node(task_id: str) -> Dict[str, Any]:
            task = self._tasks[task_id]
            data = task.to_dict()
            data["children_nodes"] = [build_node(child_id) for child_id in task.children]
            return data

        return build_node(root.id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "roots": list(self._root_order),
            "tasks": {task_id: task.to_dict() for task_id, task in self._tasks.items()},
        }

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        self._tasks.clear()
        self._root_order = list(data.get("roots", []))

        raw_tasks = data.get("tasks", {})
        for task_id, task_data in raw_tasks.items():
            self._tasks[task_id] = Task(
                id=task_data["id"],
                title=task_data["title"],
                status=task_data.get("status", TASK_STATUS_PENDING),
                parent_id=task_data.get("parent_id"),
                children=list(task_data.get("children", [])),
                result=task_data.get("result"),
                error=task_data.get("error"),
                meta=dict(task_data.get("meta", {})),
                created_at=task_data.get("created_at", _utc_now_iso()),
                updated_at=task_data.get("updated_at", _utc_now_iso()),
            )

    # -------------------------------------------------------------------------
    # 內部方法
    # -------------------------------------------------------------------------
    def _require_task(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        return task

    def _is_runnable_leaf(self, task: Task) -> bool:
        if len(task.children) > 0:
            return False
        if task.status != TASK_STATUS_PENDING:
            return False
        return True

    def _collect_scan_order(self, root_id: Optional[str] = None) -> List[str]:
        ordered: List[str] = []

        def walk(task_id: str) -> None:
            ordered.append(task_id)
            task = self._tasks[task_id]
            for child_id in task.children:
                walk(child_id)

        if root_id is not None:
            self._require_task(root_id)
            walk(root_id)
            return ordered

        for rid in self._root_order:
            walk(rid)
        return ordered

    def _collect_descendants(self, root_id: str) -> List[str]:
        root = self._require_task(root_id)
        result: List[str] = []

        def walk(task_id: str) -> None:
            task = self._tasks[task_id]
            for child_id in task.children:
                result.append(child_id)
                walk(child_id)

        walk(root.id)
        return result

    def _refresh_parent_chain(self, task_id: str) -> None:
        current = self._require_task(task_id)
        parent_id = current.parent_id

        while parent_id is not None:
            parent = self._require_task(parent_id)
            children = [self._tasks[child_id] for child_id in parent.children]

            if not children:
                parent.status = TASK_STATUS_COMPLETED
            else:
                child_statuses = {child.status for child in children}

                if TASK_STATUS_FAILED in child_statuses:
                    parent.status = TASK_STATUS_FAILED
                    failed_children = [child for child in children if child.status == TASK_STATUS_FAILED]
                    parent.error = failed_children[0].error if failed_children else parent.error

                elif TASK_STATUS_BLOCKED in child_statuses:
                    parent.status = TASK_STATUS_BLOCKED
                    blocked_children = [child for child in children if child.status == TASK_STATUS_BLOCKED]
                    parent.error = blocked_children[0].error if blocked_children else parent.error

                elif all(status == TASK_STATUS_COMPLETED for status in child_statuses):
                    parent.status = TASK_STATUS_COMPLETED
                    parent.error = None

                elif TASK_STATUS_RUNNING in child_statuses:
                    parent.status = TASK_STATUS_RUNNING

                else:
                    parent.status = TASK_STATUS_PENDING

            parent.updated_at = _utc_now_iso()
            parent_id = parent.parent_id