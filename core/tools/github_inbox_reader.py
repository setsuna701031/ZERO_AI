from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}


def read_inbox(workspace_root: Any | None = None) -> Dict[str, Any]:
    root = _root(workspace_root)
    inbox = root / "workspace" / "github_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / ".gitkeep").touch()

    files: List[Dict[str, Any]] = []
    content_parts: List[str] = []
    raw_parts: List[str] = []

    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        text = _read_supported_file(path)
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
            }
        )
        content_parts.append(f"[{path.name}]\n{text}")
        raw_parts.append(text)

    content = "\n\n".join(content_parts).strip()
    raw_content = "\n\n".join(raw_parts).strip()
    return {
        "files": files,
        "content": content,
        "type": detect_type(raw_content),
    }


def detect_type(content: str) -> str:
    text = str(content or "").lower()
    if "pull request" in text or _contains_pr_token(text):
        return "pr"
    if "diff" in text or "---" in content or "+++" in content:
        return "diff"
    if "issue" in text:
        return "issue"
    return "unknown"


def _read_supported_file(path: Path) -> str:
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            return path.read_text(encoding="utf-8-sig", errors="replace")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _contains_pr_token(text: str) -> bool:
    return any(token == "pr" for token in text.replace("/", " ").replace("-", " ").split())


def _root(workspace_root: Any | None) -> Path:
    if workspace_root is None:
        return REPO_ROOT
    root = Path(workspace_root).resolve(strict=False)
    if root.name == "workspace":
        return root.parent
    return root
