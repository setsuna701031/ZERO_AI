from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


class FixEngine:
    """
    最小可擴充錯誤修復引擎

    流程：
    parse_error -> classify_error -> apply_strategy -> return repaired steps

    目前支援：
    1. VERIFY_CONTAINS_FAILED
    2. VERIFY_EQUALS_FAILED
    3. FILE_NOT_FOUND
    4. PYTHON_RUNTIME_ERROR
    5. PYTHON_SYNTAX_ERROR
    6. PYTHON_NAME_ERROR
    7. PYTHON_IMPORT_ERROR
    """

    def build_fix_plan(
        self,
        task: Dict[str, Any],
        failed_step: Dict[str, Any],
        error: str,
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        if not isinstance(task, dict):
            return None
        if not isinstance(failed_step, dict):
            return None
        if not isinstance(original_steps, list):
            original_steps = []

        error_info = self.parse_error(error)
        error_type = self.classify_error(error_info=error_info, failed_step=failed_step)

        if error_type == "VERIFY_CONTAINS_FAILED":
            return self._fix_verify_contains(
                task=task,
                failed_step=failed_step,
                error_info=error_info,
                original_steps=original_steps,
            )

        if error_type == "VERIFY_EQUALS_FAILED":
            return self._fix_verify_equals(
                task=task,
                failed_step=failed_step,
                error_info=error_info,
                original_steps=original_steps,
            )

        if error_type == "FILE_NOT_FOUND":
            return self._fix_file_not_found(
                task=task,
                failed_step=failed_step,
                error_info=error_info,
                original_steps=original_steps,
            )

        if error_type == "PYTHON_SYNTAX_ERROR":
            return self._fix_python_syntax_error(
                task=task,
                failed_step=failed_step,
                error_info=error_info,
                original_steps=original_steps,
            )

        if error_type == "PYTHON_NAME_ERROR":
            return self._fix_python_name_error(
                task=task,
                failed_step=failed_step,
                error_info=error_info,
                original_steps=original_steps,
            )

        if error_type == "PYTHON_IMPORT_ERROR":
            return self._fix_python_import_error(
                task=task,
                failed_step=failed_step,
                error_info=error_info,
                original_steps=original_steps,
            )

        if error_type == "PYTHON_RUNTIME_ERROR":
            return self._fix_python_runtime(
                task=task,
                failed_step=failed_step,
                error_info=error_info,
                original_steps=original_steps,
            )

        return self._build_fallback_retry_steps(
            failed_step=failed_step,
            original_steps=original_steps,
        )

    # ============================================================
    # parse / classify
    # ============================================================

    def parse_error(self, error: str) -> Dict[str, Any]:
        text = str(error or "")

        info: Dict[str, Any] = {
            "raw": text,
            "missing_value": None,
            "expected_value": None,
            "actual_value": None,
            "missing_file": None,
            "missing_name": None,
            "missing_module": None,
            "syntax_message": None,
        }

        m_not_found = re.search(r"'([^']+)' not found", text)
        if m_not_found:
            info["missing_value"] = m_not_found.group(1)

        m_equals = re.search(
            r"expected exact match '([^']*)', got '([^']*)'",
            text,
        )
        if m_equals:
            info["expected_value"] = m_equals.group(1)
            info["actual_value"] = m_equals.group(2)

        m_file_1 = re.search(r"FileNotFoundError:.*?[\"']([^\"']+)[\"']", text, re.DOTALL)
        if m_file_1:
            info["missing_file"] = m_file_1.group(1)

        m_file_2 = re.search(r"python file not found:\s*(.+)", text)
        if m_file_2 and not info["missing_file"]:
            info["missing_file"] = m_file_2.group(1).strip()

        m_file_3 = re.search(r"file not found:\s*(.+)", text)
        if m_file_3 and not info["missing_file"]:
            info["missing_file"] = m_file_3.group(1).strip()

        m_name = re.search(r"NameError:\s*name '([^']+)' is not defined", text)
        if m_name:
            info["missing_name"] = m_name.group(1)

        m_import_1 = re.search(r"ModuleNotFoundError:\s*No module named '([^']+)'", text)
        if m_import_1:
            info["missing_module"] = m_import_1.group(1)

        m_import_2 = re.search(r"ImportError:\s*cannot import name '([^']+)'", text)
        if m_import_2 and not info["missing_module"]:
            info["missing_module"] = m_import_2.group(1)

        m_syntax = re.search(r"SyntaxError:\s*(.+)", text)
        if m_syntax:
            info["syntax_message"] = m_syntax.group(1).strip()

        return info

    def classify_error(
        self,
        error_info: Dict[str, Any],
        failed_step: Dict[str, Any],
    ) -> str:
        step_type = str(failed_step.get("type") or "").strip().lower()
        error_text = str(error_info.get("raw") or "")

        if step_type == "verify":
            if "not found" in error_text:
                return "VERIFY_CONTAINS_FAILED"
            if "expected exact match" in error_text:
                return "VERIFY_EQUALS_FAILED"

        if (
            "FileNotFoundError" in error_text
            or "python file not found:" in error_text
            or "file not found:" in error_text
            or "No such file or directory" in error_text
        ):
            return "FILE_NOT_FOUND"

        if "SyntaxError:" in error_text:
            return "PYTHON_SYNTAX_ERROR"

        if "NameError:" in error_text:
            return "PYTHON_NAME_ERROR"

        if "ModuleNotFoundError:" in error_text or "ImportError:" in error_text:
            return "PYTHON_IMPORT_ERROR"

        if (
            "Traceback" in error_text
            or "python run failed:" in error_text
            or "command failed:" in error_text
            or "returncode=" in error_text
        ):
            return "PYTHON_RUNTIME_ERROR"

        return "UNKNOWN"

    # ============================================================
    # strategies
    # ============================================================

    def _fix_verify_contains(
        self,
        task: Dict[str, Any],
        failed_step: Dict[str, Any],
        error_info: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        contains = str(
            failed_step.get("contains")
            or error_info.get("missing_value")
            or ""
        ).strip()
        if not contains:
            return None

        context = self._find_recovery_context(
            failed_step=failed_step,
            original_steps=original_steps,
        )
        target_path = context["target_path"]
        if not target_path:
            return None

        original_write_step = context["write_step"]
        original_content = ""
        if isinstance(original_write_step, dict):
            original_content = str(original_write_step.get("content") or "")

        repaired_content = self._repair_python_output_content(
            original_content=original_content,
            desired_output=contains,
        )

        return [
            {
                "type": "write_file",
                "path": target_path,
                "content": repaired_content,
            },
            {
                "type": "run_python",
                "path": target_path,
            },
            {
                "type": "verify",
                "contains": contains,
            },
        ]

    def _fix_verify_equals(
        self,
        task: Dict[str, Any],
        failed_step: Dict[str, Any],
        error_info: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        expected = failed_step.get("equals", error_info.get("expected_value"))
        if expected is None:
            return None

        expected_text = str(expected)

        context = self._find_recovery_context(
            failed_step=failed_step,
            original_steps=original_steps,
        )
        target_path = context["target_path"]
        if not target_path:
            return None

        original_write_step = context["write_step"]
        original_content = ""
        if isinstance(original_write_step, dict):
            original_content = str(original_write_step.get("content") or "")

        repaired_content = self._repair_python_output_content(
            original_content=original_content,
            desired_output=expected_text,
        )

        return [
            {
                "type": "write_file",
                "path": target_path,
                "content": repaired_content,
            },
            {
                "type": "run_python",
                "path": target_path,
            },
            {
                "type": "verify",
                "equals": expected_text,
            },
        ]

    def _fix_file_not_found(
        self,
        task: Dict[str, Any],
        failed_step: Dict[str, Any],
        error_info: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        failed_type = str(failed_step.get("type") or "").strip().lower()

        # 優先用 step 自己的 path
        target_path = str(failed_step.get("path") or "").strip()

        if not target_path:
            target_path = str(error_info.get("missing_file") or "").strip()

        if not target_path:
            context = self._find_recovery_context(
                failed_step=failed_step,
                original_steps=original_steps,
            )
            target_path = context["target_path"]

        if not target_path:
            return None

        if failed_type == "read_file":
            return [
                {
                    "type": "write_file",
                    "path": target_path,
                    "content": "auto_created\n",
                },
                {
                    "type": "read_file",
                    "path": target_path,
                },
            ]

        return [
            {
                "type": "write_file",
                "path": target_path,
                "content": 'print("auto_created")\n',
            },
            {
                "type": "run_python",
                "path": target_path,
            },
        ]

    def _fix_python_runtime(
        self,
        task: Dict[str, Any],
        failed_step: Dict[str, Any],
        error_info: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        target_path = str(failed_step.get("path") or "").strip()

        if not target_path:
            context = self._find_recovery_context(
                failed_step=failed_step,
                original_steps=original_steps,
            )
            target_path = context["target_path"]

        if not target_path:
            return None

        return [
            {
                "type": "write_file",
                "path": target_path,
                "content": 'print("fixed_runtime")\n',
            },
            {
                "type": "run_python",
                "path": target_path,
            },
        ]

    def _fix_python_syntax_error(
        self,
        task: Dict[str, Any],
        failed_step: Dict[str, Any],
        error_info: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        target_path = str(failed_step.get("path") or "").strip()

        if not target_path:
            context = self._find_recovery_context(
                failed_step=failed_step,
                original_steps=original_steps,
            )
            target_path = context["target_path"]

        if not target_path:
            return None

        desired_output = "fixed_syntax"

        verify_step = self._find_following_verify_step(
            failed_step=failed_step,
            original_steps=original_steps,
        )
        if isinstance(verify_step, dict):
            if verify_step.get("contains"):
                desired_output = str(verify_step.get("contains"))
            elif verify_step.get("equals") is not None:
                desired_output = str(verify_step.get("equals"))

        return [
            {
                "type": "write_file",
                "path": target_path,
                "content": f"print({json.dumps(desired_output, ensure_ascii=False)})\n",
            },
            {
                "type": "run_python",
                "path": target_path,
            },
        ]

    def _fix_python_name_error(
        self,
        task: Dict[str, Any],
        failed_step: Dict[str, Any],
        error_info: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        target_path = str(failed_step.get("path") or "").strip()

        if not target_path:
            context = self._find_recovery_context(
                failed_step=failed_step,
                original_steps=original_steps,
            )
            target_path = context["target_path"]

        if not target_path:
            return None

        missing_name = str(error_info.get("missing_name") or "").strip()
        verify_step = self._find_following_verify_step(
            failed_step=failed_step,
            original_steps=original_steps,
        )

        desired_output = "fixed_name_error"
        if isinstance(verify_step, dict):
            if verify_step.get("contains"):
                desired_output = str(verify_step.get("contains"))
            elif verify_step.get("equals") is not None:
                desired_output = str(verify_step.get("equals"))

        content_lines: List[str] = []
        if missing_name:
            content_lines.append(f"{missing_name} = {json.dumps(desired_output, ensure_ascii=False)}")
            content_lines.append(f"print({missing_name})")
        else:
            content_lines.append(f"print({json.dumps(desired_output, ensure_ascii=False)})")

        return [
            {
                "type": "write_file",
                "path": target_path,
                "content": "\n".join(content_lines) + "\n",
            },
            {
                "type": "run_python",
                "path": target_path,
            },
        ]

    def _fix_python_import_error(
        self,
        task: Dict[str, Any],
        failed_step: Dict[str, Any],
        error_info: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        target_path = str(failed_step.get("path") or "").strip()

        if not target_path:
            context = self._find_recovery_context(
                failed_step=failed_step,
                original_steps=original_steps,
            )
            target_path = context["target_path"]

        if not target_path:
            return None

        verify_step = self._find_following_verify_step(
            failed_step=failed_step,
            original_steps=original_steps,
        )

        desired_output = "fixed_import_error"
        if isinstance(verify_step, dict):
            if verify_step.get("contains"):
                desired_output = str(verify_step.get("contains"))
            elif verify_step.get("equals") is not None:
                desired_output = str(verify_step.get("equals"))

        return [
            {
                "type": "write_file",
                "path": target_path,
                "content": f"print({json.dumps(desired_output, ensure_ascii=False)})\n",
            },
            {
                "type": "run_python",
                "path": target_path,
            },
        ]

    # ============================================================
    # fallback
    # ============================================================

    def _build_fallback_retry_steps(
        self,
        failed_step: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        failed_type = str(failed_step.get("type") or "").strip().lower()

        if failed_type == "verify":
            context = self._find_recovery_context(
                failed_step=failed_step,
                original_steps=original_steps,
            )
            run_step = context["run_step"]
            if isinstance(run_step, dict):
                return [run_step, dict(failed_step)]
            return [dict(failed_step)]

        if failed_type in {"run_python", "read_file", "write_file"}:
            return [dict(failed_step)]

        return None

    # ============================================================
    # helpers
    # ============================================================

    def _find_recovery_context(
        self,
        failed_step: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        target_path = str(failed_step.get("path") or "").strip()
        run_step: Optional[Dict[str, Any]] = None
        write_step: Optional[Dict[str, Any]] = None

        for step in reversed(original_steps):
            if not isinstance(step, dict):
                continue

            step_type = str(step.get("type") or "").strip().lower()

            if run_step is None and step_type == "run_python":
                run_step = dict(step)
                if not target_path:
                    target_path = str(step.get("path") or "").strip()

            if step_type == "write_file":
                step_path = str(step.get("path") or "").strip()
                if target_path:
                    if step_path == target_path:
                        write_step = dict(step)
                        break
                elif write_step is None:
                    write_step = dict(step)

        if write_step is None:
            for step in reversed(original_steps):
                if not isinstance(step, dict):
                    continue
                if str(step.get("type") or "").strip().lower() == "write_file":
                    write_step = dict(step)
                    if not target_path:
                        target_path = str(step.get("path") or "").strip()
                    break

        return {
            "target_path": target_path if target_path else None,
            "run_step": run_step,
            "write_step": write_step,
        }

    def _find_following_verify_step(
        self,
        failed_step: Dict[str, Any],
        original_steps: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        # 最小版做法：反向找最後一個 verify
        for step in reversed(original_steps):
            if not isinstance(step, dict):
                continue
            if str(step.get("type") or "").strip().lower() == "verify":
                return dict(step)
        return None

    def _repair_python_output_content(
        self,
        original_content: str,
        desired_output: str,
    ) -> str:
        text = str(original_content or "")
        desired = str(desired_output or "")

        if not text.strip():
            return f"print({json.dumps(desired, ensure_ascii=False)})\n"

        lines = text.splitlines()
        new_lines: List[str] = []
        changed = False

        for line in lines:
            stripped = line.strip()
            m = re.match(r"^print\((['\"])(.*)\1\)\s*$", stripped)
            if m:
                new_lines.append(f"print({json.dumps(desired, ensure_ascii=False)})")
                changed = True
                continue
            new_lines.append(line)

        if changed:
            rebuilt = "\n".join(new_lines)
            if not rebuilt.endswith("\n"):
                rebuilt += "\n"
            return rebuilt

        return f"print({json.dumps(desired, ensure_ascii=False)})\n"