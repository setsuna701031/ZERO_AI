from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = Path(__file__).resolve().parent
PERSONA_ASSETS_DIR = REPO_ROOT / "assets" / "persona" / "zero_v1"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


try:
    from flask import Flask, jsonify, request, send_from_directory
except Exception:
    print("Flask is not installed or cannot be imported.")
    print("Install it with:")
    print("python -m pip install flask")
    raise


from core.display.ui_bridge import (
    drop_text_file,
    get_latest_summary,
    get_system_status,
    get_task_detail,
    get_tasks,
    list_shared_files,
    read_shared_file,
)


APP_HOST = "127.0.0.1"
APP_PORT = 7860


app = Flask(
    __name__,
    static_folder=str(UI_DIR),
    static_url_path="",
)


def _safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value)
    if not text.strip():
        return fallback
    return text


def _build_status_payload() -> Dict[str, Any]:
    latest_summary = get_latest_summary()
    tasks = get_tasks(limit=10)
    system_status = get_system_status()
    shared_files = list_shared_files(limit=20)

    return {
        "success": True,
        "mode": "ui_status",
        "summary": latest_summary or "目前沒有找到最新 summary。",
        "response": {
            "system_status": system_status,
            "latest_summary": latest_summary,
            "tasks": tasks,
            "shared_files": shared_files,
        },
        "meta": {
            "model": "local-ui-bridge",
            "used_fallback": False,
            "llm_used": False,
        },
    }


def _format_tasks_for_display(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "目前沒有讀到 task runtime_state.json。"

    lines: list[str] = []
    for index, task in enumerate(tasks, start=1):
        task_id = _safe_text(task.get("task_id"), "-")
        status = _safe_text(task.get("status"), "-")
        step = _safe_text(task.get("step"), "-")
        goal = _safe_text(task.get("goal"), "-")
        final_answer = _safe_text(task.get("final_answer"), "")

        block = [
            f"{index}. {task_id}",
            f"   status: {status}",
            f"   step  : {step}",
            f"   goal  : {goal}",
        ]

        if final_answer:
            block.append(f"   result: {final_answer}")

        block.append(f"   inspect: task {task_id}")

        lines.append("\n".join(block))

    return "\n\n".join(lines)


def _format_shared_files_for_display(files: list[str]) -> str:
    if not files:
        return "目前 workspace/shared 沒有可列出的檔案。"

    return "\n".join(f"- {name}\n  view: view {name}" for name in files)


def _format_task_detail_for_display(detail: Dict[str, Any]) -> str:
    if not detail.get("found"):
        return f"[TASK DETAIL]\nTask not found.\n\n{detail.get('error', '')}"

    summary = detail.get("summary") or {}
    steps = detail.get("steps") or []
    files = detail.get("available_files") or []

    lines: list[str] = [
        "[TASK DETAIL]",
        f"Task ID      : {summary.get('task_id') or detail.get('task_id') or '-'}",
        f"Status       : {summary.get('status') or '-'}",
        f"Step         : {summary.get('step') or '-'}",
        f"Goal         : {summary.get('goal') or '-'}",
        f"Final Answer : {summary.get('final_answer') or '-'}",
    ]

    if summary.get("scenario") or summary.get("mode") or summary.get("pipeline_name"):
        lines.extend(
            [
                "",
                "[PIPELINE]",
                f"Scenario     : {summary.get('scenario') or '-'}",
                f"Mode         : {summary.get('mode') or '-'}",
                f"Pipeline     : {summary.get('pipeline_name') or '-'}",
            ]
        )

    lines.extend(
        [
            "",
            "[FILES]",
            "\n".join(f"- {name}" for name in files) if files else "-",
            "",
            "[PLAN STEPS]",
        ]
    )

    if steps:
        for index, step in enumerate(steps, start=1):
            if isinstance(step, dict):
                name = step.get("name") or step.get("type") or step.get("action") or "step"
                target = step.get("path") or step.get("target") or step.get("output") or ""
                lines.append(f"{index}. {name} {target}".rstrip())
            else:
                lines.append(f"{index}. {step}")
    else:
        lines.append("-")

    return "\n".join(lines)


def _format_shared_file_for_display(file_info: Dict[str, Any]) -> str:
    if not file_info.get("found"):
        return f"[SHARED FILE]\nFile not found.\n\n{file_info.get('error', '')}"

    return (
        "[SHARED FILE]\n"
        f"Name: {file_info.get('filename')}\n"
        f"Path: {file_info.get('path')}\n\n"
        "[CONTENT]\n"
        f"{file_info.get('content') or ''}"
    )


def _payload(
    *,
    success: bool,
    mode: str,
    summary: str,
    response: str,
    meta_model: str = "local-ui-bridge",
    used_fallback: bool = False,
    llm_used: bool = False,
    warning: Optional[str] = None,
    error: Optional[str] = None,
    ui: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "success": success,
        "mode": mode,
        "summary": summary,
        "response": response,
        "content": response,
        "warning": warning,
        "error": error,
        "meta": {
            "model": meta_model,
            "used_fallback": used_fallback,
            "llm_used": llm_used,
        },
    }

    if ui is not None:
        data["ui"] = ui

    if extra:
        data.update(extra)

    return data


def _build_chat_payload(message: str) -> Dict[str, Any]:
    text = message.strip()
    normalized = text.lower()

    status_payload = _build_status_payload()
    status_data = status_payload["response"]

    system_status = status_data["system_status"]
    latest_summary = status_data["latest_summary"]
    tasks = status_data["tasks"]
    shared_files = status_data["shared_files"]

    if normalized in {"status", "/status", "狀態", "系統狀態"}:
        response_text = (
            "[ZERO UI STATUS]\n"
            f"System Status: {system_status}\n\n"
            "[TASKS]\n"
            f"{_format_tasks_for_display(tasks)}\n\n"
            "[SHARED FILES]\n"
            f"{_format_shared_files_for_display(shared_files)}"
        )

        return _payload(
            success=True,
            mode="ui_bridge_status",
            summary=f"系統目前狀態：{system_status}",
            response=response_text,
            ui=status_data,
        )

    if normalized in {"summary", "/summary", "最新摘要", "摘要"}:
        response_text = latest_summary or "目前沒有找到最新 summary。"

        return _payload(
            success=True,
            mode="ui_bridge_summary",
            summary="已讀取 workspace/shared 內最新的 *_summary.txt。",
            response=response_text,
            ui=status_data,
        )

    if normalized in {"tasks", "/tasks", "任務", "任務狀態"}:
        response_text = _format_tasks_for_display(tasks)

        return _payload(
            success=True,
            mode="ui_bridge_tasks",
            summary=f"已讀取最近 {len(tasks)} 筆任務狀態。可輸入 task <task_id> 查看單一任務。",
            response=response_text,
            ui=status_data,
        )

    if normalized in {"files", "/files", "shared", "輸出檔案"}:
        response_text = _format_shared_files_for_display(shared_files)

        return _payload(
            success=True,
            mode="ui_bridge_shared_files",
            summary=f"已列出 workspace/shared 最近 {len(shared_files)} 個檔案。可輸入 view <filename> 查看內容。",
            response=response_text,
            ui=status_data,
        )

    if normalized.startswith("task "):
        task_id = text[5:].strip()
        detail = get_task_detail(task_id)
        response_text = _format_task_detail_for_display(detail)

        return _payload(
            success=bool(detail.get("found")),
            mode="ui_bridge_task_detail",
            summary=(
                f"已讀取任務：{detail.get('task_id')}"
                if detail.get("found")
                else f"找不到任務：{task_id}"
            ),
            response=response_text,
            ui=status_data,
            error=None if detail.get("found") else detail.get("error"),
            extra={"task_detail": detail},
        )

    if normalized.startswith("view "):
        filename = text[5:].strip()
        file_info = read_shared_file(filename)
        response_text = _format_shared_file_for_display(file_info)

        return _payload(
            success=bool(file_info.get("found")),
            mode="ui_bridge_shared_file_view",
            summary=(
                f"已讀取 shared 檔案：{file_info.get('filename')}"
                if file_info.get("found")
                else f"找不到 shared 檔案：{filename}"
            ),
            response=response_text,
            ui=status_data,
            error=None if file_info.get("found") else file_info.get("error"),
            extra={"shared_file": file_info},
        )

    if normalized.startswith("drop "):
        content = text[5:].strip()

        if not content:
            return _payload(
                success=False,
                mode="ui_bridge_drop",
                summary="drop 指令沒有內容。",
                error="請輸入 drop 後面的文字內容。",
                response="格式：drop 你要丟進 inbox 的文字",
                ui=status_data,
            )

        path = drop_text_file(content)

        response_text = (
            "已將文字寫入 UI inbox。\n\n"
            f"Path: {path}\n\n"
            "注意：這一步只是把內容放進 workspace/inbox，"
            "不等於已經觸發完整 agent loop。"
        )

        return _payload(
            success=True,
            mode="ui_bridge_drop",
            summary="已將文字放入 workspace/inbox。",
            response=response_text,
            ui=_build_status_payload()["response"],
        )

    help_text = (
        "ZERO Web UI 已接到本地 ui_bridge。\n\n"
        "目前可用指令：\n"
        "- status / 狀態：顯示系統狀態、任務、shared 檔案\n"
        "- summary / 摘要：顯示最新 *_summary.txt\n"
        "- tasks / 任務：顯示最近任務狀態\n"
        "- task <task_id>：查看單一任務狀態與計畫摘要\n"
        "- files / 輸出檔案：列出 workspace/shared 檔案\n"
        "- view <filename>：讀取 workspace/shared 裡的指定檔案\n"
        "- drop 文字內容：把文字寫入 workspace/inbox\n\n"
        "目前這個 server.py 仍是 display/read-first，不直接開放完整 agent 遠端控制。"
    )

    return _payload(
        success=True,
        mode="ui_bridge_help",
        summary="Web UI 後端已運作，但這句不是完整 agent loop 執行。",
        warning="目前 /api/chat 先接 ui_bridge，不直接改 agent_loop 或 scheduler。",
        response=help_text,
        used_fallback=True,
        ui=status_data,
    )


@app.route("/", methods=["GET"])
def index() -> Any:
    return send_from_directory(UI_DIR, "index.html")


@app.route("/assets/persona/zero_v1/<path:filename>", methods=["GET"])
def persona_asset(filename: str) -> Any:
    return send_from_directory(PERSONA_ASSETS_DIR, filename)


@app.route("/api/health", methods=["GET"])
def api_health() -> Any:
    return jsonify(
        {
            "success": True,
            "message": "ZERO Web UI server is running.",
            "host": APP_HOST,
            "port": APP_PORT,
            "persona_assets": str(PERSONA_ASSETS_DIR),
        }
    )


@app.route("/api/status", methods=["GET"])
def api_status() -> Any:
    try:
        return jsonify(_build_status_payload())
    except Exception as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "mode": "ui_status",
                    "summary": "讀取 UI 狀態失敗。",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "meta": {
                        "model": "local-ui-bridge",
                        "used_fallback": False,
                        "llm_used": False,
                    },
                }
            ),
            500,
        )


@app.route("/api/chat", methods=["POST"])
def api_chat() -> Any:
    try:
        payload: Optional[Dict[str, Any]] = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return (
                jsonify(
                    {
                        "success": False,
                        "mode": "ui_bridge",
                        "summary": "請求格式錯誤。",
                        "error": "Expected JSON object.",
                        "response": "前端應送出 JSON，例如：{\"message\":\"status\"}",
                        "meta": {
                            "model": "local-ui-bridge",
                            "used_fallback": False,
                            "llm_used": False,
                        },
                    }
                ),
                400,
            )

        message = _safe_text(payload.get("message")).strip()

        if not message:
            return jsonify(
                {
                    "success": False,
                    "mode": "ui_bridge",
                    "summary": "沒有收到 message。",
                    "error": "Missing message.",
                    "response": "請輸入文字後再送出。",
                    "meta": {
                        "model": "local-ui-bridge",
                        "used_fallback": False,
                        "llm_used": False,
                    },
                }
            )

        return jsonify(_build_chat_payload(message))

    except Exception as exc:
        return (
            jsonify(
                {
                    "success": False,
                    "mode": "ui_bridge",
                    "summary": "Web UI 後端處理失敗。",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "response": "server.py 處理 /api/chat 時發生錯誤。",
                    "meta": {
                        "model": "local-ui-bridge",
                        "used_fallback": False,
                        "llm_used": False,
                    },
                }
            ),
            500,
        )


def main() -> int:
    print("ZERO Web UI server")
    print(f"Repo root       : {REPO_ROOT}")
    print(f"UI dir          : {UI_DIR}")
    print(f"Persona assets  : {PERSONA_ASSETS_DIR}")
    print(f"URL             : http://{APP_HOST}:{APP_PORT}")
    print("")
    app.run(host=APP_HOST, port=APP_PORT, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
