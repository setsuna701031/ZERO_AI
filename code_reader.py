"""
code_reader.py

ZERO Code Context Reader v0.1.1

Purpose:
- Read code/text files safely before controlled editing.
- Provide exact current content so later controlled_replace can use the correct
  old_text instead of guessing.
- Keep this layer read-only.
- Support workspace/ by default.
- Support core/, services/, app.py only when explicitly allowed.

This is the first piece of READ -> THINK -> EDIT.

Examples:
python code_reader.py --path workspace/shared/sample_code.py
python code_reader.py --path core/repo_sandbox/tool.py --allow-core
python code_reader.py --path workspace/shared/sample_code.py --max-chars 4000 --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPO_ROOT = "."
DEFAULT_MAX_CHARS = 12000
CODE_READER_VERSION = "code_reader_v0_1_1"


TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".bat",
    ".ps1",
    ".sh",
    ".sql",
    ".xml",
}


@dataclass(frozen=True)
class CodeReadResult:
    ok: bool
    status: str
    path: str
    resolved_path: str
    repo_root: str
    content: str
    truncated: bool
    max_chars: int
    size_bytes: int
    sha256: str
    line_count: int
    error: str = ""
    version: str = CODE_READER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CodeReaderError(RuntimeError):
    pass


def _normalize_path(path: str) -> str:
    text = str(path or "").strip().strip("'\"`")
    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text.lstrip("./")


def _is_core_path(normalized_path: str) -> bool:
    return (
        normalized_path == "app.py"
        or normalized_path.startswith("core/")
        or normalized_path.startswith("services/")
        or normalized_path.startswith("tests/")
        or normalized_path.startswith("ui/")
    )


def _is_allowed_path(normalized_path: str, *, allow_core: bool) -> bool:
    if normalized_path.startswith("workspace/"):
        return True

    if allow_core and _is_core_path(normalized_path):
        return True

    return False


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def _resolve_safe_path(repo_root: str | Path, target_path: str, *, allow_core: bool) -> Path:
    root = Path(repo_root).resolve()
    normalized = _normalize_path(target_path)

    if not normalized:
        raise CodeReaderError("empty path")

    if normalized.startswith("/") or ".." in Path(normalized).parts:
        raise CodeReaderError("unsafe path")

    if not _is_allowed_path(normalized, allow_core=allow_core):
        if _is_core_path(normalized):
            raise CodeReaderError("core/services/tests/ui/app.py reads require --allow-core")
        raise CodeReaderError("only workspace/ paths are allowed by default")

    resolved = (root / normalized).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CodeReaderError("path escapes repo root") from exc

    return resolved


def read_code_file(
    path: str,
    *,
    repo_root: str | Path = DEFAULT_REPO_ROOT,
    max_chars: int = DEFAULT_MAX_CHARS,
    allow_core: bool = False,
    encoding: str = "utf-8",
) -> CodeReadResult:
    root = Path(repo_root).resolve()
    normalized = _normalize_path(path)

    try:
        resolved = _resolve_safe_path(root, normalized, allow_core=allow_core)

        if not resolved.exists():
            raise CodeReaderError("file does not exist")

        if not resolved.is_file():
            raise CodeReaderError("path is not a file")

        if not _is_text_file(resolved):
            raise CodeReaderError(f"unsupported file extension: {resolved.suffix}")

        raw = resolved.read_bytes()
        size_bytes = len(raw)
        sha256 = hashlib.sha256(raw).hexdigest()

        try:
            full_content = raw.decode(encoding)
        except UnicodeDecodeError:
            full_content = raw.decode(encoding, errors="replace")

        if max_chars <= 0:
            max_chars = DEFAULT_MAX_CHARS

        truncated = len(full_content) > max_chars
        content = full_content[:max_chars] if truncated else full_content
        line_count = full_content.count("\n") + (1 if full_content else 0)

        return CodeReadResult(
            ok=True,
            status="success",
            path=normalized,
            resolved_path=str(resolved),
            repo_root=str(root),
            content=content,
            truncated=truncated,
            max_chars=max_chars,
            size_bytes=size_bytes,
            sha256=sha256,
            line_count=line_count,
        )

    except Exception as exc:
        return CodeReadResult(
            ok=False,
            status="blocked" if isinstance(exc, CodeReaderError) else "failed",
            path=normalized,
            resolved_path="",
            repo_root=str(root),
            content="",
            truncated=False,
            max_chars=max_chars,
            size_bytes=0,
            sha256="",
            line_count=0,
            error=str(exc),
        )


def format_read_result(result: CodeReadResult) -> str:
    if not result.ok:
        return (
            "[CODE READER]\n"
            f"Status: {result.status}\n"
            f"Path: {result.path}\n"
            f"Error: {result.error}\n"
        )

    header = (
        "[CODE READER]\n"
        f"Status: {result.status}\n"
        f"Path: {result.path}\n"
        f"Resolved: {result.resolved_path}\n"
        f"Size: {result.size_bytes} bytes\n"
        f"Lines: {result.line_count}\n"
        f"SHA256: {result.sha256}\n"
        f"Truncated: {result.truncated}\n"
        "\n"
        "[CONTENT]\n"
    )
    suffix = ""
    if result.truncated:
        suffix = f"\n\n[TRUNCATED after {result.max_chars} chars]"
    return header + result.content + suffix


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ZERO safe code context reader")
    parser.add_argument("--path", required=True, help="Path to read, usually workspace/...")
    parser.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--allow-core", action="store_true")
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    result = read_code_file(
        args.path,
        repo_root=args.repo_root,
        max_chars=args.max_chars,
        allow_core=args.allow_core,
        encoding=args.encoding,
    )

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_read_result(result))

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
