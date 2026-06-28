from __future__ import annotations

from types import SimpleNamespace

from core.tasks.scheduler import Scheduler


def _scheduler(workspace_dir: str = "E:/zero_ai") -> Scheduler:
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.workspace_dir = workspace_dir
    scheduler.debug = False
    return scheduler


def _gateway_payload(**overrides):
    payload = {
        "contract_version": "planner_contract.v1",
        "action": "write_file",
        "raw_action": "write",
        "goal": "write file",
        "target_path": "workspace/shared/out.txt",
        "content": "hello",
        "command": "",
        "reason": "",
        "metadata": {},
        "is_valid": True,
        "contract_errors": [],
        "contract_warnings": [],
        "adapter_ok": True,
        "runtime_entry_ok": True,
        "planner_gateway_ok": True,
        "scheduler_planner_gateway_used": True,
        "scheduler_planner_legacy_fallback_used": False,
        "scheduler_planner_runtime_ok": True,
    }
    payload.update(overrides)
    return payload


def test_should_force_deterministic_task_planner_for_shared_paths_and_markers() -> None:
    scheduler = _scheduler()

    assert scheduler._should_force_deterministic_task_planner("write workspace/shared/report.txt")
    assert scheduler._should_force_deterministic_task_planner("verify the file exists at workspace/output.txt")
    assert scheduler._should_force_deterministic_task_planner("confirm that result contains alpha")
    assert scheduler._should_force_deterministic_task_planner("check if artifact exists")


def test_should_force_deterministic_task_planner_ignores_plain_goal() -> None:
    scheduler = _scheduler()

    assert not scheduler._should_force_deterministic_task_planner("summarize the project direction")


def test_plan_goal_via_agent_planners_returns_none_without_agent_loop() -> None:
    scheduler = _scheduler()
    scheduler.agent_loop = None

    assert scheduler._plan_goal_via_agent_planners("write a file") is None


def test_plan_goal_via_agent_planners_prefers_llm_planner_over_deterministic() -> None:
    class RecordingPlanner:
        def __init__(self, name: str, step_type: str) -> None:
            self.name = name
            self.step_type = step_type
            self.calls = []

        def plan(self, context=None, user_input="", route=None):
            self.calls.append({"context": context, "user_input": user_input, "route": route})
            return {
                "planner_mode": self.name,
                "intent": self.step_type,
                "steps": [{"type": self.step_type}],
            }

    llm_planner = RecordingPlanner("llm", "llm_step")
    deterministic_planner = RecordingPlanner("deterministic", "deterministic_step")
    scheduler = _scheduler()
    scheduler.agent_loop = SimpleNamespace(
        llm_planner=llm_planner,
        planner=deterministic_planner,
    )

    plan = scheduler._plan_goal_via_agent_planners("plan this")

    assert plan is not None
    assert plan["planner_mode"] == "llm"
    assert plan["steps"] == [{"type": "llm_step"}]
    assert len(llm_planner.calls) == 1
    assert deterministic_planner.calls == []


def test_plan_goal_via_agent_planners_passes_document_payload_and_route_marker() -> None:
    class CapturingPlanner:
        def __init__(self) -> None:
            self.calls = []

        def plan(self, context=None, user_input="", route=None):
            self.calls.append({"context": context, "user_input": user_input, "route": route})
            return {
                "planner_mode": "document",
                "intent": "document_task",
                "steps": [{"type": "write_file", "path": "workspace/shared/doc.txt"}],
            }

    planner = CapturingPlanner()
    scheduler = _scheduler("E:/zero_ai/workspace")
    scheduler.agent_loop = SimpleNamespace(llm_planner=planner, planner=None)

    payload = {"document_payload": {"title": "Spec"}, "document_path": "workspace/input.docx"}
    plan = scheduler._plan_goal_via_agent_planners("convert document", document_payload=payload)

    assert plan is not None
    call = planner.calls[0]
    assert call["context"]["workspace"] == "E:/zero_ai/workspace"
    assert call["context"]["document_payload"] == {"title": "Spec"}
    assert call["context"]["document_path"] == "workspace/input.docx"
    assert call["route"]["document_task"] is True


def test_call_planner_like_supports_user_input_only_signature() -> None:
    class UserInputOnlyPlanner:
        def __init__(self) -> None:
            self.received = None

        def plan(self, user_input):
            self.received = user_input
            return {"planner_mode": "single_arg", "steps": [{"type": "command", "command": "python -V"}]}

    scheduler = _scheduler()
    planner = UserInputOnlyPlanner()

    plan = scheduler._call_planner_like(
        planner,
        context={"workspace": scheduler.workspace_dir},
        user_input="show python version",
        route={"mode": "task"},
    )

    assert planner.received == "show python version"
    assert plan["steps"][0]["type"] == "command"


def test_call_planner_like_supports_context_only_signature() -> None:
    class ContextOnlyPlanner:
        def __init__(self) -> None:
            self.received = None

        def run(self, context):
            self.received = context
            return {"planner_mode": "context_only", "steps": [{"type": "read_file", "path": "README.md"}]}

    scheduler = _scheduler()
    planner = ContextOnlyPlanner()
    context = {"workspace": scheduler.workspace_dir}

    plan = scheduler._call_planner_like(
        planner,
        context=context,
        user_input="read readme",
        route={"mode": "task"},
    )

    assert planner.received == context
    assert plan["steps"][0]["type"] == "read_file"


def test_call_planner_like_gateway_compatible_plan_normalizes_to_steps() -> None:
    class GatewayCompatiblePlanner:
        def __call__(self, context=None, user_input="", route=None):
            return _gateway_payload(
                action="verify_file",
                raw_action="verify",
                goal=user_input,
                target_path="workspace/shared/out.txt",
                reason="target exists",
            )

    scheduler = _scheduler()

    raw_plan = scheduler._call_planner_like(
        GatewayCompatiblePlanner(),
        context={"workspace": scheduler.workspace_dir},
        user_input="verify output",
        route={"mode": "task"},
    )
    normalized = scheduler._normalize_external_plan(raw_plan)

    assert normalized is not None
    assert normalized["planner_mode"] == "planner_contract_gateway"
    assert normalized["intent"] == "verify_file"
    assert normalized["steps"] == [
        {
            "type": "verify",
            "path": "workspace/shared/out.txt",
            "target_path": "workspace/shared/out.txt",
            "reason": "target exists",
            "planner_contract_action": "verify_file",
        }
    ]
