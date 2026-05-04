from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class CodeEditIntent:
    """
    Parsed code-edit intent for Code Chain v0.6.

    v0.6 rule:
    - Do not emit legacy executable mode="replace_text".
    - Emit mode="controlled_replace" so downstream execution uses backup,
      controlled replacement, and verification paths.

    Compatibility:
    - Keep old_text/new_text for older repo_edit_tool code.
    - Also expose old_line/new_line for controlled_replace code paths.
    """
    status: str
    file_path: str = ""
    mode: str = "controlled_replace"
    old_text: str = ""
    new_text: str = ""
    old_line: str = ""
    new_line: str = ""
    instruction: str = ""
    reason: str = ""


_WORKSPACE_PATH_PATTERN = re.compile(
    r"(workspace[/\\][A-Za-z0-9_.\- /\\]+?\.(?:py|md|txt|json|yaml|yml|toml|ini|cfg|html|css|js|ts|tsx|jsx|bat|ps1|sh))",
    re.IGNORECASE,
)


def _clean_quote(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"', "`"}:
        return text[1:-1]
    return text


def _normalize_path(path: str) -> str:
    text = str(path or "").strip().strip("'\"`.,;:")
    text = text.replace("\\", "/")
    text = re.sub(r"/+", "/", text)
    text = text.lstrip("./")
    return text


def _is_allowed_workspace_path(path: str) -> bool:
    normalized = _normalize_path(path)
    return normalized.startswith("workspace/")


def _extract_file_path(task_text: str) -> str:
    """
    Extract only the workspace/... path.

    Important bug fix:
    Older extraction could capture the leading verb, producing:
        "Modify workspace/shared/sample_code.py"
    This function must return:
        "workspace/shared/sample_code.py"
    """
    text = str(task_text or "")
    match = _WORKSPACE_PATH_PATTERN.search(text)
    if not match:
        return ""

    path = match.group(1)
    return _normalize_path(path)


def _extract_quoted_pairs(task_text: str) -> tuple[str, str]:
    """
    Extract old/new replacement text from common forms:

    - replace 'old' with 'new'
    - change "old" to "new"
    - from `old` to `new`
    - 把 'old' 改成 'new'
    """
    text = str(task_text or "")

    patterns = [
        r"(?:replace|change|modify|update)\s+(['\"`])(?P<old>.*?)\1\s+(?:with|to)\s+(['\"`])(?P<new>.*?)\3",
        r"(?:from)\s+(['\"`])(?P<old>.*?)\1\s+(?:to)\s+(['\"`])(?P<new>.*?)\3",
        r"(?:把|將)\s*(['\"`])(?P<old>.*?)\1\s*(?:改成|替換成|換成|變成)\s*(['\"`])(?P<new>.*?)\3",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return _clean_quote(match.group("old")), _clean_quote(match.group("new"))

    quoted = re.findall(r"(['\"`])((?:(?!\1).)*?)\1", text, flags=re.DOTALL)
    values = [item[1] for item in quoted if len(item) >= 2]
    if len(values) >= 2:
        return _clean_quote(values[0]), _clean_quote(values[1])

    return "", ""


def _infer_comment_new_line(task_text: str, old_text: str, new_text: str) -> str:
    """
    If the task asks to add a comment but does not provide exact comment text,
    use a small safe Python comment for return-line edits.

    This keeps v0.6 as a single controlled replacement:
        old_line -> comment + new_line
    """
    text = str(task_text or "").lower()
    if not old_text or not new_text:
        return new_text

    wants_comment = (
        "add a comment" in text
        or "add comment" in text
        or "comment above" in text
        or "加入註解" in text
        or "加註解" in text
    )
    if not wants_comment:
        return new_text

    stripped_old = old_text.strip()
    stripped_new = new_text.strip()
    if stripped_old.startswith("return ") and stripped_new.startswith("return "):
        return "# Explicit addition for clarity\n" + new_text

    return new_text


def parse_code_edit_intent(task_text: str) -> CodeEditIntent:
    """
    Parse a natural-language repo edit request into a controlled_replace intent.

    Valid result:
        status="ready"
        mode="controlled_replace"
        file_path starts with workspace/
        old_line/new_line populated
    """
    text = str(task_text or "").strip()
    if not text:
        return CodeEditIntent(
            status="blocked",
            reason="empty task text",
            instruction=text,
        )

    file_path = _extract_file_path(text)
    if not file_path:
        return CodeEditIntent(
            status="blocked",
            reason="no explicit workspace file path found",
            instruction=text,
        )

    if not _is_allowed_workspace_path(file_path):
        return CodeEditIntent(
            status="blocked",
            file_path=file_path,
            reason="only workspace/ paths are allowed for natural-language repo edit intent",
            instruction=text,
        )

    old_text, new_text = _extract_quoted_pairs(text)
    if not old_text or not new_text:
        return CodeEditIntent(
            status="blocked",
            file_path=file_path,
            reason="missing old_text/new_text replacement pair",
            instruction=text,
        )

    final_new_text = _infer_comment_new_line(text, old_text, new_text)

    return CodeEditIntent(
        status="ready",
        file_path=file_path,
        mode="controlled_replace",
        old_text=old_text,
        new_text=final_new_text,
        old_line=old_text,
        new_line=final_new_text,
        instruction=text,
        reason="safe single-file workspace controlled_replace intent",
    )


def build_repo_edit_payload(intent: CodeEditIntent) -> Dict[str, Any]:
    """
    Build repo_edit_tool payload.

    Always forces v0.6 controlled_replace mode while preserving legacy aliases.
    """
    if not isinstance(intent, CodeEditIntent):
        return {
            "status": "blocked",
            "mode": "controlled_replace",
            "operation": "controlled_replace",
            "type": "controlled_replace",
            "reason": "invalid CodeEditIntent",
            "controlled_replace": True,
            "controlled_replace_ready": False,
            "code_chain_version": "v0.6",
        }

    payload = asdict(intent)

    payload["mode"] = "controlled_replace"
    payload["operation"] = "controlled_replace"
    payload["type"] = "controlled_replace"

    payload["path"] = intent.file_path
    payload["target_path"] = intent.file_path
    payload["file"] = intent.file_path

    payload["old_line"] = intent.old_line or intent.old_text
    payload["new_line"] = intent.new_line or intent.new_text
    payload["old_text"] = intent.old_text or intent.old_line
    payload["new_text"] = intent.new_text or intent.new_line

    payload["controlled_replace"] = True
    payload["controlled_replace_ready"] = intent.status == "ready"
    payload["code_chain_version"] = "v0.6"

    return payload


__all__ = [
    "CodeEditIntent",
    "parse_code_edit_intent",
    "build_repo_edit_payload",
]
