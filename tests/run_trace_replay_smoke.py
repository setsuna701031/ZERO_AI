from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
TASK_ID = "task_trace_replay_smoke"


def fail(message: str) -> int:
    print(f"[trace-replay-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[trace-replay-smoke] PASS: {message}")


def write_fixture() -> None:
    task_dir = REPO_ROOT / "workspace" / "tasks" / TASK_ID
    outbox_dir = REPO_ROOT / "workspace" / "github_outbox"
    task_dir.mkdir(parents=True, exist_ok=True)
    outbox_dir.mkdir(parents=True, exist_ok=True)

    commit_path = outbox_dir / "trace_replay_smoke_commit_message.txt"
    pr_path = outbox_dir / "trace_replay_smoke_pr_description.md"
    commit_path.write_text("Update trace replay\n\n- Smoke fixture", encoding="utf-8")
    pr_path.write_text("## Summary\n- Smoke fixture", encoding="utf-8")

    plan = {
        "semantic_type": "git_pipeline_task",
        "execution_route": "git_pipeline_path",
        "steps": [
            {
                "type": "tool",
                "tool_name": "git_pipeline",
                "tool_input": {},
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
        "goal": "analyze git diff and generate GitHub outbox artifacts",
        "steps": plan["steps"],
        "results": [
            {
                "ok": True,
                "step_type": "tool",
                "result": {
                    "ok": True,
                    "tool": "git_pipeline",
                    "analysis": {"files": ["replay.py"], "summary": "Add read-only trace replay"},
                    "diff_result": {"ok": True, "tool": "git_diff"},
                    "status_result": {"ok": True, "tool": "git_status"},
                    "commit_message": {
                        "ok": True,
                        "trace": {"origin": "llm"},
                        "outbox_result": {"ok": True, "output_path": str(commit_path)},
                    },
                    "pr_description": {
                        "ok": True,
                        "trace": {"origin": "llm"},
                        "outbox_result": {"ok": True, "output_path": str(pr_path)},
                    },
                    "artifacts": {
                        "commit_message": str(commit_path),
                        "pr_description": str(pr_path),
                    },
                    "git_commit": False,
                    "git_push": False,
                    "github_create_pr": False,
                },
            }
        ],
    }
    result = {
        "ok": True,
        "task_id": TASK_ID,
        "status": "finished",
        "result": runtime_state["results"][0],
    }

    (task_dir / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    (task_dir / "runtime_state.json").write_text(json.dumps(runtime_state, indent=2), encoding="utf-8")
    (task_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (task_dir / "execution_log.json").write_text("[]", encoding="utf-8")


def main() -> int:
    print("[trace-replay-smoke] START")
    write_fixture()
    pass_step("fixture written")

    completed = subprocess.run(
        [PYTHON, str(REPO_ROOT / "replay.py"), "--task", TASK_ID],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return fail(f"replay exited {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")

    output = completed.stdout
    print(output)
    required = [
        "Mode: read_only",
        "does not execute tasks or tools",
        "git_diff",
        "(origin: git)",
        "git_status",
        "generate_commit",
        "(origin: llm)",
        "generate_pr",
        "outbox_write",
        "(origin: github_outbox)",
        "trace_replay_smoke_commit_message.txt (size:",
        "trace_replay_smoke_pr_description.md (size:",
        "sha256:",
        "git_commit: false",
        "git_push: false",
        "github_create_pr: false",
        "mutation_attempt: 0",
        "no_commit_push_pr: true",
        "Summary: ZERO replayed a read-only git analysis pipeline that generated artifacts without mutating the repository.",
    ]
    for text in required:
        if text not in output:
            return fail(f"missing output text: {text}")

    pass_step("read-only replay summary includes steps, artifacts, and safety flags")

    json_completed = subprocess.run(
        [PYTHON, str(REPO_ROOT / "replay.py"), "--task", TASK_ID, "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if json_completed.returncode != 0:
        return fail(f"json replay exited {json_completed.returncode}: {json_completed.stderr}")
    payload = json.loads(json_completed.stdout)
    if payload.get("replay_mode") != "read_only":
        return fail(f"json replay_mode mismatch: {payload}")
    if payload.get("safety", {}).get("no_commit_push_pr") is not True:
        return fail(f"json safety mismatch: {payload}")
    if payload.get("safety", {}).get("mutation_attempt") != 0:
        return fail(f"json mutation_attempt mismatch: {payload}")
    first_step = payload.get("steps", [{}])[0]
    if first_step.get("origin") != "git":
        return fail(f"json origin mismatch: {payload}")
    first_artifact = payload.get("artifacts", [{}])[0]
    if first_artifact.get("size_bytes") is None or not first_artifact.get("sha256_12"):
        return fail(f"json artifact metadata missing: {payload}")
    if "read-only git analysis pipeline" not in str(payload.get("summary") or ""):
        return fail(f"json summary missing: {payload}")
    pass_step("json output preserves read-only safety contract")

    print("[trace-replay-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
