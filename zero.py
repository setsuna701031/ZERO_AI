from __future__ import annotations

import sys

from apps.github_assistant import run_github_assistant


def print_help() -> None:
    print(
        """
ZERO - Engineering Automation CLI

Commands:
  pr "issue text"
      Generate Git-ready engineering artifacts

  draft_pr "issue text"
      Generate artifacts and preview PR content

  analyze_repo "issue text"
      Read repo status/diff and write local GitHub workflow artifacts

  analyze_diff "issue text"
      Read local diff and write a focused review package

Examples:
  python zero.py pr "Fix login bug"
  python zero.py draft_pr "Improve scheduler stability"
  python zero.py analyze_repo "Prepare release review"

Safety:
  No GitHub API. No commit. No push.
"""
    )


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1].strip().lower() in {"help", "-h", "--help"}:
        print_help()
        return 0

    if len(sys.argv) < 3:
        print_help()
        return 1

    command = sys.argv[1].strip().lower()
    content = " ".join(sys.argv[2:]).strip()

    if command == "pr":
        return run_github_assistant(content)
    if command == "draft_pr":
        return run_github_assistant(content, mode="draft_pr")
    if command in {"analyze_repo", "analyze_diff"}:
        return run_github_assistant(content, mode=command)

    print(f"Unknown command: {command}")
    print("Supported commands: pr, draft_pr, analyze_repo, analyze_diff")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
