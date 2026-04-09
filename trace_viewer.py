# trace_viewer.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import mimetypes
import os
import sys
import threading
import traceback
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


APP_TITLE = "ZERO Trace Viewer"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


# 你之後如果有固定 trace 位置，可以直接加在這裡
DEFAULT_TRACE_DIR_CANDIDATES = [
    "data/traces",
    "traces",
    "runtime/traces",
    "logs/traces",
    "logs",
    "data",
    "workspace/shared",
]

SUPPORTED_FILE_EXTS = {".json", ".jsonl", ".log", ".txt"}


@dataclass
class TraceEvent:
    seq: int
    ts: str = ""
    event_type: str = ""
    source: str = ""
    step_id: str = ""
    task_id: str = ""
    status: str = ""
    title: str = ""
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceFile:
    path: str
    name: str
    mtime: float
    size: int
    events: List[TraceEvent] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


def safe_read_text(path: Path) -> str:
    encodings = ["utf-8", "utf-8-sig", "cp950", "big5", "latin-1"]
    last_error = None
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except Exception as exc:
            last_error = exc
    raise last_error  # type: ignore[misc]


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def iso_from_timestamp(ts: float) -> str:
    try:
        return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def format_size(num: int) -> str:
    size = float(num)
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num} B"


def html_escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def try_parse_json(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        return None


def looks_like_jsonl(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    hit = 0
    sample = lines[:20]
    for line in sample:
        if try_parse_json(line) is not None:
            hit += 1
    return hit >= max(1, len(sample) // 2)


def normalize_event(obj: Any, seq: int, fallback_source: str = "") -> TraceEvent:
    if isinstance(obj, dict):
        ts = first_non_empty(
            obj,
            ["ts", "timestamp", "time", "created_at", "updated_at", "datetime"],
            "",
        )
        event_type = first_non_empty(
            obj,
            ["event_type", "type", "kind", "phase", "action", "name"],
            "",
        )
        source = first_non_empty(
            obj,
            ["source", "module", "component", "origin"],
            fallback_source,
        )
        step_id = first_non_empty(
            obj,
            ["step_id", "node_id", "id", "step", "stage_id"],
            "",
        )
        task_id = first_non_empty(
            obj,
            ["task_id", "run_id", "trace_id", "job_id"],
            "",
        )
        status = first_non_empty(
            obj,
            ["status", "result", "state", "outcome"],
            "",
        )
        title = first_non_empty(
            obj,
            ["title", "summary", "label", "step_name"],
            "",
        )
        message = first_non_empty(
            obj,
            ["message", "msg", "detail", "observation", "reason", "text"],
            "",
        )

        if not message:
            if "input" in obj or "output" in obj or "error" in obj:
                message = build_compact_message(obj)
            else:
                message = ""

        return TraceEvent(
            seq=seq,
            ts=str(ts or ""),
            event_type=str(event_type or ""),
            source=str(source or ""),
            step_id=str(step_id or ""),
            task_id=str(task_id or ""),
            status=str(status or ""),
            title=str(title or ""),
            message=str(message or ""),
            raw=obj,
        )

    return TraceEvent(
        seq=seq,
        ts="",
        event_type="raw",
        source=fallback_source,
        step_id="",
        task_id="",
        status="",
        title="",
        message=str(obj),
        raw={"value": obj},
    )


def build_compact_message(obj: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ["input", "output", "error", "command", "tool", "tool_name", "reason"]:
        if key in obj and obj[key] not in (None, "", [], {}):
            value = obj[key]
            if isinstance(value, (dict, list)):
                value = json_dumps(value)
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


def first_non_empty(obj: Dict[str, Any], keys: List[str], default: Any = "") -> Any:
    for key in keys:
        value = obj.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def parse_trace_file(path: Path) -> TraceFile:
    stat = path.stat()
    text = safe_read_text(path)
    events: List[TraceEvent] = []

    parsed = try_parse_json(text)
    if parsed is not None:
        events = parse_json_payload(parsed, path.name)
    elif looks_like_jsonl(text):
        seq = 1
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parsed_line = try_parse_json(line)
            if parsed_line is None:
                events.append(
                    TraceEvent(
                        seq=seq,
                        event_type="line",
                        source=path.name,
                        message=line,
                        raw={"line": line},
                    )
                )
            else:
                events.append(normalize_event(parsed_line, seq, path.name))
            seq += 1
    else:
        events = parse_plain_text(text, path.name)

    summary = build_summary(events)

    return TraceFile(
        path=str(path.resolve()),
        name=path.name,
        mtime=stat.st_mtime,
        size=stat.st_size,
        events=events,
        summary=summary,
    )


def parse_json_payload(payload: Any, fallback_source: str) -> List[TraceEvent]:
    events: List[TraceEvent] = []

    if isinstance(payload, list):
        for i, item in enumerate(payload, start=1):
            events.append(normalize_event(item, i, fallback_source))
        return events

    if isinstance(payload, dict):
        # 常見 trace 結構猜測
        for container_key in ["events", "trace", "steps", "records", "items", "logs"]:
            value = payload.get(container_key)
            if isinstance(value, list):
                for i, item in enumerate(value, start=1):
                    events.append(normalize_event(item, i, fallback_source))
                return events

        # 如果本身就是單一事件
        events.append(normalize_event(payload, 1, fallback_source))
        return events

    events.append(normalize_event(payload, 1, fallback_source))
    return events


def parse_plain_text(text: str, fallback_source: str) -> List[TraceEvent]:
    events: List[TraceEvent] = []
    seq = 1
    lines = text.splitlines()

    # 嘗試把空行分段
    blocks: List[str] = []
    current: List[str] = []
    for line in lines:
        if line.strip():
            current.append(line)
        else:
            if current:
                blocks.append("\n".join(current))
                current = []
    if current:
        blocks.append("\n".join(current))

    if not blocks:
        blocks = [text]

    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        events.append(
            TraceEvent(
                seq=seq,
                event_type="text",
                source=fallback_source,
                message=stripped,
                raw={"text": stripped},
            )
        )
        seq += 1

    return events


def build_summary(events: List[TraceEvent]) -> Dict[str, Any]:
    types: Dict[str, int] = {}
    statuses: Dict[str, int] = {}
    task_ids: Dict[str, int] = {}

    for ev in events:
        if ev.event_type:
            types[ev.event_type] = types.get(ev.event_type, 0) + 1
        if ev.status:
            statuses[ev.status] = statuses.get(ev.status, 0) + 1
        if ev.task_id:
            task_ids[ev.task_id] = task_ids.get(ev.task_id, 0) + 1

    return {
        "event_count": len(events),
        "types": types,
        "statuses": statuses,
        "task_ids": task_ids,
    }


class TraceRepository:
    def __init__(self, base_dir: Path, trace_dirs: Optional[List[Path]] = None):
        self.base_dir = base_dir.resolve()
        self.trace_dirs = trace_dirs or self._resolve_default_trace_dirs()

    def _resolve_default_trace_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        seen = set()

        for rel in DEFAULT_TRACE_DIR_CANDIDATES:
            p = (self.base_dir / rel).resolve()
            if p.exists() and p.is_dir():
                key = str(p)
                if key not in seen:
                    dirs.append(p)
                    seen.add(key)

        # 如果都沒找到，就至少把專案根目錄放進去，避免完全沒東西
        if not dirs:
            dirs.append(self.base_dir)

        return dirs

    def discover_files(self) -> List[Path]:
        files: List[Path] = []
        seen = set()

        for directory in self.trace_dirs:
            if not directory.exists():
                continue

            # 避免掃太深太亂，先限制在 4 層
            for path in directory.rglob("*"):
                try:
                    if not path.is_file():
                        continue
                    if path.suffix.lower() not in SUPPORTED_FILE_EXTS:
                        continue
                    if ".git" in path.parts:
                        continue
                    rel_parts = [p.lower() for p in path.parts]
                    joined = "/".join(rel_parts)
                    keywords = ["trace", "execution", "runtime", "task", "log", "record"]
                    if not any(k in joined for k in keywords):
                        continue
                    resolved = str(path.resolve())
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    files.append(path)
                except Exception:
                    continue

        files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        return files

    def list_trace_files(self) -> List[TraceFile]:
        results: List[TraceFile] = []
        for path in self.discover_files():
            try:
                results.append(parse_trace_file(path))
            except Exception as exc:
                results.append(
                    TraceFile(
                        path=str(path.resolve()),
                        name=path.name,
                        mtime=path.stat().st_mtime if path.exists() else 0,
                        size=path.stat().st_size if path.exists() else 0,
                        events=[
                            TraceEvent(
                                seq=1,
                                event_type="parse_error",
                                source=path.name,
                                status="error",
                                title="解析失敗",
                                message=str(exc),
                                raw={"traceback": traceback.format_exc()},
                            )
                        ],
                        summary={"event_count": 1, "types": {"parse_error": 1}},
                    )
                )
        return results

    def get_trace_file(self, file_name: str) -> Optional[TraceFile]:
        for path in self.discover_files():
            if path.name == file_name:
                try:
                    return parse_trace_file(path)
                except Exception:
                    return None
        return None


class TraceViewerHandler(BaseHTTPRequestHandler):
    repo: TraceRepository = None  # type: ignore[assignment]

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        path = parsed.path

        try:
            if path == "/":
                self._send_html(self.render_index(query))
                return

            if path == "/view":
                file_name = query.get("file", [""])[0]
                self._send_html(self.render_trace_file(file_name, query))
                return

            if path == "/api/files":
                data = self.api_files()
                self._send_json(data)
                return

            if path == "/api/file":
                file_name = query.get("file", [""])[0]
                data = self.api_file(file_name)
                self._send_json(data)
                return

            if path == "/raw":
                file_name = query.get("file", [""])[0]
                self._send_raw_file(file_name)
                return

            self.send_error(404, "Not Found")
        except Exception as exc:
            self._send_html(self.render_error_page(exc), status=500)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("[trace_viewer] " + (format % args) + "\n")

    def api_files(self) -> Dict[str, Any]:
        files = self.repo.list_trace_files()
        items = []
        for tf in files:
            items.append(
                {
                    "name": tf.name,
                    "path": tf.path,
                    "mtime": tf.mtime,
                    "mtime_text": iso_from_timestamp(tf.mtime),
                    "size": tf.size,
                    "size_text": format_size(tf.size),
                    "summary": tf.summary,
                }
            )
        return {"ok": True, "count": len(items), "items": items}

    def api_file(self, file_name: str) -> Dict[str, Any]:
        if not file_name:
            return {"ok": False, "error": "missing file"}
        tf = self.repo.get_trace_file(file_name)
        if not tf:
            return {"ok": False, "error": f"file not found: {file_name}"}
        return {
            "ok": True,
            "file": {
                "name": tf.name,
                "path": tf.path,
                "mtime": tf.mtime,
                "mtime_text": iso_from_timestamp(tf.mtime),
                "size": tf.size,
                "size_text": format_size(tf.size),
                "summary": tf.summary,
                "events": [event_to_dict(ev) for ev in tf.events],
            },
        }

    def _send_raw_file(self, file_name: str) -> None:
        tf = self.repo.get_trace_file(file_name)
        if not tf:
            self.send_error(404, "File not found")
            return

        path = Path(tf.path)
        ctype, _ = mimetypes.guess_type(str(path))
        if not ctype:
            ctype = "text/plain; charset=utf-8"

        raw = safe_read_text(path)
        body = raw.encode("utf-8", errors="replace")

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        body = json_dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def render_index(self, query: Dict[str, List[str]]) -> str:
        search = query.get("q", [""])[0].strip().lower()
        files = self.repo.list_trace_files()

        if search:
            filtered: List[TraceFile] = []
            for tf in files:
                text = f"{tf.name} {tf.path}".lower()
                if search in text:
                    filtered.append(tf)
            files = filtered

        file_cards = []
        for tf in files:
            summary = tf.summary or {}
            event_count = summary.get("event_count", 0)
            task_ids = summary.get("task_ids", {})
            types = summary.get("types", {})
            statuses = summary.get("statuses", {})

            file_cards.append(
                f"""
                <div class="card">
                    <div class="row row-top">
                        <div>
                            <div class="file-name">{html_escape(tf.name)}</div>
                            <div class="file-meta">{html_escape(tf.path)}</div>
                        </div>
                        <div class="align-right">
                            <div class="badge">{html_escape(format_size(tf.size))}</div>
                            <div class="muted">{html_escape(iso_from_timestamp(tf.mtime))}</div>
                        </div>
                    </div>

                    <div class="summary-grid">
                        <div class="stat">
                            <div class="stat-label">events</div>
                            <div class="stat-value">{event_count}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">task ids</div>
                            <div class="stat-value">{len(task_ids)}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">types</div>
                            <div class="stat-value">{len(types)}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">statuses</div>
                            <div class="stat-value">{len(statuses)}</div>
                        </div>
                    </div>

                    <div class="chips">
                        {render_map_chips(types, max_items=8)}
                    </div>

                    <div class="card-actions">
                        <a class="btn" href="/view?file={urllib.parse.quote(tf.name)}">查看</a>
                        <a class="btn btn-ghost" href="/raw?file={urllib.parse.quote(tf.name)}" target="_blank">原始檔</a>
                    </div>
                </div>
                """
            )

        empty_html = ""
        if not files:
            empty_html = """
            <div class="empty">
                沒找到 trace 檔案。<br>
                你可以先把 trace / execution log 放進 data/traces、traces、logs 之類目錄，再重新整理。
            </div>
            """

        return f"""
        <!doctype html>
        <html lang="zh-Hant">
        <head>
            <meta charset="utf-8">
            <title>{APP_TITLE}</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            {base_style()}
        </head>
        <body>
            <div class="container">
                <div class="hero">
                    <div>
                        <h1>{APP_TITLE}</h1>
                        <p class="subtitle">掃描 ZERO 的 trace / execution log，快速查看 execution → decision → correction 流程。</p>
                    </div>
                    <div class="hero-actions">
                        <a class="btn" href="/">重新整理</a>
                    </div>
                </div>

                <form class="toolbar" method="get" action="/">
                    <input
                        class="search"
                        type="text"
                        name="q"
                        placeholder="搜尋檔名或路徑..."
                        value="{html_escape(search)}"
                    />
                    <button class="btn" type="submit">搜尋</button>
                </form>

                <div class="hint">
                    掃描位置：
                    {", ".join(html_escape(str(p)) for p in self.repo.trace_dirs)}
                </div>

                {empty_html}
                <div class="grid">
                    {"".join(file_cards)}
                </div>
            </div>
        </body>
        </html>
        """

    def render_trace_file(self, file_name: str, query: Dict[str, List[str]]) -> str:
        if not file_name:
            return self.render_error_page(ValueError("缺少 file 參數"))

        tf = self.repo.get_trace_file(file_name)
        if not tf:
            return self.render_error_page(FileNotFoundError(f"找不到檔案: {file_name}"))

        q = query.get("q", [""])[0].strip().lower()
        type_filter = query.get("type", [""])[0].strip().lower()
        status_filter = query.get("status", [""])[0].strip().lower()

        events = tf.events
        if q:
            events = [
                ev for ev in events
                if q in (
                    " ".join(
                        [
                            ev.ts,
                            ev.event_type,
                            ev.source,
                            ev.step_id,
                            ev.task_id,
                            ev.status,
                            ev.title,
                            ev.message,
                            json_dumps(ev.raw),
                        ]
                    ).lower()
                )
            ]

        if type_filter:
            events = [ev for ev in events if ev.event_type.lower() == type_filter]

        if status_filter:
            events = [ev for ev in events if ev.status.lower() == status_filter]

        type_options = sorted({ev.event_type for ev in tf.events if ev.event_type})
        status_options = sorted({ev.status for ev in tf.events if ev.status})

        event_rows = []
        for ev in events:
            event_rows.append(
                f"""
                <div class="event">
                    <div class="event-head">
                        <div class="event-seq">#{ev.seq}</div>
                        <div class="event-main">
                            <div class="event-title">
                                <span class="pill pill-type">{html_escape(ev.event_type or "event")}</span>
                                {f'<span class="pill pill-status">{html_escape(ev.status)}</span>' if ev.status else ''}
                                {f'<span class="pill">{html_escape(ev.source)}</span>' if ev.source else ''}
                                {f'<span class="pill">{html_escape(ev.task_id)}</span>' if ev.task_id else ''}
                                {f'<span class="pill">{html_escape(ev.step_id)}</span>' if ev.step_id else ''}
                            </div>
                            <div class="event-meta">
                                {html_escape(ev.ts or "")}
                                {f' · {html_escape(ev.title)}' if ev.title else ''}
                            </div>
                        </div>
                    </div>
                    <div class="event-body">
                        <pre>{html_escape(ev.message or "")}</pre>
                    </div>
                    <details class="raw-box">
                        <summary>raw</summary>
                        <pre>{html_escape(json_dumps(ev.raw))}</pre>
                    </details>
                </div>
                """
            )

        return f"""
        <!doctype html>
        <html lang="zh-Hant">
        <head>
            <meta charset="utf-8">
            <title>{html_escape(tf.name)} - {APP_TITLE}</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            {base_style()}
        </head>
        <body>
            <div class="container">
                <div class="hero">
                    <div>
                        <h1>{html_escape(tf.name)}</h1>
                        <p class="subtitle">{html_escape(tf.path)}</p>
                    </div>
                    <div class="hero-actions">
                        <a class="btn btn-ghost" href="/">返回</a>
                        <a class="btn" href="/raw?file={urllib.parse.quote(tf.name)}" target="_blank">原始檔</a>
                    </div>
                </div>

                <div class="summary-bar">
                    <div class="stat">
                        <div class="stat-label">mtime</div>
                        <div class="stat-value small">{html_escape(iso_from_timestamp(tf.mtime))}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">size</div>
                        <div class="stat-value small">{html_escape(format_size(tf.size))}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">events</div>
                        <div class="stat-value">{len(tf.events)}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">shown</div>
                        <div class="stat-value">{len(events)}</div>
                    </div>
                </div>

                <form class="toolbar" method="get" action="/view">
                    <input type="hidden" name="file" value="{html_escape(tf.name)}">
                    <input
                        class="search"
                        type="text"
                        name="q"
                        placeholder="搜尋 task_id / step / message / raw..."
                        value="{html_escape(q)}"
                    />
                    <select class="select" name="type">
                        <option value="">全部 type</option>
                        {"".join(
                            f'<option value="{html_escape(opt)}" {"selected" if opt.lower() == type_filter else ""}>{html_escape(opt)}</option>'
                            for opt in type_options
                        )}
                    </select>
                    <select class="select" name="status">
                        <option value="">全部 status</option>
                        {"".join(
                            f'<option value="{html_escape(opt)}" {"selected" if opt.lower() == status_filter else ""}>{html_escape(opt)}</option>'
                            for opt in status_options
                        )}
                    </select>
                    <button class="btn" type="submit">套用</button>
                </form>

                <div class="chips">
                    {render_map_chips(tf.summary.get("types", {}), title_prefix="type")}
                </div>

                <div class="chips">
                    {render_map_chips(tf.summary.get("statuses", {}), title_prefix="status")}
                </div>

                <div class="events">
                    {"".join(event_rows) if event_rows else '<div class="empty">沒有符合條件的事件。</div>'}
                </div>
            </div>
        </body>
        </html>
        """

    def render_error_page(self, exc: Exception) -> str:
        return f"""
        <!doctype html>
        <html lang="zh-Hant">
        <head>
            <meta charset="utf-8">
            <title>Error - {APP_TITLE}</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            {base_style()}
        </head>
        <body>
            <div class="container">
                <div class="hero">
                    <div>
                        <h1>Trace Viewer Error</h1>
                        <p class="subtitle">{html_escape(str(exc))}</p>
                    </div>
                    <div class="hero-actions">
                        <a class="btn btn-ghost" href="/">返回首頁</a>
                    </div>
                </div>
                <div class="card">
                    <pre>{html_escape(traceback.format_exc())}</pre>
                </div>
            </div>
        </body>
        </html>
        """


def render_map_chips(data: Dict[str, int], max_items: int = 12, title_prefix: str = "") -> str:
    if not data:
        return ""
    items = sorted(data.items(), key=lambda x: (-x[1], str(x[0])))
    parts: List[str] = []
    for key, value in items[:max_items]:
        title = f"{title_prefix}: {key}" if title_prefix else str(key)
        parts.append(
            f'<span class="chip" title="{html_escape(title)}">{html_escape(key)} <b>{value}</b></span>'
        )
    return "".join(parts)


def event_to_dict(ev: TraceEvent) -> Dict[str, Any]:
    return {
        "seq": ev.seq,
        "ts": ev.ts,
        "event_type": ev.event_type,
        "source": ev.source,
        "step_id": ev.step_id,
        "task_id": ev.task_id,
        "status": ev.status,
        "title": ev.title,
        "message": ev.message,
        "raw": ev.raw,
    }


def base_style() -> str:
    return """
    <style>
        :root {
            --bg: #0b1020;
            --panel: #121a2b;
            --panel-2: #182238;
            --text: #eaf0ff;
            --muted: #9fb0d3;
            --line: #263451;
            --accent: #6ea8fe;
            --accent-2: #9d7bff;
            --ok: #41d392;
            --warn: #ffc857;
            --bad: #ff6b6b;
            --chip: #202c45;
        }

        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Arial, "Microsoft JhengHei", "PingFang TC", sans-serif;
            background: linear-gradient(180deg, #0b1020 0%, #0f1423 100%);
            color: var(--text);
        }

        .container {
            max-width: 1280px;
            margin: 0 auto;
            padding: 24px;
        }

        .hero {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
            margin-bottom: 20px;
            padding: 20px;
            background: rgba(18, 26, 43, 0.92);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.25);
        }

        h1 {
            margin: 0 0 8px 0;
            font-size: 28px;
            line-height: 1.2;
        }

        .subtitle {
            margin: 0;
            color: var(--muted);
            line-height: 1.5;
        }

        .toolbar {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 16px;
            align-items: center;
        }

        .search, .select {
            background: var(--panel);
            color: var(--text);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px 14px;
            font-size: 14px;
        }

        .search {
            flex: 1 1 320px;
            min-width: 240px;
        }

        .select {
            min-width: 160px;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            color: #081222;
            background: linear-gradient(135deg, var(--accent), var(--accent-2));
            border: none;
            border-radius: 12px;
            padding: 12px 16px;
            font-weight: 700;
            cursor: pointer;
        }

        .btn-ghost {
            color: var(--text);
            background: transparent;
            border: 1px solid var(--line);
        }

        .hint {
            margin-bottom: 18px;
            color: var(--muted);
            font-size: 13px;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 16px;
        }

        .card {
            background: rgba(18, 26, 43, 0.92);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 18px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.18);
        }

        .row {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .row-top {
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 14px;
        }

        .align-right {
            text-align: right;
        }

        .file-name {
            font-size: 18px;
            font-weight: 700;
            word-break: break-word;
        }

        .file-meta {
            margin-top: 6px;
            color: var(--muted);
            font-size: 12px;
            word-break: break-all;
        }

        .badge, .chip, .pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--chip);
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 6px 10px;
            color: var(--text);
            font-size: 12px;
        }

        .chips {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 10px 0 0 0;
        }

        .summary-grid, .summary-bar {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 10px;
        }

        .stat {
            background: var(--panel-2);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 12px;
        }

        .stat-label {
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 6px;
        }

        .stat-value {
            font-size: 24px;
            font-weight: 700;
            line-height: 1.1;
        }

        .stat-value.small {
            font-size: 14px;
            line-height: 1.4;
            word-break: break-word;
        }

        .card-actions, .hero-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .events {
            display: flex;
            flex-direction: column;
            gap: 14px;
            margin-top: 18px;
        }

        .event {
            background: rgba(18, 26, 43, 0.92);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 16px;
        }

        .event-head {
            display: flex;
            gap: 12px;
            align-items: flex-start;
            margin-bottom: 12px;
        }

        .event-seq {
            min-width: 56px;
            text-align: center;
            background: var(--panel-2);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 8px 10px;
            font-weight: 700;
        }

        .event-main {
            flex: 1;
            min-width: 0;
        }

        .event-title {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 8px;
        }

        .event-meta {
            color: var(--muted);
            font-size: 13px;
        }

        .pill-type {
            border-color: rgba(110,168,254,0.5);
        }

        .pill-status {
            border-color: rgba(65,211,146,0.5);
        }

        .event-body pre,
        .raw-box pre,
        .card pre {
            margin: 0;
            white-space: pre-wrap;
            word-break: break-word;
            background: #0b1324;
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 14px;
            color: #dbe8ff;
            overflow-x: auto;
        }

        .raw-box {
            margin-top: 12px;
        }

        .raw-box summary {
            cursor: pointer;
            color: var(--muted);
            margin-bottom: 10px;
        }

        .empty {
            padding: 28px;
            border: 1px dashed var(--line);
            border-radius: 18px;
            color: var(--muted);
            text-align: center;
            background: rgba(18, 26, 43, 0.55);
        }

        .muted {
            color: var(--muted);
            font-size: 12px;
            margin-top: 4px;
        }

        @media (max-width: 900px) {
            .hero {
                flex-direction: column;
            }

            .summary-grid, .summary-bar {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 560px) {
            .container {
                padding: 14px;
            }

            .grid {
                grid-template-columns: 1fr;
            }

            .summary-grid, .summary-bar {
                grid-template-columns: 1fr;
            }
        }
    </style>
    """


def build_server(host: str, port: int, repo: TraceRepository) -> ThreadingHTTPServer:
    class Handler(TraceViewerHandler):
        pass

    Handler.repo = repo
    return ThreadingHTTPServer((host, port), Handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZERO Trace Viewer")
    parser.add_argument(
        "--base-dir",
        default=".",
        help="專案根目錄，預設目前目錄",
    )
    parser.add_argument(
        "--trace-dir",
        action="append",
        default=[],
        help="額外指定 trace 目錄，可重複傳入多次",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"監聽 host，預設 {DEFAULT_HOST}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"監聽 port，預設 {DEFAULT_PORT}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    base_dir = Path(args.base_dir).resolve()
    extra_dirs = []
    for item in args.trace_dir:
        p = Path(item)
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        extra_dirs.append(p)

    repo = TraceRepository(base_dir=base_dir)
    if extra_dirs:
        merged = list(repo.trace_dirs)
        seen = {str(p.resolve()) for p in merged}
        for p in extra_dirs:
            rp = p.resolve()
            if str(rp) not in seen and rp.exists() and rp.is_dir():
                merged.append(rp)
                seen.add(str(rp))
        repo.trace_dirs = merged

    print("=" * 72)
    print(f"{APP_TITLE}")
    print(f"base_dir   : {base_dir}")
    print("trace_dirs :")
    for d in repo.trace_dirs:
        print(f"  - {d}")
    print(f"url        : http://{args.host}:{args.port}")
    print("=" * 72)

    server = build_server(args.host, args.port, repo)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[trace_viewer] stopped by user")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())