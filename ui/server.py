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
    list_inbox_files,
    list_shared_files,
    read_inbox_file,
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
    inbox_files = list_inbox_files(limit=20)

    return {
        "success": True,
        "mode": "ui_status",
        "summary": latest_summary or "目前沒有找到最新 summary。",
        "response": {
            "system_status": system_status,
            "latest_summary": latest_summary,
            "tasks": tasks,
            "shared_files": shared_files,
            "inbox_files": inbox_files,
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
        final_answer = _safe_text(task.get("final_answer"), "-")

        lines.append(
            "\n".join(
                [
                    f"{index}. {task_id}",
                    f"   status : {status}",
                    f"   step   : {step}",
                    f"   goal   : {goal}",
                    f"   result : {final_answer}",
                    f"   inspect: task {task_id}",
                ]
            )
        )

    return "\n\n".join(lines)


def _format_task_detail_for_display(detail: dict[str, Any]) -> str:
    files = detail.get("files") or []

    file_lines = []
    for item in files:
        file_lines.append(
            f"- {item.get('name')} ({item.get('size')} bytes)"
        )

    if not file_lines:
        file_lines.append("- no task-local files found")

    return (
        "[TASK DETAIL]\n"
        f"Task ID      : {detail.get('task_id') or '-'}\n"
        f"Status       : {detail.get('status') or '-'}\n"
        f"Step         : {detail.get('step') or '-'}\n"
        f"Goal         : {detail.get('goal') or '-'}\n"
        f"Final Answer : {detail.get('final_answer') or '-'}\n"
        "\n"
        "[PIPELINE]\n"
        f"Scenario     : {detail.get('scenario') or '-'}\n"
        f"Mode         : {detail.get('mode') or '-'}\n"
        f"Pipeline     : {detail.get('pipeline_name') or '-'}\n"
        f"Execution    : {detail.get('execution_name') or '-'}\n"
        "\n"
        "[FILES]\n"
        + "\n".join(file_lines)
    )


def _format_shared_files_for_display(files: list[str]) -> str:
    if not files:
        return "目前 workspace/shared 沒有可列出的檔案。"

    lines = []
    for name in files:
        lines.append(f"- {name}\n  view: view {name}")

    return "\n".join(lines)


def _format_inbox_files_for_display(files: list[dict[str, Any]]) -> str:
    if not files:
        return (
            "目前 workspace/inbox 沒有可列出的檔案。\n\n"
            "可用：\n"
            "- drop 文字內容\n"
            "- drop-as filename.txt 文字內容"
        )

    lines = []
    for item in files:
        name = _safe_text(item.get("name"), "-")
        size = item.get("size", "-")
        lines.append(f"- {name} ({size} bytes)\n  view: inbox {name}")

    return "\n".join(lines)


def _build_chat_payload(message: str) -> Dict[str, Any]:
    raw_message = message.strip()
    normalized = raw_message.lower()

    status_payload = _build_status_payload()
    status_data = status_payload["response"]

    system_status = status_data["system_status"]
    latest_summary = status_data["latest_summary"]
    tasks = status_data["tasks"]
    shared_files = status_data["shared_files"]
    inbox_files = status_data["inbox_files"]

    if normalized in {"status", "/status", "狀態", "系統狀態"}:
        response_text = (
            "[ZERO UI STATUS]\n"
            f"System Status: {system_status}\n\n"
            "[TASKS]\n"
            f"{_format_tasks_for_display(tasks)}\n\n"
            "[SHARED FILES]\n"
            f"{_format_shared_files_for_display(shared_files)}\n\n"
            "[INBOX]\n"
            f"{_format_inbox_files_for_display(inbox_files)}"
        )

        return {
            "success": True,
            "mode": "ui_bridge_status",
            "summary": f"系統目前狀態：{system_status}",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": status_data,
        }

    if normalized in {"summary", "/summary", "最新摘要", "摘要"}:
        response_text = latest_summary or "目前沒有找到最新 summary。"

        return {
            "success": True,
            "mode": "ui_bridge_summary",
            "summary": "已讀取 workspace/shared 內最新的 *_summary.txt。",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": status_data,
        }

    if normalized in {"tasks", "/tasks", "任務", "任務狀態"}:
        response_text = _format_tasks_for_display(tasks)

        return {
            "success": True,
            "mode": "ui_bridge_tasks",
            "summary": f"已讀取最近 {len(tasks)} 筆任務狀態。可輸入 task <task_id> 查看單一任務。",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": status_data,
        }

    if normalized.startswith("task "):
        task_id = raw_message[5:].strip()
        detail = get_task_detail(task_id)

        if detail is None:
            response_text = f"找不到任務或任務 ID 不合法：{task_id}"
            return {
                "success": False,
                "mode": "ui_bridge_task_detail",
                "summary": "讀取任務失敗。",
                "error": response_text,
                "response": response_text,
                "content": response_text,
                "meta": {
                    "model": "local-ui-bridge",
                    "used_fallback": False,
                    "llm_used": False,
                },
                "ui": status_data,
            }

        response_text = _format_task_detail_for_display(detail)

        return {
            "success": True,
            "mode": "ui_bridge_task_detail",
            "summary": f"已讀取任務：{task_id}",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": status_data,
            "task": detail,
        }

    if normalized in {"files", "/files", "shared", "輸出檔案"}:
        response_text = _format_shared_files_for_display(shared_files)

        return {
            "success": True,
            "mode": "ui_bridge_shared_files",
            "summary": f"已列出 workspace/shared 最近 {len(shared_files)} 個檔案。可輸入 view <filename> 查看內容。",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": status_data,
        }

    if normalized.startswith("view "):
        filename = raw_message[5:].strip()
        file_info = read_shared_file(filename)

        if file_info is None:
            response_text = f"找不到 shared 檔案或檔名不合法：{filename}"
            return {
                "success": False,
                "mode": "ui_bridge_shared_file_view",
                "summary": "讀取 shared 檔案失敗。",
                "error": response_text,
                "response": response_text,
                "content": response_text,
                "meta": {
                    "model": "local-ui-bridge",
                    "used_fallback": False,
                    "llm_used": False,
                },
                "ui": status_data,
            }

        response_text = (
            "[SHARED FILE]\n"
            f"Name: {file_info['name']}\n"
            f"Path: {file_info['path']}\n"
            f"Size: {file_info['size']} bytes\n"
            "\n"
            "[CONTENT]\n"
            f"{file_info['content']}"
        )

        return {
            "success": True,
            "mode": "ui_bridge_shared_file_view",
            "summary": f"已讀取 shared 檔案：{file_info['name']}",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": status_data,
            "file": file_info,
        }

    if normalized in {"inbox", "/inbox", "收件匣", "輸入匣"}:
        response_text = _format_inbox_files_for_display(inbox_files)

        return {
            "success": True,
            "mode": "ui_bridge_inbox",
            "summary": f"已列出 workspace/inbox 最近 {len(inbox_files)} 個檔案。",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": status_data,
        }

    if normalized.startswith("inbox "):
        filename = raw_message[6:].strip()
        file_info = read_inbox_file(filename)

        if file_info is None:
            response_text = f"找不到 inbox 檔案或檔名不合法：{filename}"
            return {
                "success": False,
                "mode": "ui_bridge_inbox_file_view",
                "summary": "讀取 inbox 檔案失敗。",
                "error": response_text,
                "response": response_text,
                "content": response_text,
                "meta": {
                    "model": "local-ui-bridge",
                    "used_fallback": False,
                    "llm_used": False,
                },
                "ui": status_data,
            }

        response_text = (
            "[INBOX FILE]\n"
            f"Name: {file_info['name']}\n"
            f"Path: {file_info['path']}\n"
            f"Size: {file_info['size']} bytes\n"
            "\n"
            "[CONTENT]\n"
            f"{file_info['content']}"
        )

        return {
            "success": True,
            "mode": "ui_bridge_inbox_file_view",
            "summary": f"已讀取 inbox 檔案：{file_info['name']}",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": status_data,
            "file": file_info,
        }

    if normalized.startswith("drop-as "):
        rest = raw_message[8:].strip()
        if " " not in rest:
            response_text = "格式：drop-as filename.txt 文字內容"
            return {
                "success": False,
                "mode": "ui_bridge_drop_as",
                "summary": "drop-as 指令格式錯誤。",
                "error": response_text,
                "response": response_text,
                "content": response_text,
                "meta": {
                    "model": "local-ui-bridge",
                    "used_fallback": False,
                    "llm_used": False,
                },
                "ui": status_data,
            }

        filename, content = rest.split(" ", 1)
        filename = filename.strip()
        content = content.strip()

        if not content:
            response_text = "drop-as 指令沒有內容。格式：drop-as filename.txt 文字內容"
            return {
                "success": False,
                "mode": "ui_bridge_drop_as",
                "summary": "drop-as 指令沒有內容。",
                "error": response_text,
                "response": response_text,
                "content": response_text,
                "meta": {
                    "model": "local-ui-bridge",
                    "used_fallback": False,
                    "llm_used": False,
                },
                "ui": status_data,
            }

        try:
            path = drop_text_file(content, filename=filename)
        except Exception as exc:
            response_text = f"寫入 inbox 失敗：{exc}"
            return {
                "success": False,
                "mode": "ui_bridge_drop_as",
                "summary": "寫入 inbox 失敗。",
                "error": response_text,
                "response": response_text,
                "content": response_text,
                "meta": {
                    "model": "local-ui-bridge",
                    "used_fallback": False,
                    "llm_used": False,
                },
                "ui": status_data,
            }

        response_text = (
            "[DROP FILE]\n"
            f"Path: {path}\n\n"
            "已將文字寫入 workspace/inbox。\n"
            "注意：這只是輸入匣，不會自動執行 agent_loop 或 scheduler。\n\n"
            f"view: inbox {Path(path).name}"
        )

        return {
            "success": True,
            "mode": "ui_bridge_drop_as",
            "summary": f"已寫入 inbox 檔案：{Path(path).name}",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": _build_status_payload()["response"],
        }

    if normalized.startswith("drop "):
        content = raw_message[5:].strip()

        if not content:
            response_text = "格式：drop 你要丟進 inbox 的文字"
            return {
                "success": False,
                "mode": "ui_bridge_drop",
                "summary": "drop 指令沒有內容。",
                "error": response_text,
                "response": response_text,
                "content": response_text,
                "meta": {
                    "model": "local-ui-bridge",
                    "used_fallback": False,
                    "llm_used": False,
                },
                "ui": status_data,
            }

        try:
            path = drop_text_file(content)
        except Exception as exc:
            response_text = f"寫入 inbox 失敗：{exc}"
            return {
                "success": False,
                "mode": "ui_bridge_drop",
                "summary": "寫入 inbox 失敗。",
                "error": response_text,
                "response": response_text,
                "content": response_text,
                "meta": {
                    "model": "local-ui-bridge",
                    "used_fallback": False,
                    "llm_used": False,
                },
                "ui": status_data,
            }

        response_text = (
            "[DROP TEXT]\n"
            f"Path: {path}\n\n"
            "已將文字寫入 workspace/inbox。\n"
            "注意：這只是輸入匣，不會自動執行 agent_loop 或 scheduler。\n\n"
            f"view: inbox {Path(path).name}"
        )

        return {
            "success": True,
            "mode": "ui_bridge_drop",
            "summary": "已將文字放入 workspace/inbox。",
            "response": response_text,
            "content": response_text,
            "meta": {
                "model": "local-ui-bridge",
                "used_fallback": False,
                "llm_used": False,
            },
            "ui": _build_status_payload()["response"],
        }

    help_text = (
        "ZERO Web UI 已接到本地 ui_bridge。\n\n"
        "目前可用指令：\n"
        "- status / 狀態：顯示系統狀態、任務、shared 檔案、inbox 檔案\n"
        "- summary / 摘要：顯示最新 *_summary.txt\n"
        "- tasks / 任務：顯示最近任務狀態\n"
        "- task <task_id>：查看單一任務 detail\n"
        "- files / 輸出檔案：列出 workspace/shared 檔案\n"
        "- view <filename>：讀取 workspace/shared 檔案內容\n"
        "- inbox：列出 workspace/inbox 檔案\n"
        "- inbox <filename>：讀取 workspace/inbox 檔案內容\n"
        "- drop 文字內容：把文字寫入 workspace/inbox，自動命名\n"
        "- drop-as filename.txt 文字內容：把文字寫入 workspace/inbox 指定檔名\n\n"
        "目前這是 read-only viewer + safe inbox drop workflow。\n"
        "它不會自動執行 agent_loop、scheduler 或任何遠端控制。"
    )

    return {
        "success": True,
        "mode": "ui_bridge_help",
        "summary": "Web UI 後端已運作。這是 display/inbox bridge，不是完整 agent control。",
        "warning": "目前 /api/chat 只接 ui_bridge，不直接改 agent_loop 或 scheduler。",
        "response": help_text,
        "content": help_text,
        "meta": {
            "model": "local-ui-bridge",
            "used_fallback": True,
            "llm_used": False,
        },
        "ui": status_data,
    }


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
