from __future__ import annotations

import argparse
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = REPO_ROOT / "workspace"
INBOX_DIR = WORKSPACE_DIR / "inbox"
SHARED_DIR = WORKSPACE_DIR / "shared"


MAX_PREVIEW_CHARS = 4000


@dataclass(frozen=True)
class InboxFile:
    name: str
    path: Path
    size: int
    modified: float


def _ensure_inbox() -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> Optional[str]:
    text = (name or "").strip().replace("\\", "/")
    if not text:
        return None
    if "/" in text:
        return None
    if text in {".", ".."}:
        return None
    return text


def _safe_inbox_path(name: str) -> Optional[Path]:
    safe_name = _safe_filename(name)
    if safe_name is None:
        return None

    path = INBOX_DIR / safe_name

    try:
        resolved = path.resolve()
        inbox_resolved = INBOX_DIR.resolve()
    except Exception:
        return None

    if inbox_resolved not in resolved.parents and resolved != inbox_resolved:
        return None

    return path


def _read_text(path: Path, max_chars: int = MAX_PREVIEW_CHARS) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n[truncated: showing first {max_chars} characters]"
    return text


def _list_inbox_files(limit: int = 50) -> list[InboxFile]:
    _ensure_inbox()

    files = [p for p in INBOX_DIR.iterdir() if p.is_file()]
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    result: list[InboxFile] = []
    for path in files[:limit]:
        stat = path.stat()
        result.append(
            InboxFile(
                name=path.name,
                path=path,
                size=stat.st_size,
                modified=stat.st_mtime,
            )
        )
    return result


def _normalize_stem(filename: str) -> str:
    stem = Path(filename).stem.strip().lower()
    stem = re.sub(r"[^a-z0-9_]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")
    return stem or "inbox_item"


def _looks_like_requirement(text: str, filename: str) -> bool:
    lower = f"{filename}\n{text}".lower()
    markers = [
        "requirement",
        "requirements",
        "acceptance criteria",
        "implementation plan",
        "project summary",
        "build a",
        "create a",
        "must support",
        "should support",
    ]
    return any(marker in lower for marker in markers)


def _looks_like_action_items(text: str, filename: str) -> bool:
    lower = f"{filename}\n{text}".lower()
    markers = [
        "action item",
        "action items",
        "todo",
        "to-do",
        "owner",
        "due",
        "meeting notes",
        "follow up",
        "next step",
    ]
    return any(marker in lower for marker in markers)


def _build_summary_goal(inbox_file: InboxFile) -> str:
    stem = _normalize_stem(inbox_file.name)
    source = f"workspace/inbox/{inbox_file.name}"
    output = f"workspace/shared/{stem}_summary.txt"
    return f"summarize {source} into {output}"


def _build_action_items_goal(inbox_file: InboxFile) -> str:
    stem = _normalize_stem(inbox_file.name)
    source = f"workspace/inbox/{inbox_file.name}"
    output = f"workspace/shared/{stem}_action_items.txt"
    return f"read {source} and extract action items into {output}"


def _build_requirement_goal(inbox_file: InboxFile) -> str:
    source = f"workspace/inbox/{inbox_file.name}"
    return (
        f"read {source} and produce project_summary.txt, "
        "implementation_plan.txt, and acceptance_checklist.txt"
    )


def _suggest_goal(inbox_file: InboxFile, content: str, mode: str) -> tuple[str, str]:
    normalized_mode = (mode or "auto").strip().lower()

    if normalized_mode == "summary":
        return "summary", _build_summary_goal(inbox_file)

    if normalized_mode in {"action", "actions", "action-items", "action_items"}:
        return "action_items", _build_action_items_goal(inbox_file)

    if normalized_mode in {"requirement", "requirements", "requirement-pack", "requirement_pack"}:
        return "requirement", _build_requirement_goal(inbox_file)

    if _looks_like_requirement(content, inbox_file.name):
        return "requirement", _build_requirement_goal(inbox_file)

    if _looks_like_action_items(content, inbox_file.name):
        return "action_items", _build_action_items_goal(inbox_file)

    return "summary", _build_summary_goal(inbox_file)


def _print_inbox_list(limit: int) -> int:
    files = _list_inbox_files(limit=limit)

    print("[INBOX]")
    print(f"path: {INBOX_DIR}")
    print("")

    if not files:
        print("No inbox files found.")
        print("")
        print("You can create one from the Web UI with:")
        print("  drop hello from web ui")
        print("  drop-as demo_input.txt this is a test input")
        return 0

    for item in files:
        print(f"- {item.name}")
        print(f"  size : {item.size} bytes")
        print(f"  path : {item.path}")
        print(f"  read : python tools/inbox_draft.py read {item.name}")
        print(f"  draft: python tools/inbox_draft.py draft {item.name}")
        print("")

    return 0


def _print_inbox_read(filename: str) -> int:
    path = _safe_inbox_path(filename)
    if path is None:
        print(f"[ERROR] Invalid inbox filename: {filename}")
        return 2

    if not path.exists() or not path.is_file():
        print(f"[ERROR] Inbox file not found: {filename}")
        return 2

    content = _read_text(path)

    print("[INBOX FILE]")
    print(f"name: {path.name}")
    print(f"path: {path}")
    print(f"size: {path.stat().st_size} bytes")
    print("")
    print("[CONTENT]")
    print(content)

    return 0


def _print_task_draft(filename: str, mode: str) -> int:
    path = _safe_inbox_path(filename)
    if path is None:
        print(f"[ERROR] Invalid inbox filename: {filename}")
        return 2

    if not path.exists() or not path.is_file():
        print(f"[ERROR] Inbox file not found: {filename}")
        return 2

    inbox_file = InboxFile(
        name=path.name,
        path=path,
        size=path.stat().st_size,
        modified=path.stat().st_mtime,
    )
    content = _read_text(path)
    draft_mode, suggested_goal = _suggest_goal(inbox_file, content, mode=mode)

    print("[TASK DRAFT]")
    print(f"source_file: workspace/inbox/{inbox_file.name}")
    print(f"source_path: {inbox_file.path}")
    print(f"size       : {inbox_file.size} bytes")
    print(f"mode       : {draft_mode}")
    print("")
    print("[SUGGESTED GOAL]")
    print(suggested_goal)
    print("")
    print("[SAFE NEXT STEP]")
    print("Review the goal above first. If it is correct, create the task manually:")
    print("")
    print(f'python app.py task create "{suggested_goal}"')
    print("")
    print("This tool does not create, submit, run, or execute the task.")
    print("")
    print("[PREVIEW]")
    print(content)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inbox_draft.py",
        description="Read workspace/inbox and generate safe task draft suggestions without executing tasks.",
    )

    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List workspace/inbox files.")
    list_parser.add_argument("--limit", type=int, default=50)

    read_parser = subparsers.add_parser("read", help="Read one workspace/inbox file.")
    read_parser.add_argument("filename")

    draft_parser = subparsers.add_parser("draft", help="Generate a safe task draft from one inbox file.")
    draft_parser.add_argument("filename")
    draft_parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "summary", "action_items", "action-items", "requirement", "requirement-pack"],
        help="Draft mode. Default: auto.",
    )

    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "list":
        return _print_inbox_list(limit=max(1, int(args.limit)))

    if args.command == "read":
        return _print_inbox_read(args.filename)

    if args.command == "draft":
        return _print_task_draft(args.filename, mode=args.mode)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
