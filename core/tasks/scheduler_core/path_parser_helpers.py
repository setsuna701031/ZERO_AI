from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple


# Extracted from core/tasks/scheduler.py as path/text parser helpers.
# This module must remain free of Scheduler state, queue mutation,
# execution dispatch, transaction, verify, rollback, and persistence side effects.


def _extract_python_file_paths(text: str) -> List[str]:
    results: List[str] = []
    pattern = '\\b([A-Za-z0-9_\\-./\\\\]+?\\.py)\\b'
    for match in re.finditer(pattern, str(text or '')):
        value = str(match.group(1)).strip().replace('\\', '/')
        if value and value not in results:
            results.append(value)
    return results

def _is_shared_like_path(path: str) -> bool:
    normalized = str(path or '').replace('\\', '/').lstrip('./')
    return normalized.startswith('workspace/shared/') or normalized.startswith('shared/')

def _strip_markdown_code_fences(content: str) -> str:
    text = str(content or '')
    stripped = text.strip()
    if not stripped.startswith('```'):
        return text
    lines = text.splitlines(keepends=True)
    if not lines:
        return text
    first = lines[0].strip().lower()
    if first.startswith('```'):
        lines = lines[1:]
    if lines and lines[-1].strip() == '```':
        lines = lines[:-1]
    return ''.join(lines)

def _extract_all_document_file_paths(text: str) -> List[str]:
    if not text:
        return []
    results: List[str] = []
    pattern = '\\b([A-Za-z0-9_\\-./\\\\]+?\\.(?:txt|md|log|json|csv|yaml|yml))\\b'
    for match in re.finditer(pattern, text):
        value = str(match.group(1)).strip()
        if value and value not in results:
            results.append(value)
    return results

def _extract_document_arrow_paths(text: str) -> Optional[Tuple[str, str]]:
    stripped = str(text or '').strip()
    if not stripped:
        return None
    match = re.search('([A-Za-z0-9_\\-./\\\\]+?\\.(?:txt|md|log|json|csv|yaml|yml))\\s*->\\s*([A-Za-z0-9_\\-./\\\\]+?\\.(?:txt|md|log|json|csv|yaml|yml))', stripped, flags=re.IGNORECASE)
    if not match:
        return None
    source_path = str(match.group(1)).strip()
    output_path = str(match.group(2)).strip()
    if not source_path or not output_path:
        return None
    return (source_path, output_path)

