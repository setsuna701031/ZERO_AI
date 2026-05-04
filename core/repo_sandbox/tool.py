"""Tool-facing wrapper for controlled repo sandbox edits.

Code Chain v0.6.4

Purpose:
- Accept mode="controlled_replace".
- Apply safe single-file controlled edits in sandbox first.
- Copy the edited sandbox result back to the explicit workspace file.
- Create .bak_v06 backup before overwriting the workspace file.
- Avoid fragile sandbox path assumptions by resolving multiple known sandbox
  layouts and by falling back to the diff/changed file path convention.

Safety:
- No automatic file discovery.
- One explicit file_path per call.
- No path traversal.
- controlled_replace requires exactly one old_text match.
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
    sandbox_path: str = ""
    backup_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RepoEditTool:
    """Controlled tool entry point for repo edits."""

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
        sandbox_path = ""
        backup_path = ""

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
                apply_result = self._apply_sandbox_file_back_to_workspace(
                    session=session,
                    request=request,
                    changed_files=list(report_result.changed_files or []),
                )
                applied_to_workspace = bool(apply_result.get("applied"))
                workspace_path = str(apply_result.get("workspace_path") or "")
                sandbox_path = str(apply_result.get("sandbox_path") or "")
                backup_path = str(apply_result.get("backup_path") or "")
                if not applied_to_workspace:
                    status = "failed"
                    error = str(apply_result.get("error") or "failed to apply sandbox result back to workspace")

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
                sandbox_path=sandbox_path,
                backup_path=backup_path,
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

        normalized_path = request.file_path.replace("\\", "/").strip()
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

    def _sandbox_relative_candidates(self, file_path: str, changed_files: list[str]) -> list[str]:
        base = self._repo_relative(file_path)
        values = [base]
        if base.startswith("workspace/"):
            values.append(base[len("workspace/") :])

        for changed in changed_files:
            changed_norm = self._repo_relative(str(changed))
            if changed_norm and changed_norm not in values:
                values.append(changed_norm)
            if changed_norm.startswith("workspace/"):
                stripped = changed_norm[len("workspace/") :]
                if stripped not in values:
                    values.append(stripped)

        return values

    def _candidate_sandbox_roots(self, session: ControlledEditSession) -> list[Path]:
        roots: list[Path] = []
        for value in (
            getattr(session, "sandbox_root", None),
            getattr(getattr(session, "sandbox", None), "root", None),
            getattr(getattr(session, "sandbox", None), "sandbox_root", None),
            self.sandbox_root,
            "workspace/repo_sandbox",
        ):
            if value is None:
                continue
            path = Path(value)
            if not path.is_absolute():
                path = self.repo_root / path
            resolved = path.resolve()
            if str(resolved) not in [str(p) for p in roots]:
                roots.append(resolved)
        return roots

    def _find_sandbox_path(
        self,
        session: ControlledEditSession,
        request: RepoEditRequest,
        changed_files: list[str],
    ) -> Path | None:
        candidates: list[Path] = []

        for candidate_path in [request.file_path] + changed_files:
            try:
                resolved = Path(session.sandbox.resolve_path(candidate_path)).resolve()
                candidates.append(resolved)
            except Exception:
                pass

        roots = self._candidate_sandbox_roots(session)
        relatives = self._sandbox_relative_candidates(request.file_path, changed_files)
        for root in roots:
            for rel in relatives:
                candidates.append((root / rel).resolve())

        # Last-resort scan. This is still constrained to sandbox roots and exact filename.
        target_name = Path(self._repo_relative(request.file_path)).name
        for root in roots:
            if root.exists():
                try:
                    for found in root.rglob(target_name):
                        if found.is_file():
                            candidates.append(found.resolve())
                except Exception:
                    pass

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists() and candidate.is_file():
                return candidate

        return None

    def _apply_sandbox_file_back_to_workspace(
        self,
        session: ControlledEditSession,
        request: RepoEditRequest,
        changed_files: list[str],
    ) -> dict[str, Any]:
        repo_relative = self._repo_relative(request.file_path)
        if not repo_relative:
            return {"applied": False, "error": "empty file_path"}

        if ".." in Path(repo_relative).parts:
            return {"applied": False, "error": "unsafe relative path"}

        workspace_path = (self.repo_root / repo_relative).resolve()
        repo_root = self.repo_root.resolve()
        try:
            workspace_path.relative_to(repo_root)
        except ValueError:
            return {
                "applied": False,
                "error": "workspace path escapes repo root",
                "workspace_path": str(workspace_path),
            }

        sandbox_path = self._find_sandbox_path(session, request, changed_files)
        if sandbox_path is None:
            return {
                "applied": False,
                "error": "sandbox edited file not found",
                "workspace_path": str(workspace_path),
                "sandbox_roots": [str(p) for p in self._candidate_sandbox_roots(session)],
                "sandbox_relatives": self._sandbox_relative_candidates(request.file_path, changed_files),
            }

        workspace_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = ""
        if workspace_path.exists():
            backup_candidate = workspace_path.with_name(workspace_path.name + ".bak_v06")
            if backup_candidate.exists():
                index = 1
                while True:
                    indexed = workspace_path.with_name(workspace_path.name + f".bak_v06_{index}")
                    if not indexed.exists():
                        backup_candidate = indexed
                        break
                    index += 1
            shutil.copy2(workspace_path, backup_candidate)
            backup_path = str(backup_candidate)

        shutil.copy2(sandbox_path, workspace_path)

        return {
            "applied": True,
            "workspace_path": str(workspace_path),
            "sandbox_path": str(sandbox_path),
            "backup_path": backup_path,
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
            sandbox_path="",
            backup_path="",
        )


def run_repo_edit(
    payload: RepoEditRequest | dict[str, Any],
    *,
    repo_root: str | Path = ".",
    sandbox_root: str | Path = "workspace/repo_sandbox",
) -> dict[str, Any]:
    """Function-style adapter for tool registries that expect callables."""

    return RepoEditTool(repo_root=repo_root, sandbox_root=sandbox_root).run(payload).to_dict()
