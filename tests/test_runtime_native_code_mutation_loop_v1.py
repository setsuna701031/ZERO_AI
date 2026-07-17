from __future__ import annotations

from core.runtime.runtime_native_code_mutation_loop import (
    MUTATION_STATUS_FINALIZED,
    RuntimeNativeCodeMutationLoop,
)


def test_code_mutation_loop_applies_and_verifies(tmp_path):
    loop = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)

    result = loop.run_mutation(
        goal="write hello file",
        plan_fn=lambda goal, context: {
            "impacted_files": ["hello.txt"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "hello.txt",
                    "content": "hello",
                }
            ],
        },
        verify_fn=lambda record: {
            "ok": (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello",
            "command": "read hello.txt",
        },
    )

    assert result.status == MUTATION_STATUS_FINALIZED
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello"
    assert result.final_result["ok"] is True


def test_code_mutation_loop_repairs_after_failed_verify(tmp_path):
    loop = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)

    def verify(record):
        return {
            "ok": (tmp_path / "target.py").read_text(encoding="utf-8") == "fixed",
            "command": "target content check",
        }

    result = loop.run_mutation(
        goal="repair target",
        plan_fn=lambda goal, context: {
            "impacted_files": ["target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "target.py",
                    "content": "broken",
                }
            ],
        },
        verify_fn=verify,
        repair_fn=lambda record, failure: {
            "impacted_files": ["target.py"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "target.py",
                    "content": "fixed",
                }
            ],
        },
        max_retries=1,
    )

    assert result.status == MUTATION_STATUS_FINALIZED
    assert result.retry_count == 1
    assert result.recovery_ref["recovery_ticket"]["status"] == "queued"
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == "fixed"


def test_code_mutation_loop_persists_records(tmp_path):
    loop = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)

    result = loop.run_mutation(
        goal="persist mutation",
        plan_fn=lambda goal, context: {
            "impacted_files": ["persist.txt"],
            "actions": [
                {
                    "action_type": "write_file",
                    "target_file": "persist.txt",
                    "content": "persisted",
                }
            ],
        },
    )

    reloaded = RuntimeNativeCodeMutationLoop.with_workspace(tmp_path)

    assert reloaded.get_mutation(result.mutation_id).status == MUTATION_STATUS_FINALIZED
