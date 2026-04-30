from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.tools.tool_policy import (
    build_tool_trace_event,
    evaluate_tool_policy,
)


OUTBOX_ARTIFACTS = {
    "commit_message": "workspace/github_outbox/commit_message.txt",
    "pr_description": "workspace/github_outbox/pr_description.md",
    "devlog": "workspace/github_outbox/devlog.md",
    "review_report": "workspace/github_outbox/review_report.md",
}


def write_github_outbox_artifact(
    artifact: str,
    content: Any,
    *,
    workspace_root: Any = ".",
    task_id: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    artifact_key = str(artifact or "").strip().lower()
    requested_path = OUTBOX_ARTIFACTS.get(artifact_key)
    if not requested_path:
        return _result(
            ok=False,
            artifact=artifact_key,
            content=content,
            output_path="",
            policy_decision={
                "ok": False,
                "reason": "unknown_outbox_artifact",
                "tool_class": "workspace_write",
                "side_effect_level": "workspace_write",
                "output_path": "",
            },
            task_id=task_id,
            trace_id=trace_id,
            error=f"unsupported github_outbox artifact: {artifact_key}",
        )

    policy_decision = evaluate_tool_policy(
        tool_class="workspace_write",
        actual_side_effect_level="workspace_write",
        output_path=requested_path,
        workspace_root=workspace_root,
    )
    output_path = str(policy_decision.get("output_path") or requested_path)

    if not policy_decision.get("ok"):
        return _result(
            ok=False,
            artifact=artifact_key,
            content=content,
            output_path=output_path,
            policy_decision=policy_decision,
            task_id=task_id,
            trace_id=trace_id,
            error=str(policy_decision.get("reason") or "policy_rejected"),
        )

    target = Path(output_path)
    text = "" if content is None else str(content)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except Exception as exc:
        return _result(
            ok=False,
            artifact=artifact_key,
            content=content,
            output_path=output_path,
            policy_decision=policy_decision,
            task_id=task_id,
            trace_id=trace_id,
            error=str(exc),
        )

    return _result(
        ok=True,
        artifact=artifact_key,
        content=content,
        output_path=output_path,
        policy_decision=policy_decision,
        task_id=task_id,
        trace_id=trace_id,
    )


def _result(
    *,
    ok: bool,
    artifact: str,
    content: Any,
    output_path: str,
    policy_decision: Dict[str, Any],
    task_id: str,
    trace_id: str,
    error: str = "",
) -> Dict[str, Any]:
    text = "" if content is None else str(content)
    trace = build_tool_trace_event(
        trace_id=trace_id,
        task_id=task_id,
        tool_name="github_outbox",
        tool_class="workspace_write",
        input_summary=f"write github outbox artifact: {artifact}",
        output_path=output_path,
        output_summary=f"{len(text)} chars",
        side_effect_level="workspace_write",
        policy_decision=policy_decision,
        executor_approved=bool(ok),
        status="success" if ok else "error",
        error=error,
        tool_input_full={
            "artifact": artifact,
            "content_chars": len(text),
        },
    )
    return {
        "ok": bool(ok),
        "tool": "github_outbox",
        "artifact": artifact,
        "output_path": output_path,
        "changed_files": [output_path] if ok and output_path else [],
        "summary": "write github outbox artifact" if ok else "",
        "error": None if ok else error,
        "trace": trace,
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
