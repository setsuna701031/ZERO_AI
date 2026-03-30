# core/memory/context_builder.py

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def _compact_text(text: Any, max_len: int = 500) -> str:
    s = _safe_str(text).strip()
    if not s:
        return ""
    s = " ".join(s.split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _now_ts() -> float:
    return time.time()


@dataclass
class ContextSection:
    name: str
    content: Any
    priority: int = 100


@dataclass
class ContextPacket:
    user_input: str
    mode: str = "chat"
    task_id: Optional[str] = None
    summary: str = ""
    sections: List[ContextSection] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_input": self.user_input,
            "mode": self.mode,
            "task_id": self.task_id,
            "summary": self.summary,
            "sections": [
                {
                    "name": sec.name,
                    "content": sec.content,
                    "priority": sec.priority,
                }
                for sec in sorted(self.sections, key=lambda x: x.priority)
            ],
            "meta": self.meta,
        }

    def to_json(self, ensure_ascii: bool = False, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii, indent=indent)


class ContextBuilder:
    """
    通用 context builder。

    設計原則：
    1. 不綁死任何特定 memory store 實作
    2. 盡量 duck-typing，避免你現有專案一改就炸
    3. 先提供穩定的 context packet，下一步再接進 agent loop
    """

    def __init__(
        self,
        memory_store: Optional[Any] = None,
        runtime_store: Optional[Any] = None,
        max_memory_items: int = 5,
        max_recent_events: int = 5,
        max_item_text_len: int = 400,
    ) -> None:
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.max_memory_items = max_memory_items
        self.max_recent_events = max_recent_events
        self.max_item_text_len = max_item_text_len

    # =========================
    # public
    # =========================

    def build(
        self,
        user_input: str,
        mode: str = "chat",
        task: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        建立一份結構化 context。

        回傳格式固定，方便後續：
        - agent_loop 掛進去
        - planner 後續吃進去
        - task runtime 存檔
        """
        task = task or {}
        extra = extra or {}

        packet = ContextPacket(
            user_input=_compact_text(user_input, 2000),
            mode=_safe_str(mode) or "chat",
            task_id=_safe_str(task.get("id")) or None,
            meta={
                "created_at": _now_ts(),
                "builder_version": "1.0.0",
            },
        )

        query_section = self._build_query_section(user_input=user_input, mode=mode, task=task, extra=extra)
        if query_section:
            packet.sections.append(query_section)

        task_section = self._build_task_section(task=task)
        if task_section:
            packet.sections.append(task_section)

        memory_section = self._build_memory_section(user_input=user_input, task=task)
        if memory_section:
            packet.sections.append(memory_section)

        runtime_section = self._build_runtime_section(task=task)
        if runtime_section:
            packet.sections.append(runtime_section)

        extra_section = self._build_extra_section(extra=extra)
        if extra_section:
            packet.sections.append(extra_section)

        packet.summary = self._build_summary(packet)

        return packet.to_dict()

    def render_for_prompt(self, context: Dict[str, Any]) -> str:
        """
        把結構化 context 渲染成文字，方便你下一步直接塞給 LLM / planner。
        """
        lines: List[str] = []
        lines.append("=== CONTEXT START ===")

        user_input = _safe_str(context.get("user_input"))
        mode = _safe_str(context.get("mode"))
        task_id = _safe_str(context.get("task_id"))

        if user_input:
            lines.append(f"[USER_INPUT]")
            lines.append(user_input)

        if mode:
            lines.append("")
            lines.append(f"[MODE]")
            lines.append(mode)

        if task_id:
            lines.append("")
            lines.append(f"[TASK_ID]")
            lines.append(task_id)

        summary = _safe_str(context.get("summary"))
        if summary:
            lines.append("")
            lines.append("[SUMMARY]")
            lines.append(summary)

        sections = context.get("sections", [])
        if isinstance(sections, list):
            for section in sections:
                name = _safe_str(section.get("name")).strip()
                content = section.get("content")
                if not name:
                    continue
                lines.append("")
                lines.append(f"[{name.upper()}]")
                lines.append(self._format_section_content(content))

        lines.append("=== CONTEXT END ===")
        return "\n".join(lines)

    # =========================
    # section builders
    # =========================

    def _build_query_section(
        self,
        user_input: str,
        mode: str,
        task: Dict[str, Any],
        extra: Dict[str, Any],
    ) -> Optional[ContextSection]:
        content = {
            "user_input": _compact_text(user_input, 1200),
            "mode": _safe_str(mode) or "chat",
        }

        if task:
            content["task_goal"] = _compact_text(
                task.get("goal") or task.get("title") or task.get("objective"),
                300,
            )

        if extra:
            safe_extra = {}
            for k, v in extra.items():
                if v is None:
                    continue
                if isinstance(v, (str, int, float, bool)):
                    safe_extra[k] = v
                else:
                    safe_extra[k] = _compact_text(v, 200)
            if safe_extra:
                content["extra"] = safe_extra

        return ContextSection(name="query", content=content, priority=10)

    def _build_task_section(self, task: Dict[str, Any]) -> Optional[ContextSection]:
        if not task:
            return None

        content = {
            "id": _safe_str(task.get("id")),
            "title": _compact_text(task.get("title"), 200),
            "goal": _compact_text(task.get("goal") or task.get("objective"), 400),
            "status": _safe_str(task.get("status")),
            "current_step": task.get("current_step"),
            "plan": self._compact_plan(task.get("plan")),
        }

        content = {k: v for k, v in content.items() if v not in ("", None, [], {})}
        if not content:
            return None

        return ContextSection(name="task", content=content, priority=20)

    def _build_memory_section(self, user_input: str, task: Dict[str, Any]) -> Optional[ContextSection]:
        if self.memory_store is None:
            return None

        search_query = self._build_memory_query(user_input=user_input, task=task)
        memories = self._search_memory(search_query)

        if not memories:
            recent = self._list_recent_memory()
            memories = recent

        if not memories:
            return None

        normalized = []
        for item in memories[: self.max_memory_items]:
            normalized_item = self._normalize_memory_item(item)
            if normalized_item:
                normalized.append(normalized_item)

        if not normalized:
            return None

        return ContextSection(
            name="memory",
            content={
                "query": search_query,
                "items": normalized,
            },
            priority=30,
        )

    def _build_runtime_section(self, task: Dict[str, Any]) -> Optional[ContextSection]:
        if self.runtime_store is None:
            return None

        snapshot = self._read_runtime_snapshot(task=task)
        if not snapshot:
            return None

        return ContextSection(name="runtime", content=snapshot, priority=40)

    def _build_extra_section(self, extra: Dict[str, Any]) -> Optional[ContextSection]:
        if not extra:
            return None

        content = {}
        for k, v in extra.items():
            if v is None:
                continue

            if isinstance(v, dict):
                compact_dict = {}
                for dk, dv in v.items():
                    compact_dict[_safe_str(dk)] = _compact_text(dv, 200)
                content[_safe_str(k)] = compact_dict
            elif isinstance(v, list):
                compact_list = [_compact_text(x, 200) for x in v[:10]]
                content[_safe_str(k)] = compact_list
            else:
                content[_safe_str(k)] = _compact_text(v, 200)

        if not content:
            return None

        return ContextSection(name="extra", content=content, priority=50)

    # =========================
    # memory helpers
    # =========================

    def _build_memory_query(self, user_input: str, task: Dict[str, Any]) -> str:
        parts: List[str] = []

        if task:
            for key in ("goal", "title", "objective"):
                value = _safe_str(task.get(key)).strip()
                if value:
                    parts.append(value)
                    break

        if user_input.strip():
            parts.append(user_input.strip())

        merged = " | ".join(parts).strip()
        return merged[:500]

    def _search_memory(self, query: str) -> List[Any]:
        if not self.memory_store or not query:
            return []

        # 支援 memory_store.search(query, limit=?)
        search_fn = getattr(self.memory_store, "search", None)
        if callable(search_fn):
            try:
                result = search_fn(query, limit=self.max_memory_items)
                if isinstance(result, list):
                    return result
            except TypeError:
                try:
                    result = search_fn(query)
                    if isinstance(result, list):
                        return result[: self.max_memory_items]
                except Exception:
                    return []
            except Exception:
                return []

        return []

    def _list_recent_memory(self) -> List[Any]:
        if not self.memory_store:
            return []

        # 常見命名都嘗試一下
        for method_name in ("list_recent", "recent", "list", "get_all"):
            fn = getattr(self.memory_store, method_name, None)
            if callable(fn):
                try:
                    result = fn(limit=self.max_memory_items)
                    if isinstance(result, list):
                        return result[: self.max_memory_items]
                except TypeError:
                    try:
                        result = fn()
                        if isinstance(result, list):
                            return result[: self.max_memory_items]
                    except Exception:
                        continue
                except Exception:
                    continue

        return []

    def _normalize_memory_item(self, item: Any) -> Optional[Dict[str, Any]]:
        if item is None:
            return None

        if isinstance(item, str):
            text = _compact_text(item, self.max_item_text_len)
            return {"text": text} if text else None

        if not isinstance(item, dict):
            text = _compact_text(item, self.max_item_text_len)
            return {"text": text} if text else None

        content = (
            item.get("text")
            or item.get("content")
            or item.get("value")
            or item.get("memory")
            or item.get("summary")
        )

        normalized: Dict[str, Any] = {}

        if item.get("id") is not None:
            normalized["id"] = item.get("id")

        if item.get("type") is not None:
            normalized["type"] = _safe_str(item.get("type"))

        if item.get("source") is not None:
            normalized["source"] = _safe_str(item.get("source"))

        if item.get("score") is not None:
            normalized["score"] = item.get("score")

        if item.get("created_at") is not None:
            normalized["created_at"] = item.get("created_at")

        if item.get("updated_at") is not None:
            normalized["updated_at"] = item.get("updated_at")

        text = _compact_text(content, self.max_item_text_len)
        if text:
            normalized["text"] = text

        # 補抓 metadata
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and metadata:
            compact_meta = {}
            for k, v in metadata.items():
                compact_meta[_safe_str(k)] = _compact_text(v, 120)
            normalized["metadata"] = compact_meta

        if not normalized:
            return None

        return normalized

    # =========================
    # runtime helpers
    # =========================

    def _read_runtime_snapshot(self, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.runtime_store is None:
            return None

        task_id = _safe_str(task.get("id"))
        if not task_id:
            return self._read_runtime_general()

        for method_name in ("get_task_runtime", "get_runtime", "read_task_runtime", "load_task_runtime"):
            fn = getattr(self.runtime_store, method_name, None)
            if callable(fn):
                try:
                    result = fn(task_id)
                    if isinstance(result, dict) and result:
                        return self._compact_runtime(result)
                except Exception:
                    continue

        return self._read_runtime_general()

    def _read_runtime_general(self) -> Optional[Dict[str, Any]]:
        if self.runtime_store is None:
            return None

        for method_name in ("snapshot", "get_snapshot", "read_snapshot"):
            fn = getattr(self.runtime_store, method_name, None)
            if callable(fn):
                try:
                    result = fn()
                    if isinstance(result, dict) and result:
                        return self._compact_runtime(result)
                except Exception:
                    continue

        return None

    def _compact_runtime(self, runtime: Dict[str, Any]) -> Dict[str, Any]:
        keys = [
            "task_id",
            "status",
            "current_step",
            "last_error",
            "last_result",
            "retry_count",
            "updated_at",
            "events",
        ]

        compact: Dict[str, Any] = {}

        for key in keys:
            if key not in runtime:
                continue

            value = runtime.get(key)
            if value in (None, "", [], {}):
                continue

            if key == "events" and isinstance(value, list):
                compact[key] = [self._compact_event(x) for x in value[-self.max_recent_events :]]
            elif isinstance(value, dict):
                compact[key] = {str(k): _compact_text(v, 200) for k, v in value.items()}
            else:
                compact[key] = _compact_text(value, 300)

        return compact

    def _compact_event(self, event: Any) -> Any:
        if isinstance(event, dict):
            out = {}
            for k, v in event.items():
                out[_safe_str(k)] = _compact_text(v, 160)
            return out
        return _compact_text(event, 160)

    # =========================
    # summary / formatting
    # =========================

    def _build_summary(self, packet: ContextPacket) -> str:
        parts: List[str] = []

        if packet.task_id:
            parts.append(f"task_id={packet.task_id}")

        if packet.mode:
            parts.append(f"mode={packet.mode}")

        has_memory = any(sec.name == "memory" for sec in packet.sections)
        if has_memory:
            parts.append("memory=attached")

        has_runtime = any(sec.name == "runtime" for sec in packet.sections)
        if has_runtime:
            parts.append("runtime=attached")

        if not parts:
            return "basic_context"

        return ", ".join(parts)

    def _compact_plan(self, plan: Any) -> Any:
        if not plan:
            return None

        if isinstance(plan, list):
            result = []
            for step in plan[:10]:
                if isinstance(step, dict):
                    result.append(
                        {
                            "step": step.get("step"),
                            "title": _compact_text(step.get("title"), 120),
                            "status": _safe_str(step.get("status")),
                        }
                    )
                else:
                    result.append(_compact_text(step, 120))
            return result

        if isinstance(plan, dict):
            compact = {}
            for k, v in list(plan.items())[:20]:
                compact[_safe_str(k)] = _compact_text(v, 150)
            return compact

        return _compact_text(plan, 300)

    def _format_section_content(self, content: Any) -> str:
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        try:
            return json.dumps(content, ensure_ascii=False, indent=2)
        except Exception:
            return _safe_str(content)


def build_context(
    user_input: str,
    memory_store: Optional[Any] = None,
    runtime_store: Optional[Any] = None,
    mode: str = "chat",
    task: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    方便外部直接呼叫的 helper。
    """
    builder = ContextBuilder(
        memory_store=memory_store,
        runtime_store=runtime_store,
    )
    return builder.build(
        user_input=user_input,
        mode=mode,
        task=task,
        extra=extra,
    )