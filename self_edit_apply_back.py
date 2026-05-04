#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO V Pack - Apply Back After Review

Place this file at:
    E:\zero_ai\self_edit_apply_back.py

Use only after inspecting:
    workspace/self_edit/review/changed_files.txt
    workspace/self_edit/review/diff.txt
    workspace/self_edit/persona_status.txt

Command:
    python self_edit_apply_back.py --confirm-reviewed
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict


SELF_EDIT_ROOT = Path("workspace") / "self_edit"
WORKCOPY_DIR = SELF_EDIT_ROOT / "zero_ai_workcopy"
REVIEW_DIR = SELF_EDIT_ROOT / "review"
MANIFEST_JSON = REVIEW_DIR / "manifest.json"
APPLY_RECORD_JSON = REVIEW_DIR / "apply_record.json"


def load_manifest() -> Dict[str, Any]:
    if not MANIFEST_JSON.exists():
        raise SystemExit("Missing review manifest. Run: python self_edit_zero.py package-review")
    return json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))


def safe_target(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        raise SystemExit(f"Refusing absolute path: {path_text}")
    if ".." in path.parts:
        raise SystemExit(f"Refusing parent traversal path: {path_text}")
    if path.parts and path.parts[0] == "workspace":
        raise SystemExit(f"Refusing to apply workspace-internal path: {path_text}")
    return path


def apply_back() -> None:
    manifest = load_manifest()
    files = manifest.get("files", [])
    if not files:
        print("No changes to apply.")
        return

    applied = []
    for item in files:
        rel = safe_target(str(item["path"]))
        status = item["status"]

        source = WORKCOPY_DIR / rel
        target = Path.cwd() / rel

        if status in {"added", "modified"}:
            if not source.exists():
                raise SystemExit(f"Missing workcopy source: {source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            applied.append({"path": rel.as_posix(), "status": status})

        elif status == "deleted":
            if target.exists():
                target.unlink()
            applied.append({"path": rel.as_posix(), "status": status})

        else:
            raise SystemExit(f"Unknown file status: {status}")

    APPLY_RECORD_JSON.write_text(
        json.dumps(
            {
                "applied": applied,
                "source_manifest": str(MANIFEST_JSON),
                "note": "Applied only after --confirm-reviewed gate.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Applied {len(applied)} reviewed changes.")
    print(f"Record: {APPLY_RECORD_JSON}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ZERO V Pack Apply Back")
    parser.add_argument("--confirm-reviewed", action="store_true")
    args = parser.parse_args()

    if not args.confirm_reviewed:
        raise SystemExit("Refusing to apply. Add --confirm-reviewed only after human review.")

    apply_back()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
