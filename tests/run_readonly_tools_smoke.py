from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.readonly_tools import file_reader, git_diff, git_status


PREFIX = "[readonly-tools-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def assert_readonly_result(result: dict, label: str) -> int:
    if result.get("tool_class") != "read_only":
        return fail(f"{label}: tool_class mismatch {result}")
    if result.get("side_effect_level") != "read_only":
        return fail(f"{label}: side_effect_level mismatch {result}")
    if result.get("changed_files") != []:
        return fail(f"{label}: changed_files not empty {result}")
    if result.get("git_commit") or result.get("git_push") or result.get("github_create_pr"):
        return fail(f"{label}: read-only tool reported mutation {result}")

    trace = result.get("trace", {})
    if trace.get("tool_class") != "read_only":
        return fail(f"{label}: trace tool_class mismatch {trace}")
    if trace.get("side_effect_level") != "read_only":
        return fail(f"{label}: trace side_effect_level mismatch {trace}")
    if trace.get("executor_approved") is not False:
        return fail(f"{label}: read-only trace should not claim executor approval {trace}")
    pass_step(label)
    return 0


def main() -> int:
    print(f"{PREFIX} START")

    status = git_status(repo_root=REPO_ROOT, task_id="task_readonly", trace_id="trace_status")
    if not status.get("ok"):
        return fail(f"git_status failed: {status}")
    check = assert_readonly_result(status, "git_status is real read-only")
    if check != 0:
        return check

    diff = git_diff(repo_root=REPO_ROOT, task_id="task_readonly", trace_id="trace_diff")
    if not diff.get("ok"):
        return fail(f"git_diff failed: {diff}")
    check = assert_readonly_result(diff, "git_diff is real read-only")
    if check != 0:
        return check

    limited_diff = git_diff(
        repo_root=REPO_ROOT,
        task_id="task_readonly",
        trace_id="trace_diff_limited",
        max_lines=1,
    )
    if not limited_diff.get("ok"):
        return fail(f"limited git_diff failed: {limited_diff}")
    if limited_diff.get("original_line_count", 0) > 1 and not limited_diff.get("truncated"):
        return fail(f"large git_diff was not marked truncated: {limited_diff}")
    if limited_diff.get("truncated") and len(str(limited_diff.get("stdout") or "").splitlines()) > 2:
        return fail(f"truncated git_diff kept too many lines: {limited_diff}")
    check = assert_readonly_result(limited_diff, "git_diff supports max_lines prompt guard")
    if check != 0:
        return check

    readme = file_reader("README.md", repo_root=REPO_ROOT, task_id="task_readonly", trace_id="trace_file")
    if not readme.get("ok"):
        return fail(f"file_reader failed: {readme}")
    if not readme.get("content"):
        return fail("file_reader returned empty README content")
    check = assert_readonly_result(readme, "file_reader is real read-only")
    if check != 0:
        return check

    escaped = file_reader("../secret.txt", repo_root=REPO_ROOT)
    if escaped.get("ok"):
        return fail(f"file_reader accepted escaped path: {escaped}")
    check = assert_readonly_result(escaped, "file_reader escape attempt remains read-only")
    if check != 0:
        return check

    sensitive_targets = [".env", ".git/config", "id_rsa", "secret.pem"]
    for target in sensitive_targets:
        denied = file_reader(target, repo_root=REPO_ROOT)
        if denied.get("ok"):
            return fail(f"file_reader accepted sensitive path {target}: {denied}")
        if denied.get("error") != "sensitive_path_denied":
            return fail(f"file_reader wrong denial for {target}: {denied}")
        check = assert_readonly_result(denied, f"file_reader denies sensitive path {target}")
        if check != 0:
            return check

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
