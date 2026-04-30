from __future__ import annotations

from typing import Any, Dict


TITLE_BODY_KEYS = {"title", "body"}


def format_title_body_message(*, title: str, body: str) -> str:
    clean_title = str(title or "").strip()
    clean_body = str(body or "").strip()
    if clean_title and clean_body:
        return f"{clean_title}\n\n{clean_body}"
    return clean_title or clean_body


def build_title_body_payload(*, output_schema: str, title: str, body: str) -> Dict[str, Any]:
    clean_title = str(title or "").strip()
    clean_body = str(body or "").strip()
    return {
        "output_schema": str(output_schema or "").strip(),
        "output": {
            "title": clean_title,
            "body": clean_body,
        },
        "title": clean_title,
        "body": clean_body,
        "message": format_title_body_message(title=clean_title, body=clean_body),
    }
