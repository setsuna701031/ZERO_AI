"""Tool-facing wrapper for controlled repo sandbox edits.

Code Chain v0.7.1 / tool v0.6.5

Purpose:
- Accept mode="controlled_replace".
- Edit through ControlledEditSession sandbox first.
- Return controlled diff/report.
- Apply the actual edited sandbox content back to the explicit workspace file.
- Create .bak_v06 backup before overwriting the workspace file.

Critical fix:
- Do NOT copy from guessed sandbox filesystem paths.
- The previous versions could report applied_to_workspace=true while copying
  the unmodified sandbox original file.
- This version reads the edited content through session.sandbox.read_text(),
  then writes that exact content to the real workspace path.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .controlled_edit import ControlledEditSession
from .policy import PolicyViolation, RepoSandboxPolicy


EditMode = Literal[
    "replace_file",
    "replace_text",
    "append_text",
    "controlled_replace",
]


@dataclass(frozen=True)
class RepoEditRequest:
    """Explicit request object for one controlled sandbox edit."""

    file_path: str
    instruction: str
    mode: EditMode = "replace_text"
    new_content: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    append_text: str | None = None
    test_command: str | list[str] | None = None
    timeout_seconds: int = 60

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RepoEditRequest":
        file_path = str(
            payload.get("file_path")
            or payload.get("target_path")
            or payload.get("path")
            or payload.get("file")
            or ""
        )

        mode = str(
            payload.get("mode")
            or payload.get("operation")
            or payload.get("type")
            or "replace_text"
        )

        old_text = payload.get("old_text")
        if old_text is None:
            old_text = payload.get("old_line")

        new_text = payload.get("new_text")
        if new_text is None:
            new_text = payload.get("new_line")

        instruction = str(
            payload.get("instruction")
            or payload.get("task_text")
            or payload.get("reason")
            or ""
        )

        return cls(
            file_path=file_path,
            instruction=instruction,
            mode=mode,  # type: ignore[arg-type]
            new_content=payload.get("new_content"),
            old_text=old_text,
            new_text=new_text,
            append_text=payload.get("append_text"),
            test_command=payload.get("test_command"),
            timeout_seconds=int(payload.get("timeout_seconds", 60)),
        )


@dataclass(frozen=True)
class RepoEditToolResult:
    status: Literal["success", "blocked", "failed"]
    file_path: str
    instruction: str
    changed_files: list[str]
    selected_files: list[str]
    test_command: str | None
    test_allowed: bool
    test_result: str
    diff: str
    report: str
    error: str | None = None
    applied_to_workspace: bool = False
    workspace_path: str = ""
    backup_path: str = ""
    apply_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RepoEditTool:
    """Controlled tool entry point for repo edits.

    Safety boundary:
    - no automatic file discovery;
    - no arbitrary path writes;
    - only one explicit file_path per call;
    - controlled_replace requires exactly one old_text match;
    - optional verification command must pass RepoSandboxPolicy.
    """

    name = "repo_edit"
    description = "Controlled single-file repo edit with sandbox, diff, backup, and apply."

    def __init__(
        self,
        repo_root: str | Path = ".",
        sandbox_root: str | Path = "workspace/repo_sandbox",
        *,
        policy: RepoSandboxPolicy | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.sandbox_root = sandbox_root
        self.policy = policy or RepoSandboxPolicy()

    def run(self, payload: RepoEditRequest | dict[str, Any]) -> RepoEditToolResult:
        request = payload if isinstance(payload, RepoEditRequest) else RepoEditRequest.from_dict(payload)
        applied_to_workspace = False
        workspace_path = ""
        backup_path = ""
        apply_source = ""

        try:
            self._validate_request(request)

            session = ControlledEditSession(
                self.repo_root,
                self.sandbox_root,
                policy=self.policy,
            )
            session.prepare_files([request.file_path])
            self._apply_edit(session, request)

            if request.test_command is not None:
                test_allowed, test_output, blocked_reason = session.run_test(
                    request.test_command,
                    timeout_seconds=request.timeout_seconds,
                )
                controlled_result = session.result()
                test_command = (
                    request.test_command
                    if isinstance(request.test_command, str)
                    else " ".join(request.test_command)
                )
                report_result = controlled_result.__class__(
                    selected_files=controlled_result.selected_files,
                    changed_files=controlled_result.changed_files,
                    reasons=controlled_result.reasons,
                    test_command=test_command,
                    test_allowed=test_allowed,
                    test_result=test_output,
                    diff=controlled_result.diff,
                    blocked_reason=blocked_reason,
                )
            else:
                report_result = session.result()

            status: Literal["success", "blocked", "failed"] = "success"
            error = None
            if request.test_command is not None and not report_result.test_allowed:
                status = "blocked"
                error = report_result.blocked_reason

            if status == "success":
                apply_result = self._apply_session_content_back_to_workspace(session, request)
                applied_to_workspace = bool(apply_result.get("applied"))
                workspace_path = str(apply_result.get("workspace_path") or "")
                backup_path = str(apply_result.get("backup_path") or "")
                apply_source = str(apply_result.get("apply_source") or "")
                if not applied_to_workspace:
                    status = "failed"
                    error = str(apply_result.get("error") or "failed to apply edited content back to workspace")

            return RepoEditToolResult(
                status=status,
                file_path=request.file_path,
                instruction=request.instruction,
                changed_files=report_result.changed_files,
                selected_files=report_result.selected_files,
                test_command=report_result.test_command,
                test_allowed=report_result.test_allowed,
                test_result=report_result.test_result,
                diff=report_result.diff,
                report=report_result.to_report(),
                error=error,
                applied_to_workspace=applied_to_workspace,
                workspace_path=workspace_path,
                backup_path=backup_path,
                apply_source=apply_source,
            )
        except PolicyViolation as exc:
            return self._error_result("blocked", request, str(exc))
        except Exception as exc:
            return self._error_result("failed", request, f"{type(exc).__name__}: {exc}")

    def _validate_request(self, request: RepoEditRequest) -> None:
        if not request.file_path.strip():
            raise PolicyViolation("repo_edit requires explicit file_path")

        if not request.instruction.strip():
            raise PolicyViolation("repo_edit requires instruction")

        if request.mode not in {"replace_file", "replace_text", "append_text", "controlled_replace"}:
            raise PolicyViolation(f"unsupported edit mode: {request.mode}")

        normalized_path = self._repo_relative(request.file_path)
        if normalized_path.startswith("/") or ".." in Path(normalized_path).parts:
            raise PolicyViolation("unsafe file_path")

        if request.mode == "replace_file" and request.new_content is None:
            raise PolicyViolation("replace_file requires new_content")

        if request.mode in {"replace_text", "controlled_replace"} and (
            request.old_text is None or request.new_text is None
        ):
            raise PolicyViolation(f"{request.mode} requires old_text and new_text")

        if request.mode == "append_text" and request.append_text is None:
            raise PolicyViolation("append_text requires append_text")

    def _apply_edit(self, session: ControlledEditSession, request: RepoEditRequest) -> None:
        reason = request.instruction.strip()

        if request.mode == "replace_file":
            assert request.new_content is not None
            session.replace_file_text(request.file_path, request.new_content, reason=reason)
            return

        if request.mode in {"replace_text", "controlled_replace"}:
            assert request.old_text is not None
            assert request.new_text is not None

            current = session.sandbox.read_text(request.file_path)

            match_count = current.count(request.old_text)
            if match_count <= 0:
                raise PolicyViolation("old_text was not found in sandbox file; refusing blind edit")

            if request.mode == "controlled_replace" and match_count != 1:
                raise PolicyViolation(
                    f"controlled_replace requires exactly one old_text match; found {match_count}"
                )

            updated = current.replace(request.old_text, request.new_text, 1)
            session.replace_file_text(request.file_path, updated, reason=reason)
            return

        if request.mode == "append_text":
            assert request.append_text is not None
            current = session.sandbox.read_text(request.file_path)
            separator = "" if current.endswith("\n") or not current else "\n"
            session.replace_file_text(request.file_path, current + separator + request.append_text, reason=reason)
            return

        raise PolicyViolation(f"unsupported edit mode: {request.mode}")

    def _repo_relative(self, file_path: str) -> str:
        return file_path.replace("\\", "/").strip().lstrip("/")

    def _resolve_workspace_path(self, file_path: str) -> Path:
        repo_relative = self._repo_relative(file_path)
        if not repo_relative:
            raise PolicyViolation("empty file_path")

        if ".." in Path(repo_relative).parts:
            raise PolicyViolation("unsafe relative path")

        workspace_path = (self.repo_root / repo_relative).resolve()
        try:
            workspace_path.relative_to(self.repo_root)
        except ValueError as exc:
            raise PolicyViolation("workspace path escapes repo root") from exc

        return workspace_path

    def _read_edited_session_content(
        self,
        session: ControlledEditSession,
        request: RepoEditRequest,
    ) -> tuple[str, str]:
        """Read the exact edited content from the session sandbox abstraction.

        This is the stable source of truth after session.replace_file_text().
        Filesystem layout under workspace/repo_sandbox may vary by implementation,
        so this method does not rely on copied-file paths.
        """

        try:
            content = session.sandbox.read_text(request.file_path)
            return content, "session.sandbox.read_text(request.file_path)"
        except Exception as first_exc:
            stripped = self._repo_relative(request.file_path)
            if stripped.startswith("workspace/"):
                stripped = stripped[len("workspace/") :]
            try:
                content = session.sandbox.read_text(stripped)
                return content, "session.sandbox.read_text(stripped_workspace_path)"
            except Exception as second_exc:
                raise PolicyViolation(
                    "unable to read edited sandbox content: "
                    f"{type(first_exc).__name__}: {first_exc}; "
                    f"{type(second_exc).__name__}: {second_exc}"
                ) from second_exc

    def _make_backup_path(self, workspace_path: Path) -> Path:
        backup_candidate = workspace_path.with_name(workspace_path.name + ".bak_v06")
        if not backup_candidate.exists():
            return backup_candidate

        index = 1
        while True:
            indexed = workspace_path.with_name(workspace_path.name + f".bak_v06_{index}")
            if not indexed.exists():
                return indexed
            index += 1

    def _apply_session_content_back_to_workspace(
        self,
        session: ControlledEditSession,
        request: RepoEditRequest,
    ) -> dict[str, Any]:
        workspace_path = self._resolve_workspace_path(request.file_path)

        try:
            edited_content, apply_source = self._read_edited_session_content(session, request)
        except PolicyViolation as exc:
            return {
                "applied": False,
                "error": str(exc),
                "workspace_path": str(workspace_path),
            }

        workspace_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = ""
        if workspace_path.exists():
            backup_candidate = self._make_backup_path(workspace_path)
            shutil.copy2(workspace_path, backup_candidate)
            backup_path = str(backup_candidate)

        workspace_path.write_text(edited_content, encoding="utf-8")

        # Hard verification: the real file must equal what we read from the
        # edited session content.
        try:
            written = workspace_path.read_text(encoding="utf-8")
        except Exception as exc:
            return {
                "applied": False,
                "error": f"workspace write verification failed: {exc}",
                "workspace_path": str(workspace_path),
                "backup_path": backup_path,
                "apply_source": apply_source,
            }

        if written != edited_content:
            return {
                "applied": False,
                "error": "workspace write verification mismatch",
                "workspace_path": str(workspace_path),
                "backup_path": backup_path,
                "apply_source": apply_source,
            }

        return {
            "applied": True,
            "workspace_path": str(workspace_path),
            "backup_path": backup_path,
            "apply_source": apply_source,
        }

    def _error_result(
        self,
        status: Literal["blocked", "failed"],
        request: RepoEditRequest,
        error: str,
    ) -> RepoEditToolResult:
        return RepoEditToolResult(
            status=status,
            file_path=request.file_path,
            instruction=request.instruction,
            changed_files=[],
            selected_files=[],
            test_command=None,
            test_allowed=False,
            test_result="",
            diff="",
            report=f"[REPO EDIT TOOL]\nStatus: {status}\nError: {error}\n",
            error=error,
            applied_to_workspace=False,
            workspace_path="",
            backup_path="",
            apply_source="",
        )


def run_repo_edit(
    payload: RepoEditRequest | dict[str, Any],
    *,
    repo_root: str | Path = ".",
    sandbox_root: str | Path = "workspace/repo_sandbox",
) -> dict[str, Any]:
    """Function-style adapter for tool registries that expect callables."""

    return RepoEditTool(repo_root=repo_root, sandbox_root=sandbox_root).run(payload).to_dict()
