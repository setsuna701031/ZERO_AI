"""Filesystem sandbox for controlled repository edits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .diff import build_unified_diff
from .policy import RepoSandboxPolicy, PolicyViolation


@dataclass(frozen=True)
class SandboxFile:
    relative_path: Path
    repo_path: Path
    original_path: Path
    sandbox_path: Path

    @property
    def display_path(self) -> str:
        return self.relative_path.as_posix()


class RepoSandbox:
    """Copies explicit repo files into a sandbox and compares changes there."""

    def __init__(
        self,
        repo_root: str | Path,
        sandbox_root: str | Path = "workspace/repo_sandbox",
        *,
        policy: RepoSandboxPolicy | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.sandbox_root = Path(sandbox_root)
        if not self.sandbox_root.is_absolute():
            self.sandbox_root = (self.repo_root / self.sandbox_root).resolve()
        else:
            self.sandbox_root = self.sandbox_root.resolve()

        self.original_root = self.sandbox_root / "original"
        self.worktree_root = self.sandbox_root / "worktree"
        self.policy = policy or RepoSandboxPolicy()
        self._files: dict[str, SandboxFile] = {}

    def reset(self) -> None:
        if self.sandbox_root.exists():
            shutil.rmtree(self.sandbox_root)
        self.original_root.mkdir(parents=True, exist_ok=True)
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        self._files.clear()

    def prepare(self, relative_paths: list[str | Path], *, reset: bool = True) -> list[SandboxFile]:
        if reset:
            self.reset()
        else:
            self.original_root.mkdir(parents=True, exist_ok=True)
            self.worktree_root.mkdir(parents=True, exist_ok=True)

        prepared: list[SandboxFile] = []
        seen: set[str] = set()
        for item in relative_paths:
            safe_relative = self.policy.validate_repo_file(self.repo_root, item)
            key = safe_relative.as_posix()
            if key in seen:
                continue
            seen.add(key)

            repo_path = self.repo_root / safe_relative
            original_path = self.original_root / safe_relative
            sandbox_path = self.worktree_root / safe_relative

            original_path.parent.mkdir(parents=True, exist_ok=True)
            sandbox_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_path, original_path)
            shutil.copy2(repo_path, sandbox_path)

            sandbox_file = SandboxFile(
                relative_path=safe_relative,
                repo_path=repo_path,
                original_path=original_path,
                sandbox_path=sandbox_path,
            )
            self._files[key] = sandbox_file
            prepared.append(sandbox_file)

        return prepared

    def get_file(self, relative_path: str | Path) -> SandboxFile:
        safe_relative = self.policy.normalize_relative_path(relative_path)
        key = safe_relative.as_posix()
        try:
            return self._files[key]
        except KeyError as exc:
            raise PolicyViolation(f"file was not prepared in sandbox: {key}") from exc

    def read_text(self, relative_path: str | Path) -> str:
        sandbox_file = self.get_file(relative_path)
        return sandbox_file.sandbox_path.read_text(encoding="utf-8", errors="replace")

    def write_text(self, relative_path: str | Path, content: str) -> SandboxFile:
        sandbox_file = self.get_file(relative_path)
        sandbox_file.sandbox_path.write_text(content, encoding="utf-8")
        return sandbox_file

    def build_diff(self, relative_path: str | Path) -> str:
        sandbox_file = self.get_file(relative_path)
        return build_unified_diff(
            sandbox_file.original_path,
            sandbox_file.sandbox_path,
            sandbox_file.relative_path,
        )

    def build_all_diffs(self) -> str:
        diffs: list[str] = []
        for key in sorted(self._files):
            diff = self.build_diff(key)
            if diff.strip():
                diffs.append(diff)
        return "\n".join(diffs)

    def changed_files(self) -> list[str]:
        changed: list[str] = []
        for key, sandbox_file in sorted(self._files.items()):
            original = sandbox_file.original_path.read_bytes()
            edited = sandbox_file.sandbox_path.read_bytes()
            if original != edited:
                changed.append(key)
        return changed
