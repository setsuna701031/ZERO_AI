# core/task/task_state.py

from typing import Dict, List


class TaskStatus:
    """
    Task 狀態定義
    """

    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING = "waiting"
    REPLANNING = "replanning"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @classmethod
    def all_status(cls) -> List[str]:
        return [
            cls.PENDING,
            cls.PLANNING,
            cls.RUNNING,
            cls.WAITING,
            cls.REPLANNING,
            cls.FAILED,
            cls.COMPLETED,
            cls.CANCELLED,
        ]


# 合法狀態轉移表
VALID_TRANSITIONS: Dict[str, List[str]] = {
    TaskStatus.PENDING: [
        TaskStatus.PLANNING,
        TaskStatus.CANCELLED,
    ],
    TaskStatus.PLANNING: [
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    ],
    TaskStatus.RUNNING: [
        TaskStatus.WAITING,
        TaskStatus.REPLANNING,
        TaskStatus.FAILED,
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
    ],
    TaskStatus.WAITING: [
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    ],
    TaskStatus.REPLANNING: [
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    ],
    TaskStatus.FAILED: [
        TaskStatus.REPLANNING,
        TaskStatus.CANCELLED,
    ],
    TaskStatus.COMPLETED: [],
    TaskStatus.CANCELLED: [],
}


def can_transition(from_status: str, to_status: str) -> bool:
    """
    檢查狀態是否可以轉移
    """
    if from_status not in VALID_TRANSITIONS:
        return False
    return to_status in VALID_TRANSITIONS[from_status]


def is_terminal(status: str) -> bool:
    """
    是否為終止狀態
    """
    return status in [
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
    ]


def validate_status(status: str) -> bool:
    """
    檢查 status 是否為合法狀態
    """
    return status in TaskStatus.all_status()