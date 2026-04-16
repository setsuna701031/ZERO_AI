from __future__ import annotations

import copy
import os
import subprocess
import sys
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

    def _success(
        self,
        *,
        result: Optional[Dict[str, Any]] = None,
        step: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "ok": True,
            "error": None,
            "result": result or {},
            "step": copy.deepcopy(step or {}),
        }
        if extra:
            payload.update(extra)
        return payload

    def _error(
        self,
        *,
        error_type: str,
        message: str,
        step: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "ok": False,
            "error": {
                "type": error_type,
                "message": message,
                "retryable": retryable,
                "details": details or {},
            },
            "result": result or {},
            "step": copy.deepcopy(step or {}),
        }
        if extra:
            payload.update(extra)
        return payload


class ToolStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        if self.executor.tool_registry is None:
            return self._error(
                error_type="tool_registry_missing",
                message="tool_registry missing",
                step=step,
            )

        tool_name = str(step.get("tool_name", "")).strip()
        if not tool_name:
            return self._error(
                error_type="tool_name_missing",
                message="tool_name missing",
                step=step,
            )

        tool_input = copy.deepcopy(step.get("tool_input", {}) or {})

        if previous_result is not None:
            tool_input["previous_result"] = previous_result
        if task is not None:
            tool_input["task"] = copy.deepcopy(task)
        if context is not None:
            tool_input["context"] = copy.deepcopy(context)

        try:
            result = self.executor.tool_registry.execute_tool(tool_name, tool_input)
        except Exception as e:
            return self._error(
                error_type="tool_execute_exception",
                message=f"tool execute failed: {e}",
                step=step,
                details={"tool_name": tool_name},
            )

        inner_ok = self.executor._extract_inner_ok(result)
        if inner_ok:
            return self._success(
                result=result,
                step=step,
                extra={"tool_name": tool_name},
            )

        return self._error(
            error_type="tool_step_failed",
            message="tool returned failure",
            step=step,
            result=result,
            details={"tool_name": tool_name},
            extra={"tool_name": tool_name},
        )


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
            return self._error(
                error_type="command_missing",
                message="command missing",
                step=step,
            )

        cwd = self.executor._resolve_cwd(step=step, task=task, context=context)
        command = self._auto_python(command, cwd)

        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
            )
        except Exception as e:
            return self._error(
                error_type="command_execute_exception",
                message=str(e),
                step=step,
                result={
                    "command": command,
                    "cwd": cwd,
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": None,
                },
            )

        ok = completed.returncode == 0
        result = {
            "command": command,
            "cwd": cwd,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
        }

        if ok:
            return self._success(result=result, step=step)

        return self._error(
            error_type="command_failed",
            message=f"command failed (code {completed.returncode})",
            step=step,
            result=result,
        )

    def _auto_python(self, command: str, cwd: str) -> str:
        parts = command.split()
        if not parts:
            return command

        first = parts[0].strip()
        first_lower = first.lower()

        if first_lower in ["python", "python3", "py"]:
            return command

        if first_lower.endswith(".py"):
            script_path = self._resolve_python_script_path(first, cwd)
            python_cmd = sys.executable
            rest = parts[1:]
            quoted_script = f'"{script_path}"'
            if rest:
                return f'"{python_cmd}" {quoted_script} {" ".join(rest)}'
            return f'"{python_cmd}" {quoted_script}'

        return command

    def _resolve_python_script_path(self, script: str, cwd: str) -> str:
        script = script.strip().strip('"').strip("'")

        if os.path.isabs(script):
            return script

        candidate_in_cwd = os.path.abspath(os.path.join(cwd, script))
        if os.path.exists(candidate_in_cwd):
            return candidate_in_cwd

        candidate_in_project_root = os.path.abspath(os.path.join(os.getcwd(), script))
        if os.path.exists(candidate_in_project_root):
            return candidate_in_project_root

        return script


class RunPythonStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        path = str(step.get("path", "")).strip()
        if not path:
            return self._error(
                error_type="python_path_missing",
                message="python path missing",
                step=step,
            )

        cwd = self.executor._resolve_cwd(step=step, task=task, context=context)
        script_path = self._resolve_python_script_path(path=path, step=step, task=task, context=context, cwd=cwd)

        if not os.path.exists(script_path):
            return self._error(
                error_type="python_file_not_found",
                message=f"python file not found: {script_path}",
                step=step,
                result={
                    "path": path,
                    "resolved_path": script_path,
                    "cwd": cwd,
                },
            )

        command = [sys.executable, script_path]

        extra_args = step.get("args", [])
        if isinstance(extra_args, list):
            command.extend(str(x) for x in extra_args if x is not None)

        try:
            completed = subprocess.run(
                command,
                cwd=os.path.dirname(script_path) or cwd,
                capture_output=True,
                text=True,
            )
        except Exception as e:
            return self._error(
                error_type="run_python_exception",
                message=f"run python failed: {e}",
                step=step,
                result={
                    "path": path,
                    "resolved_path": script_path,
                    "cwd": cwd,
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": None,
                },
            )

        ok = completed.returncode == 0
        result = {
            "type": "run_python",
            "path": path,
            "resolved_path": script_path,
            "cwd": cwd,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
        }

        if ok:
            return self._success(
                result=result,
                step=step,
                extra={
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
            )

        return self._error(
            error_type="python_failed",
            message=f"python failed (code {completed.returncode})",
            step=step,
            result=result,
            extra={
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )

    def _resolve_python_script_path(
        self,
        path: str,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        cwd: str,
    ) -> str:
        clean = str(path).strip().strip('"').strip("'")
        if not clean:
            return clean

        if os.path.isabs(clean):
            return clean

        ordered_candidates = []

        def add_candidate(candidate: str) -> None:
            candidate = str(candidate or "").strip()
            if not candidate:
                return
            normalized = os.path.abspath(candidate)
            if normalized not in ordered_candidates:
                ordered_candidates.append(normalized)

        add_candidate(os.path.join(cwd, clean))

        if isinstance(step, dict):
            for key in ("task_dir", "workspace", "sandbox_dir", "cwd"):
                base = str(step.get(key, "")).strip()
                if base:
                    add_candidate(os.path.join(base, clean))

        if isinstance(task, dict):
            for key in ("task_dir", "workspace", "sandbox_dir", "cwd", "workspace_dir"):
                base = str(task.get(key, "")).strip()
                if base:
                    add_candidate(os.path.join(base, clean))

        if isinstance(context, dict):
            for key in ("task_dir", "workspace", "sandbox_dir", "cwd"):
                base = str(context.get(key, "")).strip()
                if base:
                    add_candidate(os.path.join(base, clean))

        add_candidate(os.path.join(os.getcwd(), clean))

        for candidate in ordered_candidates:
            if os.path.exists(candidate):
                return candidate

        try:
            resolved_read = self.executor.resolve_read_path(
                relative_path=clean,
                task=task,
                prefer_scopes=("sandbox", "shared"),
                return_fallback_candidate_if_missing=True,
            )
            if resolved_read and os.path.exists(resolved_read):
                return resolved_read
        except Exception:
            pass

        return ordered_candidates[0] if ordered_candidates else os.path.abspath(os.path.join(cwd, clean))


class WriteFileStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        path = step.get("path")
        content = step.get("content", None)
        scope = str(step.get("scope", "sandbox")).strip().lower() or "sandbox"

        if not path:
            return self._error(
                error_type="path_missing",
                message="path missing",
                step=step,
            )

        if content is None or bool(step.get("use_previous_text", False)):
            extracted = self._extract_text_from_previous(previous_result)
            if extracted is not None:
                content = extracted

        if content is None:
            content = ""

        try:
            full_path = self.executor.resolve_write_path(
                relative_path=str(path),
                task=task,
                default_scope=scope,
            )
        except Exception as e:
            return self._error(
                error_type="path_resolve_failed",
                message=f"path resolve failed: {e}",
                step=step,
                result={
                    "path": str(path),
                    "scope": scope,
                },
            )

        try:
            parent = os.path.dirname(full_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(str(content))
        except Exception as e:
            return self._error(
                error_type="write_file_failed",
                message=f"write file failed: {e}",
                step=step,
                result={
                    "path": full_path,
                    "scope": scope,
                },
            )

        result = {
            "type": "write_file",
            "path": str(path),
            "full_path": full_path,
            "scope": scope,
            "bytes": len(str(content).encode("utf-8")),
            "content": str(content),
        }
        return self._success(
            result=result,
            step=step,
            extra={"content": str(content)},
        )

    def _extract_text_from_previous(self, previous_result: Any) -> Optional[str]:
        if previous_result is None:
            return None

        if isinstance(previous_result, str):
            return previous_result

        if not isinstance(previous_result, dict):
            return None

        for key in ("text", "content", "message", "final_answer"):
            value = previous_result.get(key)
            if isinstance(value, str):
                return value

        result_block = previous_result.get("result")
        if isinstance(result_block, dict):
            for key in ("text", "content", "message"):
                value = result_block.get(key)
                if isinstance(value, str):
                    return value

        return None


class EnsureFileStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        path = step.get("path")
        scope = str(step.get("scope", "sandbox")).strip().lower() or "sandbox"

        if not path:
            return self._error(
                error_type="path_missing",
                message="path missing",
                step=step,
            )

        try:
            full_path = self.executor.resolve_write_path(
                relative_path=str(path),
                task=task,
                default_scope=scope,
            )
        except Exception as e:
            return self._error(
                error_type="path_resolve_failed",
                message=f"path resolve failed: {e}",
                step=step,
                result={
                    "path": str(path),
                    "scope": scope,
                },
            )

        try:
            parent = os.path.dirname(full_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            created = False
            if not os.path.exists(full_path):
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write("")
                created = True
        except Exception as e:
            return self._error(
                error_type="ensure_file_failed",
                message=f"ensure file failed: {e}",
                step=step,
                result={
                    "path": full_path,
                    "scope": scope,
                },
            )

        return self._success(
            result={
                "type": "ensure_file",
                "path": str(path),
                "full_path": full_path,
                "scope": scope,
                "created": created,
                "preserved_existing": not created,
            },
            step=step,
            extra={
                "path": full_path,
                "created": created,
            },
        )


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
            return self._error(
                error_type="path_missing",
                message="path missing",
                step=step,
            )

        try:
            candidates = self.executor.resolve_read_candidates(
                relative_path=str(path),
                task=task,
                prefer_scopes=("sandbox", "shared"),
            )
            full_path = self.executor.resolve_read_path(
                relative_path=str(path),
                task=task,
                prefer_scopes=("sandbox", "shared"),
                return_fallback_candidate_if_missing=True,
            )
        except Exception as e:
            return self._error(
                error_type="path_resolve_failed",
                message=f"path resolve failed: {e}",
                step=step,
            )

        if not os.path.exists(full_path):
            return self._error(
                error_type="file_not_found",
                message=f"file not found: {full_path}",
                step=step,
                result={
                    "path": full_path,
                    "candidates": candidates,
                },
            )

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return self._error(
                error_type="read_file_failed",
                message=f"read file failed: {e}",
                step=step,
                result={
                    "path": full_path,
                    "candidates": candidates,
                },
            )

        return self._success(
            result={
                "type": "read_file",
                "path": str(path),
                "full_path": full_path,
                "content": content,
                "candidates": candidates,
            },
            step=step,
            extra={
                "content": content,
                "path": full_path,
            },
        )


class VerifyStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        path = str(step.get("path", "")).strip()

        # 相容你現在的 minimal test：如果沒有 path，但有 contains/equals，
        # 就直接對 previous_result 做文字驗證
        if not path and ("contains" in step or "equals" in step):
            previous_text = self._extract_previous_text(previous_result)

            if "contains" in step:
                expected = str(step.get("contains", ""))
                actual = expected in previous_text
                if actual:
                    return self._success(
                        result={
                            "type": "verify",
                            "mode": "contains",
                            "expected": expected,
                            "actual": actual,
                            "content": previous_text,
                        },
                        step=step,
                        extra={"content": previous_text},
                    )
                return self._error(
                    error_type="verify_contains_failed",
                    message=f'verify contains failed: "{expected}" not found',
                    step=step,
                    result={
                        "type": "verify",
                        "mode": "contains",
                        "expected": expected,
                        "actual": actual,
                        "content": previous_text,
                    },
                    extra={"content": previous_text},
                )

            if "equals" in step:
                expected = str(step.get("equals", ""))
                actual_text = previous_text.strip()
                ok = actual_text == expected
                if ok:
                    return self._success(
                        result={
                            "type": "verify",
                            "mode": "equals",
                            "expected": expected,
                            "actual": actual_text,
                            "content": previous_text,
                        },
                        step=step,
                        extra={"content": previous_text},
                    )
                return self._error(
                    error_type="verify_equals_failed",
                    message=f'verify equals failed: expected "{expected}", got "{actual_text}"',
                    step=step,
                    result={
                        "type": "verify",
                        "mode": "equals",
                        "expected": expected,
                        "actual": actual_text,
                        "content": previous_text,
                    },
                    extra={"content": previous_text},
                )

        if not path:
            return self._error(
                error_type="verify_path_missing",
                message="verify path missing",
                step=step,
            )

        try:
            candidates = self.executor.resolve_read_candidates(
                relative_path=path,
                task=task,
                prefer_scopes=("sandbox", "shared"),
            )
            full_path = self.executor.resolve_read_path(
                relative_path=path,
                task=task,
                prefer_scopes=("sandbox", "shared"),
                return_fallback_candidate_if_missing=True,
            )
        except Exception as e:
            return self._error(
                error_type="verify_path_resolve_failed",
                message=f"verify path resolve failed: {e}",
                step=step,
                result={"path": path},
            )

        if "exists" in step:
            expected_exists = bool(step.get("exists"))
            actual_exists = os.path.exists(full_path)
            ok = actual_exists == expected_exists

            result = {
                "type": "verify",
                "mode": "exists",
                "path": path,
                "full_path": full_path,
                "candidates": candidates,
                "expected": expected_exists,
                "actual": actual_exists,
            }
            if ok:
                return self._success(result=result, step=step)
            return self._error(
                error_type="verify_exists_failed",
                message=f"verify exists failed: expected {expected_exists}, got {actual_exists}",
                step=step,
                result=result,
            )

        if not os.path.exists(full_path):
            return self._error(
                error_type="verify_target_not_found",
                message=f"verify target not found: {full_path}",
                step=step,
                result={
                    "type": "verify",
                    "path": path,
                    "full_path": full_path,
                    "candidates": candidates,
                },
            )

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return self._error(
                error_type="verify_read_failed",
                message=f"verify read failed: {e}",
                step=step,
                result={
                    "type": "verify",
                    "path": path,
                    "full_path": full_path,
                    "candidates": candidates,
                },
            )

        if "contains" in step:
            expected = str(step.get("contains", ""))
            actual = expected in content
            result = {
                "type": "verify",
                "mode": "contains",
                "path": path,
                "full_path": full_path,
                "candidates": candidates,
                "expected": expected,
                "actual": actual,
                "content": content,
            }
            if actual:
                return self._success(result=result, step=step, extra={"content": content})
            return self._error(
                error_type="verify_contains_failed",
                message=f'verify contains failed: "{expected}" not found',
                step=step,
                result=result,
                extra={"content": content},
            )

        if "equals" in step:
            expected = str(step.get("equals", ""))
            actual = content.strip()
            ok = actual == expected
            result = {
                "type": "verify",
                "mode": "equals",
                "path": path,
                "full_path": full_path,
                "candidates": candidates,
                "expected": expected,
                "actual": actual,
                "content": content,
            }
            if ok:
                return self._success(result=result, step=step, extra={"content": content})
            return self._error(
                error_type="verify_equals_failed",
                message=f'verify equals failed: expected "{expected}", got "{actual}"',
                step=step,
                result=result,
                extra={"content": content},
            )

        return self._error(
            error_type="verify_mode_missing",
            message="verify step missing mode",
            step=step,
            result={
                "type": "verify",
                "path": path,
                "full_path": full_path,
                "candidates": candidates,
            },
        )

    def _extract_previous_text(self, previous_result: Any) -> str:
        if previous_result is None:
            return ""

        if isinstance(previous_result, str):
            return previous_result

        if not isinstance(previous_result, dict):
            return ""

        for key in ("content", "text", "message", "final_answer"):
            value = previous_result.get(key)
            if isinstance(value, str):
                return value

        result_block = previous_result.get("result")
        if isinstance(result_block, dict):
            for key in ("content", "text", "message"):
                value = result_block.get(key)
                if isinstance(value, str):
                    return value

        return ""


class RespondStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        message = step.get("message") or step.get("content", "")
        return self._success(
            result={"message": message},
            step=step,
            extra={"message": str(message)},
        )


class LLMStepHandler(BaseStepHandler):
    def handle(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        llm_client = getattr(self.executor, "llm_client", None)
        if llm_client is None:
            return self._error(
                error_type="llm_client_missing",
                message="llm_client missing",
                step=step,
            )

        prompt = self._build_prompt(step=step, previous_result=previous_result)
        prompt = str(prompt).strip()

        if not prompt:
            return self._error(
                error_type="llm_prompt_missing",
                message="llm prompt missing",
                step=step,
            )

        try:
            if hasattr(llm_client, "ask") and callable(llm_client.ask):
                llm_result = llm_client.ask(prompt)
            elif hasattr(llm_client, "generate") and callable(llm_client.generate):
                llm_result = llm_client.generate(prompt)
            else:
                return self._error(
                    error_type="llm_client_method_missing",
                    message="llm_client missing ask/generate method",
                    step=step,
                )
        except Exception as e:
            return self._error(
                error_type="llm_call_failed",
                message=f"llm call failed: {e}",
                step=step,
            )

        text = self._normalize_llm_result(llm_result)
        return self._success(
            result={
                "prompt": prompt,
                "text": text,
                "raw": llm_result,
            },
            step=step,
            extra={"text": text},
        )

    def _build_prompt(self, step: Dict[str, Any], previous_result: Any) -> str:
        prompt_template = step.get("prompt_template")
        if isinstance(prompt_template, str) and prompt_template.strip():
            file_content = self._extract_previous_content(previous_result)
            return prompt_template.replace("{{file_content}}", file_content)

        prompt = step.get("prompt") or step.get("input") or ""
        return str(prompt)

    def _extract_previous_content(self, previous_result: Any) -> str:
        if previous_result is None:
            return ""

        if isinstance(previous_result, str):
            return previous_result

        if not isinstance(previous_result, dict):
            return ""

        for key in ("content", "text", "message", "final_answer"):
            value = previous_result.get(key)
            if isinstance(value, str):
                return value

        result_block = previous_result.get("result")
        if isinstance(result_block, dict):
            for key in ("content", "text", "message"):
                value = result_block.get(key)
                if isinstance(value, str):
                    return value

        return ""

    def _normalize_llm_result(self, llm_result: Any) -> str:
        if isinstance(llm_result, str):
            return llm_result

        if isinstance(llm_result, dict):
            for key in ("text", "content", "message", "answer", "response"):
                value = llm_result.get(key)
                if isinstance(value, str):
                    return value

        return str(llm_result)