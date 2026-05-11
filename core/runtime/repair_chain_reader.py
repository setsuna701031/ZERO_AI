from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional


class RepairChainReader:
    """
    ZERO Repair Chain Reader.

    Purpose:
    - Read repair-chain orchestration metadata from runtime_state.json.
    - Return a compact summary for scheduler / planner / UI layers.
    - Keep scheduler.py from directly parsing large runtime_state payloads.

    This reader is intentionally read-only.  It never mutates task state, never
    writes files, and never runs execution.
    """

    def __init__(self, workspace_root: str = "workspace") -> None:
        self.workspace_root = os.path.abspath(workspace_root)

    def read_task_runtime_state(
        self,
        task: Dict[str, Any],
        runtime_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if isinstance(runtime_state, dict):
            return copy.deepcopy(runtime_state)

        runtime_state_file = self._runtime_state_file_from_task(task)
        if not runtime_state_file or not os.path.exists(runtime_state_file):
            return {}

        return self._read_json(runtime_state_file, default={})

    def read_summary(
        self,
        task: Dict[str, Any],
        runtime_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = self.read_task_runtime_state(task=task, runtime_state=runtime_state)
        if not isinstance(state, dict):
            state = {}

        repair_context = state.get("repair_context")
        if not isinstance(repair_context, dict):
            repair_context = {}

        engineering_execution = repair_context.get("engineering_execution")
        if not isinstance(engineering_execution, dict):
            engineering_execution = {}

        last_chain = repair_context.get("last_repair_chain_consistency")
        if not isinstance(last_chain, dict):
            last_chain = self._find_latest_chain_summary_from_execution_log(state)

        history = repair_context.get("repair_chain_consistency_history")
        if not isinstance(history, list):
            history = self._extract_chain_history_from_summary(last_chain)

        compact = self._compact_summary(
            task=task,
            runtime_state=state,
            repair_context=repair_context,
            engineering_execution=engineering_execution,
            last_chain=last_chain,
            history=history,
        )
        return compact

    def read_summary_from_file(self, runtime_state_file: str) -> Dict[str, Any]:
        state = self._read_json(runtime_state_file, default={})
        return self.read_summary(task={}, runtime_state=state)

    def is_chain_replay_verified(
        self,
        task: Dict[str, Any],
        runtime_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        summary = self.read_summary(task=task, runtime_state=runtime_state)
        return str(summary.get("chain_status") or "") == "chain_replay_verified"

    def has_chain_failure_or_rollback(
        self,
        task: Dict[str, Any],
        runtime_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        summary = self.read_summary(task=task, runtime_state=runtime_state)
        if str(summary.get("chain_status") or "") == "chain_has_rollback_or_failure":
            return True
        return bool(summary.get("failed_steps") or summary.get("rolled_back_steps"))

    def _compact_summary(
        self,
        *,
        task: Dict[str, Any],
        runtime_state: Dict[str, Any],
        repair_context: Dict[str, Any],
        engineering_execution: Dict[str, Any],
        last_chain: Dict[str, Any],
        history: List[Any],
    ) -> Dict[str, Any]:
        chain_status = str(
            last_chain.get("status")
            or engineering_execution.get("repair_chain_consistency_status")
            or ""
        ).strip()

        chain_id = str(
            last_chain.get("chain_id")
            or engineering_execution.get("repair_chain_id")
            or task.get("repair_chain_id")
            or task.get("task_id")
            or task.get("task_name")
            or runtime_state.get("task_id")
            or runtime_state.get("task_name")
            or ""
        ).strip()

        total_steps = self._safe_int(
            last_chain.get("total_steps"),
            self._safe_int(engineering_execution.get("repair_chain_total_steps"), 0),
        )
        replay_verified_steps = self._safe_int(
            last_chain.get("replay_verified_steps"),
            self._safe_int(engineering_execution.get("repair_chain_replay_verified_steps"), 0),
        )
        failed_steps = self._safe_int(
            last_chain.get("failed_steps"),
            self._safe_int(engineering_execution.get("repair_chain_failed_steps"), 0),
        )
        rolled_back_steps = self._safe_int(last_chain.get("rolled_back_steps"), 0)
        verified_steps = self._safe_int(last_chain.get("verified_steps"), 0)

        latest_step = last_chain.get("latest_step")
        if not isinstance(latest_step, dict):
            latest_step = {}

        return {
            "ok": bool(chain_status),
            "schema": "zero.repair_chain_reader.summary.v1",
            "task_id": str(task.get("task_id") or runtime_state.get("task_id") or ""),
            "task_name": str(task.get("task_name") or runtime_state.get("task_name") or ""),
            "runtime_status": str(runtime_state.get("status") or ""),
            "chain_id": chain_id,
            "chain_status": chain_status,
            "is_replay_verified": chain_status == "chain_replay_verified",
            "has_failure_or_rollback": chain_status == "chain_has_rollback_or_failure" or failed_steps > 0 or rolled_back_steps > 0,
            "total_steps": total_steps,
            "verified_steps": verified_steps,
            "replay_verified_steps": replay_verified_steps,
            "failed_steps": failed_steps,
            "rolled_back_steps": rolled_back_steps,
            "governed_mutation_steps": self._safe_int(last_chain.get("governed_mutation_steps"), 0),
            "autonomous_self_repair_steps": self._safe_int(last_chain.get("autonomous_self_repair_steps"), 0),
            "history_len": len(history),
            "latest_step": copy.deepcopy(latest_step),
            "engineering_execution": {
                "repair_chain_consistency_status": str(engineering_execution.get("repair_chain_consistency_status") or ""),
                "repair_chain_id": str(engineering_execution.get("repair_chain_id") or ""),
                "repair_chain_total_steps": engineering_execution.get("repair_chain_total_steps"),
                "repair_chain_replay_verified_steps": engineering_execution.get("repair_chain_replay_verified_steps"),
                "repair_chain_failed_steps": engineering_execution.get("repair_chain_failed_steps"),
            },
        }

    def _find_latest_chain_summary_from_execution_log(self, runtime_state: Dict[str, Any]) -> Dict[str, Any]:
        execution_log = runtime_state.get("execution_log")
        if not isinstance(execution_log, list):
            return {}

        latest: Dict[str, Any] = {}
        for item in execution_log:
            if not isinstance(item, dict):
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                continue
            summary = result.get("repair_chain_consistency")
            if isinstance(summary, dict):
                latest = copy.deepcopy(summary)

        return latest

    def _extract_chain_history_from_summary(self, summary: Dict[str, Any]) -> List[Any]:
        if not isinstance(summary, dict):
            return []
        history = summary.get("history")
        if isinstance(history, list):
            return copy.deepcopy(history)
        latest = summary.get("latest_step")
        if isinstance(latest, dict):
            return [copy.deepcopy(latest)]
        return []

    def _runtime_state_file_from_task(self, task: Dict[str, Any]) -> str:
        if not isinstance(task, dict):
            return ""

        for key in ("runtime_state_file", "runtime_state_path"):
            value = task.get(key)
            if isinstance(value, str) and value.strip():
                return os.path.abspath(value.strip())

        task_dir = task.get("task_dir")
        if isinstance(task_dir, str) and task_dir.strip():
            task_dir_text = task_dir.strip()
            if os.path.isabs(task_dir_text):
                return os.path.join(task_dir_text, "runtime_state.json")
            return os.path.abspath(task_dir_text + os.sep + "runtime_state.json")

        task_id = str(task.get("task_id") or task.get("task_name") or "").strip()
        if task_id:
            return os.path.join(self.workspace_root, "tasks", task_id, "runtime_state.json")

        return ""

    def _read_json(self, path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if data is not None else copy.deepcopy(default)
        except Exception:
            return copy.deepcopy(default)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)


def read_repair_chain_summary(
    task: Dict[str, Any],
    runtime_state: Optional[Dict[str, Any]] = None,
    workspace_root: str = "workspace",
) -> Dict[str, Any]:
    return RepairChainReader(workspace_root=workspace_root).read_summary(
        task=task,
        runtime_state=runtime_state,
    )


__all__ = [
    "RepairChainReader",
    "read_repair_chain_summary",
]
