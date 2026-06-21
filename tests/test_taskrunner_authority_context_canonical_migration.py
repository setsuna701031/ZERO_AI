from __future__ import annotations

from pathlib import Path

from core.goals.goal_lineage_contract import create_root_goal_lineage
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.task_runner import TaskRunner


def test_taskrunner_authority_builder_is_not_runtime_overlaid() -> None:
    source = Path(TaskRunner._build_taskrunner_authority_context.__code__.co_filename).read_text(
        encoding="utf-8-sig"
    )
    assert "TaskRunner._build_taskrunner_authority_context =" not in source
    assert TaskRunner._build_taskrunner_authority_context.__qualname__.startswith("TaskRunner.")


def test_canonical_contract_preserves_authority_identity_and_chain_domains() -> None:
    lineage = create_root_goal_lineage(
        goal_id="goal-wave1",
        session_id="operator-wave1",
        runtime_session_id="runtime-wave1",
    )
    task = {
        "task_id": "task-wave1",
        **lineage,
        "goal_lineage": lineage,
        "runtime_identity": {"identity_id": "identity-wave1"},
        "runtime_identity_graph": {**lineage, "execution_id": "execution-wave1", "capability_id": "capability-wave1"},
        "continuation_id": "continuation-wave1",
        "continuation_chain": ["root-wave1", "continuation-wave1"],
        "repair_chain_id": "repair-wave1",
        "repair_context": {"repair_chain_id": "repair-wave1", "attempt": 1},
        "authority_context": {
            "authority_layer": "scheduler",
            "authority_role": "orchestration",
            "authority_chain": [{"layer": "scheduler", "execution_authority_granted": False}],
        },
        "runtime_execution_capability": RuntimeDispatcher._execution_capability(
            {"task_id": "task-wave1", "package_id": "", "session_id": "operator-wave1"}
        ),
    }

    context = TaskRunner()._build_taskrunner_authority_context(
        task=task,
        state={},
        step={"id": "step-wave1", "type": "apply_patch"},
        upstream_context={},
    )

    assert context["authority_role"] == "canonical_delegation"
    assert context["execution_authority_granted"] is False
    assert context["runtime_identity"] == task["runtime_identity"]
    assert context["runtime_identity_graph"] == task["runtime_identity_graph"]
    assert context["goal_lineage"] == lineage
    assert context["session_id"] == "operator-wave1"
    assert context["runtime_session_id"] == "runtime-wave1"
    assert context["continuation_id"] == "continuation-wave1"
    assert context["continuation_chain"] == task["continuation_chain"]
    assert context["repair_chain_id"] == "repair-wave1"
    assert context["repair_context"] == task["repair_context"]
    assert [item["layer"] for item in context["authority_chain"]] == ["scheduler", "task_runner"]
