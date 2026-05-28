from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import RuntimeNativeCodeMutationLoop
from core.runtime.runtime_native_engineering_session import RuntimeNativeEngineeringSession
from core.runtime.runtime_native_repo_engineering_surface import RuntimeNativeRepoEngineeringSurface


def build_repo(tmp_path):
    (tmp_path / "core/runtime").mkdir(parents=True, exist_ok=True)
    (tmp_path / "core/runtime/runtime_native_code_mutation_loop.py").write_text(
        "BROKEN = True\n",
        encoding="utf-8",
    )


def test_engineering_session_repo_context_and_mutation(tmp_path):
    build_repo(tmp_path)

    repo_surface = RuntimeNativeRepoEngineeringSurface.with_workspace(tmp_path)
    mutation_loop = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    session = RuntimeNativeEngineeringSession.with_workspace(
        tmp_path,
        repo_surface=repo_surface,
        mutation_loop=mutation_loop,
    )

    opened = session.open_session(goal="fix runtime mutation loop")
    captured = session.capture_repo_context(opened.session_id, keywords=["mutation"])

    assert captured.repo_context["repo_files"] >= 1
    assert len(captured.engineering_task["impacted_files"]) >= 1

    completed = session.run_mutation(
        captured.session_id,
        plan_fn=lambda goal, context: {
            "impacted_files": captured.engineering_task["impacted_files"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "core/runtime/runtime_native_code_mutation_loop.py",
                    "content": "BROKEN = False\n",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": (tmp_path / "core/runtime/runtime_native_code_mutation_loop.py").read_text(encoding="utf-8") == "BROKEN = False\n",
            "command": "targeted content check",
        },
    )

    assert completed.status == "completed"
    assert completed.final_result["ok"] is True
    assert len(completed.mutation_history) == 1
    assert len(completed.verification_history) == 1
    assert len(completed.timeline) >= 4


def test_engineering_session_resume_and_handoff(tmp_path):
    repo_surface = RuntimeNativeRepoEngineeringSurface.with_workspace(tmp_path)
    mutation_loop = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)
    session = RuntimeNativeEngineeringSession.with_workspace(
        tmp_path,
        repo_surface=repo_surface,
        mutation_loop=mutation_loop,
    )

    opened = session.open_session(goal="needs operator handoff")
    resumed = session.create_resume_point(
        opened.session_id,
        reason="crash recovery checkpoint",
        payload={"step": "before mutation"},
    )

    assert resumed.status == "resumed"
    assert len(resumed.resume_points) == 1

    handed = session.operator_handoff(
        opened.session_id,
        reason="requires approval",
        next_action="approve file mutation",
    )

    assert handed.status == "blocked"
    assert len(handed.operator_handoffs) == 1


def test_engineering_session_persists(tmp_path):
    session = RuntimeNativeEngineeringSession.with_workspace(tmp_path)

    opened = session.open_session(goal="persist engineering session")
    session.create_resume_point(opened.session_id, reason="checkpoint")

    reloaded = RuntimeNativeEngineeringSession.with_workspace(tmp_path)

    assert reloaded.get_session(opened.session_id).session_id == opened.session_id
    assert len(reloaded.engineering_timeline(opened.session_id)) >= 2
