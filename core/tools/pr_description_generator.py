from __future__ import annotations

from typing import Any, Dict, List

from core.tools.generator_schema import build_title_body_payload, format_title_body_message
from core.tools.github_outbox import write_github_outbox_artifact
from core.tools.tool_policy import build_tool_trace_event, evaluate_tool_policy


def generate_pr_description(
    *,
    analysis: Dict[str, Any] | None = None,
    commit_message: Dict[str, Any] | None = None,
    changed_files: List[str] | None = None,
    task_id: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    analysis_data = analysis if isinstance(analysis, dict) else {}
    commit_data = commit_message if isinstance(commit_message, dict) else {}
    files = changed_files if isinstance(changed_files, list) else _extract_files(analysis_data)

    title = _build_title(analysis=analysis_data, commit_message=commit_data)
    body = _build_body(analysis=analysis_data, commit_message=commit_data, files=files)
    payload = build_title_body_payload(
        output_schema="pr_description.v1",
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
        tool_name="pr_description_generator",
        tool_class="generate_only",
        input_summary="generate PR description from analysis and commit message",
        output_summary=f"{len(message)} chars",
        side_effect_level="none",
        policy_decision=policy_decision,
        executor_approved=False,
        status="success" if policy_decision.get("ok") else "error",
        error="" if policy_decision.get("ok") else str(policy_decision.get("reason") or ""),
        origin="pr_description_generator",
        tool_input_full={
            "changed_file_count": len(files),
            "has_commit_message": bool(commit_data),
        },
    )
    return {
        "ok": bool(policy_decision.get("ok")),
        "tool": "pr_description_generator",
        "tool_class": "generate_only",
        "side_effect_level": "none",
        **payload,
        "changed_files": [],
        "summary": "generate PR description",
        "error": None if policy_decision.get("ok") else policy_decision.get("reason"),
        "trace": trace,
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }


def generate_pr_description_to_outbox(
    *,
    analysis: Dict[str, Any] | None = None,
    commit_message: Dict[str, Any] | None = None,
    changed_files: List[str] | None = None,
    workspace_root: Any = ".",
    task_id: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    generated = generate_pr_description(
        analysis=analysis,
        commit_message=commit_message,
        changed_files=changed_files,
        task_id=task_id,
        trace_id=f"{trace_id}_generate" if trace_id else "",
    )
    if not generated.get("ok"):
        return {
            "ok": False,
            "tool": "pr_description_generator_pipeline",
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
        "pr_description",
        message,
        workspace_root=workspace_root,
        task_id=task_id,
        trace_id=f"{trace_id}_outbox" if trace_id else "",
    )
    return {
        "ok": bool(outbox_result.get("ok")),
        "tool": "pr_description_generator_pipeline",
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


def _extract_files(analysis: Dict[str, Any]) -> List[str]:
    files = analysis.get("files")
    if isinstance(files, list):
        return [str(item) for item in files]
    return []


def _build_title(*, analysis: Dict[str, Any], commit_message: Dict[str, Any]) -> str:
    commit_title = str(commit_message.get("title") or "").strip()
    if commit_title:
        return commit_title

    summary = str(analysis.get("summary") or "").strip()
    if summary:
        return summary.splitlines()[0].strip("- ").strip()

    return "Describe project changes"


def _build_body(
    *,
    analysis: Dict[str, Any],
    commit_message: Dict[str, Any],
    files: List[str],
) -> str:
    lines = ["## Summary"]
    summary = str(analysis.get("summary") or "").strip()
    commit_body = str(commit_message.get("body") or "").strip()
    if summary:
        lines.append(f"- {summary}")
    elif commit_body:
        first_body_line = commit_body.splitlines()[0].strip("- ").strip()
        lines.append(f"- {first_body_line}")
    else:
        lines.append("- Describe the current project changes.")

    lines.extend(["", "## Changed Files"])
    if files:
        lines.extend(f"- `{path}`" for path in files)
    else:
        lines.append("- No changed files detected.")

    lines.extend(["", "## Safety"])
    risk = str(analysis.get("risk") or "").strip()
    if risk:
        lines.append(f"- {risk}")
    lines.append("- Generated as an outbox artifact only; no commit, push, or PR is created.")
    return "\n".join(lines)
