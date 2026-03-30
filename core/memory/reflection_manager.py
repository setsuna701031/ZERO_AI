from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

from core.memory.reflection_engine import ReflectionEngine


class ReflectionManager:
    """
    ReflectionManager
    -----------------
    職責：
    1. 呼叫 ReflectionEngine 進行分析
    2. 整理 task id / 檔名
    3. 將 reflection report 存成 json
    4. 提供讀取最近 report / 指定 report 的能力

    預設輸出路徑：
    data/reflections/
    """

    def __init__(
        self,
        reflection_dir: str = "data/reflections",
        engine: Optional[ReflectionEngine] = None,
    ) -> None:
        self.reflection_dir = reflection_dir
        self.engine = engine or ReflectionEngine()
        os.makedirs(self.reflection_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        plan: Any = None,
        runtime: Any = None,
        log: Any = None,
        result: Any = None,
    ) -> Dict[str, Any]:
        return self.engine.analyze(
            plan=plan,
            runtime=runtime,
            log=log,
            result=result,
        )

    def analyze_and_save(
        self,
        task_id: Optional[str] = None,
        plan: Any = None,
        runtime: Any = None,
        log: Any = None,
        result: Any = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        report = self.analyze(
            plan=plan,
            runtime=runtime,
            log=log,
            result=result,
        )

        final_task_id = self._resolve_task_id(task_id, runtime=runtime, result=result)
        timestamp = self._utc_now_compact()

        wrapped_report = {
            "task_id": final_task_id,
            "saved_at": self._utc_now_iso(),
            "reflection_version": "1.0",
            "meta": extra_meta or {},
            "report": report,
        }

        filename = f"{final_task_id}_{timestamp}.json"
        file_path = os.path.join(self.reflection_dir, filename)

        self._write_json(file_path, wrapped_report)
        wrapped_report["file_path"] = file_path
        return wrapped_report

    def list_reports(self) -> Dict[str, Any]:
        files = self._list_json_files_sorted()
        items = []

        for name in files:
            path = os.path.join(self.reflection_dir, name)
            info = self._safe_read_json(path)
            items.append(
                {
                    "filename": name,
                    "file_path": path,
                    "task_id": info.get("task_id"),
                    "saved_at": info.get("saved_at"),
                    "status": self._extract_status(info),
                    "score": self._extract_score(info),
                }
            )

        return {
            "ok": True,
            "count": len(items),
            "items": items,
        }

    def get_latest_report(self) -> Dict[str, Any]:
        files = self._list_json_files_sorted()
        if not files:
            return {
                "ok": False,
                "message": "目前沒有任何 reflection report。",
                "report": None,
            }

        latest_name = files[-1]
        file_path = os.path.join(self.reflection_dir, latest_name)
        data = self._safe_read_json(file_path)

        return {
            "ok": True,
            "filename": latest_name,
            "file_path": file_path,
            "report": data,
        }

    def get_report_by_filename(self, filename: str) -> Dict[str, Any]:
        safe_name = os.path.basename(filename)
        file_path = os.path.join(self.reflection_dir, safe_name)

        if not os.path.exists(file_path):
            return {
                "ok": False,
                "message": f"找不到 reflection report: {safe_name}",
                "report": None,
            }

        data = self._safe_read_json(file_path)
        return {
            "ok": True,
            "filename": safe_name,
            "file_path": file_path,
            "report": data,
        }

    def get_latest_report_for_task(self, task_id: str) -> Dict[str, Any]:
        normalized_task_id = self._sanitize_task_id(task_id)
        files = self._list_json_files_sorted()

        matched = [f for f in files if f.startswith(normalized_task_id + "_")]

        if not matched:
            return {
                "ok": False,
                "message": f"找不到 task_id={normalized_task_id} 的 reflection report。",
                "report": None,
            }

        latest_name = matched[-1]
        file_path = os.path.join(self.reflection_dir, latest_name)
        data = self._safe_read_json(file_path)

        return {
            "ok": True,
            "filename": latest_name,
            "file_path": file_path,
            "report": data,
        }

    def delete_report(self, filename: str) -> Dict[str, Any]:
        safe_name = os.path.basename(filename)
        file_path = os.path.join(self.reflection_dir, safe_name)

        if not os.path.exists(file_path):
            return {
                "ok": False,
                "message": f"找不到檔案: {safe_name}",
            }

        os.remove(file_path)
        return {
            "ok": True,
            "message": f"已刪除 reflection report: {safe_name}",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_task_id(
        self,
        task_id: Optional[str],
        runtime: Any = None,
        result: Any = None,
    ) -> str:
        if task_id:
            return self._sanitize_task_id(task_id)

        if isinstance(runtime, dict):
            runtime_task_id = runtime.get("task_id") or runtime.get("id")
            if runtime_task_id:
                return self._sanitize_task_id(runtime_task_id)

        if isinstance(result, dict):
            result_task_id = result.get("task_id") or result.get("id")
            if result_task_id:
                return self._sanitize_task_id(result_task_id)

        return "task_unknown"

    def _sanitize_task_id(self, value: str) -> str:
        text = str(value).strip()
        if not text:
            return "task_unknown"

        text = re.sub(r"[^\w\-]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text or "task_unknown"

    def _utc_now_iso(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _utc_now_compact(self) -> str:
        return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _write_json(self, file_path: str, data: Dict[str, Any]) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _safe_read_json(self, file_path: str) -> Dict[str, Any]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            return {
                "task_id": None,
                "saved_at": None,
                "report": {
                    "ok": False,
                    "summary": f"讀取 reflection 檔案失敗: {exc}",
                    "score": 0,
                    "status": "broken",
                    "issues": [
                        {
                            "level": "critical",
                            "code": "reflection_file_read_failed",
                            "message": str(exc),
                        }
                    ],
                    "strengths": [],
                    "suggestions": [],
                    "metrics": {},
                },
            }

    def _list_json_files_sorted(self) -> list[str]:
        if not os.path.exists(self.reflection_dir):
            return []

        files = [
            name
            for name in os.listdir(self.reflection_dir)
            if name.lower().endswith(".json")
        ]
        files.sort()
        return files

    def _extract_status(self, wrapped_report: Dict[str, Any]) -> Optional[str]:
        report = wrapped_report.get("report") or {}
        return report.get("status")

    def _extract_score(self, wrapped_report: Dict[str, Any]) -> Optional[int]:
        report = wrapped_report.get("report") or {}
        return report.get("score")


if __name__ == "__main__":
    manager = ReflectionManager()

    demo_plan = {
        "goal": "查詢資料並完成輸出",
        "steps": [
            "接收任務",
            "規劃步驟",
            "呼叫工具",
            "整理答案",
            "驗證結果",
        ],
    }

    demo_runtime = {
        "task_id": "demo_task_001",
        "status": "success",
        "duration_sec": 4.2,
        "executed_steps": 5,
        "failed_steps": 0,
        "retried_steps": 1,
    }

    demo_log = [
        {"level": "info", "message": "task started"},
        {"level": "warning", "message": "tool timeout, retry once"},
        {"level": "info", "message": "tool success"},
        {"level": "info", "message": "task finished"},
    ]

    demo_result = {
        "task_id": "demo_task_001",
        "success": True,
        "status": "completed",
        "final_output": "已完成查詢並整理答案",
        "error": None,
    }

    saved = manager.analyze_and_save(
        task_id="demo_task_001",
        plan=demo_plan,
        runtime=demo_runtime,
        log=demo_log,
        result=demo_result,
        extra_meta={"source": "manual_test"},
    )

    print(json.dumps(saved, ensure_ascii=False, indent=2))