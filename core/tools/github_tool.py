from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from core.runtime.execution_gateway import safe_subprocess_run


class GitHubCommitTool:
    """
    Minimal local-git commit adapter for tool_call flows.

    This tool intentionally does not call the GitHub API, push, create branches,
    or run force operations. It writes the provided files, stages those exact
    paths, and creates one local commit.
    """

    name = "github_commit"

    def __init__(self, workspace_root: Any = "workspace") -> None:
        self.allowed_root = Path(workspace_root or "workspace").resolve(strict=False)
        self.allowed_root.mkdir(parents=True, exist_ok=True)

    def execute(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = tool_input if isinstance(tool_input, dict) else {}
        try:
            repo_path = self._resolve_repo_path(payload.get("repo_path"))
            message = str(payload.get("message") or "").strip()
            files = payload.get("files")

            if not message:
                return _failed("commit message is required", repo_path=repo_path)
            if not isinstance(files, list) or not files:
                return _failed("files must be a non-empty list", repo_path=repo_path)
            if not self._is_git_repo(repo_path):
                return _failed("repo_path is not a git repository", repo_path=repo_path)

            changed_files: List[str] = []
            relative_paths: List[str] = []
            for file_item in files:
                if not isinstance(file_item, dict):
                    return _failed("each file must be an object", repo_path=repo_path)
                if "content" not in file_item:
                    return _failed("file content is required", repo_path=repo_path)

                target = self._resolve_file_path(repo_path, file_item.get("path"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("" if file_item.get("content") is None else str(file_item.get("content")), encoding="utf-8")

                rel_path = target.relative_to(repo_path).as_posix()
                changed_files.append(str(target))
                relative_paths.append(rel_path)

            add_result = self._git(repo_path, ["add", "--", *relative_paths])
            if add_result.returncode != 0:
                return _failed(
                    "git add failed",
                    repo_path=repo_path,
                    changed_files=changed_files,
                    stdout=add_result.stdout,
                    stderr=add_result.stderr,
                )

            commit_result = self._git(
                repo_path,
                [
                    "-c",
                    "user.name=ZERO",
                    "-c",
                    "user.email=zero@example.invalid",
                    "commit",
                    "-m",
                    message,
                    "--",
                    *relative_paths,
                ],
            )
            if commit_result.returncode != 0:
                return _failed(
                    "git commit failed",
                    repo_path=repo_path,
                    changed_files=changed_files,
                    stdout=commit_result.stdout,
                    stderr=commit_result.stderr,
                )

            hash_result = self._git(repo_path, ["rev-parse", "HEAD"])
            if hash_result.returncode != 0:
                return _failed(
                    "git rev-parse failed",
                    repo_path=repo_path,
                    changed_files=changed_files,
                    stdout=hash_result.stdout,
                    stderr=hash_result.stderr,
                )

            commit_hash = str(hash_result.stdout or "").strip()
            return {
                "ok": True,
                "status": "success",
                "tool": self.name,
                "tool_class": "git_local",
                "side_effect_level": "repo_write",
                "repo_path": str(repo_path),
                "commit_hash": commit_hash,
                "changed_files": changed_files,
                "summary": f"created local git commit {commit_hash[:12]}",
                "error": None,
                "git_commit": True,
                "git_push": False,
                "github_create_pr": False,
            }
        except ValueError as exc:
            return _failed(str(exc), status="blocked")
        except Exception as exc:
            return _failed(str(exc))

    def run(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(tool_input)

    def invoke(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(tool_input)

    def _resolve_repo_path(self, repo_path: Any) -> Path:
        raw = str(repo_path or "").strip()
        if not raw:
            raise ValueError("repo_path is required")
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = self.allowed_root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise ValueError("repo_path is outside allowed directory") from exc
        return resolved

    def _resolve_file_path(self, repo_path: Path, file_path: Any) -> Path:
        raw = str(file_path or "").strip().replace("\\", "/").lstrip("/")
        if not raw:
            raise ValueError("file path is required")
        parts = [part for part in raw.split("/") if part]
        if any(part == ".." for part in parts):
            raise ValueError("parent traversal is not allowed")
        if any(part == ".git" for part in parts):
            raise ValueError("writing .git paths is not allowed")

        target = (repo_path / raw).resolve(strict=False)
        try:
            target.relative_to(repo_path)
        except ValueError as exc:
            raise ValueError("file path escapes repo_path") from exc
        return target

    def _is_git_repo(self, repo_path: Path) -> bool:
        result = self._git(repo_path, ["rev-parse", "--is-inside-work-tree"])
        return result.returncode == 0 and str(result.stdout or "").strip().lower() == "true"

    def _git(self, repo_path: Path, args: List[str]) -> SimpleNamespace:
        result = safe_subprocess_run(
            ["git", "-c", f"safe.directory={repo_path}", *args],
            cwd=str(repo_path),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        return SimpleNamespace(
            returncode=result.get("returncode"),
            stdout=result.get("stdout") or "",
            stderr=result.get("stderr") or "",
        )


def _failed(
    message: str,
    *,
    status: str = "failed",
    repo_path: Path | None = None,
    changed_files: List[str] | None = None,
    stdout: str = "",
    stderr: str = "",
) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "tool": GitHubCommitTool.name,
        "tool_class": "git_local",
        "side_effect_level": "none" if status == "blocked" else "repo_write",
        "repo_path": "" if repo_path is None else str(repo_path),
        "commit_hash": "",
        "changed_files": changed_files or [],
        "summary": "",
        "stdout": stdout,
        "stderr": stderr,
        "error": message,
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
