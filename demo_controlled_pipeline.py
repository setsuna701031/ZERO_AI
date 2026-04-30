from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.tools.approval_record import write_approval_record
from core.tools.git_pipeline import GitPipelineTool


REPO_ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
TASK_ID = "task_demo_controlled_pipeline"


def main() -> int:
    print("[DEMO] Controlled GitHub pipeline")
    print("")

    print("1. detect git diff")
    pipeline_result = GitPipelineTool(workspace_root=REPO_ROOT).execute(
        {
            "repo_root": str(REPO_ROOT),
            "task_id": TASK_ID,
            "trace_id": "trace_demo_controlled_pipeline",
        }
    )
    if not pipeline_result.get("ok"):
        print(f"FAIL: git pipeline failed: {pipeline_result.get('error')}")
        return 1
    print("   ok: read-only git inputs collected")

    print("2. generate artifacts")
    artifacts = pipeline_result.get("artifacts", {})
    print(f"   commit_message: {artifacts.get('commit_message')}")
    print(f"   pr_description : {artifacts.get('pr_description')}")

    task_dir = _write_replay_fixture(pipeline_result)
    print("3. replay trace")
    replay = _run([PYTHON, str(REPO_ROOT / "replay.py"), "--task", TASK_ID])
    print(_indent(replay.stdout.strip()))
    if replay.returncode != 0:
        print(replay.stderr)
        return replay.returncode

    print("")
    print("4. approval decision")
    approval = write_approval_record(
        decision="approved",
        workspace_root=REPO_ROOT,
        task_id=TASK_ID,
        trace_path=f"workspace/tasks/{TASK_ID}/trace.json",
        source="demo_controlled_pipeline",
    )
    if not approval.get("ok"):
        print(f"FAIL: approval record failed: {approval.get('error')}")
        return 1
    print(f"   approved record: {approval.get('record_logical_path')}")

    print("5. execution plan (blocked)")
    controlled = _run(
        [
            PYTHON,
            str(REPO_ROOT / "policy_execute.py"),
            "--approval",
            str(approval.get("record_path") or ""),
            "--policy-preview",
        ]
    )
    print(_indent(controlled.stdout.strip()))
    if controlled.returncode != 0:
        print(controlled.stderr)
        return controlled.returncode

    print("")
    print("[DEMO] PASS: generated artifacts, replayed trace, wrote approval, and showed blocked execution plan.")
    return 0


def _write_replay_fixture(pipeline_result: dict) -> Path:
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
        "goal": "demo controlled git pipeline",
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
        "source": "demo_controlled_pipeline",
        "events": [],
    }

    _write_json(task_dir / "plan.json", plan)
    _write_json(task_dir / "runtime_state.json", runtime_state)
    _write_json(task_dir / "result.json", result)
    _write_json(task_dir / "trace.json", trace)
    (task_dir / "execution_log.json").write_text("[]", encoding="utf-8")
    return task_dir


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


def _indent(text: str) -> str:
    return "\n".join(f"   {line}" for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
