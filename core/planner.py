from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


class Planner:
    """
    ZERO Planner

    作用：
    1. 根據 goal 產生 steps
    2. 先支援 generic task 與 http server task
    3. step params 開始使用 context variables
    """

    def __init__(
        self,
        llm_client: Any = None,
        tool_registry: Any = None,
        workspace_root: Optional[str] = None,
        project_root: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.workspace_root = workspace_root
        self.project_root = project_root
        self.extra_config = kwargs

    # ------------------------------------------------------------------
    # public api
    # ------------------------------------------------------------------

    def create_plan(self, goal: str) -> Dict[str, Any]:
        cleaned_goal = (goal or "").strip()
        if not cleaned_goal:
            return self._build_empty_plan(goal="")

        lowered = cleaned_goal.lower()

        if self._looks_like_http_server_task(lowered):
            return self._build_http_server_plan(cleaned_goal)

        return self._build_generic_plan(cleaned_goal)

    def plan_task(self, goal: str) -> Dict[str, Any]:
        return self.create_plan(goal)

    def plan(self, goal: str) -> Dict[str, Any]:
        return self.create_plan(goal)

    # ------------------------------------------------------------------
    # plan builders
    # ------------------------------------------------------------------

    def _build_empty_plan(self, goal: str) -> Dict[str, Any]:
        now = self._now_str()
        return {
            "task_id": "",
            "goal": goal,
            "steps": [],
            "status": "planned",
            "created_at": now,
            "updated_at": now,
        }

    def _build_generic_plan(self, goal: str) -> Dict[str, Any]:
        now = self._now_str()

        steps: List[Dict[str, Any]] = [
            {
                "step_id": "step_1",
                "name": "Create project workspace",
                "title": "Create project workspace",
                "type": "workspace",
                "action": "create_dir",
                "params": {
                    "path": "",
                },
                "status": "pending",
            },
            {
                "step_id": "step_2",
                "name": "Write task summary file",
                "title": "Write task summary file",
                "type": "workspace",
                "action": "write_file",
                "params": {
                    "path": "result.txt",
                    "content": (
                        "ZERO generic planner executed.\n"
                        f"Original goal: {goal}\n"
                        "Task workspace: {{task_workspace}}\n"
                        "Task id: {{task_id}}\n"
                    ),
                },
                "status": "pending",
            },
            {
                "step_id": "step_3",
                "name": "Read task summary file",
                "title": "Read task summary file",
                "type": "workspace",
                "action": "read_file",
                "params": {
                    "path": "{{last_relative_path}}",
                },
                "status": "pending",
            },
        ]

        return {
            "task_id": "",
            "goal": goal,
            "steps": steps,
            "status": "planned",
            "created_at": now,
            "updated_at": now,
        }

    def _build_http_server_plan(self, goal: str) -> Dict[str, Any]:
        now = self._now_str()

        server_code = self._http_server_source()

        steps: List[Dict[str, Any]] = [
            {
                "step_id": "step_1",
                "name": "Create project workspace",
                "title": "Create project workspace",
                "type": "workspace",
                "action": "create_dir",
                "params": {
                    "path": "",
                },
                "status": "pending",
            },
            {
                "step_id": "step_2",
                "name": "Write HTTP server file",
                "title": "Write HTTP server file",
                "type": "workspace",
                "action": "write_file",
                "params": {
                    "path": "server.py",
                    "content": server_code,
                },
                "status": "pending",
            },
            {
                "step_id": "step_3",
                "name": "Read HTTP server file",
                "title": "Read HTTP server file",
                "type": "workspace",
                "action": "read_file",
                "params": {
                    "path": "{{last_relative_path}}",
                },
                "status": "pending",
            },
            {
                "step_id": "step_4",
                "name": "Start server",
                "title": "Start server",
                "type": "process",
                "action": "run_server",
                "params": {
                    "server_file": "{{last_relative_path}}",
                    "host": "127.0.0.1",
                    "port": 8000,
                },
                "status": "pending",
            },
            {
                "step_id": "step_5",
                "name": "Test HTTP endpoint",
                "title": "Test HTTP endpoint",
                "type": "process",
                "action": "test_http",
                "params": {
                    "url": "{{server_url}}",
                },
                "status": "pending",
            },
            {
                "step_id": "step_6",
                "name": "Write task summary file",
                "title": "Write task summary file",
                "type": "workspace",
                "action": "write_file",
                "params": {
                    "path": "result.txt",
                    "content": (
                        "ZERO http server planner executed.\n"
                        f"Original goal: {goal}\n"
                        "Server file: {{last_server_file}}\n"
                        "Server URL: {{server_url}}\n"
                        "Task workspace: {{task_workspace}}\n"
                    ),
                },
                "status": "pending",
            },
            {
                "step_id": "step_7",
                "name": "Read task summary file",
                "title": "Read task summary file",
                "type": "workspace",
                "action": "read_file",
                "params": {
                    "path": "{{last_relative_path}}",
                },
                "status": "pending",
            },
            {
                "step_id": "step_8",
                "name": "Stop server",
                "title": "Stop server",
                "type": "process",
                "action": "stop_server",
                "params": {},
                "status": "pending",
            },
        ]

        return {
            "task_id": "",
            "goal": goal,
            "steps": steps,
            "status": "planned",
            "created_at": now,
            "updated_at": now,
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _looks_like_http_server_task(self, lowered_goal: str) -> bool:
        keywords = [
            "http server",
            "web server",
            "server",
            "api server",
            "http",
        ]
        return any(keyword in lowered_goal for keyword in keywords)

    def _now_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _http_server_source(self) -> str:
        return (
            'from http.server import BaseHTTPRequestHandler, HTTPServer\n'
            '\n'
            'HOST = "127.0.0.1"\n'
            'PORT = 8000\n'
            '\n'
            '\n'
            'class SimpleHandler(BaseHTTPRequestHandler):\n'
            '    def do_GET(self):\n'
            '        self.send_response(200)\n'
            '        self.send_header("Content-type", "text/plain; charset=utf-8")\n'
            '        self.end_headers()\n'
            '        self.wfile.write("ZERO local web server is running.".encode("utf-8"))\n'
            '\n'
            '    def log_message(self, format, *args):\n'
            '        return\n'
            '\n'
            '\n'
            'def main() -> None:\n'
            '    server = HTTPServer((HOST, PORT), SimpleHandler)\n'
            '    print(f"Server running at http://{HOST}:{PORT}", flush=True)\n'
            '    try:\n'
            '        server.serve_forever()\n'
            '    except KeyboardInterrupt:\n'
            '        pass\n'
            '    finally:\n'
            '        server.server_close()\n'
            '\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    main()\n'
        )