from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class DummyStepExecutor:
    """
    測試用 Step Executor

    支援三種路徑：
    1. demo_ok
       - 直接成功
    2. demo_fail_first
       - 第一次失敗，第二次成功
    3. demo_always_fail
       - 每次都失敗

    其他 path 預設當作一般 workspace 動作處理。
    """

    def __init__(self) -> None:
        self._attempts: Dict[str, int] = {}

    def execute(self, step: Dict[str, Any], workspace: str) -> Dict[str, Any]:
        tool = step.get("tool")
        action_input = step.get("input", {}) or {}
        title = step.get("title", "")
        step_id = step.get("id", "")
        index = step.get("index", 0)

        if tool != "workspace":
            return {
                "ok": False,
                "tool": tool,
                "input": action_input,
                "message": f"unsupported tool: {tool}",
                "step_id": step_id,
                "title": title,
                "index": index,
            }

        action = action_input.get("action")
        path_value = action_input.get("path", "")

        print(f"[DummyStepExecutor] tool = {tool} | path = {path_value}")

        attempt_key = f"{workspace}:{step_id}:{path_value}"
        attempt_count = self._attempts.get(attempt_key, 0) + 1
        self._attempts[attempt_key] = attempt_count

        if path_value == "demo_fail_first":
            if attempt_count == 1:
                print("[DummyStepExecutor] forced failure on first attempt")
                return {
                    "ok": False,
                    "tool": tool,
                    "input": action_input,
                    "message": "forced failure on first attempt",
                    "step_id": step_id,
                    "title": title,
                    "index": index,
                }

            print("[DummyStepExecutor] retry success")
            return self._run_workspace_action(
                action=action,
                path_value=path_value,
                workspace=workspace,
                tool=tool,
                action_input=action_input,
                step_id=step_id,
                title=title,
                index=index,
                success_message="retry success",
            )

        if path_value == "demo_always_fail":
            print("[DummyStepExecutor] forced permanent failure")
            return {
                "ok": False,
                "tool": tool,
                "input": action_input,
                "message": "forced permanent failure",
                "step_id": step_id,
                "title": title,
                "index": index,
            }

        return self._run_workspace_action(
            action=action,
            path_value=path_value,
            workspace=workspace,
            tool=tool,
            action_input=action_input,
            step_id=step_id,
            title=title,
            index=index,
            success_message="step completed",
        )

    def _run_workspace_action(
        self,
        action: str,
        path_value: str,
        workspace: str,
        tool: str,
        action_input: Dict[str, Any],
        step_id: str,
        title: str,
        index: int,
        success_message: str,
    ) -> Dict[str, Any]:
        base_dir = Path(workspace)
        target = base_dir / path_value if path_value else base_dir

        try:
            if action == "mkdir":
                target.mkdir(parents=True, exist_ok=True)

            elif action == "write_text":
                content = action_input.get("content", "")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            elif action == "append_text":
                content = action_input.get("content", "")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("a", encoding="utf-8") as f:
                    f.write(content)

            elif action == "read_text":
                if not target.exists():
                    return {
                        "ok": False,
                        "tool": tool,
                        "input": action_input,
                        "message": f"file not found: {target}",
                        "step_id": step_id,
                        "title": title,
                        "index": index,
                    }
                content = target.read_text(encoding="utf-8")
                return {
                    "ok": True,
                    "tool": tool,
                    "input": action_input,
                    "message": success_message,
                    "content": content,
                    "step_id": step_id,
                    "title": title,
                    "index": index,
                }

            elif action == "exists":
                return {
                    "ok": True,
                    "tool": tool,
                    "input": action_input,
                    "message": success_message,
                    "exists": target.exists(),
                    "step_id": step_id,
                    "title": title,
                    "index": index,
                }

            else:
                return {
                    "ok": False,
                    "tool": tool,
                    "input": action_input,
                    "message": f"unsupported workspace action: {action}",
                    "step_id": step_id,
                    "title": title,
                    "index": index,
                }

            return {
                "ok": True,
                "tool": tool,
                "input": action_input,
                "message": success_message,
                "step_id": step_id,
                "title": title,
                "index": index,
            }

        except Exception as e:
            return {
                "ok": False,
                "tool": tool,
                "input": action_input,
                "message": f"{type(e).__name__}: {e}",
                "step_id": step_id,
                "title": title,
                "index": index,
            }