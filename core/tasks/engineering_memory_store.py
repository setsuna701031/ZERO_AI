from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path
from typing import Any, Mapping


STORE_SCHEMA = "zero.engineering_task.memory_store.v1"
RECORD_SCHEMA = "zero.engineering_task.memory_record.v1"
RETRIEVAL_SCHEMA = "zero.engineering_task.memory_retrieval.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_state_id(value: Any) -> str:
    text = _clean_text(value, "engineering_task")
    safe = []
    for char in text:
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("_")
    cleaned = "".join(safe).strip("._-")
    return cleaned[:120] or "engineering_task"


def _tokens(value: Any) -> list[str]:
    text = str(value or "").lower()
    seen: set[str] = set()
    result: list[str] = []
    for token in re.findall(r"[a-z0-9_]+", text):
        if len(token) < 3 or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def _record_text(record: Mapping[str, Any]) -> str:
    parts = [
        record.get("task_id"),
        record.get("goal"),
        record.get("selected_task"),
        record.get("execution_order"),
        record.get("observations"),
        record.get("decisions"),
        record.get("replans"),
        record.get("prioritization_data"),
        record.get("acceptance_criteria"),
        record.get("result_summary"),
    ]
    return " ".join(json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item or "") for item in parts)


def _keyword_score(query_tokens: set[str], record_tokens: set[str]) -> int:
    return len(query_tokens & record_tokens)


def _goal_similarity(query_tokens: set[str], record_tokens: set[str]) -> float:
    if not query_tokens or not record_tokens:
        return 0.0
    union = query_tokens | record_tokens
    return len(query_tokens & record_tokens) / len(union)


class EngineeringMemoryStore:
    """Persistence for EngineeringTaskRunner execution knowledge.

    The store is state-only. It records task runner result knowledge under the
    existing work-package workspace area and does not execute, plan, mutate
    source files, or bypass the AER work-package path.
    """

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)
        self.path = self.repo_root / "workspace" / "work_packages" / "engineering_memory_store.json"

    def _read_store(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": STORE_SCHEMA, "records": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"schema": STORE_SCHEMA, "records": []}
        if not isinstance(data, dict):
            return {"schema": STORE_SCHEMA, "records": []}
        records = data.get("records")
        if not isinstance(records, list):
            records = []
        return {"schema": STORE_SCHEMA, "records": [dict(item) for item in records if isinstance(item, Mapping)]}

    def _write_store(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def save_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _clean_text(record.get("task_id"), "engineering_task")
        payload = {
            "schema": RECORD_SCHEMA,
            "memory_id": _clean_text(record.get("memory_id"), f"engineering-memory-{_safe_state_id(task_id)}"),
            "task_id": task_id,
            "goal": _clean_text(record.get("goal"), task_id),
            "selected_task": copy.deepcopy(record.get("selected_task") if isinstance(record.get("selected_task"), Mapping) else {}),
            "execution_order": copy.deepcopy(record.get("execution_order") if isinstance(record.get("execution_order"), list) else []),
            "observations": copy.deepcopy(record.get("observations") if isinstance(record.get("observations"), list) else []),
            "decisions": copy.deepcopy(record.get("decisions") if isinstance(record.get("decisions"), list) else []),
            "replans": copy.deepcopy(record.get("replans") if isinstance(record.get("replans"), list) else []),
            "prioritization_data": copy.deepcopy(record.get("prioritization_data") if isinstance(record.get("prioritization_data"), Mapping) else {}),
            "acceptance_criteria": copy.deepcopy(record.get("acceptance_criteria") if isinstance(record.get("acceptance_criteria"), list) else []),
            "result_summary": copy.deepcopy(record.get("result_summary") if isinstance(record.get("result_summary"), Mapping) else {}),
            "status": _clean_text(record.get("status"), "completed"),
            "ok": bool(record.get("ok", True)),
            "created_at": float(record.get("created_at") or time.time()),
        }
        payload["keywords"] = _tokens(_record_text(payload))

        store = self._read_store()
        records = [item for item in store["records"] if str(item.get("memory_id")) != payload["memory_id"]]
        records.append(payload)
        store["records"] = sorted(records, key=lambda item: str(item.get("memory_id") or ""))
        store["updated_at"] = time.time()
        self._write_store(store)
        return copy.deepcopy(payload)

    def load_relevant_memory(self, *, goal: str, limit: int = 5) -> dict[str, Any]:
        query_tokens = set(_tokens(goal))
        scored: list[dict[str, Any]] = []
        for record in self._read_store()["records"]:
            if not bool(record.get("ok", True)) or str(record.get("status") or "").lower() == "blocked":
                continue
            record_tokens = set(record.get("keywords") if isinstance(record.get("keywords"), list) else _tokens(_record_text(record)))
            keyword_score = _keyword_score(query_tokens, record_tokens)
            goal_similarity = _goal_similarity(query_tokens, set(_tokens(record.get("goal"))))
            if keyword_score <= 0 and goal_similarity <= 0:
                continue
            scored.append(
                {
                    "record": copy.deepcopy(record),
                    "keyword_score": keyword_score,
                    "goal_similarity": goal_similarity,
                    "score": keyword_score + goal_similarity,
                }
            )

        scored.sort(
            key=lambda item: (
                -float(item["score"]),
                str(_as_mapping(item["record"]).get("task_id") or ""),
                str(_as_mapping(item["record"]).get("memory_id") or ""),
            )
        )
        matches = scored[: max(0, int(limit))]
        return {
            "schema": RETRIEVAL_SCHEMA,
            "goal": _clean_text(goal),
            "query_keywords": sorted(query_tokens),
            "record_count": len(matches),
            "records": [copy.deepcopy(item["record"]) for item in matches],
            "matches": copy.deepcopy(matches),
            "deterministic": True,
            "retrieval_methods": ["keyword", "goal_similarity"],
            "ignored_blocked_records": True,
            "store_path": str(self.path),
        }


def build_memory_record_from_result_bundle(result_bundle: Mapping[str, Any]) -> dict[str, Any]:
    requirement_summary = _as_mapping(result_bundle.get("requirement_summary"))
    plan = _as_mapping(result_bundle.get("multi_step_plan"))
    package_id = _clean_text(result_bundle.get("package_id") or requirement_summary.get("package_id"), "engineering_task")
    status = _clean_text(result_bundle.get("status"), "completed" if bool(result_bundle.get("ok")) else "blocked")
    return {
        "task_id": package_id,
        "goal": _clean_text(plan.get("goal") or requirement_summary.get("goal"), package_id),
        "selected_task": copy.deepcopy(result_bundle.get("selected_task") if isinstance(result_bundle.get("selected_task"), Mapping) else {}),
        "execution_order": copy.deepcopy(result_bundle.get("execution_order") if isinstance(result_bundle.get("execution_order"), list) else []),
        "observations": copy.deepcopy(result_bundle.get("observations") if isinstance(result_bundle.get("observations"), list) else []),
        "decisions": copy.deepcopy(result_bundle.get("decisions") if isinstance(result_bundle.get("decisions"), list) else []),
        "replans": copy.deepcopy(result_bundle.get("replans") if isinstance(result_bundle.get("replans"), list) else []),
        "prioritization_data": copy.deepcopy(result_bundle.get("prioritization_data") if isinstance(result_bundle.get("prioritization_data"), Mapping) else {}),
        "acceptance_criteria": copy.deepcopy(result_bundle.get("acceptance_criteria") if isinstance(result_bundle.get("acceptance_criteria"), list) else []),
        "result_summary": {
            "ok": bool(result_bundle.get("ok")),
            "status": status,
            "package_id": package_id,
            "changed_files": copy.deepcopy(_as_mapping(result_bundle.get("change_set")).get("files") if isinstance(_as_mapping(result_bundle.get("change_set")).get("files"), list) else []),
            "stopped_reason": _clean_text(result_bundle.get("stopped_reason")),
            "verification_ok": bool(_as_mapping(result_bundle.get("verification_result")).get("ok")),
        },
        "status": status,
        "ok": bool(result_bundle.get("ok")),
    }


__all__ = [
    "EngineeringMemoryStore",
    "RECORD_SCHEMA",
    "RETRIEVAL_SCHEMA",
    "STORE_SCHEMA",
    "build_memory_record_from_result_bundle",
]
