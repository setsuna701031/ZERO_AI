"""Controlled edit session for repo sandbox operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.runtime.execution_gateway import safe_subprocess_run

from .policy import RepoSandboxPolicy, PolicyViolation
from .sandbox import RepoSandbox, SandboxFile

EditFunction = Callable[[str], str]


@dataclass
class ControlledEditResult:
    selected_files: list[str]
    changed_files: list[str]
    reasons: dict[str, str]
    test_command: str | None
    test_allowed: bool
    test_result: str
    diff: str
    blocked_reason: str | None = None

    def to_report(self) -> str:
        lines: list[str] = []
        lines.append("[CONTROLLED EDIT RESULT]")
        lines.append(f"Selected files: {', '.join(self.selected_files) if self.selected_files else '(none)'}")
        lines.append(f"Changed files : {', '.join(self.changed_files) if self.changed_files else '(none)'}")
        lines.append("")
        lines.append("[REASONS]")
        if self.reasons:
            for path, reason in self.reasons.items():
                lines.append(f"- {path}: {reason}")
        else:
            lines.append("- (none)")
        lines.append("")
        lines.append("[TEST]")
        lines.append(f"Command: {self.test_command or '(not run)'}")
        lines.append(f"Allowed: {self.test_allowed}")
        if self.blocked_reason:
            lines.append(f"Blocked reason: {self.blocked_reason}")
        lines.append(self.test_result.rstrip() if self.test_result else "(no output)")
        lines.append("")
        lines.append("[DIFF]")
        lines.append(self.diff.rstrip() if self.diff else "(no changes)")
        return "\n".join(lines) + "\n"


@dataclass
class ControlledEditSession:
    repo_root: str | Path
    sandbox_root: str | Path = "workspace/repo_sandbox"
    policy: RepoSandboxPolicy = field(default_factory=RepoSandboxPolicy)

    def __post_init__(self) -> None:
        self.sandbox = RepoSandbox(
            self.repo_root,
            self.sandbox_root,
            policy=self.policy,
        )
        self._selected: list[SandboxFile] = []
        self._reasons: dict[str, str] = {}

    def prepare_files(self, relative_paths: list[str | Path]) -> list[SandboxFile]:
        self._selected = self.sandbox.prepare(relative_paths, reset=True)
        self._reasons = {item.display_path: "selected for controlled sandbox edit" for item in self._selected}
        return self._selected

    def edit_file(self, relative_path: str | Path, edit_fn: EditFunction, *, reason: str) -> None:
        current = self.sandbox.read_text(relative_path)
        updated = edit_fn(current)
        self.sandbox.write_text(relative_path, updated)
        safe_path = self.policy.normalize_relative_path(relative_path).as_posix()
        self._reasons[safe_path] = reason

    def replace_file_text(self, relative_path: str | Path, new_content: str, *, reason: str) -> None:
        self.sandbox.write_text(relative_path, new_content)
        safe_path = self.policy.normalize_relative_path(relative_path).as_posix()
        self._reasons[safe_path] = reason

    def run_test(self, command: str | list[str], *, timeout_seconds: int = 60) -> tuple[bool, str, str | None]:
        decision = self.policy.check_command(command)
        display_command = command if isinstance(command, str) else " ".join(command)
        if not decision.allowed:
            return False, f"BLOCKED: {decision.reason}\n", decision.reason

        completed = safe_subprocess_run(
            command,
            cwd=str(self.sandbox.worktree_root),
            shell=isinstance(command, str),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        if completed.get("returncode") is None and completed.get("error"):
            return True, f"TIMEOUT after {timeout_seconds}s: {display_command}\n", None

        output = []
        output.append(f"returncode: {completed.get('returncode')}")
        if completed.get("stdout"):
            output.append("stdout:")
            output.append(str(completed.get("stdout") or "").rstrip())
        if completed.get("stderr"):
            output.append("stderr:")
            output.append(str(completed.get("stderr") or "").rstrip())
        return True, "\n".join(output) + "\n", None

    def result(self, *, test_command: str | list[str] | None = None) -> ControlledEditResult:
        test_allowed = False
        test_output = "(test not requested)\n"
        blocked_reason: str | None = None
        display_command: str | None = None

        if test_command is not None:
            display_command = test_command if isinstance(test_command, str) else " ".join(test_command)
            test_allowed, test_output, blocked_reason = self.run_test(test_command)

        return ControlledEditResult(
            selected_files=[item.display_path for item in self._selected],
            changed_files=self.sandbox.changed_files(),
            reasons=dict(self._reasons),
            test_command=display_command,
            test_allowed=test_allowed,
            test_result=test_output,
            diff=self.sandbox.build_all_diffs(),
            blocked_reason=blocked_reason,
        )

    def require_prepared(self) -> None:
        if not self._selected:
            raise PolicyViolation("no files have been prepared for controlled edit")
