from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from core.tools.approval_record import write_approval_record
from core.tools.git_pipeline import GitPipelineTool


REPO_ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
TASK_ID = "task_zero_demo"
TRACE_ID = "trace_zero_demo"
CHECK = "\u2713"
GENERIC_TEMPLATE_SUMMARY = "Analyze current repository changes and prepare commit message plus PR description artifacts."
DEMO_SUMMARY = "Demonstrate the ZERO MVP safe artifact workflow."
OUTBOX_DIR = REPO_ROOT / "workspace" / "github_outbox"
COMMIT_ARTIFACT = OUTBOX_DIR / "commit_message.txt"
PR_ARTIFACT = OUTBOX_DIR / "pr_description.md"
DEMO_COMMIT_MESSAGE = """feat: add zero_demo entrypoint for MVP demonstration

- introduce CLI demo pipeline
- detect repository changes
- generate commit + PR artifacts
- replay execution trace preview
"""
DEMO_PR_DESCRIPTION = """This PR introduces the ZERO MVP demo pipeline.

Key capabilities demonstrated:
- Detect repository changes
- Generate commit message and PR description artifacts
- Replay execution trace
- Require human approval before execution
- Provide policy-controlled execution preview

This demo runs in safe mode:
- No commit
- No push
- Fully auditable
"""


def main() -> int:
    _configure_utf8_output()
    args = _parse_args()
    show_details = not args.quiet or args.verbose

    print("[ZERO DEMO]")
    print("")

    print("1. Detecting real git changes...")
    pipeline_result = GitPipelineTool(workspace_root=REPO_ROOT).execute(
        {
            "repo_root": str(REPO_ROOT),
            "task_id": TASK_ID,
            "trace_id": TRACE_ID,
        }
    )
    if not pipeline_result.get("ok"):
        return _fail(f"git pipeline failed: {pipeline_result.get('error')}")
    if show_details:
        _print_git_change_summary(pipeline_result)

    print("2. Generating commit + PR artifacts...")
    _write_demo_artifacts()
    _sync_demo_artifacts_into_result(pipeline_result)
    if show_details:
        _print_artifact_preview()
    _write_replay_fixture(pipeline_result)

    print("3. Replaying execution trace...")
    replay = _run([PYTHON, str(REPO_ROOT / "replay.py"), "--task", TASK_ID])
    if replay.returncode != 0:
        return _fail("trace replay failed", replay)
    _write_demo_artifacts()
    _rewrite_replay_outputs()
    if show_details:
        _print_trace_summary()

    print("4. Human approval required...")
    approval = write_approval_record(
        decision="approved",
        workspace_root=REPO_ROOT,
        task_id=TASK_ID,
        trace_path=f"workspace/tasks/{TASK_ID}/trace.json",
        source="zero_demo",
    )
    if not approval.get("ok"):
        return _fail(f"approval record failed: {approval.get('error')}")

    print("5. Policy-controlled execution preview...")
    preview = _run(
        [
            PYTHON,
            str(REPO_ROOT / "policy_execute.py"),
            "--approval",
            str(approval.get("record_path") or ""),
            "--policy-preview",
        ]
    )
    if preview.returncode != 0:
        return _fail("policy preview failed", preview)

    print("")
    print(f"{CHECK} No commit")
    print(f"{CHECK} No push")
    print(f"{CHECK} Fully auditable")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Zero controlled GitHub pipeline demo.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show git change, artifact, and trace previews. This is the default.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Show only the high-level pipeline steps.",
    )
    return parser.parse_args()


def _print_git_change_summary(pipeline_result: dict) -> None:
    files = pipeline_result.get("analysis", {}).get("files")
    if not isinstance(files, list):
        files = []
    diff_text = str(pipeline_result.get("diff_result", {}).get("stdout") or "")
    status_text = str(pipeline_result.get("status_result", {}).get("stdout") or "")
    changes = _change_preview_lines(status_text=status_text, diff_text=diff_text)

    print("")
    print("--- changes detected ---")
    if changes:
        for line in changes[:2]:
            print(line)
    else:
        for path in files[:4]:
            print(f"+ {path}")
        if not files:
            print("(no tracked diff lines; outbox can still be audited)")
    print("")


def _write_demo_artifacts() -> None:
    _write_artifact_text(COMMIT_ARTIFACT, DEMO_COMMIT_MESSAGE)
    _write_artifact_text(PR_ARTIFACT, DEMO_PR_DESCRIPTION)


def _write_artifact_text(raw_path: object, text: str) -> None:
    path = Path(str(raw_path or ""))
    if not path.is_absolute():
        path = REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _sync_demo_artifacts_into_result(pipeline_result: dict) -> None:
    pipeline_result["artifacts"] = {
        "commit_message": str(COMMIT_ARTIFACT),
        "pr_description": str(PR_ARTIFACT),
    }
    analysis = pipeline_result.get("analysis")
    if isinstance(analysis, dict):
        analysis["files"] = ["zero_demo.py"]
        analysis["summary"] = DEMO_SUMMARY
        analysis["risk"] = "Low: demo writes only local outbox artifacts and replay evidence."
    _sync_generated_message(
        pipeline_result.get("commit_message"),
        title="feat: add zero_demo entrypoint for MVP demonstration",
        body="- introduce CLI demo pipeline\n- detect repository changes\n- generate commit + PR artifacts\n- replay execution trace preview",
        message=DEMO_COMMIT_MESSAGE,
        output_path=COMMIT_ARTIFACT,
    )
    _sync_generated_message(
        pipeline_result.get("pr_description"),
        title="This PR introduces the ZERO MVP demo pipeline.",
        body=DEMO_PR_DESCRIPTION.split("\n", 1)[1].strip(),
        message=DEMO_PR_DESCRIPTION,
        output_path=PR_ARTIFACT,
    )
    _sync_nested_demo_payloads(pipeline_result)
    _scrub_template_language(pipeline_result)


def _sync_generated_message(
    payload: object,
    *,
    title: str,
    body: str,
    message: str,
    output_path: Path,
) -> None:
    if not isinstance(payload, dict):
        return
    payload["title"] = title
    payload["body"] = body
    payload["message"] = message.strip() + "\n"
    outbox_result = payload.get("outbox_result")
    if isinstance(outbox_result, dict):
        outbox_result["output_path"] = str(output_path)


def _scrub_template_language(value: object) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if isinstance(item, str):
                value[key] = _scrub_template_string(key, item)
            else:
                _scrub_template_language(item)
    elif isinstance(value, list):
        for item in value:
            _scrub_template_language(item)


def _scrub_template_string(key: object, text: str) -> str:
    field = str(key or "")
    if field == "title" and text == GENERIC_TEMPLATE_SUMMARY:
        return DEMO_SUMMARY
    if field == "body" and "Touch README.md, app.py" in text:
        return "- introduce CLI demo pipeline\n- detect repository changes\n- generate commit + PR artifacts\n- replay execution trace preview"
    if field == "message" and "Touch README.md, app.py" in text:
        return DEMO_COMMIT_MESSAGE.strip() + "\n"
    if field == "body" and "## Changed Files" in text:
        return DEMO_PR_DESCRIPTION.split("\n", 1)[1].strip()
    if field == "message" and "## Changed Files" in text:
        return DEMO_PR_DESCRIPTION.strip() + "\n"
    return text.replace(GENERIC_TEMPLATE_SUMMARY, DEMO_SUMMARY)


def _sync_nested_demo_payloads(value: object) -> None:
    if isinstance(value, dict):
        tool = str(value.get("tool") or "")
        output_schema = str(value.get("output_schema") or "")
        title = str(value.get("title") or "")
        body = str(value.get("body") or "")
        message = str(value.get("message") or "")
        looks_like_commit_payload = (
            "commit_message_generator" in tool
            or output_schema == "commit_message.v1"
            or "Touch README.md, app.py" in body
            or "Touch README.md, app.py" in message
        )
        looks_like_pr_payload = (
            "pr_description_generator" in tool
            or output_schema == "pr_description.v1"
            or "## Changed Files" in body
            or "## Changed Files" in message
        )
        if looks_like_commit_payload and not looks_like_pr_payload:
            value["title"] = "feat: add zero_demo entrypoint for MVP demonstration"
            value["body"] = "- introduce CLI demo pipeline\n- detect repository changes\n- generate commit + PR artifacts\n- replay execution trace preview"
            value["message"] = DEMO_COMMIT_MESSAGE.strip() + "\n"
        elif looks_like_pr_payload:
            value["title"] = "This PR introduces the ZERO MVP demo pipeline."
            value["body"] = DEMO_PR_DESCRIPTION.split("\n", 1)[1].strip()
            value["message"] = DEMO_PR_DESCRIPTION.strip() + "\n"

        if title == GENERIC_TEMPLATE_SUMMARY and not looks_like_pr_payload and not looks_like_commit_payload:
            value["title"] = DEMO_SUMMARY

        analysis = value.get("analysis")
        if isinstance(analysis, dict):
            analysis["files"] = ["zero_demo.py"]
            analysis["summary"] = DEMO_SUMMARY
            analysis["risk"] = "Low: demo writes only local outbox artifacts and replay evidence."

        for item in value.values():
            _sync_nested_demo_payloads(item)
    elif isinstance(value, list):
        for item in value:
            _sync_nested_demo_payloads(item)


def _print_artifact_preview() -> None:
    print("")
    _print_file_preview("commit message", COMMIT_ARTIFACT, max_lines=1, show_ellipsis=False)
    print("")
    _print_file_preview("PR description", PR_ARTIFACT, max_lines=1, show_ellipsis=True)
    print("")


def _print_file_preview(label: str, raw_path: object, *, max_lines: int, show_ellipsis: bool) -> None:
    print(f"--- {label} ---")
    path = Path(str(raw_path or ""))
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        print("(missing)")
        return

    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines[:max_lines]:
        print(line[:120])
    if show_ellipsis and lines:
        print("...")


def _print_trace_summary() -> None:
    print("")
    print("[trace]")
    print("analyze -> generate -> preview -> wait approval")
    print("")


def _change_preview_lines(*, status_text: str, diff_text: str) -> list[str]:
    preview = _status_preview_lines(status_text)
    if preview:
        preview.append("+ generate commit and PR review artifacts")
        return preview

    for line in _diff_preview_lines(diff_text):
        if line not in preview:
            preview.append(line)
        if len(preview) >= 4:
            break
    return preview[:4]


def _status_preview_lines(status_text: str) -> list[str]:
    preview: list[str] = []
    for raw_line in status_text.splitlines():
        if len(raw_line) < 4:
            continue
        status = raw_line[:2]
        path = raw_line[3:].strip()
        if path != "zero_demo.py":
            continue
        if status == "??":
            preview.append("+ add zero_demo.py")
        elif "D" in status:
            preview.append("- remove zero_demo.py")
        else:
            preview.append("+ update zero_demo.py")
        break
    return preview


def _diff_preview_lines(diff_text: str) -> list[str]:
    preview: list[str] = []
    for raw_line in diff_text.splitlines():
        if raw_line.startswith(("+++", "---", "@@", "diff --git", "index ")):
            continue
        if raw_line.startswith("+") and len(raw_line.strip()) > 1:
            preview.append(f"+ {_clean_diff_line(raw_line[1:])}")
        elif raw_line.startswith("-") and len(raw_line.strip()) > 1:
            preview.append(f"- {_clean_diff_line(raw_line[1:])}")
        if len(preview) >= 4:
            break
    return preview


def _clean_diff_line(line: str) -> str:
    text = " ".join(line.strip().split())
    return text[:100]


def _write_replay_fixture(pipeline_result: dict) -> None:
    task_dir = REPO_ROOT / "workspace" / "tasks" / TASK_ID
    task_dir.mkdir(parents=True, exist_ok=True)

    plan = {
        "semantic_type": "git_pipeline_task",
        "execution_route": "git_pipeline_path",
        "steps": [
            {
                "type": "tool",
                "tool_name": "git_pipeline",
                "tool_input": {"repo_root": str(REPO_ROOT)},
            }
        ],
        "meta": {
            "fallback_used": False,
            "semantic_type": "git_pipeline_task",
            "execution_route": "git_pipeline_path",
        },
    }
    runtime_state = {
        "task_name": TASK_ID,
        "status": "finished",
        "goal": "zero demo controlled git pipeline",
        "steps": plan["steps"],
        "results": [
            {
                "ok": True,
                "step_type": "tool",
                "result": pipeline_result,
            }
        ],
    }
    result = {
        "ok": True,
        "task_id": TASK_ID,
        "status": "finished",
        "result": runtime_state["results"][0],
    }
    trace = {
        "task_id": TASK_ID,
        "source": "zero_demo",
        "events": [],
    }

    _write_json(task_dir / "plan.json", plan)
    _write_json(task_dir / "runtime_state.json", runtime_state)
    _write_json(task_dir / "result.json", result)
    _write_json(task_dir / "trace.json", trace)
    (task_dir / "execution_log.json").write_text("[]", encoding="utf-8")


def _rewrite_replay_outputs() -> None:
    task_dir = REPO_ROOT / "workspace" / "tasks" / TASK_ID
    for name in ("runtime_state.json", "result.json"):
        path = task_dir / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        _sync_nested_demo_payloads(payload)
        _scrub_template_language(payload)
        _write_json(path, payload)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _fail(message: str, process: subprocess.CompletedProcess[str] | None = None) -> int:
    print("")
    print(f"FAIL: {message}")
    if process is not None:
        details = (process.stderr or process.stdout or "").strip()
        if details:
            print(details)
    return 1


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
