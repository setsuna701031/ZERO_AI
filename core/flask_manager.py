import os
import re
import sys
import time
import signal
import socket
import py_compile
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
APP_FILE = BASE_DIR / "app.py"
PID_FILE = BASE_DIR / "flask_server.pid"

AUTO_START = "# ZERO_AUTO_ROUTES_START"
AUTO_END = "# ZERO_AUTO_ROUTES_END"

HOST = "127.0.0.1"
PORT = 5000


def _python_executable() -> str:
    return sys.executable


def _read_app_text() -> str:
    return APP_FILE.read_text(encoding="utf-8")


def _write_app_text(text: str) -> None:
    APP_FILE.write_text(text, encoding="utf-8")


def _validate_route_name(route_name: str) -> tuple[bool, str]:
    if not route_name:
        return False, "route name is empty"

    if not re.fullmatch(r"[A-Za-z0-9_]+", route_name):
        return False, "route name only allows letters, numbers, underscore"

    return True, "ok"


def syntax_check_app() -> dict:
    try:
        py_compile.compile(str(APP_FILE), doraise=True)
        return {
            "success": True,
            "message": "語法檢查通過。",
            "command": f"{_python_executable()} -m py_compile {APP_FILE}",
            "file_path": str(APP_FILE),
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"語法檢查失敗：{exc}",
            "command": f"{_python_executable()} -m py_compile {APP_FILE}",
            "file_path": str(APP_FILE),
        }


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None

    try:
        content = PID_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return None
        return int(content)
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _remove_pid_file() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink()


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _get_listening_pids_on_port(port: int) -> list[int]:
    pids: set[int] = set()

    if os.name == "nt":
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            if "LISTENING" not in line.upper():
                continue

            parts = re.split(r"\s+", line)
            if len(parts) < 5:
                continue

            local_addr = parts[1]
            pid_text = parts[-1]

            if local_addr.endswith(f":{port}"):
                try:
                    pids.add(int(pid_text))
                except ValueError:
                    pass
    else:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pids.add(int(line))
            except ValueError:
                pass

    return sorted(pids)


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def _kill_pid(pid: int) -> bool:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
        else:
            os.kill(pid, signal.SIGTERM)

        return True
    except Exception:
        return False


def _kill_all_listeners_on_port(port: int) -> list[int]:
    killed: list[int] = []
    pids = _get_listening_pids_on_port(port)

    for pid in pids:
        if _kill_pid(pid):
            killed.append(pid)

    if killed:
        time.sleep(1.0)

    return killed


def _wait_for_port_state(host: str, port: int, should_be_open: bool, timeout: float = 5.0) -> bool:
    start = time.time()

    while time.time() - start < timeout:
        state = _is_port_open(host, port)
        if state == should_be_open:
            return True
        time.sleep(0.2)

    return False


def _wait_for_single_listener(port: int, expected_pid: int | None = None, timeout: float = 5.0) -> tuple[bool, list[int]]:
    start = time.time()

    while time.time() - start < timeout:
        pids = _get_listening_pids_on_port(port)

        if expected_pid is not None:
            if pids == [expected_pid]:
                return True, pids
        else:
            if len(pids) == 1:
                return True, pids

        time.sleep(0.2)

    return False, _get_listening_pids_on_port(port)


def start_flask_internal() -> dict:
    existing_pids = _get_listening_pids_on_port(PORT)
    if existing_pids:
        return {
            "success": False,
            "message": f"啟動前偵測到 {PORT} port 已被占用，PID={existing_pids}",
            "port_pids": existing_pids,
        }

    try:
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            process = subprocess.Popen(
                [_python_executable(), str(APP_FILE)],
                cwd=str(BASE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        else:
            process = subprocess.Popen(
                [_python_executable(), str(APP_FILE)],
                cwd=str(BASE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        pid = process.pid
        _write_pid(pid)

        port_open_ok = _wait_for_port_state(HOST, PORT, should_be_open=True, timeout=5.0)
        if not port_open_ok:
            if _is_pid_running(pid):
                _kill_pid(pid)
            _remove_pid_file()
            return {
                "success": False,
                "message": f"Flask 啟動失敗：{PORT} port 在等待時間內未開啟。",
                "pid": pid,
            }

        single_ok, pids = _wait_for_single_listener(PORT, expected_pid=pid, timeout=5.0)
        if not single_ok:
            if _is_pid_running(pid) and pid not in pids:
                _kill_pid(pid)
            return {
                "success": False,
                "message": f"Flask 啟動異常：{PORT} port 監聽 PID 不符合預期，當前 PID={pids}",
                "pid": pid,
                "port_pids": pids,
            }

        return {
            "success": True,
            "message": f"Flask 已啟動：http://{HOST}:{PORT}，目前 PID=[{pid}]",
            "pid": pid,
            "port_pids": pids,
        }
    except Exception as exc:
        _remove_pid_file()
        return {
            "success": False,
            "message": f"Flask 啟動失敗：{exc}",
        }


def stop_flask_internal() -> dict:
    pid_from_file = _read_pid()
    killed: list[int] = []

    if pid_from_file and _is_pid_running(pid_from_file):
        if _kill_pid(pid_from_file):
            killed.append(pid_from_file)
            time.sleep(0.8)

    port_pids = _get_listening_pids_on_port(PORT)
    for pid in port_pids:
        if pid not in killed:
            if _kill_pid(pid):
                killed.append(pid)

    if killed:
        time.sleep(1.0)

    still_listening = _get_listening_pids_on_port(PORT)
    _remove_pid_file()

    if still_listening:
        return {
            "success": False,
            "message": f"Flask 停止不完整，{PORT} port 仍被 PID={still_listening} 占用。",
            "killed_pids": killed,
            "remaining_pids": still_listening,
        }

    if killed:
        return {
            "success": True,
            "message": f"Flask 已停止，清除 PID={killed}",
            "killed_pids": killed,
        }

    return {
        "success": True,
        "message": "目前沒有偵測到運行中的 Flask。",
        "killed_pids": [],
    }


def restart_flask_internal() -> dict:
    stop_result = stop_flask_internal()

    if not stop_result.get("success"):
        return {
            "success": False,
            "message": f"重啟失敗：停止舊 Flask 時發生問題。{stop_result.get('message', '')}",
            "stop_result": stop_result,
        }

    if _is_port_open(HOST, PORT):
        killed = _kill_all_listeners_on_port(PORT)
        time.sleep(1.0)

        if _is_port_open(HOST, PORT):
            remain = _get_listening_pids_on_port(PORT)
            return {
                "success": False,
                "message": f"重啟失敗：停止後 {PORT} port 仍被占用，PID={remain}",
                "killed_pids": killed,
                "remaining_pids": remain,
            }

    start_result = start_flask_internal()
    if not start_result.get("success"):
        return start_result

    return {
        "success": True,
        "message": start_result["message"].replace("已啟動", "已重新啟動"),
        "pid": start_result.get("pid"),
        "port_pids": start_result.get("port_pids", []),
    }


def build_flask_api() -> dict:
    if APP_FILE.exists():
        return {
            "success": True,
            "message": f"app.py 已存在：{APP_FILE}",
            "file_path": str(APP_FILE),
        }

    template = '''from flask import Flask, jsonify, request
from core.ai_handler import handle_ai_ask

app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "ZERO Flask API is running",
        "status": "ok"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "health": "good"
    })


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "zero_core": "running",
        "flask": "ok",
        "version": "v0.1.0"
    })


@app.route("/ai/ask", methods=["POST"])
def ai_ask():
    data = request.get_json(silent=True) or {}
    result = handle_ai_ask(data)
    return jsonify(result)


# ZERO_AUTO_ROUTES_START

# ZERO_AUTO_ROUTES_END


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
'''
    APP_FILE.write_text(template, encoding="utf-8")

    return {
        "success": True,
        "message": f"已建立 Flask API 檔案：{APP_FILE}",
        "file_path": str(APP_FILE),
    }


def _extract_auto_block(app_text: str) -> tuple[str, str, str]:
    if AUTO_START not in app_text or AUTO_END not in app_text:
        raise ValueError("app.py 找不到 ZERO_AUTO_ROUTES_START / END 區塊")

    start_idx = app_text.index(AUTO_START)
    end_idx = app_text.index(AUTO_END)

    before = app_text[: start_idx + len(AUTO_START)]
    middle = app_text[start_idx + len(AUTO_START): end_idx]
    after = app_text[end_idx:]

    return before, middle, after


def list_flask_routes() -> dict:
    try:
        app_text = _read_app_text()
        _, middle, _ = _extract_auto_block(app_text)

        route_blocks = re.findall(
            r'@app\.route\("/([^"]+)", methods=\[(.*?)\]\)\s+def\s+([A-Za-z0-9_]+)\(',
            middle,
            flags=re.DOTALL,
        )

        result = []
        for route_path, method_text, func_name in route_blocks:
            method_text = method_text.replace('"', "").replace("'", "").strip()
            result.append({
                "route": f"/{route_path}",
                "methods": method_text,
                "function": func_name,
            })

        return {
            "success": True,
            "message": "列出 Flask 自動路由成功。",
            "routes": result,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"列出 Flask 路由失敗：{exc}",
            "routes": [],
        }


def _generate_get_route_code(route_name: str) -> str:
    func_name = f"zero_route_{route_name}"
    return f'''

@app.route("/{route_name}", methods=["GET"])
def {func_name}():
    return jsonify({{
        "route": "{route_name}",
        "message": "ZERO auto route {route_name} is running"
    }})
'''


def _generate_post_route_code(route_name: str) -> str:
    func_name = f"zero_post_route_{route_name}"
    return f'''

@app.route("/{route_name}", methods=["POST"])
def {func_name}():
    data = request.get_json(silent=True) or {{}}
    return jsonify({{
        "route": "{route_name}",
        "received": data
    }})
'''


def add_flask_route(route_name: str, method: str = "GET") -> dict:
    ok, message = _validate_route_name(route_name)
    if not ok:
        return {"success": False, "message": message}

    method = method.upper().strip()
    if method not in {"GET", "POST"}:
        return {"success": False, "message": "only GET or POST supported"}

    try:
        app_text = _read_app_text()
        before, middle, after = _extract_auto_block(app_text)

        existing_patterns = [
            f'@app.route("/{route_name}", methods=["GET"])',
            f'@app.route("/{route_name}", methods=["POST"])',
            f"def zero_route_{route_name}(",
            f"def zero_post_route_{route_name}(",
        ]
        for pattern in existing_patterns:
            if pattern in middle:
                return {
                    "success": False,
                    "message": f"route '{route_name}' 已存在。",
                }

        if method == "GET":
            new_code = _generate_get_route_code(route_name)
        else:
            new_code = _generate_post_route_code(route_name)

        updated = before + middle.rstrip() + new_code + "\n\n" + after.lstrip()
        _write_app_text(updated)

        return {
            "success": True,
            "message": f"已新增 {method} route: /{route_name}",
            "route_name": route_name,
            "method": method,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"新增 Flask route 失敗：{exc}",
        }


def remove_flask_route(route_name: str) -> dict:
    ok, message = _validate_route_name(route_name)
    if not ok:
        return {"success": False, "message": message}

    try:
        app_text = _read_app_text()
        before, middle, after = _extract_auto_block(app_text)

        pattern_get = re.compile(
            rf'\n*@app\.route\("/{re.escape(route_name)}", methods=\["GET"\]\)\n'
            rf'def zero_route_{re.escape(route_name)}\(\):\n'
            rf'(?:    .*\n)+?',
            flags=re.MULTILINE,
        )

        pattern_post = re.compile(
            rf'\n*@app\.route\("/{re.escape(route_name)}", methods=\["POST"\]\)\n'
            rf'def zero_post_route_{re.escape(route_name)}\(\):\n'
            rf'(?:    .*\n)+?',
            flags=re.MULTILINE,
        )

        new_middle = pattern_get.sub("\n", middle)
        new_middle = pattern_post.sub("\n", new_middle)

        if new_middle == middle:
            return {
                "success": False,
                "message": f"route '{route_name}' 不存在。",
            }

        updated = before + new_middle.rstrip() + "\n\n" + after.lstrip()
        _write_app_text(updated)

        return {
            "success": True,
            "message": f"已移除 route: /{route_name}",
            "route_name": route_name,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"移除 Flask route 失敗：{exc}",
        }