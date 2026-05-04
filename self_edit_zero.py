#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO Y Pack - Self Edit Workcopy Runner + Fixed Diff Engine

Place this file at:
    E:\zero_ai\self_edit_zero.py

Purpose:
- Copy live ZERO repo into workspace/self_edit/zero_ai_workcopy.
- Keep edits constrained to the workcopy.
- Produce complete review artifacts before anything is applied back.

Y Pack fixes:
- Detects added files correctly.
- Detects modified files correctly.
- Detects deleted files correctly.
- Handles Windows cp950/utf-8 diff issues.
- Writes robust manifest / changed_files / diff.
- Keeps workspace/self_edit excluded from live-side noise, but compares workcopy root correctly.
- Keeps Persona tool files in live root excluded from review noise.

Commands:
    python self_edit_zero.py prepare
    python self_edit_zero.py status
    python self_edit_zero.py diff
    python self_edit_zero.py package-review
    python self_edit_zero.py reset-workcopy
"""

from __future__ import annotations

import argparse
import datetime as _dt
import filecmp
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".test_tmp",
    "tmp",
    "temp",
    "logs",
    ".cache",
}

EXCLUDE_FILE_NAMES = {
    "persona_command_console.py",
    "persona_workcopy_executor.py",
}

EXCLUDE_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
}

SELF_EDIT_ROOT = Path("workspace") / "self_edit"
WORKCOPY_DIR = SELF_EDIT_ROOT / "zero_ai_workcopy"
REVIEW_DIR = SELF_EDIT_ROOT / "review"

STATUS_JSON = SELF_EDIT_ROOT / "persona_status.json"
STATUS_TXT = SELF_EDIT_ROOT / "persona_status.txt"
COPY_SKIPPED_JSON = REVIEW_DIR / "copy_skipped.json"
CHANGED_FILES_TXT = REVIEW_DIR / "changed_files.txt"
DIFF_TXT = REVIEW_DIR / "diff.txt"
MANIFEST_JSON = REVIEW_DIR / "manifest.json"
DIFF_SUMMARY_JSON = REVIEW_DIR / "diff_summary.json"


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def repo_root() -> Path:
    return Path.cwd().resolve()


def ensure_dirs() -> None:
    SELF_EDIT_ROOT.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_excluded_live(path: Path, root: Path) -> bool:
    """
    Exclusion rules for the live repo scan.

    Important:
    - Exclude workspace/self_edit entirely from live side.
      Otherwise review artifacts and workcopy internals pollute the live baseline.
    - Exclude root-level Persona helper scripts from review noise.
      These are control-plane files, not workcopy payload changes.
    """
    try:
        rel = relative_posix(path, root)
    except ValueError:
        return True

    parts = rel.split("/")

    if rel == "workspace/self_edit" or rel.startswith("workspace/self_edit/"):
        return True

    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True

    if path.name in EXCLUDE_FILE_NAMES:
        return True

    if path.is_file() and path.suffix.lower() in EXCLUDE_FILE_SUFFIXES:
        return True

    return False


def is_excluded_workcopy(path: Path, workcopy_root: Path) -> bool:
    """
    Exclusion rules for the workcopy scan.

    Important Y fix:
    - Do NOT exclude every workspace/self_edit path relative to workcopy blindly,
      because legitimate code may live under workcopy root.
    - Only exclude runtime self-edit internals under:
        workcopy/workspace/self_edit/zero_ai_workcopy
        workcopy/workspace/self_edit/review
        workcopy/workspace/self_edit/persona_inbox
        workcopy/workspace/self_edit/persona_outbox
        workcopy/workspace/self_edit/persona_execution
      This prevents recursive self-edit noise, but still detects root-level added files
      such as persona_status_bridge.py.
    """
    try:
        rel = relative_posix(path, workcopy_root)
    except ValueError:
        return True

    parts = rel.split("/")

    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True

    runtime_prefixes = (
        "workspace/self_edit/zero_ai_workcopy",
        "workspace/self_edit/review",
        "workspace/self_edit/persona_inbox",
        "workspace/self_edit/persona_outbox",
        "workspace/self_edit/persona_execution",
    )
    if rel == "workspace/self_edit" or any(rel == p or rel.startswith(p + "/") for p in runtime_prefixes):
        return True

    if path.name in EXCLUDE_FILE_NAMES:
        # Important: this only excludes control-plane files that were copied from live root.
        # If later a real project needs these files tracked, remove this from EXCLUDE_FILE_NAMES.
        return True

    if path.is_file() and path.suffix.lower() in EXCLUDE_FILE_SUFFIXES:
        return True

    return False


def write_status(phase: str, summary: str, extra: Optional[Dict[str, Any]] = None) -> None:
    ensure_dirs()

    payload: Dict[str, Any] = {
        "system": "ZERO",
        "package": "Y",
        "feature": "self_edit_workcopy_fixed_diff_engine",
        "phase": phase,
        "summary": summary,
        "generated_at": utc_now(),
        "paths": {
            "self_edit_root": str(SELF_EDIT_ROOT),
            "workcopy": str(WORKCOPY_DIR),
            "review_dir": str(REVIEW_DIR),
            "persona_status_json": str(STATUS_JSON),
            "persona_status_txt": str(STATUS_TXT),
            "copy_skipped_json": str(COPY_SKIPPED_JSON),
            "changed_files": str(CHANGED_FILES_TXT),
            "diff": str(DIFF_TXT),
            "manifest": str(MANIFEST_JSON),
            "diff_summary": str(DIFF_SUMMARY_JSON),
        },
        "policy": {
            "live_repo_write_allowed": False,
            "workcopy_write_allowed": True,
            "apply_back_requires_human_review": True,
        },
    }

    if extra:
        payload["details"] = extra

    STATUS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "[ZERO PERSONA STATUS]",
        "Package : Y",
        f"Phase   : {phase}",
        f"Time    : {payload['generated_at']}",
        "",
        summary,
        "",
        "[BOUNDARY]",
        f"Live repo write allowed : {payload['policy']['live_repo_write_allowed']}",
        f"Workcopy write allowed  : {payload['policy']['workcopy_write_allowed']}",
        f"Review before apply     : {payload['policy']['apply_back_requires_human_review']}",
    ]

    if extra:
        lines.append("")
        lines.append("[DETAILS]")
        for k, v in extra.items():
            lines.append(f"{k}: {v}")

    STATUS_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_status() -> None:
    if not STATUS_TXT.exists():
        write_status("unknown", "No self-edit action has been run yet.")
    print(STATUS_TXT.read_text(encoding="utf-8"))


def tolerant_copy_file(src: Path, dst: Path, skipped: List[Dict[str, str]]) -> None:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except Exception as exc:
        skipped.append(
            {
                "source": str(src),
                "target": str(dst),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )


def copy_repo_to_workcopy(force: bool = False) -> None:
    root = repo_root()
    ensure_dirs()

    if WORKCOPY_DIR.exists():
        if not force:
            raise SystemExit(
                f"Workcopy already exists: {WORKCOPY_DIR}\n"
                "Use: python self_edit_zero.py reset-workcopy"
            )
        shutil.rmtree(WORKCOPY_DIR, ignore_errors=True)

    skipped: List[Dict[str, str]] = []
    work_abs = (root / WORKCOPY_DIR).resolve()
    work_abs.mkdir(parents=True, exist_ok=True)

    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)

        kept_dirs: List[str] = []
        for dirname in dirnames:
            d = current_path / dirname
            if not is_excluded_live(d, root):
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in filenames:
            src = current_path / filename
            if is_excluded_live(src, root):
                continue

            try:
                rel = src.resolve().relative_to(root.resolve())
            except ValueError:
                continue

            dst = work_abs / rel
            tolerant_copy_file(src, dst, skipped)

    COPY_SKIPPED_JSON.write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "skipped_count": len(skipped),
                "skipped": skipped,
                "note": "Skipped files are usually locked runtime/temp/cache files. Review if this count is unexpectedly high.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    write_status(
        phase="prepared",
        summary="ZERO repo copied into isolated self-edit workcopy.",
        extra={
            "live_repo": str(root),
            "workcopy": str(work_abs),
            "copy_skipped_count": len(skipped),
            "copy_skipped_json": str(COPY_SKIPPED_JSON),
            "write_policy": "ZERO may edit workcopy only. Live repo must remain unchanged until review/apply.",
        },
    )


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def safe_sha256(path: Optional[Path]) -> Optional[str]:
    if path is None or not path.exists() or not path.is_file():
        return None

    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def collect_file_maps() -> Tuple[Dict[str, Path], Dict[str, Path]]:
    root = repo_root()
    work = root / WORKCOPY_DIR

    if not work.exists():
        raise SystemExit("Missing workcopy. Run: python self_edit_zero.py prepare")

    live_files: Dict[str, Path] = {}
    for p in iter_files(root):
        if is_excluded_live(p, root):
            continue
        live_files[relative_posix(p, root)] = p

    work_files: Dict[str, Path] = {}
    for p in iter_files(work):
        if is_excluded_workcopy(p, work):
            continue
        work_files[relative_posix(p, work)] = p

    return live_files, work_files


def files_equal(a: Path, b: Path) -> bool:
    try:
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def collect_changes() -> Tuple[List[str], Dict[str, Any], Dict[str, int]]:
    live_files, work_files = collect_file_maps()

    changed: List[str] = []
    manifest: Dict[str, Any] = {
        "generated_at": utc_now(),
        "live_repo": str(repo_root()),
        "workcopy": str((repo_root() / WORKCOPY_DIR).resolve()),
        "files": [],
    }
    counts = {"added": 0, "modified": 0, "deleted": 0}

    all_paths = sorted(set(live_files.keys()) | set(work_files.keys()))
    for name in all_paths:
        live_p = live_files.get(name)
        work_p = work_files.get(name)

        if live_p is None and work_p is not None:
            status = "added"
        elif live_p is not None and work_p is None:
            status = "deleted"
        elif live_p is not None and work_p is not None:
            if files_equal(live_p, work_p):
                continue
            status = "modified"
        else:
            continue

        changed.append(name)
        counts[status] += 1
        manifest["files"].append(
            {
                "path": name,
                "status": status,
                "live_exists": live_p is not None and live_p.exists(),
                "workcopy_exists": work_p is not None and work_p.exists(),
                "live_size": live_p.stat().st_size if live_p is not None and live_p.exists() else None,
                "workcopy_size": work_p.stat().st_size if work_p is not None and work_p.exists() else None,
                "live_sha256": safe_sha256(live_p),
                "workcopy_sha256": safe_sha256(work_p),
            }
        )

    manifest["summary"] = {
        "changed_file_count": len(changed),
        "added": counts["added"],
        "modified": counts["modified"],
        "deleted": counts["deleted"],
    }

    return changed, manifest, counts


def git_diff_no_index(left: str, right: str) -> str:
    cmd = ["git", "diff", "--no-index", "--", left, right]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception as exc:
        return f"### diff command failed\n{type(exc).__name__}: {exc}\n"

    if proc.returncode not in (0, 1):
        return "### diff failed\n" + (proc.stderr or "") + "\n"

    return proc.stdout or ""


def synthetic_added_diff(name: str, path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"diff --git a/{name} b/{name}\nnew file mode 100644\n--- /dev/null\n+++ b/{name}\n@@ read failed @@\n+{type(exc).__name__}: {exc}\n"

    lines = content.splitlines()
    out = [
        f"diff --git a/{name} b/{name}",
        "new file mode 100644",
        "--- /dev/null",
        f"+++ b/{name}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    out.extend("+" + line for line in lines)
    if content.endswith("\n"):
        return "\n".join(out) + "\n"
    return "\n".join(out) + "\n\\ No newline at end of file\n"


def synthetic_deleted_diff(name: str, path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"diff --git a/{name} b/{name}\ndeleted file mode 100644\n--- a/{name}\n+++ /dev/null\n@@ read failed @@\n-{type(exc).__name__}: {exc}\n"

    lines = content.splitlines()
    out = [
        f"diff --git a/{name} b/{name}",
        "deleted file mode 100644",
        f"--- a/{name}",
        "+++ /dev/null",
        f"@@ -1,{len(lines)} +0,0 @@",
    ]
    out.extend("-" + line for line in lines)
    if content.endswith("\n"):
        return "\n".join(out) + "\n"
    return "\n".join(out) + "\n\\ No newline at end of file\n"


def unified_diff_for_manifest_item(item: Dict[str, Any]) -> str:
    root = repo_root()
    name = item["path"]
    status = item["status"]
    live_p = root / name
    work_p = root / WORKCOPY_DIR / name

    if status == "added":
        if work_p.exists():
            # Synthetic diff is more reliable than git diff --no-index /dev/null on Windows.
            return synthetic_added_diff(name, work_p)
        return f"### added file missing in workcopy: {name}\n"

    if status == "deleted":
        if live_p.exists():
            return synthetic_deleted_diff(name, live_p)
        return f"### deleted file missing in live repo: {name}\n"

    if status == "modified":
        if live_p.exists() and work_p.exists():
            return git_diff_no_index(str(live_p), str(work_p))
        return f"### modified file missing endpoint: {name}\n"

    return f"### unknown diff status {status} for {name}\n"


def write_review_artifacts() -> None:
    ensure_dirs()
    changed, manifest, counts = collect_changes()

    CHANGED_FILES_TXT.write_text("\n".join(changed) + ("\n" if changed else ""), encoding="utf-8")
    MANIFEST_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    DIFF_SUMMARY_JSON.write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "changed_file_count": len(changed),
                "added": counts["added"],
                "modified": counts["modified"],
                "deleted": counts["deleted"],
                "files": [{"path": f["path"], "status": f["status"]} for f in manifest["files"]],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    diff_chunks: List[str] = []
    for item in manifest["files"]:
        chunk = unified_diff_for_manifest_item(item)
        diff_chunks.append(chunk if isinstance(chunk, str) else "")

    DIFF_TXT.write_text("\n".join(diff_chunks), encoding="utf-8")

    write_status(
        phase="review_ready",
        summary="Self-edit review artifacts generated.",
        extra={
            "changed_file_count": len(changed),
            "added": counts["added"],
            "modified": counts["modified"],
            "deleted": counts["deleted"],
            "changed_files": str(CHANGED_FILES_TXT),
            "diff": str(DIFF_TXT),
            "manifest": str(MANIFEST_JSON),
            "diff_summary": str(DIFF_SUMMARY_JSON),
            "next_gate": "Human review required before apply-back.",
        },
    )


def reset_workcopy() -> None:
    if WORKCOPY_DIR.exists():
        shutil.rmtree(WORKCOPY_DIR, ignore_errors=True)
    write_status("reset", "Self-edit workcopy removed. Live repo was not modified.")


def main() -> int:
    parser = argparse.ArgumentParser(description="ZERO Y Pack Self-Edit Workcopy Runner + Fixed Diff Engine")
    parser.add_argument(
        "command",
        choices=["prepare", "status", "diff", "package-review", "reset-workcopy"],
    )
    args = parser.parse_args()

    if args.command == "prepare":
        copy_repo_to_workcopy(force=False)
        print_status()
        return 0

    if args.command == "status":
        print_status()
        return 0

    if args.command in {"diff", "package-review"}:
        write_review_artifacts()
        print_status()
        return 0

    if args.command == "reset-workcopy":
        reset_workcopy()
        print_status()
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
