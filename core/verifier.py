from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


class Verifier:
    """
    ZERO Verifier

    作用：
    1. 檢查 tool 執行結果是否真的成功
    2. 提供 verify evidence
    3. 讓 AgentLoop 能做 execute -> verify 流程

    目前先支援：
    - workspace.create_task
    - workspace.write_note
    - workspace.write_plan
    - workspace.list_tasks
    - file.read
    - file.write
    """

    def verify_step(
        self,
        step: Dict[str, Any],
        step_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        tool_name = step.get("tool_name")
        payload = step_result.get("payload", {})
        result = step_result.get("result", {})

        if not step_result.get("success", False):
            return self._build_verify_result(
                ok=False,
                status="execution_failed",
                summary="Execution failed before verify.",
                evidence=[],
                error=step_result.get("error", "step execution failed")
            )

        if not isinstance(payload, dict):
            payload = {}

        if not isinstance(result, dict):
            result = {}

        action = payload.get("action") or result.get("action")

        if tool_name == "workspace":
            return self._verify_workspace_action(action, payload, result)

        if tool_name == "file":
            return self._verify_file_action(action, payload, result)

        return self._build_verify_result(
            ok=True,
            status="no_rule",
            summary=f"No verifier rule for tool '{tool_name}'. Assume success.",
            evidence=[],
            error=None
        )

    # =====================================================
    # Workspace verify
    # =====================================================

    def _verify_workspace_action(
        self,
        action: Optional[str],
        payload: Dict[str, Any],
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        if action == "create_task":
            return self._verify_workspace_create_task(result)

        if action == "write_note":
            return self._verify_workspace_write_note(result)

        if action == "write_plan":
            return self._verify_workspace_write_plan(result)

        if action == "list_tasks":
            return self._verify_workspace_list_tasks(result)

        return self._build_verify_result(
            ok=True,
            status="no_rule",
            summary=f"No workspace verify rule for action '{action}'. Assume success.",
            evidence=[],
            error=None
        )

    def _verify_workspace_create_task(self, result: Dict[str, Any]) -> Dict[str, Any]:
        task_id = result.get("task_id")
        task_dir = result.get("task_dir")
        evidence: List[str] = []

        if not isinstance(task_id, str) or not task_id.strip():
            return self._build_verify_result(
                ok=False,
                status="missing_task_id",
                summary="Verify failed: create_task missing task_id.",
                evidence=evidence,
                error="missing task_id"
            )

        if not isinstance(task_dir, str) or not task_dir.strip():
            return self._build_verify_result(
                ok=False,
                status="missing_task_dir",
                summary=f"Verify failed: create_task missing task_dir for {task_id}.",
                evidence=evidence,
                error="missing task_dir"
            )

        task_path = Path(task_dir)
        if not task_path.exists():
            return self._build_verify_result(
                ok=False,
                status="task_dir_not_found",
                summary=f"Verify failed: task directory not found for {task_id}.",
                evidence=evidence,
                error=f"task directory not found: {task_dir}"
            )

        if not task_path.is_dir():
            return self._build_verify_result(
                ok=False,
                status="task_dir_not_directory",
                summary=f"Verify failed: task path is not a directory for {task_id}.",
                evidence=evidence,
                error=f"task path is not directory: {task_dir}"
            )

        evidence.append(str(task_path))

        return self._build_verify_result(
            ok=True,
            status="verified",
            summary=f"Verified workspace task created: {task_id}",
            evidence=evidence,
            error=None
        )

    def _verify_workspace_write_note(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return self._verify_workspace_text_write(
            result=result,
            path_key="notes_path",
            content_key="written_text",
            label="note"
        )

    def _verify_workspace_write_plan(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return self._verify_workspace_text_write(
            result=result,
            path_key="plan_path",
            content_key="written_text",
            label="plan"
        )

    def _verify_workspace_text_write(
        self,
        result: Dict[str, Any],
        path_key: str,
        content_key: str,
        label: str
    ) -> Dict[str, Any]:
        task_id = result.get("task_id")
        file_path = result.get(path_key)
        expected_text = result.get(content_key, "")
        evidence: List[str] = []

        if not isinstance(file_path, str) or not file_path.strip():
            return self._build_verify_result(
                ok=False,
                status="missing_output_path",
                summary=f"Verify failed: write_{label} missing file path.",
                evidence=evidence,
                error=f"missing {path_key}"
            )

        path = Path(file_path)
        if not path.exists():
            return self._build_verify_result(
                ok=False,
                status="output_not_found",
                summary=f"Verify failed: {label} file not found.",
                evidence=evidence,
                error=f"file not found: {file_path}"
            )

        if not path.is_file():
            return self._build_verify_result(
                ok=False,
                status="output_not_file",
                summary=f"Verify failed: {label} path is not a file.",
                evidence=evidence,
                error=f"path is not file: {file_path}"
            )

        evidence.append(str(path))

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            return self._build_verify_result(
                ok=False,
                status="read_failed",
                summary=f"Verify failed: cannot read {label} file.",
                evidence=evidence,
                error=str(exc)
            )

        if isinstance(expected_text, str) and expected_text.strip():
            if expected_text not in content:
                return self._build_verify_result(
                    ok=False,
                    status="content_mismatch",
                    summary=f"Verify failed: written {label} text not found in file.",
                    evidence=evidence,
                    error="expected text not found in file"
                )

        return self._build_verify_result(
            ok=True,
            status="verified",
            summary=f"Verified workspace {label} written" + (f" for {task_id}" if task_id else ""),
            evidence=evidence,
            error=None
        )

    def _verify_workspace_list_tasks(self, result: Dict[str, Any]) -> Dict[str, Any]:
        results = result.get("results", [])
        if not isinstance(results, list):
            return self._build_verify_result(
                ok=False,
                status="invalid_results",
                summary="Verify failed: list_tasks returned invalid results.",
                evidence=[],
                error="results is not a list"
            )

        return self._build_verify_result(
            ok=True,
            status="verified",
            summary=f"Verified task listing: {len(results)} task(s).",
            evidence=[],
            error=None
        )

    # =====================================================
    # File verify
    # =====================================================

    def _verify_file_action(
        self,
        action: Optional[str],
        payload: Dict[str, Any],
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        if action == "read":
            return self._verify_file_read(payload, result)

        if action == "write":
            return self._verify_file_write(payload, result)

        return self._build_verify_result(
            ok=True,
            status="no_rule",
            summary=f"No file verify rule for action '{action}'. Assume success.",
            evidence=[],
            error=None
        )

    def _verify_file_read(
        self,
        payload: Dict[str, Any],
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        path_value = result.get("path") or payload.get("path")
        evidence: List[str] = []

        if not isinstance(path_value, str) or not path_value.strip():
            return self._build_verify_result(
                ok=False,
                status="missing_path",
                summary="Verify failed: file read missing path.",
                evidence=evidence,
                error="missing path"
            )

        path = Path(path_value)
        if not path.exists():
            return self._build_verify_result(
                ok=False,
                status="file_not_found",
                summary="Verify failed: read target file not found.",
                evidence=evidence,
                error=f"file not found: {path_value}"
            )

        if not path.is_file():
            return self._build_verify_result(
                ok=False,
                status="not_a_file",
                summary="Verify failed: read target is not a file.",
                evidence=evidence,
                error=f"not a file: {path_value}"
            )

        evidence.append(str(path))

        return self._build_verify_result(
            ok=True,
            status="verified",
            summary=f"Verified file read target exists: {path_value}",
            evidence=evidence,
            error=None
        )

    def _verify_file_write(
        self,
        payload: Dict[str, Any],
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        path_value = result.get("path") or payload.get("path")
        expected_content = result.get("content", payload.get("content", ""))
        evidence: List[str] = []

        if not isinstance(path_value, str) or not path_value.strip():
            return self._build_verify_result(
                ok=False,
                status="missing_path",
                summary="Verify failed: file write missing path.",
                evidence=evidence,
                error="missing path"
            )

        path = Path(path_value)
        if not path.exists():
            return self._build_verify_result(
                ok=False,
                status="file_not_found",
                summary="Verify failed: written file not found.",
                evidence=evidence,
                error=f"file not found: {path_value}"
            )

        if not path.is_file():
            return self._build_verify_result(
                ok=False,
                status="not_a_file",
                summary="Verify failed: written target is not a file.",
                evidence=evidence,
                error=f"not a file: {path_value}"
            )

        evidence.append(str(path))

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            return self._build_verify_result(
                ok=False,
                status="read_failed",
                summary="Verify failed: cannot read written file.",
                evidence=evidence,
                error=str(exc)
            )

        if isinstance(expected_content, str) and expected_content and expected_content not in content:
            return self._build_verify_result(
                ok=False,
                status="content_mismatch",
                summary="Verify failed: expected content not found in file.",
                evidence=evidence,
                error="expected content not found in file"
            )

        return self._build_verify_result(
            ok=True,
            status="verified",
            summary=f"Verified file write: {path_value}",
            evidence=evidence,
            error=None
        )

    # =====================================================
    # Helpers
    # =====================================================

    def _build_verify_result(
        self,
        ok: bool,
        status: str,
        summary: str,
        evidence: List[str],
        error: Optional[str]
    ) -> Dict[str, Any]:
        return {
            "ok": ok,
            "status": status,
            "summary": summary,
            "evidence": evidence,
            "error": error,
        }