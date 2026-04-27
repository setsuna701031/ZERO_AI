from __future__ import annotations

import copy
import json
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


    def _normalize_external_result(
        self,
        result: Any,
        *,
        step: Optional[Dict[str, Any]] = None,
        source: str = "external",
    ) -> Dict[str, Any]:
        """
        Normalize tool/command-like external results into a predictable envelope.

        This does not execute retries and does not call planners.
        It only makes malformed or ambiguous tool output easier for upper layers to observe.
        """
        if isinstance(result, dict):
            normalized = copy.deepcopy(result)
        elif isinstance(result, str):
            parsed = self._try_parse_json_object(result)
            if isinstance(parsed, dict):
                normalized = parsed
                normalized.setdefault("_normalized_from", "json_string")
            else:
                normalized = {
                    "ok": bool(result.strip()),
                    "stdout": result,
                    "stderr": "",
                    "returncode": 0 if result.strip() else None,
                    "_normalized_from": "string",
                }
        elif result is None:
            normalized = {
                "ok": False,
                "stdout": "",
                "stderr": "",
                "returncode": None,
                "_normalized_from": "none",
            }
        else:
            normalized = {
                "ok": False,
                "raw_result": copy.deepcopy(result),
                "stdout": "",
                "stderr": "",
                "returncode": None,
                "_normalized_from": type(result).__name__,
            }

        stdout = self._coerce_text(
            normalized.get("stdout")
            or normalized.get("output_text")
            or normalized.get("output")
            or normalized.get("text")
            or ""
        )
        stderr = self._coerce_text(
            normalized.get("stderr")
            or normalized.get("error_output")
            or normalized.get("err")
            or ""
        )

        returncode = self._safe_int_or_none(
            normalized.get("returncode", normalized.get("return_code", normalized.get("exit_code")))
        )

        if "ok" in normalized:
            ok = self._coerce_bool(normalized.get("ok"), default=True)
        elif returncode is not None:
            ok = returncode == 0
        elif stderr.strip() and not stdout.strip():
            ok = False
        else:
            ok = True

        error_payload = normalized.get("error")
        error_message = ""
        error_type = self._coerce_text(normalized.get("error_type") or "")

        if isinstance(error_payload, dict):
            error_message = self._coerce_text(error_payload.get("message") or "")
            if not error_type:
                error_type = self._coerce_text(error_payload.get("type") or "")
        elif error_payload is not None:
            error_message = self._coerce_text(error_payload)

        if not error_type:
            if returncode is not None and returncode != 0:
                error_type = "external_returncode_failed"
            elif stderr.strip() and not stdout.strip():
                error_type = "external_stderr"

        normalized["ok"] = ok
        normalized["stdout"] = stdout
        normalized["stderr"] = stderr
        normalized["returncode"] = returncode
        normalized["stdout_present"] = bool(stdout.strip())
        normalized["stderr_present"] = bool(stderr.strip())
        normalized["empty_output"] = (
            not bool(stdout.strip())
            and not bool(stderr.strip())
            and not bool(normalized.get("result"))
        )
        normalized["source"] = source

        if error_type:
            normalized["error_type"] = error_type

        if error_message:
            normalized["error_message"] = error_message

        normalized["empty_output_retry_candidate"] = bool(
            normalized["empty_output"] and normalized.get("ok") is True
        )

        if stderr.strip() and not ok and not isinstance(normalized.get("error"), dict):
            normalized["error"] = {
                "type": error_type or "external_stderr",
                "message": error_message or stderr.strip(),
                "retryable": bool(normalized.get("empty_output_retry_candidate", False)),
                "details": {
                    "source": source,
                    "returncode": returncode,
                    "stderr": stderr,
                },
            }

        if isinstance(step, dict):
            normalized.setdefault("step_type", step.get("type"))
            normalized.setdefault("step_id", step.get("id"))

        return normalized

    def _try_parse_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None

        candidates = [raw]
        first = raw.find("{")
        last = raw.rfind("}")
        if first >= 0 and last > first:
            candidates.append(raw[first : last + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed

        return None

    def _coerce_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return str(value)
        except Exception:
            return ""

    def _coerce_bool(self, value: Any, *, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        text = self._coerce_text(value).strip().lower()
        if text in {"1", "true", "yes", "y", "ok", "pass", "passed", "success"}:
            return True
        if text in {"0", "false", "no", "n", "fail", "failed", "error"}:
            return False
        return default

    def _safe_int_or_none(self, value: Any) -> Optional[int]:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            try:
                return int(value)
            except Exception:
                return None
        text = self._coerce_text(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except Exception:
            return None


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

        normalized_result = self._normalize_external_result(
            result,
            step=step,
            source=f"tool:{tool_name}",
        )

        inner_ok = self.executor._extract_inner_ok(normalized_result)
        if inner_ok and not normalized_result.get("empty_output_retry_candidate"):
            return self._success(
                result=normalized_result,
                step=step,
                extra={
                    "tool_name": tool_name,
                    "normalized_tool_result": True,
                },
            )

        if inner_ok and normalized_result.get("empty_output_retry_candidate"):
            return self._error(
                error_type="tool_empty_output",
                message="tool returned empty output",
                step=step,
                result=normalized_result,
                retryable=True,
                details={
                    "tool_name": tool_name,
                    "empty_output_retry_candidate": True,
                },
                extra={
                    "tool_name": tool_name,
                    "normalized_tool_result": True,
                },
            )

        error_type = str(normalized_result.get("error_type") or "tool_step_failed")
        message = str(
            normalized_result.get("error_message")
            or normalized_result.get("stderr")
            or "tool returned failure"
        )

        return self._error(
            error_type=error_type,
            message=message,
            step=step,
            result=normalized_result,
            details={
                "tool_name": tool_name,
                "returncode": normalized_result.get("returncode"),
                "stderr_present": normalized_result.get("stderr_present"),
                "stdout_present": normalized_result.get("stdout_present"),
            },
            extra={
                "tool_name": tool_name,
                "normalized_tool_result": True,
            },
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
        return self._extract_text_deep(previous_result)

    def _extract_text_deep(self, payload: Any, depth: int = 0) -> Optional[str]:
        if depth > 10:
            return None

        if payload is None:
            return None

        if isinstance(payload, str):
            return payload

        if isinstance(payload, dict):
            for key in ("text", "content", "message", "final_answer", "response", "stdout"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value

            for nested_key in ("result", "raw", "data", "payload", "output", "previous_result"):
                nested = payload.get(nested_key)
                text = self._extract_text_deep(nested, depth + 1)
                if isinstance(text, str):
                    return text

        if isinstance(payload, list):
            for item in reversed(payload):
                text = self._extract_text_deep(item, depth + 1)
                if isinstance(text, str):
                    return text

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

        prompt = self._build_prompt(step=step, previous_result=previous_result, context=context)
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

    def _build_prompt(self, step: Dict[str, Any], previous_result: Any, context: Optional[Dict[str, Any]] = None) -> str:
        prompt_template = step.get("prompt_template")
        if isinstance(prompt_template, str) and prompt_template.strip():
            file_content = self._extract_previous_content(previous_result, context=context)
            return prompt_template.replace("{{file_content}}", file_content)

        prompt = step.get("prompt") or step.get("input") or ""
        return str(prompt)

    def _extract_previous_content(self, previous_result: Any, context: Optional[Dict[str, Any]] = None) -> str:
        if isinstance(context, dict):
            file_content = context.get("file_content")
            if isinstance(file_content, str):
                return file_content

        text = self._extract_text_deep(previous_result)
        return text or ""

    def _extract_text_deep(self, payload: Any, depth: int = 0) -> Optional[str]:
        if depth > 10:
            return None

        if payload is None:
            return None

        if isinstance(payload, str):
            return payload

        if isinstance(payload, dict):
            for key in ("content", "text", "message", "final_answer", "response", "stdout"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value

            for nested_key in ("result", "raw", "data", "payload", "output", "previous_result"):
                nested = payload.get(nested_key)
                text = self._extract_text_deep(nested, depth + 1)
                if isinstance(text, str):
                    return text

        if isinstance(payload, list):
            for item in reversed(payload):
                text = self._extract_text_deep(item, depth + 1)
                if isinstance(text, str):
                    return text

        return None

    def _normalize_llm_result(self, llm_result: Any) -> str:
        if isinstance(llm_result, str):
            return llm_result

        if isinstance(llm_result, dict):
            for key in ("text", "content", "message", "answer", "response"):
                value = llm_result.get(key)
                if isinstance(value, str):
                    return value

        return str(llm_result)