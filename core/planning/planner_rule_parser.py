from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def extract_command(text: str) -> Optional[str]:
    lowered = str(text or "").lower().strip()
    if lowered.startswith(("python ", "python3 ", "cmd ", "powershell ", "py ")):
        return str(text or "").strip()
    return None


def extract_run_python_request(text: str) -> Optional[Dict[str, Any]]:
    stripped = str(text or "").strip()
    lowered = stripped.lower()

    file_path = extract_file_path(stripped)
    if not file_path or not file_path.lower().endswith(".py"):
        return None

    run_markers = [
        "run python file",
        "run python script",
        "run file",
        "execute python file",
        "execute python script",
        "execute file",
        "執行 python",
        "執行python",
        "執行檔案",
        "執行腳本",
        "跑 python",
        "跑python",
        "運行 python",
        "run ",
        "execute ",
    ]

    if any(marker in lowered for marker in run_markers):
        return {
            "type": "run_python",
            "path": file_path,
        }

    return None


def infer_path_scope(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip().lower()
    if normalized.startswith("workspace/shared/") or normalized.startswith("shared/"):
        return "shared"
    return "auto"


def has_verify_intent(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False

    lowered = stripped.lower()

    english_patterns = [
        r"^verify\b",
        r"^verifies\b",
        r"^verified\b",
        r"\bcheck that\b",
        r"\bchecks that\b",
        r"\bconfirm that\b",
        r"\bconfirms that\b",
        r"\bcheck whether\b",
        r"\bconfirm whether\b",
        r"\bfile exists\b",
        r"\bdoes not exist\b",
        r"\bcontains\b",
        r"\bequals\b",
        r"\bis exactly\b",
    ]
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in english_patterns):
        return True

    zh_markers = ["確認", "檢查", "驗證", "是否存在", "有沒有", "包含", "含有", "等於", "是否為", "是不是", "是否等於"]
    return any(marker in stripped for marker in zh_markers)


def extract_verify_request(text: str, last_path: Optional[str]) -> Optional[Dict[str, Any]]:
    stripped = str(text or "").strip()
    lowered = stripped.lower()

    if not has_verify_intent(stripped):
        return None

    path = extract_file_path(stripped) or last_path

    exists_patterns = [
        r"(?:^verify\b|\bverifies\b|\bverified\b|\bcheck that\b|\bchecks that\b|\bconfirm that\b|\bconfirms that\b)\s+(.+?)\s+exists\b",
        r"(?:^verify\b|\bverifies\b|\bverified\b|\bcheck that\b|\bchecks that\b|\bconfirm that\b|\bconfirms that\b)\s+(?:the\s+)?file\s+exists\b",
        r"(?:^verify\b|\bverifies\b|\bverified\b|\bcheck that\b|\bchecks that\b|\bconfirm that\b|\bconfirms that\b)\s+it\s+exists\b",
    ]
    for pattern in exists_patterns:
        if re.search(pattern, lowered, flags=re.IGNORECASE) and path:
            return {
                "type": "verify",
                "path": path,
                "scope": infer_path_scope(path),
                "exists": True,
            }

    not_exists_patterns = [
        r"(?:^verify\b|\bverifies\b|\bverified\b|\bcheck that\b|\bchecks that\b|\bconfirm that\b|\bconfirms that\b)\s+(.+?)\s+does not exist\b",
        r"(?:^verify\b|\bverifies\b|\bverified\b|\bcheck that\b|\bchecks that\b|\bconfirm that\b|\bconfirms that\b)\s+(?:the\s+)?file\s+does not exist\b",
        r"(?:^verify\b|\bverifies\b|\bverified\b|\bcheck that\b|\bchecks that\b|\bconfirm that\b|\bconfirms that\b)\s+it\s+does not exist\b",
    ]
    for pattern in not_exists_patterns:
        if re.search(pattern, lowered, flags=re.IGNORECASE) and path:
            return {
                "type": "verify",
                "path": path,
                "scope": infer_path_scope(path),
                "exists": False,
            }

    contains_match = re.search(r"(?:contains|contain)\s+(.+)$", stripped, flags=re.IGNORECASE)
    if contains_match and path:
        raw = strip_quotes(contains_match.group(1).strip())
        if raw:
            return {
                "type": "verify",
                "path": path,
                "scope": infer_path_scope(path),
                "contains": raw,
            }

    equals_match = re.search(r"(?:equals|equal to|is exactly)\s+(.+)$", stripped, flags=re.IGNORECASE)
    if equals_match and path:
        raw = strip_quotes(equals_match.group(1).strip())
        if raw:
            return {
                "type": "verify",
                "path": path,
                "scope": infer_path_scope(path),
                "equals": raw,
            }

    zh_exists = any(k in stripped for k in ["存在", "有沒有", "是否存在"])
    if zh_exists and path:
        return {
            "type": "verify",
            "path": path,
            "scope": infer_path_scope(path),
            "exists": True,
        }

    zh_contains_match = re.search(r"(?:包含|含有)\s+(.+)$", stripped)
    if zh_contains_match and path:
        raw = strip_quotes(zh_contains_match.group(1).strip())
        if raw:
            return {
                "type": "verify",
                "path": path,
                "scope": infer_path_scope(path),
                "contains": raw,
            }

    zh_equals_match = re.search(r"(?:等於|是否為|是不是|是否等於)\s+(.+)$", stripped)
    if zh_equals_match and path:
        raw = strip_quotes(zh_equals_match.group(1).strip())
        if raw:
            return {
                "type": "verify",
                "path": path,
                "scope": infer_path_scope(path),
                "equals": raw,
            }

    if path and re.search(r"(?:^verify\b|\bverifies\b|\bverified\b|\bcheck\b|\bconfirm\b)", lowered, flags=re.IGNORECASE):
        return {
            "type": "verify",
            "path": path,
            "scope": infer_path_scope(path),
            "exists": True,
        }

    return None


def extract_file_path(text: str) -> Optional[str]:
    if not text:
        return None

    patterns = [
        r"\b([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))\b",
    ]

    candidates: List[str] = []
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            value = str(m.group(1)).strip()
            if value:
                candidates.append(value)

    if not candidates:
        return None

    return candidates[0]


def looks_like_read(text: str) -> bool:
    lowered = str(text or "").lower()
    keywords = [
        "讀取",
        "讀出來",
        "讀一下",
        "查看",
        "read",
        "open",
        "看一下",
        "檢查",
        "打開",
        "顯示內容",
        "show content",
    ]
    return any(k in lowered for k in keywords)


def resolve_read_path(text: str, last_path: Optional[str]) -> Optional[str]:
    explicit_path = extract_file_path(text)
    if explicit_path:
        return explicit_path

    lowered = str(text or "").lower().strip()

    implicit_read_markers = [
        "再讀出來",
        "讀出來",
        "把它讀出來",
        "把他讀出來",
        "把檔案讀出來",
        "把那個讀出來",
        "再讀",
        "讀一下",
        "看一下",
        "打開它",
        "打開",
        "查看內容",
        "read it",
        "open it",
        "show it",
    ]

    if last_path and any(marker in lowered for marker in implicit_read_markers):
        return last_path

    if last_path and looks_like_read(text):
        return last_path

    return None


def extract_write_request(text: str) -> Optional[Dict[str, Any]]:
    stripped = str(text or "").strip()
    lowered = stripped.lower()

    if extract_run_python_request(stripped):
        return None

    has_write_intent = any(k in stripped for k in ["寫", "建立", "新增", "創建", "產生"]) or any(
        k in lowered for k in ["create", "write", "writes", "make", "generate"]
    )
    if not has_write_intent:
        return None

    normalized = re.sub(
        r"^(?:create\s+a\s+task\s+that\s+|create\s+task\s+that\s+|please\s+|pls\s+)",
        "",
        stripped,
        flags=re.IGNORECASE,
    ).strip()

    path = extract_file_path(normalized) or extract_file_path(stripped)
    if not path:
        return None

    content = ""
    has_explicit_content = False

    english_match = re.search(
        r"(?:write|writes)\s+(.+?)\s+to\s+([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if english_match:
        raw_content = english_match.group(1).strip()
        target_path = english_match.group(2).strip()
        if target_path:
            path = target_path
        if raw_content:
            content = normalize_special_content(strip_quotes(raw_content))
            has_explicit_content = True

    if not has_explicit_content:
        chinese_match = re.search(
            r"(?:寫入|寫|建立|新增|創建)\s+(.+?)\s+(?:到|進|至)\s+([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))\b",
            normalized,
            flags=re.IGNORECASE,
        )
        if chinese_match:
            raw_content = chinese_match.group(1).strip()
            target_path = chinese_match.group(2).strip()
            if target_path:
                path = target_path
            if raw_content:
                content = normalize_special_content(strip_quotes(raw_content))
                has_explicit_content = True

    if not has_explicit_content:
        content, has_explicit_content = extract_write_content(normalized)

    return {
        "path": path,
        "content": content,
        "has_explicit_content": has_explicit_content,
        "scope": infer_path_scope(path),
    }


def extract_write_content(text: str) -> Tuple[str, bool]:
    stripped = str(text or "").strip()

    patterns = [
        r"內容是\s*(.+)$",
        r"內容為\s*(.+)$",
        r"內容:\s*(.+)$",
        r"內容：\s*(.+)$",
        r"寫入\s*(.+)$",
        r"內容放\s*(.+)$",
        r"with content\s+(.+)$",
        r"content is\s+(.+)$",
        r"content:\s*(.+)$",
        r"寫成\s*(.+)$",
    ]

    for pattern in patterns:
        m = re.search(pattern, stripped, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            if raw:
                return normalize_special_content(strip_quotes(raw)), True

    file_path = extract_file_path(stripped)
    if file_path:
        idx = stripped.find(file_path)
        if idx >= 0:
            tail = stripped[idx + len(file_path):].strip()

            if tail:
                tail = re.sub(
                    r"^(內容是|內容為|內容|寫入|寫成)\s*",
                    "",
                    tail,
                    flags=re.IGNORECASE,
                ).strip()

                if tail:
                    return normalize_special_content(strip_quotes(tail)), True

    return "", False


def normalize_special_content(text: str) -> str:
    value = str(text or "").strip()

    special_map = {
        "今天日期": "{{CURRENT_DATE}}",
        "今日日期": "{{CURRENT_DATE}}",
        "今天的日期": "{{CURRENT_DATE}}",
        "today date": "{{CURRENT_DATE}}",
        "today's date": "{{CURRENT_DATE}}",
    }

    lowered = value.lower()
    for key, mapped in special_map.items():
        if lowered == key.lower():
            return mapped

    return value


def strip_quotes(text: str) -> str:
    value = str(text or "").strip()
    quote_pairs = {
        "'": "'",
        '"': '"',
        "「": "」",
        "“": "”",
    }

    if len(value) >= 2:
        first = value[0]
        last = value[-1]
        if first in quote_pairs and quote_pairs[first] == last:
            return value[1:-1].strip()

    return value


def looks_like_search(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(k in lowered for k in ["搜尋", "search", "查詢", "查找"])