"""Tool-facing wrapper for controlled repo sandbox edits.

This module is intentionally small and adapter-like.  It does not decide which
files should be changed.  Callers must provide an explicit file_path and either
new_content or a small replace operation.  The tool edits only the sandbox copy,
runs an optional allowlisted verification command, and returns a structured
result containing a reviewable unified diff.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .controlled_edit import ControlledEditSession
from .policy import PolicyViolation, RepoSandboxPolicy

EditMode = Literal["replace_file", "replace_text", "append_text"]


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
        return cls(
            file_path=str(payload.get("file_path", "")),
            instruction=str(payload.get("instruction", "")),
            mode=payload.get("mode", "replace_text"),
            new_content=payload.get("new_content"),
            old_text=payload.get("old_text"),
            new_text=payload.get("new_text"),
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RepoEditTool:
    """Controlled tool entry point for repo edits.

    Safety boundary:
    - no automatic file discovery;
    - no direct writes to the source repo;
    - only one explicit file_path per call;
    - optional verification command must pass RepoSandboxPolicy.
    """

    name = "repo_edit"
    description = "Copy one explicit repo file into sandbox, edit sandbox copy, verify, and return unified diff."

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
                test_command = request.test_command if isinstance(request.test_command, str) else " ".join(request.test_command)
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
            )
        except PolicyViolation as exc:
            return self._error_result("blocked", request, str(exc))
        except Exception as exc:  # defensive boundary for tool callers
            return self._error_result("failed", request, f"{type(exc).__name__}: {exc}")

    def _validate_request(self, request: RepoEditRequest) -> None:
        if not request.file_path.strip():
            raise PolicyViolation("repo_edit requires explicit file_path")
        if not request.instruction.strip():
            raise PolicyViolation("repo_edit requires instruction")
        if request.mode not in {"replace_file", "replace_text", "append_text"}:
            raise PolicyViolation(f"unsupported edit mode: {request.mode}")
        if request.mode == "replace_file" and request.new_content is None:
            raise PolicyViolation("replace_file requires new_content")
        if request.mode == "replace_text" and (request.old_text is None or request.new_text is None):
            raise PolicyViolation("replace_text requires old_text and new_text")
        if request.mode == "append_text" and request.append_text is None:
            raise PolicyViolation("append_text requires append_text")

    def _apply_edit(self, session: ControlledEditSession, request: RepoEditRequest) -> None:
        reason = request.instruction.strip()
        if request.mode == "replace_file":
            assert request.new_content is not None
            session.replace_file_text(request.file_path, request.new_content, reason=reason)
            return

        if request.mode == "replace_text":
            assert request.old_text is not None
            assert request.new_text is not None
            current = session.sandbox.read_text(request.file_path)
            if request.old_text not in current:
                raise PolicyViolation("old_text was not found in sandbox file; refusing blind edit")
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
        )


def run_repo_edit(
    payload: RepoEditRequest | dict[str, Any],
    *,
    repo_root: str | Path = ".",
    sandbox_root: str | Path = "workspace/repo_sandbox",
) -> dict[str, Any]:
    """Function-style adapter for tool registries that expect callables."""

    return RepoEditTool(repo_root=repo_root, sandbox_root=sandbox_root).run(payload).to_dict()
