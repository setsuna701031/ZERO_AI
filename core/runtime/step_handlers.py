from __future__ import annotations

import copy
import os
import subprocess
from typing import Any, Dict, Optional


class BaseStepHandler:
    def __init__(self, executor: Any) -> None:
        self.executor = executor

    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class ToolStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        if self.executor.tool_registry is None:
            return {
                "ok": False,
                "error": "tool_registry missing",
                "result": {},
                "step": copy.deepcopy(step),
            }

        tool_name = step.get("tool_name")
        tool_input = copy.deepcopy(step.get("tool_input", {}) or {})

        if previous_result is not None:
            tool_input["previous_result"] = previous_result

        if task is not None:
            tool_input["task"] = copy.deepcopy(task)

        if context is not None:
            tool_input["context"] = copy.deepcopy(context)

        tool = self.executor.tool_registry.get_tool(tool_name)

        if not tool:
            return {
                "ok": False,
                "error": f"tool not found: {tool_name}",
                "result": {},
                "step": copy.deepcopy(step),
            }

        try:
            result = tool.execute(tool_input)
        except Exception as e:
            return {
                "ok": False,
                "error": f"tool execute failed: {e}",
                "result": {},
                "step": copy.deepcopy(step),
            }

        inner_ok = self.executor._extract_inner_ok(result)

        return {
            "ok": inner_ok,
            "error": None if inner_ok else "tool returned failure",
            "result": result,
            "step": copy.deepcopy(step),
        }


class CommandStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        command = str(step.get("command", "")).strip()
        if not command:
            return {
                "ok": False,
                "error": "command missing",
                "result": {},
                "step": copy.deepcopy(step),
            }

        cwd = self.executor._resolve_cwd(step=step, task=task, context=context)

        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
            )
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "result": {
                    "command": command,
                    "cwd": cwd,
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": None,
                },
                "step": copy.deepcopy(step),
            }

        ok = completed.returncode == 0

        return {
            "ok": ok,
            "error": None if ok else f"command failed (code {completed.returncode})",
            "result": {
                "command": command,
                "cwd": cwd,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "returncode": completed.returncode,
            },
            "step": copy.deepcopy(step),
        }


class WriteFileStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        path = step.get("path")
        content = step.get("content", "")

        if not path:
            return {
                "ok": False,
                "error": "path missing",
                "result": {},
                "step": copy.deepcopy(step),
            }

        base_dir = self.executor._resolve_base_dir_for_file(step=step, task=task)
        full_path = os.path.join(base_dir, path)
        parent = os.path.dirname(full_path)

        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "ok": True,
            "error": None,
            "result": {
                "path": full_path,
                "relative_path": path,
                "content": content,
            },
            "step": copy.deepcopy(step),
        }


class ReadFileStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        path = step.get("path")

        if not path:
            return {
                "ok": False,
                "error": "path missing",
                "result": {},
                "step": copy.deepcopy(step),
            }

        base_dir = self.executor._resolve_base_dir_for_file(step=step, task=task)
        full_path = os.path.join(base_dir, path)

        if not os.path.exists(full_path):
            return {
                "ok": False,
                "error": "file not found",
                "result": {
                    "path": full_path,
                    "relative_path": path,
                },
                "step": copy.deepcopy(step),
            }

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "ok": True,
            "error": None,
            "result": {
                "path": full_path,
                "relative_path": path,
                "content": content,
            },
            "step": copy.deepcopy(step),
        }


class RespondStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        message = step.get("message") or step.get("content", "")
        return {
            "ok": True,
            "error": None,
            "result": {"message": message},
            "step": copy.deepcopy(step),
        }


class LLMStepHandler(BaseStepHandler):
    """
    目前先做成可接入式 handler：
    - 如果 executor 上有 llm_client，且有 ask() / generate()，就呼叫
    - 沒有就回傳明確錯誤
    """

    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        llm_client = getattr(self.executor, "llm_client", None)
        if llm_client is None:
            return {
                "ok": False,
                "error": "llm_client missing",
                "result": {},
                "step": copy.deepcopy(step),
            }

        prompt = step.get("prompt") or step.get("input") or ""
        prompt = str(prompt).strip()
        if not prompt:
            return {
                "ok": False,
                "error": "llm prompt missing",
                "result": {},
                "step": copy.deepcopy(step),
            }

        try:
            if hasattr(llm_client, "ask") and callable(llm_client.ask):
                llm_result = llm_client.ask(prompt)
            elif hasattr(llm_client, "generate") and callable(llm_client.generate):
                llm_result = llm_client.generate(prompt)
            else:
                return {
                    "ok": False,
                    "error": "llm_client missing ask/generate method",
                    "result": {},
                    "step": copy.deepcopy(step),
                }
        except Exception as e:
            return {
                "ok": False,
                "error": f"llm call failed: {e}",
                "result": {},
                "step": copy.deepcopy(step),
            }

        text = self._extract_text(llm_result)

        save_to = str(step.get("save_to", "")).strip()
        saved_path = ""
        if save_to:
            base_dir = self.executor._resolve_base_dir_for_file(step=step, task=task)
            saved_path = os.path.join(base_dir, save_to)
            parent = os.path.dirname(saved_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(saved_path, "w", encoding="utf-8") as f:
                f.write(text)

        return {
            "ok": True,
            "error": None,
            "result": {
                "prompt": prompt,
                "text": text,
                "saved_path": saved_path,
                "raw": llm_result,
            },
            "step": copy.deepcopy(step),
        }

    def _extract_text(self, llm_result: Any) -> str:
        if isinstance(llm_result, str):
            return llm_result

        if isinstance(llm_result, dict):
            for key in ("text", "answer", "response", "content", "output"):
                value = llm_result.get(key)
                if isinstance(value, str):
                    return value

        return str(llm_result)