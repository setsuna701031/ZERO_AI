import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class TaskMemory:
    """
    ZERO Task Memory
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        os.makedirs(self.workspace_root, exist_ok=True)

        self.memory_file = os.path.join(self.workspace_root, "task_memory.json")

        if not os.path.exists(self.memory_file):
            self._write_data([])

    def add_record(
        self,
        user_input: str,
        mode: str,
        summary: str,
        success: bool,
        plan: Optional[Dict[str, Any]] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        changed_files: Optional[List[str]] = None,
        evidence: Optional[List[str]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        records = self._read_data()

        record = {
            "id": self._generate_record_id(records),
            "timestamp": self._now_iso(),
            "user_input": user_input,
            "mode": mode,
            "summary": summary,
            "success": success,
            "plan": plan or {},
            "steps": steps or [],
            "changed_files": changed_files or [],
            "evidence": evidence or [],
            "error": error,
        }

        records.append(record)
        self._write_data(records)

        return {
            "ok": True,
            "summary": f"Task record added: {record['id']}",
            "record_id": record["id"],
            "record": record,
        }

    def get_all_records(self) -> Dict[str, Any]:
        records = self._read_data()
        return {
            "ok": True,
            "count": len(records),
            "records": records,
            "summary": f"Loaded {len(records)} task record(s).",
        }

    def get_recent_records(self, limit: int = 5) -> Dict[str, Any]:
        records = self._read_data()
        safe_limit = max(1, int(limit))
        recent = records[-safe_limit:]

        return {
            "ok": True,
            "count": len(recent),
            "records": recent,
            "summary": f"Loaded {len(recent)} recent task record(s).",
        }

    def get_record_by_id(self, record_id: str) -> Dict[str, Any]:
        records = self._read_data()

        for record in records:
            if str(record.get("id")) == str(record_id):
                return {
                    "ok": True,
                    "record": record,
                    "summary": f"Found task record: {record_id}",
                }

        return {
            "ok": False,
            "error": "record_not_found",
            "summary": f"Task record not found: {record_id}",
        }

    def clear(self) -> Dict[str, Any]:
        self._write_data([])
        return {
            "ok": True,
            "summary": "Task memory cleared."
        }

    def get_last_record(self) -> Dict[str, Any]:
        records = self._read_data()

        if not records:
            return {
                "ok": False,
                "error": "no_records",
                "summary": "No task records found."
            }

        record = records[-1]
        return {
            "ok": True,
            "record": record,
            "summary": f"Loaded last task record: {record.get('id')}",
        }

    def _read_data(self) -> List[Dict[str, Any]]:
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                return data

            return []
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            return []
        except Exception:
            return []

    def _write_data(self, data: List[Dict[str, Any]]) -> None:
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _generate_record_id(self, records: List[Dict[str, Any]]) -> str:
        next_index = len(records) + 1
        return f"task_{next_index:04d}"

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")