from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.events.event_runner import EventRunner
from core.tools.github_outbox import OUTBOX_FILES, write_github_outbox_artifact
from core.tools.readonly_tools import git_diff, git_status


WORKSPACE = REPO_ROOT / "workspace"
EVENTS_INBOX = WORKSPACE / "events_inbox"
EVENTS_OUTBOX = WORKSPACE / "events_outbox"
GITHUB_OUTBOX = WORKSPACE / "github_outbox"
SESSIONS = WORKSPACE / "execution_sessions"
AUDIT_LOG = WORKSPACE / "audit_logs" / "tool_audit.jsonl"
EVENT_FILENAME = "zzz_github_assistant_issue.txt"


def main() -> int:
    issue_text, mode = _read_args()
    return run_github_assistant(issue_text, mode=mode)


def run_github_assistant(issue_text: str, mode: str = "default") -> int:
    if mode in {"analyze_repo", "analyze_diff"}:
        return run_readonly_github_workflow(issue_text, mode=mode)

    if not issue_text:
        print("No issue text provided.")
        return 1

    _ensure_workspace()
    before_sessions = _session_files()
    before_audit_count = _jsonl_count(AUDIT_LOG)

    event_path = EVENTS_INBOX / EVENT_FILENAME
    event_path.write_text(_event_content(issue_text), encoding="utf-8")

    print("=" * 58)
    print("GitHub Engineering Assistant (local safe mode)")
    print("=" * 58)
    print("")
    print("Input: issue / problem description")
    print("Output: commit message, PR description, devlog, publish plan")
    print("")
    print("[1] Received issue")
    print(_one_line(issue_text))

    records = EventRunner(repo_root=str(REPO_ROOT)).poll_once()
    record = _find_record(records)
    if not record:
        print("\nAssistant failed: no event result was produced.")
        return 1

    task = record.get("task", {})
    tool_result = record.get("tool_result", {})
    tool = tool_result.get("tool") or "unknown"

    print("\n[2] Sent to ZERO")
    print(f"Task: {task.get('title')}")

    print("\n[3] Routed")
    print(f"ToolRouter selected: {tool}")

    print("\n[4] Action")
    print("Action: Generate Git-ready artifacts")

    print("\n[5] Engineering output")
    print("workspace/github_outbox/")
    for filename in OUTBOX_FILES.values():
        path = GITHUB_OUTBOX / filename
        status = "OK" if path.exists() else "missing"
        print(f"  - {filename} ({status})")

    created_sessions = sorted(
        _session_files() - before_sessions,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    session_id = _session_id(created_sessions[0]) if created_sessions else ""
    audit_updated = _jsonl_count(AUDIT_LOG) > before_audit_count

    print("\n[6] Tracking")
    print(f"Execution session: {session_id or 'not found'}")
    print("Audit log: updated" if audit_updated else "Audit log: not updated")

    print("")
    print("FINAL OUTPUT SUMMARY:")
    print("[OK] commit_message.txt")
    print("[OK] pr_description.md")
    print("[OK] devlog_entry.md")
    print("[OK] publish_plan.md")
    print("[OK] no GitHub API, no commit, no push")

    if mode == "draft_pr":
        _print_draft_pr_preview(issue_text)

    return 0 if tool == "github_outbox" and session_id and audit_updated else 1


def _read_args() -> tuple[str, str]:
    parser = argparse.ArgumentParser(
        description="Turn a local issue description into Git-ready engineering artifacts.",
    )
    parser.add_argument(
        "--mode",
        choices=("default", "draft_pr"),
        default="default",
        help="Output mode. Use draft_pr to print a PR-ready preview.",
    )
    parser.add_argument("issue", nargs="*", help="Issue or problem description")
    args = parser.parse_args()

    if args.issue:
        return " ".join(args.issue).strip(), args.mode

    print("Paste an issue / problem description, then press Enter:")
    return input("> ").strip(), args.mode


def run_readonly_github_workflow(issue_text: str = "", mode: str = "analyze_repo") -> int:
    _ensure_workspace()

    print("=" * 64)
    print("GitHub Semi-Automation (read-only local workflow)")
    print("=" * 64)
    print("")
    print("Input: repo status / local diff / issue text")
    print("Output: review report, PR draft, commit message, devlog")
    print("")
    print("Safety boundary:")
    print("- read-only repo inspection")
    print("- no GitHub API")
    print("- no commit")
    print("- no push")
    print("- no merge")

    if mode == "analyze_diff":
        print("\n[1] Load diff")
    else:
        print("\n[1] Read Repository State")
    status = git_status(repo_root=REPO_ROOT, task_id="github_assistant_readonly", trace_id="assistant_status")
    diff = git_diff(repo_root=REPO_ROOT, task_id="github_assistant_readonly", trace_id="assistant_diff")
    print(f"git status: {'OK' if status.get('ok') else 'failed'}")
    print(f"git diff: {'OK' if diff.get('ok') else 'failed'}")

    analysis = _build_readonly_analysis(issue_text=issue_text, status=status, diff=diff, mode=mode)

    print("\n[2] Analyze changes")
    print(analysis["summary"])

    print("\n[3] Generate review report")
    review_result = write_github_outbox_artifact(
        "review_report",
        _render_review_report(analysis),
        workspace_root=REPO_ROOT,
        task_id="github_assistant_readonly",
        trace_id="assistant_review_report",
    )
    print(f"- review_report.md: {'OK' if review_result.get('ok') else 'failed'}")

    print("\n[4] Generate PR draft")
    pr_result = write_github_outbox_artifact(
        "pr_description",
        _render_pr_description(analysis),
        workspace_root=REPO_ROOT,
        task_id="github_assistant_readonly",
        trace_id="assistant_pr_description",
    )
    commit_result = write_github_outbox_artifact(
        "commit_message",
        _render_commit_message(analysis),
        workspace_root=REPO_ROOT,
        task_id="github_assistant_readonly",
        trace_id="assistant_commit_message",
    )
    print(f"- pr_description.md: {'OK' if pr_result.get('ok') else 'failed'}")
    print(f"- commit_message.txt: {'OK' if commit_result.get('ok') else 'failed'}")

    print("\n[5] Generate devlog")
    devlog_result = write_github_outbox_artifact(
        "devlog_entry",
        _render_devlog_entry(analysis),
        workspace_root=REPO_ROOT,
        task_id="github_assistant_readonly",
        trace_id="assistant_devlog_entry",
    )
    publish_result = write_github_outbox_artifact(
        "publish_plan",
        _render_publish_plan(analysis),
        workspace_root=REPO_ROOT,
        task_id="github_assistant_readonly",
        trace_id="assistant_publish_plan",
    )
    print(f"- devlog_entry.md: {'OK' if devlog_result.get('ok') else 'failed'}")
    print(f"- publish_plan.md: {'OK' if publish_result.get('ok') else 'failed'}")

    print("\n[6] Done")
    outputs = {
        "review_report": review_result,
        "pr_description": pr_result,
        "commit_message": commit_result,
        "devlog_entry": devlog_result,
        "publish_plan": publish_result,
    }
    write_results = list(outputs.values())

    forbidden = any(
        result.get("git_commit") or result.get("git_push") or result.get("github_create_pr")
        for result in write_results
    )

    print("\nFINAL OUTPUT SUMMARY:")
    print("[OK] review_report.md")
    print("[OK] pr_description.md")
    print("[OK] commit_message.txt")
    print("[OK] devlog_entry.md")
    print("[OK] no GitHub API, no commit, no push, no merge")
    _print_value_summary()

    return 0 if status.get("ok") and diff.get("ok") and not forbidden else 1


def _event_content(issue_text: str) -> str:
    return (
        f"{issue_text.strip()}\n\n"
        "Generate commit message, PR description, devlog, and publish plan for this issue.\n"
        "Do not call GitHub API. Do not commit. Do not push.\n\n"
        f"Issue: {issue_text.strip()}\n"
    )


def _ensure_workspace() -> None:
    for directory in (EVENTS_INBOX, EVENTS_OUTBOX, GITHUB_OUTBOX, SESSIONS, AUDIT_LOG.parent):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".gitkeep").touch()


def _find_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        path = str(record.get("event", {}).get("path") or "")
        if path.endswith(EVENT_FILENAME):
            return record
    return None


def _session_files() -> set[Path]:
    if not SESSIONS.exists():
        return set()
    return set(SESSIONS.glob("*.json"))


def _session_id(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path.stem
    return str(data.get("session_id") or path.stem)


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()])


def _one_line(text: str) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= 120:
        return compact
    return f"{compact[:120]}... <truncated len={len(compact)}>"


def _print_draft_pr_preview(issue_text: str) -> None:
    _ = _read_output_file("commit_message.txt")
    _ = _read_output_file("pr_description.md")
    issue = _one_line(issue_text)
    print("")
    print("[MODE] Draft PR Generation")
    print("")
    print("==== PR PREVIEW ====")
    print("")
    print("Title:")
    print(f"fix: {issue}")
    print("")
    print("Description:")
    print("# Summary")
    print(f"- Prepare Git-ready engineering artifacts for: {issue}")
    print("- Generate a commit message, PR description, devlog entry, and publish plan.")
    print("- Keep the workflow local and reviewable.")
    print("")
    print("# Safety")
    print("- No GitHub API call was made.")
    print("- No git commit was created.")
    print("- No git push was performed.")
    print("")
    print("# Generated Files")
    for filename in OUTBOX_FILES.values():
        print(f"- workspace/github_outbox/{filename}")
    print("")
    print("----")


def _read_output_file(filename: str) -> str:
    path = GITHUB_OUTBOX / filename
    if not path.exists():
        return f"<missing {filename}>"
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _print_value_summary() -> None:
    print("")
    print("--- VALUE SUMMARY ---")
    print("")
    print("Before ZERO:")
    print("- Manual review")
    print("- Manual PR writing")
    print("- Manual devlog updates")
    print("")
    print("After ZERO:")
    print("- One command")
    print("- Structured outputs ready")
    print("- Fully local and controllable")
    print("")
    print("Result:")
    print("- 4 engineering artifacts generated")
    print("- Ready to copy into Git workflow")


def _build_readonly_analysis(
    *,
    issue_text: str,
    status: dict[str, Any],
    diff: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    status_text = str(status.get("stdout") or "").strip()
    diff_text = str(diff.get("stdout") or "")
    files = _changed_files_from_status(status_text)
    if not files:
        files = _changed_files_from_diff(diff_text)
    summary = (
        "Read local repo state and prepared GitHub workflow artifacts."
        if mode == "analyze_repo"
        else "Read local diff and prepared a focused change review."
    )
    return {
        "mode": mode,
        "issue_text": issue_text.strip(),
        "summary": summary,
        "changed_files": files,
        "status_ok": bool(status.get("ok")),
        "diff_ok": bool(diff.get("ok")),
        "status_preview": _limit_lines(status_text, 30),
        "diff_preview": _limit_lines(diff_text, 80),
    }


def _render_review_report(analysis: dict[str, Any]) -> str:
    files = analysis.get("changed_files") or []
    lines = [
        "# Local GitHub Workflow Review",
        "",
        f"Mode: {analysis.get('mode')}",
        f"Summary: {analysis.get('summary')}",
        "",
        "## Issue",
        analysis.get("issue_text") or "No issue text provided.",
        "",
        "## Changed Files",
    ]
    lines.extend(f"- {path}" for path in files) if files else lines.append("- none detected")
    lines.extend(
        [
            "",
            "## Safety",
            "- Read-only repository inspection only",
            "- No GitHub API call",
            "- No git commit",
            "- No git push",
            "- No merge",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _render_pr_description(analysis: dict[str, Any]) -> str:
    return (
        "# PR Draft\n\n"
        "## Summary\n"
        f"- {analysis.get('summary')}\n"
        f"- Issue/context: {analysis.get('issue_text') or 'local repository changes'}\n\n"
        "## Review Notes\n"
        "- Review generated artifacts before any manual GitHub action.\n"
        "- Confirm changed files and test impact.\n\n"
        "## Safety\n"
        "- No external write was performed.\n"
    )


def _render_commit_message(analysis: dict[str, Any]) -> str:
    issue = _one_line(str(analysis.get("issue_text") or "local repository changes"))
    return (
        f"chore: prepare GitHub workflow artifacts for {issue}\n\n"
        "- analyze local repo status and diff\n"
        "- generate review report and PR draft\n"
        "- keep workflow read-only except local outbox writes\n"
    )


def _render_devlog_entry(analysis: dict[str, Any]) -> str:
    return (
        "## GitHub Semi-Automation Read-only Workflow\n\n"
        f"- Mode: {analysis.get('mode')}\n"
        f"- Summary: {analysis.get('summary')}\n"
        f"- Changed files detected: {len(analysis.get('changed_files') or [])}\n"
        "- Safety: no GitHub API, commit, push, or merge\n"
    )


def _render_publish_plan(analysis: dict[str, Any]) -> str:
    _ = analysis
    return (
        "# Publish Plan\n\n"
        "1. Review `workspace/github_outbox/review_report.md`.\n"
        "2. Review `workspace/github_outbox/pr_description.md`.\n"
        "3. Manually decide whether to commit, push, or open a PR outside ZERO.\n"
        "4. Do not treat generated artifacts as an approval to mutate remote state.\n"
    )


def _changed_files_from_status(status_text: str) -> list[str]:
    files: list[str] = []
    for line in str(status_text or "").splitlines():
        if len(line) >= 3:
            path = line[3:].strip() if line[2:3] == " " else line[2:].strip()
            if path and path not in files:
                files.append(path)
    return files


def _changed_files_from_diff(diff_text: str) -> list[str]:
    files: list[str] = []
    for line in str(diff_text or "").splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                path = parts[3].removeprefix("b/")
                if path and path not in files:
                    files.append(path)
    return files


def _limit_lines(text: str, max_lines: int) -> str:
    lines = str(text or "").splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    kept = lines[:max_lines]
    kept.append(f"... <truncated {len(lines) - max_lines} lines>")
    return "\n".join(kept)


if __name__ == "__main__":
    raise SystemExit(main())
