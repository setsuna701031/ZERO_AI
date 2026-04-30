from __future__ import annotations

from typing import Any, Dict, List

from core.tools.generator_schema import build_title_body_payload, format_title_body_message
from core.tools.github_outbox import write_github_outbox_artifact
from core.tools.tool_policy import build_tool_trace_event, evaluate_tool_policy


def generate_commit_message(
    *,
    diff_text: str = "",
    summary: str = "",
    changed_files: List[str] | None = None,
    task_id: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    files = changed_files if isinstance(changed_files, list) else _extract_changed_files(diff_text)
    title = _build_title(summary=summary, files=files)
    body = _build_body(summary=summary, files=files)
    payload = build_title_body_payload(
        output_schema="commit_message.v1",
        title=title,
        body=body,
    )
    message = str(payload.get("message") or "")

    policy_decision = evaluate_tool_policy(
        tool_class="generate_only",
        actual_side_effect_level="none",
    )
    trace = build_tool_trace_event(
        trace_id=trace_id,
        task_id=task_id,
        tool_name="commit_message_generator",
        tool_class="generate_only",
        input_summary="generate commit message from diff summary",
        output_summary=f"{len(message)} chars",
        side_effect_level="none",
        policy_decision=policy_decision,
        executor_approved=False,
        status="success" if policy_decision.get("ok") else "error",
        error="" if policy_decision.get("ok") else str(policy_decision.get("reason") or ""),
        origin="commit_message_generator",
        tool_input_full={
            "summary_chars": len(str(summary or "")),
            "diff_chars": len(str(diff_text or "")),
            "changed_file_count": len(files),
        },
    )
    return {
        "ok": bool(policy_decision.get("ok")),
        "tool": "commit_message_generator",
        "tool_class": "generate_only",
        "side_effect_level": "none",
        **payload,
        "changed_files": [],
        "summary": "generate commit message",
        "error": None if policy_decision.get("ok") else policy_decision.get("reason"),
        "trace": trace,
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }


def generate_commit_message_to_outbox(
    *,
    diff_text: str = "",
    summary: str = "",
    changed_files: List[str] | None = None,
    workspace_root: Any = ".",
    task_id: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    generated = generate_commit_message(
        diff_text=diff_text,
        summary=summary,
        changed_files=changed_files,
        task_id=task_id,
        trace_id=f"{trace_id}_generate" if trace_id else "",
    )
    if not generated.get("ok"):
        return {
            "ok": False,
            "tool": "commit_message_generator_pipeline",
            "message": generated.get("message", ""),
            "outbox_result": {},
            "generation_result": generated,
            "error": generated.get("error"),
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
        }

    title = str(generated.get("title") or "")
    body = str(generated.get("body") or "")
    message = format_title_body_message(title=title, body=body)
    outbox_result = write_github_outbox_artifact(
        "commit_message",
        message,
        workspace_root=workspace_root,
        task_id=task_id,
        trace_id=f"{trace_id}_outbox" if trace_id else "",
    )
    return {
        "ok": bool(outbox_result.get("ok")),
        "tool": "commit_message_generator_pipeline",
        "output_schema": generated.get("output_schema"),
        "output": generated.get("output"),
        "title": title,
        "body": body,
        "message": message,
        "outbox_result": outbox_result,
        "generation_result": generated,
        "error": outbox_result.get("error"),
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }


def _extract_changed_files(diff_text: str) -> List[str]:
    files: List[str] = []
    for line in str(diff_text or "").splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.append(parts[3].removeprefix("b/"))
    return files


def _build_title(*, summary: str, files: List[str]) -> str:
    normalized = str(summary or "").strip()
    if normalized:
        first_sentence = normalized.splitlines()[0].strip("- ").strip()
        if first_sentence:
            return _title_case_message(first_sentence)

    if files:
        area = _common_area(files)
        if area:
            return f"Update {area}"

    return "Update project changes"


def _build_body(*, summary: str, files: List[str]) -> str:
    bullets: List[str] = []
    normalized = str(summary or "").strip()
    if normalized:
        bullets.append(f"- {normalized.splitlines()[0].strip('- ').strip()}")

    if files:
        preview = ", ".join(files[:3])
        suffix = "" if len(files) <= 3 else f" and {len(files) - 3} more"
        bullets.append(f"- Touch {preview}{suffix}")

    bullets.append("- Keep changes as generated artifacts only; no commit, push, or PR is created")
    return "\n".join(bullets)


def format_commit_message(*, title: str, body: str) -> str:
    return format_title_body_message(title=title, body=body)


def _common_area(files: List[str]) -> str:
    first = str(files[0] or "")
    if "/" in first:
        return first.split("/", 1)[0]
    if "\\" in first:
        return first.split("\\", 1)[0]
    return first or "project"


def _title_case_message(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return "Update project changes"
    return clean[0].upper() + clean[1:]
