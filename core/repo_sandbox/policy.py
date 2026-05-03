"""Policy checks for ZERO repo sandbox operations.

The sandbox policy intentionally starts conservative:
- only explicit relative file paths are allowed;
- dangerous repository internals and secret-like files are blocked;
- test commands are allowlisted;
- destructive / network / package-management commands are blocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shlex


class PolicyViolation(ValueError):
    """Raised when a repo sandbox operation violates policy."""


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class RepoSandboxPolicy:
    """Conservative policy for controlled repo editing."""

    blocked_path_parts = {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }

    blocked_name_fragments = {
        ".env",
        "secret",
        "secrets",
        "token",
        "tokens",
        "apikey",
        "api_key",
        "private_key",
        "password",
        "passwd",
        "credential",
        "credentials",
    }

    safe_command_prefixes = (
        ("python", "-m", "pytest"),
        ("py", "-m", "pytest"),
        ("pytest",),
        ("typhon", "tests"),
        ("python", "tests"),
        ("python", "demos"),
        ("python", "scripts"),
        ("py", "tests"),
        ("py", "demos"),
        ("py", "scripts"),
    )

    blocked_command_tokens = {
        "rm",
        "del",
        "rmdir",
        "remove-item",
        "erase",
        "format",
        "git",
        "push",
        "merge",
        "rebase",
        "reset",
        "clean",
        "checkout",
        "pip",
        "install",
        "npm",
        "pnpm",
        "yarn",
        "curl",
        "wget",
        "ssh",
        "scp",
        "powershell",
        "cmd",
        "bash",
        "sh",
    }

    def normalize_relative_path(self, relative_path: str | Path) -> Path:
        raw = str(relative_path).replace("\\", "/").strip()
        if not raw:
            raise PolicyViolation("empty path is not allowed")

        pure = PurePosixPath(raw)
        if pure.is_absolute():
            raise PolicyViolation(f"absolute path is not allowed: {relative_path}")
        if any(part in ("", ".", "..") for part in pure.parts):
            raise PolicyViolation(f"path traversal is not allowed: {relative_path}")

        lowered_parts = [part.lower() for part in pure.parts]
        for part in lowered_parts:
            if part in self.blocked_path_parts:
                raise PolicyViolation(f"blocked path segment: {part}")

        lowered_name = pure.name.lower()
        for fragment in self.blocked_name_fragments:
            if fragment in lowered_name:
                raise PolicyViolation(f"blocked secret-like filename: {pure.name}")

        return Path(*pure.parts)

    def validate_repo_file(self, repo_root: str | Path, relative_path: str | Path) -> Path:
        safe_relative = self.normalize_relative_path(relative_path)
        root = Path(repo_root).resolve()
        candidate = (root / safe_relative).resolve()

        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PolicyViolation(f"path escapes repo root: {relative_path}") from exc

        if not candidate.exists():
            raise PolicyViolation(f"file does not exist: {safe_relative.as_posix()}")
        if not candidate.is_file():
            raise PolicyViolation(f"path is not a file: {safe_relative.as_posix()}")

        return safe_relative

    def check_command(self, command: str | list[str] | tuple[str, ...]) -> PolicyDecision:
        if isinstance(command, str):
            try:
                tokens = shlex.split(command, posix=False)
            except ValueError as exc:
                return PolicyDecision(False, f"cannot parse command: {exc}")
        else:
            tokens = [str(part) for part in command]

        if not tokens:
            return PolicyDecision(False, "empty command is not allowed")

        lowered = [token.lower() for token in tokens]
        for token in lowered:
            if token in self.blocked_command_tokens:
                return PolicyDecision(False, f"blocked command token: {token}")

        for prefix in self.safe_command_prefixes:
            if len(lowered) >= len(prefix) and tuple(lowered[: len(prefix)]) == prefix:
                return PolicyDecision(True, "command matches safe allowlist")

        if len(lowered) >= 2 and lowered[0] in {"python", "py"}:
            script = lowered[1].replace("\\", "/")
            if script.startswith(("tests/", "demos/", "scripts/")) and ".." not in script:
                return PolicyDecision(True, "python script is inside tests/demos/scripts")

        return PolicyDecision(False, "command is not in the safe allowlist")

    def require_command_allowed(self, command: str | list[str] | tuple[str, ...]) -> None:
        decision = self.check_command(command)
        if not decision.allowed:
            raise PolicyViolation(decision.reason)
