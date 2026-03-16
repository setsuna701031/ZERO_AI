import os
import sys
import json
import time
import re
import socket
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


@dataclass
class StepResult:
    step_name: str
    success: bool
    message: str
    command: Optional[str] = None
    file_path: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    error_type: Optional[str] = None


@dataclass
class AgentResult:
    success: bool
    user_command: str
    plan_name: str
    steps: List[Dict[str, Any]]
    summary: str


class ProjectAgent:
    AUTO_ROUTE_START = "# ZERO_AUTO_ROUTES_START"
    AUTO_ROUTE_END = "# ZERO_AUTO_ROUTES_END"

    def __init__(self, project_root: Optional[str] = None):
        if project_root is None:
            self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        else:
            self.project_root = os.path.abspath(project_root)

        self.python_executable = sys.executable
        self.flask_host = "127.0.0.1"
        self.flask_port = 5000
        self.flask_process: Optional[subprocess.Popen] = None
        self.flask_log_path = os.path.join(self.project_root, "flask_server.log")

    # =========================
    # Public API
    # =========================

    def run(self, user_command: str) -> AgentResult:
        user_command = (user_command or "").strip()

        if not user_command:
            return self._build_result(
                success=False,
                user_command=user_command,
                plan_name="EMPTY_COMMAND",
                steps=[self._step("validate_command", False, "沒有收到指令。")],
                summary="指令為空，無法執行。"
            )

        normalized = user_command.lower().strip()

        if normalized == "build flask api":
            return self._handle_build_flask_api(user_command)

        if normalized == "stop flask api":
            return self._handle_stop_flask_api(user_command)

        if normalized == "restart flask":
            return self._handle_restart_flask(user_command)

        if normalized == "list flask routes":
            return self._handle_list_flask_routes(user_command)

        if normalized.startswith("add flask route "):
            return self._handle_add_flask_route(user_command)

        if normalized.startswith("remove flask route "):
            return self._handle_remove_flask_route(user_command)

        if normalized.startswith("install package "):
            return self._handle_install_package_command(user_command)

        return self._build_result(
            success=False,
            user_command=user_command,
            plan_name="UNKNOWN_COMMAND",
            steps=[self._step("route_command", False, f"目前尚未支援此指令：{user_command}")],
            summary="指令未支援。"
        )

    # =========================
    # Main Task
    # =========================

    def _handle_build_flask_api(self, user_command: str) -> AgentResult:
        steps: List[Dict[str, Any]] = []

        existing_py_files = self._list_python_files(self.project_root)
        steps.append(self._step(
            "scan_project_files",
            True,
            f"已掃描專案 Python 檔案，共找到 {len(existing_py_files)} 個。",
            stdout="\n".join(existing_py_files)
        ))

        target_file = self._choose_flask_entry_file(existing_py_files)
        target_path = os.path.join(self.project_root, target_file)
        steps.append(self._step(
            "choose_target_file",
            True,
            f"Flask 目標檔案決定為：{target_file}",
            file_path=target_path
        ))

        file_exists = os.path.exists(target_path)
        steps.append(self._step(
            "check_target_file_exists",
            True,
            f"檔案存在狀態：{file_exists}",
            file_path=target_path
        ))

        if not file_exists:
            create_result = self._create_flask_app_file(target_path)
            steps.append(asdict(create_result))
            if not create_result.success:
                return self._build_result(False, user_command, "BUILD_FLASK_API", steps, "建立 Flask 檔案失敗。")
        else:
            ensure_result = self._ensure_auto_route_markers(target_path)
            steps.append(asdict(ensure_result))
            if not ensure_result.success:
                return self._build_result(False, user_command, "BUILD_FLASK_API", steps, "現有 app.py 缺少 auto route 區塊，且補齊失敗。")

        syntax_result = self._run_python_compile(target_path)
        steps.append(asdict(syntax_result))
        if not syntax_result.success:
            return self._build_result(False, user_command, "BUILD_FLASK_API", steps, "Flask 檔案已建立，但語法檢查失敗。")

        pids_before = self._get_listening_pids_on_port(self.flask_port)
        steps.append(self._step(
            "check_server_already_running",
            True,
            f"{self.flask_host}:{self.flask_port} 目前 LISTENING PIDs：{pids_before if pids_before else '無'}"
        ))

        if pids_before:
            return self._build_result(
                True,
                user_command,
                "BUILD_FLASK_API",
                steps,
                f"Flask API 已可使用，網址：http://{self.flask_host}:{self.flask_port} 。目前已有服務在執行，未重複啟動。"
            )

        launch_result = self._start_flask_in_background(target_path)
        steps.append(asdict(launch_result))

        if not launch_result.success:
            error_text = (launch_result.stderr or "") + "\n" + (launch_result.stdout or "")
            missing_module = self._extract_missing_module(error_text)

            steps.append(self._step(
                "detect_missing_module",
                bool(missing_module),
                f"缺少模組偵測結果：{missing_module or '未偵測到'}"
            ))

            if missing_module:
                package_name = self._map_module_to_package(missing_module)
                install_result = self._install_package(package_name)
                steps.append(asdict(install_result))

                if install_result.success:
                    relaunch_result = self._start_flask_in_background(target_path)
                    relaunch_data = asdict(relaunch_result)
                    relaunch_data["step_name"] = "restart_flask_after_install"
                    steps.append(relaunch_data)

                    if relaunch_result.success:
                        final_check = self._is_port_open(self.flask_host, self.flask_port)
                        steps.append(self._step(
                            "verify_server_port_open_after_install",
                            final_check,
                            f"安裝套件後最終確認 {self.flask_host}:{self.flask_port} 可連線狀態：{final_check}"
                        ))
                        if final_check:
                            return self._build_result(
                                True,
                                user_command,
                                "BUILD_FLASK_API",
                                steps,
                                f"Flask API 已建立成功。啟動時偵測到缺少套件 {package_name}，已自動安裝並重新啟動成功。請打開：http://{self.flask_host}:{self.flask_port}"
                            )

            classified = self._classify_error(error_text)
            steps.append(self._step("classify_error", True, f"錯誤分類結果：{classified}", error_type=classified))
            return self._build_result(False, user_command, "BUILD_FLASK_API", steps, "Flask 檔案已建立，但背景啟動失敗。")

        final_check = self._is_port_open(self.flask_host, self.flask_port)
        steps.append(self._step(
            "verify_server_port_open",
            final_check,
            f"最終確認 {self.flask_host}:{self.flask_port} 可連線狀態：{final_check}"
        ))

        if final_check:
            return self._build_result(
                True,
                user_command,
                "BUILD_FLASK_API",
                steps,
                f"Flask API 已建立並成功背景啟動。請打開：http://{self.flask_host}:{self.flask_port}"
            )

        return self._build_result(False, user_command, "BUILD_FLASK_API", steps, "Flask 看似已啟動，但最終連線驗證失敗。")

    # =========================
    # Route Operations
    # =========================

    def _handle_list_flask_routes(self, user_command: str) -> AgentResult:
        steps: List[Dict[str, Any]] = []
        app_path = self._get_app_file_path()

        if not os.path.exists(app_path):
            steps.append(self._step("check_app_file", False, f"找不到 Flask 檔案：{app_path}", file_path=app_path))
            return self._build_result(False, user_command, "LIST_FLASK_ROUTES", steps, "找不到 app.py，請先執行 build flask api。")

        routes = self._extract_auto_route_names(app_path)
        steps.append(self._step(
            "extract_routes",
            True,
            f"已找到 {len(routes)} 個 auto routes。",
            file_path=app_path,
            stdout="\n".join(routes) if routes else "(none)"
        ))

        summary = "目前 auto routes：" + (" " + ", ".join(routes) if routes else " 無")
        return self._build_result(True, user_command, "LIST_FLASK_ROUTES", steps, summary)

    def _handle_add_flask_route(self, user_command: str) -> AgentResult:
        steps: List[Dict[str, Any]] = []
        route_name = user_command[len("add flask route "):].strip()
        app_path = self._get_app_file_path()

        safe_route_name = self._sanitize_route_name(route_name)
        if not safe_route_name:
            steps.append(self._step("sanitize_route_name", False, f"route 名稱不合法：{route_name}"))
            return self._build_result(False, user_command, "ADD_FLASK_ROUTE", steps, "新增 route 失敗，名稱不合法。只允許英文、數字、底線，且不能以數字開頭。")

        if not os.path.exists(app_path):
            steps.append(self._step("check_app_file", False, f"找不到 Flask 檔案：{app_path}", file_path=app_path))
            return self._build_result(False, user_command, "ADD_FLASK_ROUTE", steps, "找不到 app.py，請先執行 build flask api。")

        ensure_result = self._ensure_auto_route_markers(app_path)
        steps.append(asdict(ensure_result))
        if not ensure_result.success:
            return self._build_result(False, user_command, "ADD_FLASK_ROUTE", steps, "app.py 缺少 auto route 區塊，且補齊失敗。")

        existing_routes = self._extract_auto_route_names(app_path)
        steps.append(self._step(
            "read_existing_routes",
            True,
            f"現有 auto routes 數量：{len(existing_routes)}",
            stdout="\n".join(existing_routes) if existing_routes else "(none)"
        ))

        if safe_route_name not in existing_routes:
            add_result = self._append_auto_route(app_path, safe_route_name)
            steps.append(asdict(add_result))
            if not add_result.success:
                return self._build_result(False, user_command, "ADD_FLASK_ROUTE", steps, f"新增 route 失敗：/{safe_route_name}")
        else:
            steps.append(self._step(
                "append_auto_route",
                True,
                f"Route 已存在於 app.py：/{safe_route_name}",
                file_path=app_path
            ))

        syntax_result = self._run_python_compile(app_path)
        syntax_data = asdict(syntax_result)
        syntax_data["step_name"] = "syntax_check_after_add_route"
        steps.append(syntax_data)
        if not syntax_result.success:
            return self._build_result(False, user_command, "ADD_FLASK_ROUTE", steps, "新增 route 後語法檢查失敗。")

        restart_result = self._restart_flask_internal(app_path)
        restart_data = asdict(restart_result)
        restart_data["step_name"] = "restart_flask_after_add_route"
        steps.append(restart_data)
        if not restart_result.success:
            return self._build_result(False, user_command, "ADD_FLASK_ROUTE", steps, f"Route 已寫入，但 Flask 重啟失敗：/{safe_route_name}")

        http_verify = self._verify_http_route(safe_route_name)
        http_verify_data = asdict(http_verify)
        http_verify_data["step_name"] = "verify_http_route_after_add"
        steps.append(http_verify_data)

        if not http_verify.success:
            return self._build_result(False, user_command, "ADD_FLASK_ROUTE", steps, f"Route 已寫入且 Flask 已重啟，但 HTTP 驗證失敗：/{safe_route_name}")

        return self._build_result(
            True,
            user_command,
            "ADD_FLASK_ROUTE",
            steps,
            f"已新增 route 並驗證成功：/{safe_route_name} ，請打開：http://{self.flask_host}:{self.flask_port}/{safe_route_name}"
        )

    def _handle_remove_flask_route(self, user_command: str) -> AgentResult:
        steps: List[Dict[str, Any]] = []
        route_name = user_command[len("remove flask route "):].strip()
        app_path = self._get_app_file_path()

        safe_route_name = self._sanitize_route_name(route_name)
        if not safe_route_name:
            steps.append(self._step("sanitize_route_name", False, f"route 名稱不合法：{route_name}"))
            return self._build_result(False, user_command, "REMOVE_FLASK_ROUTE", steps, "刪除 route 失敗，名稱不合法。")

        if not os.path.exists(app_path):
            steps.append(self._step("check_app_file", False, f"找不到 Flask 檔案：{app_path}", file_path=app_path))
            return self._build_result(False, user_command, "REMOVE_FLASK_ROUTE", steps, "找不到 app.py，請先執行 build flask api。")

        remove_result = self._remove_auto_route(app_path, safe_route_name)
        steps.append(asdict(remove_result))
        if not remove_result.success:
            return self._build_result(False, user_command, "REMOVE_FLASK_ROUTE", steps, f"找不到可刪除的 route：/{safe_route_name}")

        syntax_result = self._run_python_compile(app_path)
        syntax_data = asdict(syntax_result)
        syntax_data["step_name"] = "syntax_check_after_remove_route"
        steps.append(syntax_data)
        if not syntax_result.success:
            return self._build_result(False, user_command, "REMOVE_FLASK_ROUTE", steps, "刪除 route 後語法檢查失敗。")

        restart_result = self._restart_flask_internal(app_path)
        restart_data = asdict(restart_result)
        restart_data["step_name"] = "restart_flask_after_remove_route"
        steps.append(restart_data)
        if not restart_result.success:
            return self._build_result(False, user_command, "REMOVE_FLASK_ROUTE", steps, f"Route 已刪除，但 Flask 重啟失敗：/{safe_route_name}")

        http_verify_removed = self._verify_http_route_removed(safe_route_name)
        http_verify_removed_data = asdict(http_verify_removed)
        http_verify_removed_data["step_name"] = "verify_http_route_removed"
        steps.append(http_verify_removed_data)

        if not http_verify_removed.success:
            return self._build_result(False, user_command, "REMOVE_FLASK_ROUTE", steps, f"Route 已從 app.py 刪除，但 HTTP 驗證未通過：/{safe_route_name}")

        return self._build_result(True, user_command, "REMOVE_FLASK_ROUTE", steps, f"已刪除 route 並驗證成功：/{safe_route_name}")

    # =========================
    # Restart / Stop
    # =========================

    def _handle_restart_flask(self, user_command: str) -> AgentResult:
        steps: List[Dict[str, Any]] = []
        app_path = self._get_app_file_path()

        if not os.path.exists(app_path):
            steps.append(self._step("check_app_file", False, f"找不到 Flask 檔案：{app_path}", file_path=app_path))
            return self._build_result(False, user_command, "RESTART_FLASK", steps, "找不到 app.py，請先執行 build flask api。")

        syntax_result = self._run_python_compile(app_path)
        steps.append(asdict(syntax_result))
        if not syntax_result.success:
            return self._build_result(False, user_command, "RESTART_FLASK", steps, "Flask 重啟前語法檢查失敗。")

        restart_result = self._restart_flask_internal(app_path)
        steps.append(asdict(restart_result))

        if restart_result.success:
            return self._build_result(True, user_command, "RESTART_FLASK", steps, f"Flask 已重新啟動。請打開：http://{self.flask_host}:{self.flask_port}")

        return self._build_result(False, user_command, "RESTART_FLASK", steps, "Flask 重啟失敗。")

    def _handle_stop_flask_api(self, user_command: str) -> AgentResult:
        steps: List[Dict[str, Any]] = []
        stop_result = self._stop_flask_internal()
        steps.append(asdict(stop_result))

        if stop_result.success:
            return self._build_result(True, user_command, "STOP_FLASK_API", steps, "Flask 背景服務已停止。")

        return self._build_result(False, user_command, "STOP_FLASK_API", steps, "停止 Flask 背景服務失敗。")

    # =========================
    # install package <name>
    # =========================

    def _handle_install_package_command(self, user_command: str) -> AgentResult:
        steps: List[Dict[str, Any]] = []
        package_name = user_command[len("install package "):].strip()

        if not package_name:
            steps.append(self._step("parse_package_name", False, "沒有提供套件名稱。"))
            return self._build_result(False, user_command, "INSTALL_PACKAGE", steps, "安裝失敗，因為沒有提供套件名稱。")

        safe_name = self._sanitize_package_name(package_name)
        if not safe_name:
            steps.append(self._step("sanitize_package_name", False, f"套件名稱不合法：{package_name}"))
            return self._build_result(False, user_command, "INSTALL_PACKAGE", steps, "安裝失敗，套件名稱不合法。")

        install_result = self._install_package(safe_name)
        steps.append(asdict(install_result))

        if install_result.success:
            return self._build_result(True, user_command, "INSTALL_PACKAGE", steps, f"套件已安裝成功：{safe_name}")

        return self._build_result(False, user_command, "INSTALL_PACKAGE", steps, f"套件安裝失敗：{safe_name}")

    # =========================
    # File / Template Logic
    # =========================

    def _get_app_file_path(self) -> str:
        return os.path.join(self.project_root, "app.py")

    def _choose_flask_entry_file(self, existing_py_files: List[str]) -> str:
        preferred = ["app.py", "server.py", "api.py"]
        normalized = {os.path.basename(x).lower(): x for x in existing_py_files}
        for name in preferred:
            if name in normalized:
                return os.path.basename(normalized[name])
        return "app.py"

    def _create_flask_app_file(self, file_path: str) -> StepResult:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            code = self._flask_template_code()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            return StepResult("create_flask_file", True, f"已建立 Flask 檔案：{file_path}", file_path=file_path)
        except Exception as e:
            return StepResult("create_flask_file", False, f"建立 Flask 檔案失敗：{e}", file_path=file_path, stderr=str(e), error_type="CREATE_FILE_ERROR")

    def _flask_template_code(self) -> str:
        return f'''from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return jsonify({{
        "message": "ZERO Flask API is running",
        "status": "ok"
    }})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({{
        "health": "good"
    }})


@app.route("/echo", methods=["POST"])
def echo():
    data = request.get_json(silent=True) or {{}}
    return jsonify({{
        "you_sent": data
    }})


{self.AUTO_ROUTE_START}

{self.AUTO_ROUTE_END}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
'''

    def _ensure_auto_route_markers(self, file_path: str) -> StepResult:
        try:
            content = self._read_text_if_exists(file_path)
            if not content:
                return StepResult("ensure_auto_route_markers", False, "讀取 app.py 失敗或內容為空。", file_path=file_path, error_type="EMPTY_APP_FILE")

            if self.AUTO_ROUTE_START in content and self.AUTO_ROUTE_END in content:
                return StepResult("ensure_auto_route_markers", True, "app.py 已包含 auto route 區塊。", file_path=file_path)

            marker_block = f"\n\n{self.AUTO_ROUTE_START}\n\n{self.AUTO_ROUTE_END}\n"
            insertion_target = '\n\nif __name__ == "__main__":'

            if insertion_target in content:
                content = content.replace(insertion_target, marker_block + insertion_target, 1)
            else:
                content += marker_block

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return StepResult("ensure_auto_route_markers", True, "已補齊 auto route 區塊。", file_path=file_path)
        except Exception as e:
            return StepResult("ensure_auto_route_markers", False, f"補齊 auto route 區塊失敗：{e}", file_path=file_path, stderr=str(e), error_type="ENSURE_AUTO_ROUTE_MARKERS_ERROR")

    def _extract_auto_route_block(self, content: str) -> Optional[str]:
        pattern = rf"{re.escape(self.AUTO_ROUTE_START)}(.*?){re.escape(self.AUTO_ROUTE_END)}"
        match = re.search(pattern, content, flags=re.DOTALL)
        if not match:
            return None
        return match.group(1)

    def _extract_auto_route_names(self, file_path: str) -> List[str]:
        content = self._read_text_if_exists(file_path)
        block = self._extract_auto_route_block(content)
        if block is None:
            return []
        names = re.findall(r'@app\.route\("/([A-Za-z_][A-Za-z0-9_]*)"', block)
        return sorted(set(names))

    def _append_auto_route(self, file_path: str, route_name: str) -> StepResult:
        try:
            content = self._read_text_if_exists(file_path)
            if self.AUTO_ROUTE_START not in content or self.AUTO_ROUTE_END not in content:
                return StepResult("append_auto_route", False, "app.py 缺少 auto route 區塊。", file_path=file_path, error_type="AUTO_ROUTE_BLOCK_NOT_FOUND")

            route_code = self._build_route_code(route_name)
            content = content.replace(self.AUTO_ROUTE_END, route_code + "\n" + self.AUTO_ROUTE_END, 1)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return StepResult("append_auto_route", True, f"已寫入 route：/{route_name}", file_path=file_path)
        except Exception as e:
            return StepResult("append_auto_route", False, f"寫入 route 失敗：{e}", file_path=file_path, stderr=str(e), error_type="APPEND_ROUTE_ERROR")

    def _remove_auto_route(self, file_path: str, route_name: str) -> StepResult:
        try:
            content = self._read_text_if_exists(file_path)

            patterns = [
                (
                    r'\n@app\.route\("/' + re.escape(route_name) + r'", methods=\["GET"\]\)\n'
                    r"def zero_route_" + re.escape(route_name) + r"\(\):\n"
                    r'    return jsonify\(\{\n'
                    r'        "route": "' + re.escape(route_name) + r'",\n'
                    r'        "message": "ZERO 自動路由 ' + re.escape(route_name) + r' 正在執行"\n'
                    r'    \}\)\n'
                ),
                (
                    r'\n@app\.route\("/' + re.escape(route_name) + r'", methods=\["GET"\]\)\n'
                    r"def zero_route_" + re.escape(route_name) + r"\(\):\n"
                    r'    return jsonify\(\{\n'
                    r'        "route": "' + re.escape(route_name) + r'",\n'
                    r'        "message": "ZERO auto route ' + re.escape(route_name) + r' is running"\n'
                    r'    \}\)\n'
                )
            ]

            new_content = content
            removed = 0
            for pattern in patterns:
                new_content, count = re.subn(pattern, "\n", new_content)
                removed += count

            if removed == 0:
                return StepResult("remove_auto_route", False, f"找不到 route：/{route_name}", file_path=file_path, error_type="ROUTE_NOT_FOUND")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return StepResult("remove_auto_route", True, f"已刪除 route：/{route_name}", file_path=file_path)
        except Exception as e:
            return StepResult("remove_auto_route", False, f"刪除 route 失敗：{e}", file_path=file_path, stderr=str(e), error_type="REMOVE_ROUTE_ERROR")

    def _build_route_code(self, route_name: str) -> str:
        return f'''
@app.route("/{route_name}", methods=["GET"])
def zero_route_{route_name}():
    return jsonify({{
        "route": "{route_name}",
        "message": "ZERO 自動路由 {route_name} 正在執行"
    }})
'''

    # =========================
    # Execution / Validation
    # =========================

    def _run_python_compile(self, file_path: str) -> StepResult:
        cmd = [self.python_executable, "-m", "py_compile", file_path]
        try:
            completed = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=10)
            if completed.returncode == 0:
                return StepResult("syntax_check", True, "語法檢查通過。", command=" ".join(cmd), file_path=file_path, stdout=completed.stdout, stderr=completed.stderr)
            return StepResult("syntax_check", False, "語法檢查失敗。", command=" ".join(cmd), file_path=file_path, stdout=completed.stdout, stderr=completed.stderr, error_type="SYNTAX_ERROR")
        except Exception as e:
            return StepResult("syntax_check", False, f"語法檢查執行失敗：{e}", command=" ".join(cmd), file_path=file_path, stderr=str(e), error_type="SYNTAX_CHECK_EXCEPTION")

    def _start_flask_in_background(self, file_path: str) -> StepResult:
        cmd = [self.python_executable, file_path]

        try:
            if self._is_port_open(self.flask_host, self.flask_port):
                existing_pids = self._get_listening_pids_on_port(self.flask_port)
                return StepResult(
                    "start_flask_background",
                    True,
                    f"偵測到 {self.flask_host}:{self.flask_port} 已有服務在運行，PID={existing_pids if existing_pids else 'unknown'}，略過重複啟動。",
                    command=" ".join(cmd),
                    file_path=file_path
                )

            log_file = open(self.flask_log_path, "w", encoding="utf-8")

            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                stdout=log_file,
                stderr=log_file,
                text=True,
                creationflags=creationflags
            )

            self.flask_process = process

            started = False
            for _ in range(20):
                if self._is_port_open(self.flask_host, self.flask_port):
                    started = True
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.5)

            if started:
                return StepResult(
                    "start_flask_background",
                    True,
                    f"Flask 已背景啟動，PID={process.pid}，網址：http://{self.flask_host}:{self.flask_port}",
                    command=" ".join(cmd),
                    file_path=file_path
                )

            stderr_text = self._read_text_if_exists(self.flask_log_path)
            return StepResult(
                "start_flask_background",
                False,
                "Flask 背景啟動失敗或未在預期時間內開啟服務埠。",
                command=" ".join(cmd),
                file_path=file_path,
                stderr=stderr_text,
                error_type=self._classify_error(stderr_text)
            )

        except Exception as e:
            return StepResult("start_flask_background", False, f"背景啟動 Flask 失敗：{e}", command=" ".join(cmd), file_path=file_path, stderr=str(e), error_type="START_BACKGROUND_ERROR")

    def _install_package(self, package_name: str) -> StepResult:
        safe_name = self._sanitize_package_name(package_name)
        if not safe_name:
            return StepResult("install_package", False, f"套件名稱不合法：{package_name}", stderr=f"Invalid package name: {package_name}", error_type="INVALID_PACKAGE_NAME")

        cmd = [self.python_executable, "-m", "pip", "install", safe_name]
        try:
            completed = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=300)
            if completed.returncode == 0:
                return StepResult("install_package", True, f"已成功安裝套件：{safe_name}", command=" ".join(cmd), stdout=completed.stdout, stderr=completed.stderr)
            return StepResult("install_package", False, f"安裝套件失敗：{safe_name}", command=" ".join(cmd), stdout=completed.stdout, stderr=completed.stderr, error_type="PIP_INSTALL_FAILED")
        except subprocess.TimeoutExpired:
            return StepResult("install_package", False, f"安裝套件逾時：{safe_name}", command=" ".join(cmd), error_type="PIP_INSTALL_TIMEOUT")
        except Exception as e:
            return StepResult("install_package", False, f"安裝套件時發生例外：{e}", command=" ".join(cmd), stderr=str(e), error_type="PIP_INSTALL_EXCEPTION")

    def _stop_flask_internal(self) -> StepResult:
        try:
            messages = []

            if self.flask_process is not None:
                if self.flask_process.poll() is None:
                    pid = self.flask_process.pid
                    self.flask_process.terminate()
                    self.flask_process.wait(timeout=5)
                    messages.append(f"已停止 agent 記錄的 Flask 行程，PID={pid}")
                else:
                    messages.append("agent 記錄的 Flask 行程原本就已結束。")
                self.flask_process = None

            pids = self._get_listening_pids_on_port(self.flask_port)
            killed_pids = []

            for pid in pids:
                if self._kill_pid(pid):
                    killed_pids.append(pid)

            if killed_pids:
                messages.append(f"已強制停止占用 {self.flask_port} port 的 PID：{killed_pids}")

            time.sleep(1.0)

            remaining = self._get_listening_pids_on_port(self.flask_port)
            if remaining:
                return StepResult(
                    "stop_flask_internal",
                    False,
                    f"停止後仍有 PID 占用 {self.flask_port}：{remaining}",
                    stderr="\n".join(messages),
                    error_type="PORT_STILL_IN_USE"
                )

            if not messages:
                messages.append("目前沒有 Flask 行程，也沒有 PID 占用 5000 port。")

            return StepResult(
                "stop_flask_internal",
                True,
                "；".join(messages)
            )

        except Exception as e:
            return StepResult("stop_flask_internal", False, f"停止 Flask 行程失敗：{e}", stderr=str(e), error_type="STOP_PROCESS_ERROR")

    def _restart_flask_internal(self, app_path: str) -> StepResult:
        stop_result = self._stop_flask_internal()
        if not stop_result.success:
            return StepResult(
                "restart_flask_internal",
                False,
                "重啟 Flask 時停止舊行程失敗。",
                stderr=(stop_result.message or "") + ("\n" + stop_result.stderr if stop_result.stderr else ""),
                error_type=stop_result.error_type
            )

        time.sleep(1.0)

        launch_result = self._start_flask_in_background(app_path)
        if not launch_result.success:
            error_text = (launch_result.stderr or "") + "\n" + (launch_result.stdout or "")
            missing_module = self._extract_missing_module(error_text)

            if missing_module:
                package_name = self._map_module_to_package(missing_module)
                install_result = self._install_package(package_name)
                if install_result.success:
                    second_launch = self._start_flask_in_background(app_path)
                    if second_launch.success:
                        return StepResult(
                            "restart_flask_internal",
                            True,
                            f"Flask 已重新啟動，啟動過程中自動安裝缺少套件：{package_name}"
                        )

            return StepResult("restart_flask_internal", False, "Flask 重啟失敗。", stderr=launch_result.stderr, error_type=launch_result.error_type)

        time.sleep(1.0)

        pids_after = self._get_listening_pids_on_port(self.flask_port)
        return StepResult(
            "restart_flask_internal",
            True,
            f"Flask 已重新啟動：http://{self.flask_host}:{self.flask_port}，目前 PID={pids_after if pids_after else 'unknown'}"
        )

    def _verify_http_route(self, route_name: str) -> StepResult:
        url = f"http://{self.flask_host}:{self.flask_port}/{route_name}"
        last_error = ""

        for _ in range(12):
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    status_code = getattr(response, "status", None) or response.getcode()
                    body = response.read().decode("utf-8", errors="ignore")

                    if status_code == 200:
                        return StepResult("verify_http_route", True, f"HTTP 驗證成功：GET {url} -> 200", stdout=body)

                    return StepResult("verify_http_route", False, f"HTTP 驗證失敗：GET {url} -> {status_code}", stdout=body, error_type="HTTP_STATUS_NOT_200")

            except urllib.error.HTTPError as e:
                try:
                    error_body = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    error_body = ""
                last_error = f"HTTPError {e.code}: {e.reason}"
                if e.code == 404:
                    time.sleep(0.8)
                    continue
                return StepResult("verify_http_route", False, f"HTTP 驗證失敗：GET {url} -> {e.code}", stderr=error_body or last_error, error_type="HTTP_ERROR")
            except Exception as e:
                last_error = str(e)
                time.sleep(0.8)

        return StepResult("verify_http_route", False, f"HTTP 驗證失敗：GET {url} 未取得 200", stderr=last_error, error_type="HTTP_VERIFY_FAILED")

    def _verify_http_route_removed(self, route_name: str) -> StepResult:
        url = f"http://{self.flask_host}:{self.flask_port}/{route_name}"
        last_result = ""

        for _ in range(12):
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    status_code = getattr(response, "status", None) or response.getcode()
                    body = response.read().decode("utf-8", errors="ignore")
                    last_result = f"收到 {status_code}"

                    if status_code == 404:
                        return StepResult("verify_http_route_removed", True, f"HTTP 驗證成功：/{route_name} 已不可用（404）", stdout=body)

                    time.sleep(0.8)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return StepResult("verify_http_route_removed", True, f"HTTP 驗證成功：/{route_name} 已不可用（404）")
                last_result = f"HTTPError {e.code}: {e.reason}"
                time.sleep(0.8)
            except Exception as e:
                last_result = str(e)
                time.sleep(0.8)

        return StepResult("verify_http_route_removed", False, f"HTTP 驗證失敗：/{route_name} 似乎仍可存取或狀態不正確", stderr=last_result, error_type="HTTP_REMOVE_VERIFY_FAILED")

    # =========================
    # Windows Port/PID Handling
    # =========================

    def _get_listening_pids_on_port(self, port: int) -> List[int]:
        if os.name != "nt":
            return []

        try:
            cmd = ["cmd", "/c", f"netstat -ano | findstr :{port}"]
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            text = (completed.stdout or "") + "\n" + (completed.stderr or "")

            pids: List[int] = []
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if "LISTENING" not in line.upper():
                    continue
                if f":{port}" not in line:
                    continue

                parts = line.split()
                if len(parts) < 5:
                    continue

                pid_text = parts[-1]
                if pid_text.isdigit():
                    pid = int(pid_text)
                    if pid > 0 and pid not in pids:
                        pids.append(pid)

            return pids
        except Exception:
            return []

    def _kill_pid(self, pid: int) -> bool:
        if pid <= 0:
            return False

        try:
            cmd = ["taskkill", "/PID", str(pid), "/F"]
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            return completed.returncode == 0
        except Exception:
            return False

    # =========================
    # Error Classification / Dependency Handling
    # =========================

    def _classify_error(self, error_text: str) -> str:
        text = (error_text or "").lower()

        if "no module named 'flask'" in text or 'no module named "flask"' in text:
            return "MODULE_NOT_FOUND_FLASK"
        if "no module named" in text:
            return "MODULE_NOT_FOUND"
        if "syntaxerror" in text:
            return "SYNTAX_ERROR"
        if "filenotfounderror" in text or "檔案不存在" in text:
            return "FILE_NOT_FOUND"
        if "permissionerror" in text:
            return "PERMISSION_ERROR"
        if "address already in use" in text or "only one usage of each socket address" in text:
            return "PORT_IN_USE"
        if "running on http://" in text or "serving flask app" in text:
            return "SERVER_RUNNING"
        if "timed out" in text:
            return "SERVER_RUNNING_TIMEOUT"

        return "UNKNOWN_ERROR"

    def _extract_missing_module(self, error_text: str) -> Optional[str]:
        if not error_text:
            return None

        patterns = [
            r"No module named '([^']+)'",
            r'No module named "([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, error_text)
            if match:
                return match.group(1).strip()

        return None

    def _map_module_to_package(self, module_name: str) -> str:
        mapping = {
            "cv2": "opencv-python",
            "PIL": "Pillow",
            "yaml": "PyYAML",
            "sklearn": "scikit-learn",
            "bs4": "beautifulsoup4",
        }
        return mapping.get(module_name, module_name)

    def _sanitize_package_name(self, package_name: str) -> Optional[str]:
        package_name = (package_name or "").strip()
        if re.fullmatch(r"[A-Za-z0-9._\-]+", package_name):
            return package_name
        return None

    def _sanitize_route_name(self, route_name: str) -> Optional[str]:
        route_name = (route_name or "").strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", route_name):
            return route_name
        return None

    # =========================
    # Helpers
    # =========================

    def _is_port_open(self, host: str, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def _read_text_if_exists(self, path: str) -> str:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            return ""
        except Exception:
            return ""

    def _list_python_files(self, root: str) -> List[str]:
        results = []
        ignore_dirs = {"__pycache__", ".git", ".venv", "venv", "env", "node_modules", "dist", "build"}

        for current_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for name in files:
                if name.lower().endswith(".py"):
                    full_path = os.path.join(current_root, name)
                    rel_path = os.path.relpath(full_path, root)
                    results.append(rel_path)

        results.sort()
        return results

    def _step(
        self,
        step_name: str,
        success: bool,
        message: str,
        command: Optional[str] = None,
        file_path: Optional[str] = None,
        stdout: str = "",
        stderr: str = "",
        error_type: Optional[str] = None
    ) -> Dict[str, Any]:
        return asdict(StepResult(
            step_name=step_name,
            success=success,
            message=message,
            command=command,
            file_path=file_path,
            stdout=stdout,
            stderr=stderr,
            error_type=error_type
        ))

    def _build_result(
        self,
        success: bool,
        user_command: str,
        plan_name: str,
        steps: List[Dict[str, Any]],
        summary: str
    ) -> AgentResult:
        return AgentResult(
            success=success,
            user_command=user_command,
            plan_name=plan_name,
            steps=steps,
            summary=summary
        )


if __name__ == "__main__":
    agent = ProjectAgent()
    result = agent.run("build flask api")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))