from dataclasses import dataclass, field

from core.runtime.operator_integration_bridge import OperatorIntegrationBridge
from core.runtime.operator_session_bootstrap import OperatorSessionBootstrap
from core.runtime.persistent_operator import PersistentOperatorRuntime
from tests.authority_test_support import sealed_dispatch_task
import pytest

pytestmark = [pytest.mark.contract]




@dataclass
class ObjectTask:
    task_id: str = "object-task"
    goal: str = "object goal"
    steps: list = field(default_factory=lambda: [{"id": "object-step", "type": "verify"}])
    metadata: dict = field(default_factory=dict)


def test_no_runtime_or_bridge_does_not_change_task():
    bootstrap = OperatorSessionBootstrap()
    task = {"task_id": "task-1", "goal": "goal", "steps": [{"id": "step-1"}]}
    context = {"request_id": "ctx-1"}

    result = bootstrap.ensure_session_for_task(task, context=context)

    assert result["created"] is False
    assert result["operator_session_id"] == ""
    assert "operator_session_id" not in task
    assert "operator_session_id" not in context


def test_dict_task_can_bootstrap_session():
    runtime = PersistentOperatorRuntime()
    bootstrap = OperatorSessionBootstrap(operator_bridge=OperatorIntegrationBridge(runtime))
    task = {
        "task_id": "task-1",
        "goal": "dict goal",
        "steps": [{"id": "step-1", "type": "analysis"}],
        "metadata": {"kind": "long_task"},
    }
    context = {}

    result = bootstrap.ensure_session_for_task(task, context=context)
    session = runtime.get_session(result["operator_session_id"])

    assert result["created"] is True
    assert task["operator_session_id"] == result["operator_session_id"]
    assert task["metadata"]["operator_session_id"] == result["operator_session_id"]
    assert context["operator_session_id"] == result["operator_session_id"]
    assert session is not None
    assert session.current_goal == "dict goal"
    assert session.pending_steps == ["step-1"]


def test_object_task_can_bootstrap_session():
    runtime = PersistentOperatorRuntime()
    bootstrap = OperatorSessionBootstrap(operator_runtime=runtime)
    task = ObjectTask()

    result = bootstrap.ensure_session_for_task(task)
    session = runtime.get_session(result["operator_session_id"])

    assert result["created"] is True
    assert task.operator_session_id == result["operator_session_id"]
    assert task.metadata["operator_session_id"] == result["operator_session_id"]
    assert session is not None
    assert session.task_id == "object-task"
    assert session.current_goal == "object goal"


def test_context_existing_operator_session_id_is_reused():
    bootstrap = OperatorSessionBootstrap(operator_bridge=OperatorIntegrationBridge())
    task = {"task_id": "task-1", "goal": "goal", "steps": [{"id": "step-1"}]}
    context = {"operator_session_id": "session-existing"}

    result = bootstrap.ensure_session_for_task(task, context=context)

    assert result["created"] is False
    assert result["operator_session_id"] == "session-existing"
    assert task["metadata"]["operator_session_id"] == "session-existing"


def test_task_metadata_existing_operator_session_id_is_reused():
    bootstrap = OperatorSessionBootstrap(operator_bridge=OperatorIntegrationBridge())
    task = {
        "task_id": "task-1",
        "goal": "goal",
        "steps": [{"id": "step-1"}],
        "metadata": {"operator_session_id": "session-from-metadata"},
    }
    context = {}

    result = bootstrap.ensure_session_for_task(task, context=context)

    assert result["created"] is False
    assert result["operator_session_id"] == "session-from-metadata"
    assert context["operator_session_id"] == "session-from-metadata"


def test_attach_session_id_writes_context_and_task_metadata():
    bootstrap = OperatorSessionBootstrap()
    task = {"task_id": "task-1"}
    context = {}

    result = bootstrap.attach_session_id(task=task, context=context, session_id="session-1")

    assert result["ok"] is True
    assert context["operator_session_id"] == "session-1"
    assert task["operator_session_id"] == "session-1"
    assert task["metadata"]["operator_session_id"] == "session-1"
    assert task["operator"]["session_id"] == "session-1"


def test_extract_session_id_prefers_context():
    bootstrap = OperatorSessionBootstrap()
    task = {
        "operator_session_id": "task-session",
        "metadata": {"operator_session_id": "metadata-session"},
    }
    context = {"operator_session_id": "context-session"}

    assert bootstrap.extract_session_id(task=task, context=context) == "context-session"


def test_pending_steps_and_goal_can_be_inferred_from_task():
    runtime = PersistentOperatorRuntime()
    bootstrap = OperatorSessionBootstrap(operator_runtime=runtime)
    task = {
        "task_id": "task-1",
        "description": "description goal",
        "pending_steps": [{"id": "pending-1", "type": "verify"}],
    }

    result = bootstrap.ensure_session_for_task(task)
    session = runtime.get_session(result["operator_session_id"])

    assert session is not None
    assert session.current_goal == "description goal"
    assert session.pending_steps == ["pending-1"]


def test_missing_fields_do_not_crash():
    runtime = PersistentOperatorRuntime()
    bootstrap = OperatorSessionBootstrap(operator_runtime=runtime)
    task = {}
    context = {"enable_operator_session": True}

    result = bootstrap.ensure_session_for_task(task, context=context)
    session = runtime.get_session(result["operator_session_id"])

    assert result["created"] is True
    assert session is not None
    assert session.task_id.startswith("operator-task:")
    assert session.pending_steps == []


def test_bootstrap_session_id_flows_to_task_runtime_and_step_executor(tmp_path):
    from core.runtime.step_executor import StepExecutor
    from core.runtime.task_runner import TaskRunner
    from core.runtime.task_runtime import TaskRuntime

    runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(runtime)
    bootstrap = OperatorSessionBootstrap(operator_bridge=bridge)
    task = {
        "task_id": "task-1",
        "goal": "shared session",
        "steps": [
            {"id": "runtime-step", "type": "verify"},
            {"id": "executor-step", "type": "operator_verification", "command": "noop"},
        ],
        "runtime_state_file": str(tmp_path / "runtime_state.json"),
    }
    context = {}

    result = bootstrap.ensure_session_for_task(task, context=context)
    session_id = result["operator_session_id"]
    task.update(sealed_dispatch_task(task))
    verification_step = {"id": "executor-step", "type": "operator_verification", "command": "noop"}
    authority_context = TaskRunner(step_executor=StepExecutor())._build_taskrunner_authority_context(
        task=task,
        state={},
        step=verification_step,
        upstream_context=context,
    )
    context.update(
        {
            "authority_context": authority_context,
            "runtime_authority_context": authority_context,
            "runtime_execution_capability": authority_context["runtime_execution_capability"],
            "runtime_identity_graph": task["runtime_identity_graph"],
            "runtime_capability_provenance": task["runtime_capability_provenance"],
            "runtime_authority_decision_id": task["runtime_authority_decision_id"],
            "authority_propagation_required": True,
        }
    )

    task_runtime = TaskRuntime(workspace_root=str(tmp_path), operator_bridge=bridge)
    task_runtime.ensure_runtime_state(task)
    task_runtime.advance_step(task, step_result={"ok": True, "message": "runtime step done"})

    executor = StepExecutor(workspace_root=str(tmp_path), operator_bridge=bridge)
    step_result = executor.execute_step(
        verification_step,
        task=task,
        context=context,
    )
    session = runtime.get_session(session_id)

    assert step_result["ok"] is True
    assert session is not None
    assert session.completed_steps == ["runtime-step", "executor-step"]
    assert context["operator_session_id"] == session_id
    assert task["metadata"]["operator_session_id"] == session_id
