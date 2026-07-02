from __future__ import annotations

import pytest

import core.runtime.runtime_supervisor_bridge as supervisor_bridge_module
from core.runtime.runtime_supervisor_bridge import RuntimeSupervisorBridge


class PassiveWatchdogLeaseBridge:
    def tick(self, *, current_tick, submit_to_recovery=False):
        return {
            "ok": True,
            "current_tick": current_tick,
            "submit_to_recovery": submit_to_recovery,
            "incident_count": 0,
            "incidents": [],
        }


class PassiveSupervisor:
    def process_many(self, incidents, *, current_tick=0):
        return []


class MutatingPathSentinel:
    def enqueue(self, *_args, **_kwargs):
        raise AssertionError("scheduler enqueue mutation path must not be called")

    def run_task_tick(self, *_args, **_kwargs):
        raise AssertionError("taskrunner mutation path must not be called")

    def execute_owned_step(self, *_args, **_kwargs):
        raise AssertionError("taskrunner step mutation path must not be called")

    def dispatch(self, *_args, **_kwargs):
        raise AssertionError("operator mutation path must not be called")


def _bridge(*, audit=None) -> RuntimeSupervisorBridge:
    return RuntimeSupervisorBridge(
        watchdog_lease_bridge=PassiveWatchdogLeaseBridge(),
        supervisor=PassiveSupervisor(),
        audit=audit,
    )


def _assert_evidence_is_non_executing(record):
    assert record["executes_recovery"] is False
    assert record["runtime_state_mutated"] is False
    lineage = record["audit_lineage"]
    assert lineage["executes_recovery"] is False
    assert lineage["runtime_state_mutated"] is False
    assert lineage["scheduler_mutation_allowed"] is False
    assert lineage["taskrunner_mutation_allowed"] is False
    assert lineage["operator_mutation_allowed"] is False


def test_recovery_activation_hook_disabled_is_no_op():
    result = _bridge().tick(current_tick=1).to_dict()

    activation = result["recovery_activation_result"]
    assert activation["ok"] is True
    assert activation["status"] == "disabled"
    assert activation["activated"] is False
    assert activation["no_op"] is True
    assert activation["recovery_execution_allowed"] is False
    assert activation["runtime_state_mutated"] is False
    assert activation["activation_intent"] == {}
    assert activation["dry_run_result"] == {}
    assert activation["execution_gate_result"] == {}
    assert activation["recovery_plan_result"] == {}
    import_boundary = activation["real_executor_import_boundary_result"]
    assert import_boundary["recovery_real_executor_enabled"] is False
    assert import_boundary["import_attempted"] is False
    assert import_boundary["real_executor_imported"] is False
    assert import_boundary["real_executor_invoked"] is False
    assert import_boundary["executes_recovery"] is False
    assert import_boundary["runtime_state_mutated"] is False
    assert activation["executor_binding_result"] == {}
    assert activation["executor_wiring_result"] == {}
    assert activation["executor_invocation_result"] == {}
    guard = activation["executor_invocation_guard_result"]
    assert guard["status"] == "executor_invocation_blocked"
    assert guard["invocation_allowed"] is False
    assert guard["executor_invoked"] is False
    assert guard["executes_recovery"] is False
    assert guard["runtime_state_mutated"] is False
    assert guard["conditions"]["recovery_activation_enabled"] is False
    assert len(activation["evidence_records"]) == 2
    assert activation["evidence_records"][0]["boundary_state"] == "disabled"
    assert activation["evidence_records"][-1]["boundary_state"] == "executor_invocation_blocked"
    _assert_evidence_is_non_executing(activation["evidence_records"][0])


def test_recovery_activation_hook_kill_switch_takes_priority():
    def admission(_context):
        raise AssertionError("admission must not run when kill switch is engaged")

    result = _bridge().tick(
        current_tick=2,
        recovery_activation_enabled=True,
        recovery_kill_switch_engaged=True,
        recovery_admission=admission,
    ).to_dict()

    activation = result["recovery_activation_result"]
    assert activation["status"] == "kill_switch_engaged"
    assert activation["no_op"] is True
    assert activation["admission"] == {}
    assert activation["activation_intent"] == {}
    assert activation["observation_result"] == {}
    assert activation["dry_run_result"] == {}
    assert activation["execution_gate_result"] == {}
    assert activation["recovery_plan_result"] == {}
    assert activation["executor_binding_result"] == {}
    assert activation["executor_wiring_result"] == {}
    assert activation["executor_invocation_result"] == {}
    guard = activation["executor_invocation_guard_result"]
    assert guard["status"] == "executor_invocation_blocked"
    assert guard["conditions"]["kill_switch_not_engaged"] is False
    assert guard["invocation_allowed"] is False
    assert guard["executor_invoked"] is False
    assert len(activation["evidence_records"]) == 2
    assert activation["evidence_records"][0]["boundary_state"] == "kill_switch_blocked"
    assert activation["evidence_records"][-1]["boundary_state"] == "executor_invocation_blocked"
    _assert_evidence_is_non_executing(activation["evidence_records"][0])


def test_recovery_activation_hook_admission_denied_is_no_op():
    result = _bridge().tick(
        current_tick=3,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": False, "reason": "test_denied"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    assert activation["status"] == "admission_denied"
    assert activation["reason"] == "test_denied"
    assert activation["no_op"] is True
    assert activation["recovery_execution_allowed"] is False
    assert activation["runtime_state_mutated"] is False
    assert activation["activation_intent"] == {}
    assert activation["observation_result"] == {}
    assert activation["dry_run_result"] == {}
    assert activation["execution_gate_result"] == {}
    assert activation["recovery_plan_result"] == {}
    assert activation["executor_binding_result"] == {}
    assert activation["executor_wiring_result"] == {}
    assert activation["executor_invocation_result"] == {}
    guard = activation["executor_invocation_guard_result"]
    assert guard["status"] == "executor_invocation_blocked"
    assert guard["conditions"]["admission_allowed"] is False
    assert guard["invocation_allowed"] is False
    assert guard["executor_invoked"] is False
    assert len(activation["evidence_records"]) == 2
    evidence = activation["evidence_records"][0]
    assert evidence["boundary_state"] == "admission_denied"
    assert evidence["audit_lineage"]["admission_status"] == "denied"
    assert activation["evidence_records"][-1]["boundary_state"] == "executor_invocation_blocked"
    _assert_evidence_is_non_executing(evidence)


def test_recovery_activation_hook_enabled_creates_intent_only():
    result = _bridge().tick(
        current_tick=4,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "focused_test"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    intent = activation["activation_intent"]
    observation = activation["observation_result"]
    dry_run = activation["dry_run_result"]
    gate = activation["execution_gate_result"]
    plan = activation["recovery_plan_result"]
    adapter_contract = activation["real_executor_adapter_contract_result"]
    adapter_verification = activation["real_executor_adapter_contract_verification_result"]
    import_boundary = activation["real_executor_import_boundary_result"]
    executor_binding = activation["executor_binding_result"]
    executor_wiring = activation["executor_wiring_result"]
    invocation_guard = activation["executor_invocation_guard_result"]
    invocation = activation["executor_invocation_result"]
    assert activation["status"] == "execution_gate_result_created"
    assert activation["activated"] is False
    assert activation["no_op"] is True
    assert activation["recovery_execution_allowed"] is False
    assert activation["dry_run_only"] is True
    assert intent["executes_recovery"] is False
    assert intent["runtime_state_mutated"] is False
    assert intent["scheduler_mutation_allowed"] is False
    assert intent["taskrunner_mutation_allowed"] is False
    assert observation["schema"] == "zero.runtime.recovery_observer.v1"
    assert observation["mode"] == "observer_report_only"
    assert observation["read_only"] is True
    assert observation["executes_recovery"] is False
    assert observation["executes_repair"] is False
    assert observation["operator_summary"]["activation_intent_lineage"] == intent
    assert observation["operator_summary"]["admission"]["allowed"] is True
    assert "without recovery execution" in observation["operator_summary"]["reason"]
    assert dry_run["schema"] == "zero.runtime.recovery_dry_run.v1"
    assert dry_run["mode"] == "dry_run_simulation_only"
    assert dry_run["read_only"] is True
    assert dry_run["executes_recovery"] is False
    assert dry_run["runtime_state_mutated"] is False
    assert dry_run["scheduler_mutation_allowed"] is False
    assert dry_run["taskrunner_mutation_allowed"] is False
    assert dry_run["operator_mutation_allowed"] is False
    assert gate["status"] == "execution_gate_disabled"
    assert gate["execution_gate_enabled"] is False
    assert gate["dry_run_passed"] is True
    assert gate["executes_recovery"] is False
    assert gate["recovery_execution_allowed"] is False
    assert gate["runtime_state_mutated"] is False
    assert gate["executor_invoked"] is False
    assert plan["plan_id"].startswith("runtime-recovery-plan-")
    assert plan["activation_intent_lineage"] == intent
    assert plan["admission_status"] == "allowed"
    assert plan["observation_status"] == "observation_ready"
    assert plan["dry_run_status"] == "simulated"
    assert plan["gate_status"] == "execution_gate_disabled"
    assert plan["proposed_actions"] == [
        "describe recovery planning for runtime_recovery_activation_planning"
    ]
    assert plan["risk_level"] == "low"
    assert plan["rollback_required"] is False
    assert plan["rollback_available"] is False
    assert plan["executable_plan"] is False
    assert plan["executes_recovery"] is False
    assert plan["runtime_state_mutated"] is False
    assert plan["executor_invoked"] is False
    assert plan["planner_result"]["status"] == "planned"
    assert plan["planner_result"]["descriptive_only"] is True
    assert plan["planner_result"]["execution_boundary"]["execution_allowed"] is False
    assert adapter_contract["status"] == "real_executor_adapter_contract_result_created"
    assert adapter_contract["module"] == "core.runtime.runtime_recovery_executor"
    assert adapter_contract["callable_name"] == "execute_recovery"
    assert adapter_contract["selected_executor_module"] == "core.runtime.runtime_recovery_executor"
    assert adapter_contract["selected_executor_function_name"] == "execute_recovery"
    assert adapter_contract["accepts_input"] == "recovery_plan_result"
    assert adapter_contract["required_input"] == "recovery_plan_result"
    assert adapter_contract["rejects_inputs"] == [
        "observation_result",
        "dry_run_result",
        "execution_gate_result",
    ]
    assert adapter_contract["forbidden_inputs"] == [
        "observation_result",
        "dry_run_result",
        "execution_gate_result",
    ]
    assert adapter_contract["invocation_contract_version"] == "zero.runtime.recovery.real_executor_adapter_contract.v1"
    assert adapter_contract["execution_side_effects"] == []
    assert adapter_contract["adapter_contract_verified"] is True
    assert adapter_contract["real_executor_invoked"] is False
    assert adapter_contract["executes_recovery"] is False
    assert adapter_contract["runtime_state_mutated"] is False
    assert adapter_contract["executable_adapter"] is False
    assert adapter_contract["execution_ready"] is False
    assert adapter_contract["input_contract"] == "RecoveryPlan"
    assert adapter_contract["input_source"] == "recovery_plan_result"
    assert adapter_verification["status"] == "real_executor_adapter_contract_verified"
    assert adapter_verification["adapter_contract_verified"] is True
    assert adapter_verification["executable_adapter"] is False
    assert adapter_verification["execution_ready"] is False
    assert adapter_verification["real_executor_invoked"] is False
    assert adapter_verification["executes_recovery"] is False
    assert adapter_verification["runtime_state_mutated"] is False
    assert adapter_verification["checks"] == {
        "module": True,
        "callable_name": True,
        "accepts_input": True,
        "rejects_inputs": True,
        "forbidden_inputs": True,
        "execution_side_effects": True,
    }
    assert adapter_verification["missing_or_invalid"] == []
    assert import_boundary["status"] == "real_executor_import_boundary_disabled"
    assert import_boundary["recovery_real_executor_enabled"] is False
    assert import_boundary["guard_ready"] is False
    assert import_boundary["adapter_contract_valid"] is True
    assert import_boundary["import_check_allowed"] is False
    assert import_boundary["import_attempted"] is False
    assert import_boundary["real_executor_imported"] is False
    assert import_boundary["real_executor_invoked"] is False
    assert import_boundary["executes_recovery"] is False
    assert import_boundary["runtime_state_mutated"] is False
    assert executor_binding["status"] == "executor_binding_result_created"
    assert executor_binding["executor_available"] is False
    assert executor_binding["executor_name"] == ""
    assert executor_binding["module"] == ""
    assert executor_binding["required_input"] == "recovery_plan_result"
    assert executor_binding["plan_id"] == plan["plan_id"]
    assert executor_binding["executable_plan"] is False
    assert executor_binding["execution_allowed"] is False
    assert executor_binding["executor_invoked"] is False
    assert executor_binding["executes_recovery"] is False
    assert executor_binding["runtime_state_mutated"] is False
    assert executor_wiring["status"] == "executor_wiring_disabled"
    assert executor_wiring["recovery_executor_enabled"] is False
    assert executor_wiring["executor_lookup_allowed"] is False
    assert executor_wiring["required_input"] == "recovery_plan_result"
    assert executor_wiring["input_source"] == "recovery_plan_result"
    assert executor_wiring["plan_id"] == plan["plan_id"]
    assert executor_wiring["executable_plan"] is False
    assert executor_wiring["gate_execution_allowed"] is False
    assert executor_wiring["execution_allowed"] is False
    assert executor_wiring["executor_invoked"] is False
    assert executor_wiring["executes_recovery"] is False
    assert executor_wiring["runtime_state_mutated"] is False
    assert invocation_guard["status"] == "executor_invocation_blocked"
    assert invocation_guard["required_input"] == "recovery_plan_result"
    assert invocation_guard["input_source"] == "recovery_plan_result"
    assert invocation_guard["plan_id"] == plan["plan_id"]
    assert invocation_guard["invocation_allowed"] is False
    assert invocation_guard["executor_invoked"] is False
    assert invocation_guard["executes_recovery"] is False
    assert invocation_guard["runtime_state_mutated"] is False
    assert invocation_guard["conditions"]["recovery_executor_enabled"] is False
    assert invocation_guard["conditions"]["recovery_plan_executable"] is False
    assert invocation == {}
    evidence_records = activation["evidence_records"]
    assert [item["boundary_state"] for item in evidence_records] == [
        "observation_result_created",
        "dry_run_result_created",
        "execution_gate_disabled",
        "recovery_plan_result_created",
        "executor_binding_result_created",
        "real_executor_adapter_contract_result_created",
        "real_executor_adapter_contract_verified",
        "executor_wiring_disabled",
        "executor_invocation_blocked",
        "real_executor_instance_contract_verified",
        "real_executor_instance_creation_boundary_disabled",
        "real_executor_instance_factory_contract_disabled",
        "real_executor_instance_factory_contract_verified",
        "real_executor_import_boundary_disabled",
    ]
    for evidence in evidence_records:
        _assert_evidence_is_non_executing(evidence)
    gate_evidence = evidence_records[-1]["audit_lineage"]
    assert gate_evidence["activation_intent_lineage"] == intent
    assert gate_evidence["admission_status"] == "allowed"
    assert gate_evidence["observation_status"] == "observation_ready"
    assert gate_evidence["dry_run_status"] == "simulated"
    assert gate_evidence["gate_status"] == "execution_gate_disabled"
    plan_evidence = evidence_records[-1]["audit_lineage"]
    assert plan_evidence["planning_status"] == "recovery_plan_result_created"
    assert plan_evidence["planning"]["plan_id"] == plan["plan_id"]
    assert plan_evidence["planning"]["proposed_actions"] == plan["proposed_actions"]
    assert plan_evidence["planning"]["executable_plan"] is False
    assert plan_evidence["planning"]["executor_invoked"] is False
    binding_evidence = evidence_records[-1]["audit_lineage"]
    assert binding_evidence["real_executor_adapter_contract_status"] == "real_executor_adapter_contract_result_created"
    assert binding_evidence["real_executor_adapter_contract_verification_status"] == "real_executor_adapter_contract_verified"
    assert binding_evidence["real_executor_adapter_contract"]["required_input"] == "recovery_plan_result"
    assert binding_evidence["real_executor_adapter_contract"]["accepts_input"] == "recovery_plan_result"
    assert binding_evidence["real_executor_adapter_contract"]["forbidden_inputs"] == [
        "observation_result",
        "dry_run_result",
        "execution_gate_result",
    ]
    assert binding_evidence["real_executor_adapter_contract"]["adapter_contract_verified"] is True
    assert binding_evidence["real_executor_adapter_contract"]["real_executor_invoked"] is False
    assert binding_evidence["real_executor_adapter_contract"]["executes_recovery"] is False
    assert binding_evidence["real_executor_adapter_contract"]["runtime_state_mutated"] is False
    assert binding_evidence["real_executor_adapter_contract"]["executable_adapter"] is False
    assert binding_evidence["real_executor_adapter_contract"]["execution_ready"] is False
    assert binding_evidence["real_executor_adapter_contract_verification"]["adapter_contract_verified"] is True
    assert binding_evidence["real_executor_adapter_contract_verification"]["execution_ready"] is False
    assert binding_evidence["real_executor_adapter_contract_verification"]["real_executor_invoked"] is False
    assert binding_evidence["real_executor_instance_contract_verification_status"] == "real_executor_instance_contract_verified"
    assert binding_evidence["real_executor_instance_contract_verification"]["instance_contract_verified"] is True
    assert binding_evidence["real_executor_instance_contract_verification"]["instance_attempted"] is False
    assert binding_evidence["real_executor_instance_contract_verification"]["executor_instance_created"] is False
    assert binding_evidence["real_executor_instance_contract_verification"]["real_executor_instantiated"] is False
    assert binding_evidence["real_executor_instance_contract_verification"]["real_executor_invoked"] is False
    assert binding_evidence["real_executor_instance_contract_verification"]["executes_recovery"] is False
    assert binding_evidence["real_executor_instance_creation_boundary_status"] == "real_executor_instance_creation_boundary_disabled"
    assert binding_evidence["real_executor_instance_creation_boundary"]["instance_creation_boundary_enabled"] is False
    assert binding_evidence["real_executor_instance_creation_boundary"]["instance_creation_boundary_ready"] is False
    assert binding_evidence["real_executor_instance_creation_boundary"]["instance_contract_verified"] is True
    assert binding_evidence["real_executor_instance_creation_boundary"]["instance_creation_allowed"] is False
    assert binding_evidence["real_executor_instance_creation_boundary"]["instance_attempted"] is False
    assert binding_evidence["real_executor_instance_creation_boundary"]["executor_instance_created"] is False
    assert binding_evidence["real_executor_instance_creation_boundary"]["real_executor_instantiated"] is False
    assert binding_evidence["real_executor_instance_creation_boundary"]["real_executor_invoked"] is False
    assert binding_evidence["real_executor_instance_creation_boundary"]["executes_recovery"] is False
    assert binding_evidence["real_executor_instance_factory_contract_status"] == "real_executor_instance_factory_contract_disabled"
    assert binding_evidence["real_executor_instance_factory_contract"]["factory_contract_enabled"] is False
    assert binding_evidence["real_executor_instance_factory_contract"]["factory_contract_verified"] is False
    assert binding_evidence["real_executor_instance_factory_contract"]["factory_module"] == "core.runtime.runtime_recovery_executor"
    assert binding_evidence["real_executor_instance_factory_contract"]["factory_name"] == "RuntimeRecoveryExecutor"
    assert binding_evidence["real_executor_instance_factory_contract"]["factory_method"] == "__init__"
    assert binding_evidence["real_executor_instance_factory_contract"]["accepts_input"] == "recovery_plan_result"
    assert binding_evidence["real_executor_instance_factory_contract"]["factory_attempted"] is False
    assert binding_evidence["real_executor_instance_factory_contract"]["factory_created"] is False
    assert binding_evidence["real_executor_instance_factory_contract"]["executor_instance_created"] is False
    assert binding_evidence["real_executor_instance_factory_contract"]["real_executor_instantiated"] is False
    assert binding_evidence["real_executor_instance_factory_contract"]["real_executor_invoked"] is False
    assert binding_evidence["real_executor_instance_factory_contract"]["executes_recovery"] is False
    assert binding_evidence["real_executor_instance_factory_contract"]["runtime_state_mutated"] is False
    assert binding_evidence["real_executor_instance_factory_contract_verification_status"] == "real_executor_instance_factory_contract_verified"
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["factory_contract_verified"] is True
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["factory_module"] == "core.runtime.runtime_recovery_executor"
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["factory_name"] == "RuntimeRecoveryExecutor"
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["factory_method"] == "__init__"
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["accepts_input"] == "recovery_plan_result"
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["factory_attempted"] is False
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["factory_created"] is False
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["executor_instance_created"] is False
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["real_executor_instantiated"] is False
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["real_executor_invoked"] is False
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["executes_recovery"] is False
    assert binding_evidence["real_executor_instance_factory_contract_verification"]["runtime_state_mutated"] is False
    assert binding_evidence["real_executor_import_boundary_status"] == "real_executor_import_boundary_disabled"
    assert binding_evidence["real_executor_import_boundary"]["recovery_real_executor_enabled"] is False
    assert binding_evidence["real_executor_import_boundary"]["import_attempted"] is False
    assert binding_evidence["real_executor_import_boundary"]["real_executor_imported"] is False
    assert binding_evidence["real_executor_import_boundary"]["real_executor_invoked"] is False
    assert binding_evidence["real_executor_import_boundary"]["executes_recovery"] is False
    assert binding_evidence["real_executor_import_boundary"]["runtime_state_mutated"] is False
    assert binding_evidence["executor_binding_status"] == "executor_binding_result_created"
    assert binding_evidence["executor_binding"]["executor_available"] is False
    assert binding_evidence["executor_binding"]["required_input"] == "recovery_plan_result"
    assert binding_evidence["executor_binding"]["plan_id"] == plan["plan_id"]
    assert binding_evidence["executor_binding"]["execution_allowed"] is False
    assert binding_evidence["executor_binding"]["executor_invoked"] is False
    assert binding_evidence["executor_binding"]["executes_recovery"] is False
    assert binding_evidence["executor_binding"]["runtime_state_mutated"] is False
    assert binding_evidence["executor_wiring_status"] == "executor_wiring_disabled"
    assert binding_evidence["executor_wiring"]["recovery_executor_enabled"] is False
    assert binding_evidence["executor_wiring"]["executor_lookup_allowed"] is False
    assert binding_evidence["executor_wiring"]["required_input"] == "recovery_plan_result"
    assert binding_evidence["executor_wiring"]["input_source"] == "recovery_plan_result"
    assert binding_evidence["executor_wiring"]["execution_allowed"] is False
    assert binding_evidence["executor_wiring"]["executor_invoked"] is False
    assert binding_evidence["executor_invocation_guard_status"] == "executor_invocation_blocked"
    assert binding_evidence["executor_invocation_guard"]["required_input"] == "recovery_plan_result"
    assert binding_evidence["executor_invocation_guard"]["invocation_allowed"] is False
    assert binding_evidence["executor_invocation_guard"]["executor_invoked"] is False
    assert binding_evidence["executor_invocation_guard"]["executes_recovery"] is False


def test_recovery_activation_hook_does_not_call_taskrunner_or_scheduler_mutation_paths():
    scheduler = MutatingPathSentinel()
    taskrunner = MutatingPathSentinel()
    operator = MutatingPathSentinel()

    result = _bridge().tick(
        current_tick=5,
        recovery_activation_enabled=True,
        recovery_admission={
            "allowed": True,
            "scheduler": scheduler,
            "taskrunner": taskrunner,
            "operator": operator,
        },
    ).to_dict()

    activation = result["recovery_activation_result"]
    assert activation["status"] == "execution_gate_result_created"
    assert activation["scheduler_mutation_allowed"] is False
    assert activation["taskrunner_mutation_allowed"] is False
    assert activation["operator_mutation_allowed"] is False
    assert activation["observation_result"]["invokes_scheduler"] is False
    assert activation["observation_result"]["operator_summary"]["operator_mutation_allowed"] is False
    assert activation["dry_run_result"]["scheduler_mutation_allowed"] is False
    assert activation["dry_run_result"]["taskrunner_mutation_allowed"] is False
    assert activation["dry_run_result"]["operator_mutation_allowed"] is False
    assert activation["execution_gate_result"]["scheduler_mutation_allowed"] is False
    assert activation["execution_gate_result"]["taskrunner_mutation_allowed"] is False
    assert activation["execution_gate_result"]["operator_mutation_allowed"] is False
    assert activation["execution_gate_result"]["executor_invoked"] is False
    assert activation["recovery_plan_result"]["executes_recovery"] is False
    assert activation["recovery_plan_result"]["runtime_state_mutated"] is False
    assert activation["recovery_plan_result"]["executor_invoked"] is False
    assert activation["executor_binding_result"]["required_input"] == "recovery_plan_result"
    assert activation["executor_binding_result"]["execution_allowed"] is False
    assert activation["executor_binding_result"]["executor_invoked"] is False
    assert activation["executor_binding_result"]["executes_recovery"] is False
    assert activation["executor_binding_result"]["runtime_state_mutated"] is False
    assert activation["executor_wiring_result"]["executor_invoked"] is False
    assert activation["executor_wiring_result"]["executes_recovery"] is False
    assert activation["executor_wiring_result"]["runtime_state_mutated"] is False
    assert activation["executor_invocation_guard_result"]["invocation_allowed"] is False
    assert activation["executor_invocation_guard_result"]["executor_invoked"] is False
    assert activation["executor_invocation_guard_result"]["executes_recovery"] is False
    assert activation["executor_invocation_guard_result"]["runtime_state_mutated"] is False
    assert activation["executor_invocation_result"] == {}
    for evidence in activation["evidence_records"]:
        _assert_evidence_is_non_executing(evidence)


def test_recovery_activation_hook_does_not_swallow_admission_errors():
    def broken_admission(_context):
        raise RuntimeError("admission failure")

    with pytest.raises(RuntimeError, match="admission failure"):
        _bridge().tick(
            current_tick=6,
            recovery_activation_enabled=True,
            recovery_admission=broken_admission,
        )


def test_recovery_activation_hook_enabled_path_uses_existing_observer_route(monkeypatch):
    calls = []

    def observer(source):
        calls.append(source)
        return {
            "schema": "zero.runtime.recovery_observer.v1",
            "mode": "observer_report_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_repair": False,
            "operator_summary": source["operator_summary"],
        }

    monkeypatch.setattr(supervisor_bridge_module, "observe_runtime_recovery", observer)
    monkeypatch.setattr(
        supervisor_bridge_module,
        "dry_run_runtime_recovery",
        lambda source: {
            "schema": "zero.runtime.recovery_dry_run.v1",
            "mode": "dry_run_simulation_only",
            "read_only": True,
            "ok": True,
            "executes_recovery": False,
            "source": source,
        },
    )

    result = _bridge().tick(
        current_tick=7,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "observer_route"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    assert len(calls) == 1
    assert activation["observation_result"]["schema"] == "zero.runtime.recovery_observer.v1"
    assert activation["observation_result"]["executes_recovery"] is False
    assert activation["dry_run_result"]["schema"] == "zero.runtime.recovery_dry_run.v1"
    assert activation["dry_run_result"]["executes_recovery"] is False
    assert activation["execution_gate_result"]["status"] == "execution_gate_disabled"
    assert calls[0]["operator_summary"]["activation_intent_lineage"] == activation["activation_intent"]
    assert activation["recovery_plan_result"]["executes_recovery"] is False


def test_recovery_activation_hook_enabled_path_uses_existing_dry_run_route(monkeypatch):
    calls = []

    def dry_run(source):
        calls.append(source)
        return {
            "schema": "zero.runtime.recovery_dry_run.v1",
            "mode": "dry_run_simulation_only",
            "read_only": True,
            "ok": True,
            "executes_recovery": False,
            "executes_repair": False,
            "runtime_state_mutated": False,
        }

    monkeypatch.setattr(supervisor_bridge_module, "dry_run_runtime_recovery", dry_run)

    result = _bridge().tick(
        current_tick=11,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "dry_run_route"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    assert len(calls) == 1
    assert calls[0]["activation_intent_lineage"] == activation["activation_intent"]
    assert calls[0]["observation_result"] == activation["observation_result"]
    assert calls[0]["executes_recovery"] is False
    assert activation["dry_run_result"]["executes_recovery"] is False
    assert activation["dry_run_result"]["runtime_state_mutated"] is False
    assert activation["execution_gate_result"]["status"] == "execution_gate_disabled"
    assert activation["execution_gate_result"]["executor_invoked"] is False
    assert activation["recovery_plan_result"]["planner_result"]["status"] == "planned"


def test_recovery_activation_execution_gate_enabled_observes_without_executor(monkeypatch):
    def dry_run(source):
        return {
            "schema": "zero.runtime.recovery_dry_run.v1",
            "mode": "dry_run_simulation_only",
            "read_only": True,
            "ok": True,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "source": source,
        }

    monkeypatch.setattr(supervisor_bridge_module, "dry_run_runtime_recovery", dry_run)

    result = _bridge().tick(
        current_tick=13,
        recovery_activation_enabled=True,
        recovery_execution_gate_enabled=True,
        recovery_admission={"allowed": True, "recovery_executor": MutatingPathSentinel()},
    ).to_dict()

    gate = result["recovery_activation_result"]["execution_gate_result"]
    assert gate["status"] == "execution_gate_observed"
    assert gate["execution_gate_enabled"] is True
    assert gate["dry_run_passed"] is True
    assert gate["executes_recovery"] is False
    assert gate["recovery_execution_allowed"] is False
    assert gate["runtime_state_mutated"] is False
    assert gate["executor_invoked"] is False
    plan = result["recovery_activation_result"]["recovery_plan_result"]
    assert plan["gate_status"] == "execution_gate_observed"
    assert plan["risk_level"] == "medium"
    assert plan["executable_plan"] is False
    assert plan["executes_recovery"] is False
    assert plan["runtime_state_mutated"] is False
    assert plan["executor_invoked"] is False
    binding = result["recovery_activation_result"]["executor_binding_result"]
    assert binding["required_input"] == "recovery_plan_result"
    assert binding["plan_id"] == plan["plan_id"]
    assert binding["executable_plan"] is False
    assert binding["execution_allowed"] is False
    assert binding["executor_invoked"] is False
    wiring = result["recovery_activation_result"]["executor_wiring_result"]
    assert wiring["status"] == "executor_wiring_disabled"
    assert wiring["execution_allowed"] is False
    assert wiring["executor_invoked"] is False
    assert wiring["executes_recovery"] is False
    guard = result["recovery_activation_result"]["executor_invocation_guard_result"]
    assert guard["status"] == "executor_invocation_blocked"
    assert guard["conditions"]["execution_gate_allowed"] is False
    assert guard["conditions"]["recovery_plan_executable"] is False
    assert guard["conditions"]["recovery_executor_enabled"] is False
    assert guard["invocation_allowed"] is False
    assert guard["executor_invoked"] is False
    assert result["recovery_activation_result"]["executor_invocation_result"] == {}
    evidence = result["recovery_activation_result"]["evidence_records"][-1]
    assert evidence["boundary_state"] == "real_executor_import_boundary_disabled"
    assert evidence["audit_lineage"]["real_executor_import_boundary_status"] == "real_executor_import_boundary_disabled"
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["import_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["real_executor_imported"] is False
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["real_executor_invoked"] is False
    assert evidence["audit_lineage"]["gate"]["executor_invoked"] is False
    assert evidence["audit_lineage"]["planning"]["executor_invoked"] is False
    assert evidence["audit_lineage"]["executor_binding"]["executor_invoked"] is False
    assert evidence["audit_lineage"]["executor_wiring"]["executor_invoked"] is False
    assert evidence["audit_lineage"]["executor_invocation_guard"]["executor_invoked"] is False
    _assert_evidence_is_non_executing(evidence)


def test_recovery_activation_dry_run_failed_blocks_execution_gate(monkeypatch):
    def dry_run(_source):
        return {
            "schema": "zero.runtime.recovery_dry_run.v1",
            "mode": "dry_run_simulation_only",
            "read_only": True,
            "ok": False,
            "blocked": True,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "dry_run_summary": {"status": "blocked", "would_execute_anything": False},
        }

    monkeypatch.setattr(supervisor_bridge_module, "dry_run_runtime_recovery", dry_run)

    result = _bridge().tick(
        current_tick=14,
        recovery_activation_enabled=True,
        recovery_execution_gate_enabled=True,
        recovery_admission={"allowed": True},
    ).to_dict()

    gate = result["recovery_activation_result"]["execution_gate_result"]
    assert gate["status"] == "execution_gate_blocked"
    assert gate["dry_run_passed"] is False
    assert gate["execution_gate_enabled"] is True
    assert gate["recovery_execution_allowed"] is False
    assert gate["executes_recovery"] is False
    assert gate["runtime_state_mutated"] is False
    assert gate["executor_invoked"] is False
    plan = result["recovery_activation_result"]["recovery_plan_result"]
    assert plan["gate_status"] == "execution_gate_blocked"
    assert plan["dry_run_status"] == "blocked"
    assert plan["risk_level"] == "high"
    assert plan["executable_plan"] is False
    assert plan["executes_recovery"] is False
    assert plan["runtime_state_mutated"] is False
    assert plan["executor_invoked"] is False
    assert plan["planner_result"]["status"] == "blocked"
    binding = result["recovery_activation_result"]["executor_binding_result"]
    assert binding["required_input"] == "recovery_plan_result"
    assert binding["executable_plan"] is False
    assert binding["execution_allowed"] is False
    assert binding["executor_invoked"] is False
    assert binding["executes_recovery"] is False
    assert binding["runtime_state_mutated"] is False
    wiring = result["recovery_activation_result"]["executor_wiring_result"]
    assert wiring["status"] == "executor_wiring_disabled"
    assert wiring["execution_allowed"] is False
    assert wiring["executor_invoked"] is False
    assert wiring["executes_recovery"] is False
    assert wiring["runtime_state_mutated"] is False
    guard = result["recovery_activation_result"]["executor_invocation_guard_result"]
    assert guard["status"] == "executor_invocation_blocked"
    assert guard["conditions"]["dry_run_result_passed"] is False
    assert guard["conditions"]["execution_gate_allowed"] is False
    assert guard["invocation_allowed"] is False
    assert guard["executor_invoked"] is False
    assert guard["executes_recovery"] is False
    assert guard["runtime_state_mutated"] is False
    assert result["recovery_activation_result"]["executor_invocation_result"] == {}
    evidence = result["recovery_activation_result"]["evidence_records"][-1]
    assert evidence["boundary_state"] == "real_executor_import_boundary_disabled"
    assert evidence["audit_lineage"]["dry_run_status"] == "blocked"
    assert evidence["audit_lineage"]["gate_status"] == "execution_gate_blocked"
    assert evidence["audit_lineage"]["planning_status"] == "recovery_plan_result_created"
    assert evidence["audit_lineage"]["executor_binding_status"] == "executor_binding_result_created"
    assert evidence["audit_lineage"]["executor_wiring_status"] == "executor_wiring_disabled"
    assert evidence["audit_lineage"]["executor_invocation_guard_status"] == "executor_invocation_blocked"
    assert evidence["audit_lineage"]["real_executor_import_boundary_status"] == "real_executor_import_boundary_disabled"
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["import_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["real_executor_imported"] is False
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["real_executor_invoked"] is False
    _assert_evidence_is_non_executing(evidence)


def test_recovery_activation_hook_noop_paths_do_not_touch_observer_or_dry_run_route(monkeypatch):
    def observer(_source):
        raise AssertionError("observer route must not run for no-op activation paths")

    def dry_run(_source):
        raise AssertionError("dry-run route must not run for no-op activation paths")

    monkeypatch.setattr(supervisor_bridge_module, "observe_runtime_recovery", observer)
    monkeypatch.setattr(supervisor_bridge_module, "dry_run_runtime_recovery", dry_run)

    disabled = _bridge().tick(current_tick=8).to_dict()["recovery_activation_result"]
    killed = _bridge().tick(
        current_tick=9,
        recovery_activation_enabled=True,
        recovery_kill_switch_engaged=True,
        recovery_admission={"allowed": True},
    ).to_dict()["recovery_activation_result"]
    denied = _bridge().tick(
        current_tick=10,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": False},
    ).to_dict()["recovery_activation_result"]

    assert disabled["status"] == "disabled"
    assert disabled["observation_result"] == {}
    assert disabled["dry_run_result"] == {}
    assert disabled["execution_gate_result"] == {}
    assert disabled["recovery_plan_result"] == {}
    assert disabled["executor_binding_result"] == {}
    assert disabled["executor_wiring_result"] == {}
    assert disabled["executor_invocation_result"] == {}
    assert disabled["executor_invocation_guard_result"]["status"] == "executor_invocation_blocked"
    assert disabled["evidence_records"][0]["boundary_state"] == "disabled"
    assert disabled["evidence_records"][-1]["boundary_state"] == "executor_invocation_blocked"
    assert killed["status"] == "kill_switch_engaged"
    assert killed["observation_result"] == {}
    assert killed["dry_run_result"] == {}
    assert killed["execution_gate_result"] == {}
    assert killed["recovery_plan_result"] == {}
    assert killed["executor_binding_result"] == {}
    assert killed["executor_wiring_result"] == {}
    assert killed["executor_invocation_result"] == {}
    assert killed["executor_invocation_guard_result"]["status"] == "executor_invocation_blocked"
    assert killed["evidence_records"][0]["boundary_state"] == "kill_switch_blocked"
    assert killed["evidence_records"][-1]["boundary_state"] == "executor_invocation_blocked"
    assert denied["status"] == "admission_denied"
    assert denied["observation_result"] == {}
    assert denied["dry_run_result"] == {}
    assert denied["execution_gate_result"] == {}
    assert denied["recovery_plan_result"] == {}
    assert denied["executor_binding_result"] == {}
    assert denied["executor_wiring_result"] == {}
    assert denied["executor_invocation_result"] == {}
    assert denied["executor_invocation_guard_result"]["status"] == "executor_invocation_blocked"
    assert denied["evidence_records"][0]["boundary_state"] == "admission_denied"
    assert denied["evidence_records"][-1]["boundary_state"] == "executor_invocation_blocked"


def test_recovery_activation_hook_does_not_swallow_dry_run_errors(monkeypatch):
    def broken_dry_run(_source):
        raise RuntimeError("dry-run failure")

    monkeypatch.setattr(supervisor_bridge_module, "dry_run_runtime_recovery", broken_dry_run)

    with pytest.raises(RuntimeError, match="dry-run failure"):
        _bridge().tick(
            current_tick=12,
            recovery_activation_enabled=True,
            recovery_admission={"allowed": True},
        )


def test_recovery_activation_gate_evidence_is_written_to_bridge_audit():
    audit = []

    result = _bridge(audit=audit).tick(
        current_tick=15,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True},
    ).to_dict()

    evidence_records = result["recovery_activation_result"]["evidence_records"]
    evidence_events = [
        event
        for event in audit
        if event.get("event_type") == "runtime_supervisor_bridge_recovery_gate_evidence"
    ]
    assert evidence_events
    assert evidence_events[-1]["payload"]["evidence_records"] == evidence_records
    assert evidence_records[-1]["audit_lineage"]["planning_status"] == "recovery_plan_result_created"
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract_status"] == "real_executor_adapter_contract_result_created"
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract_verification_status"] == "real_executor_adapter_contract_verified"
    assert evidence_records[-1]["audit_lineage"]["real_executor_import_boundary_status"] == "real_executor_import_boundary_disabled"
    assert evidence_records[-1]["audit_lineage"]["executor_binding_status"] == "executor_binding_result_created"
    assert evidence_records[-1]["audit_lineage"]["executor_wiring_status"] == "executor_wiring_disabled"
    assert evidence_records[-1]["audit_lineage"]["executor_invocation_guard_status"] == "executor_invocation_blocked"
    assert evidence_records[-1]["audit_lineage"]["executor_binding"]["required_input"] == "recovery_plan_result"
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract"]["required_input"] == "recovery_plan_result"
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract"]["forbidden_inputs"] == [
        "observation_result",
        "dry_run_result",
        "execution_gate_result",
    ]
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract"]["adapter_contract_verified"] is True
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract"]["real_executor_invoked"] is False
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract"]["execution_ready"] is False
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract_verification"]["adapter_contract_verified"] is True
    assert evidence_records[-1]["audit_lineage"]["real_executor_adapter_contract_verification"]["execution_ready"] is False
    assert evidence_records[-1]["audit_lineage"]["real_executor_import_boundary"]["import_attempted"] is False
    assert evidence_records[-1]["audit_lineage"]["real_executor_import_boundary"]["real_executor_imported"] is False
    assert evidence_records[-1]["audit_lineage"]["real_executor_import_boundary"]["real_executor_invoked"] is False
    assert evidence_records[-1]["audit_lineage"]["executor_wiring"]["required_input"] == "recovery_plan_result"
    assert evidence_records[-1]["audit_lineage"]["executor_invocation_guard"]["required_input"] == "recovery_plan_result"
    assert evidence_records[-1]["audit_lineage"]["executor_invocation_guard"]["invocation_allowed"] is False
    for evidence in evidence_records:
        _assert_evidence_is_non_executing(evidence)


def test_recovery_activation_uses_existing_aer_recovery_planner(monkeypatch):
    calls = []

    def planner(source, *, recovery_token=None, metadata=None):
        calls.append(
            {
                "source": source,
                "recovery_token": recovery_token,
                "metadata": metadata,
            }
        )
        return {
            "contract": "aer.runtime.recovery.plan.v1",
            "recovery_token": recovery_token,
            "eligible": True,
            "status": "planned",
            "reason": source["reason"],
            "plan_steps": ["describe recovery planning for runtime_recovery_activation_planning"],
            "execution_boundary": {"execution_allowed": False},
            "descriptive_only": True,
        }

    monkeypatch.setattr(supervisor_bridge_module, "build_recovery_plan", planner)

    result = _bridge().tick(
        current_tick=16,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True},
    ).to_dict()

    plan = result["recovery_activation_result"]["recovery_plan_result"]
    assert len(calls) == 1
    assert calls[0]["source"]["contract"] == supervisor_bridge_module.RECOVERY_ELIGIBILITY_CONTRACT
    assert calls[0]["source"]["eligible"] is True
    assert calls[0]["source"]["execution_summary"]["observation_status"] == "observation_ready"
    assert calls[0]["source"]["execution_summary"]["dry_run_status"] == "simulated"
    assert calls[0]["source"]["execution_summary"]["gate_status"] == "execution_gate_disabled"
    assert calls[0]["metadata"]["planning_reads"] == [
        "observation_result",
        "dry_run_result",
        "execution_gate_result",
    ]
    assert plan["planner_result"]["descriptive_only"] is True
    assert plan["executes_recovery"] is False
    assert plan["runtime_state_mutated"] is False
    assert plan["executor_invoked"] is False


def test_recovery_activation_executor_disabled_does_not_import_or_invoke_executor(monkeypatch):
    calls = []

    def find_spec(name):
        calls.append(name)
        raise AssertionError("executor lookup must not run when recovery_executor_enabled is false")

    monkeypatch.setattr(supervisor_bridge_module.importlib.util, "find_spec", find_spec)

    result = _bridge().tick(
        current_tick=17,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "recovery_executor": MutatingPathSentinel()},
    ).to_dict()

    binding = result["recovery_activation_result"]["executor_binding_result"]
    wiring = result["recovery_activation_result"]["executor_wiring_result"]
    import_boundary = result["recovery_activation_result"]["real_executor_import_boundary_result"]
    assert calls == []
    assert binding["executor_available"] is False
    assert binding["module"] == ""
    assert binding["required_input"] == "recovery_plan_result"
    assert binding["execution_allowed"] is False
    assert binding["executor_invoked"] is False
    assert binding["executes_recovery"] is False
    assert binding["runtime_state_mutated"] is False
    assert wiring["status"] == "executor_wiring_disabled"
    assert wiring["recovery_executor_enabled"] is False
    assert wiring["executor_lookup_allowed"] is False
    assert wiring["execution_allowed"] is False
    assert wiring["executor_invoked"] is False
    assert import_boundary["status"] == "real_executor_import_boundary_disabled"
    assert import_boundary["recovery_real_executor_enabled"] is False
    assert import_boundary["import_attempted"] is False
    assert import_boundary["real_executor_imported"] is False
    assert import_boundary["real_executor_invoked"] is False
    assert import_boundary["executes_recovery"] is False
    guard = result["recovery_activation_result"]["executor_invocation_guard_result"]
    assert guard["status"] == "executor_invocation_blocked"
    assert guard["conditions"]["recovery_executor_enabled"] is False
    assert guard["invocation_allowed"] is False
    assert guard["executor_invoked"] is False
    assert guard["executes_recovery"] is False
    assert result["recovery_activation_result"]["executor_invocation_result"] == {}


def test_recovery_activation_executor_enabled_non_executable_plan_does_not_lookup_or_call(monkeypatch):
    calls = []

    def find_spec(name):
        calls.append(name)
        raise AssertionError("executor lookup must not run for non-executable plan")

    monkeypatch.setattr(supervisor_bridge_module.importlib.util, "find_spec", find_spec)

    result = _bridge().tick(
        current_tick=18,
        recovery_activation_enabled=True,
        recovery_executor_enabled=True,
        recovery_admission={"allowed": True},
    ).to_dict()

    binding = result["recovery_activation_result"]["executor_binding_result"]
    wiring = result["recovery_activation_result"]["executor_wiring_result"]
    import_boundary = result["recovery_activation_result"]["real_executor_import_boundary_result"]
    assert calls == []
    assert binding["executor_available"] is False
    assert binding["executor_name"] == ""
    assert binding["module"] == ""
    assert binding["required_input"] == "recovery_plan_result"
    assert binding["execution_allowed"] is False
    assert binding["executor_invoked"] is False
    assert binding["executes_recovery"] is False
    assert binding["runtime_state_mutated"] is False
    assert wiring["status"] == "executor_wiring_blocked_non_executable_plan"
    assert wiring["recovery_executor_enabled"] is True
    assert wiring["executor_lookup_allowed"] is False
    assert wiring["required_input"] == "recovery_plan_result"
    assert wiring["execution_allowed"] is False
    assert wiring["executor_invoked"] is False
    assert wiring["executes_recovery"] is False
    assert wiring["runtime_state_mutated"] is False
    assert import_boundary["status"] == "real_executor_import_boundary_blocked_guard_not_ready"
    assert import_boundary["recovery_real_executor_enabled"] is True
    assert import_boundary["guard_ready"] is False
    assert import_boundary["import_attempted"] is False
    assert import_boundary["real_executor_imported"] is False
    assert import_boundary["real_executor_invoked"] is False
    assert import_boundary["executes_recovery"] is False
    guard = result["recovery_activation_result"]["executor_invocation_guard_result"]
    assert guard["status"] == "executor_invocation_blocked"
    assert guard["conditions"]["recovery_executor_enabled"] is True
    assert guard["conditions"]["recovery_plan_executable"] is False
    assert guard["invocation_allowed"] is False
    assert guard["executor_invoked"] is False
    assert result["recovery_activation_result"]["executor_invocation_result"] == {}


def test_recovery_activation_executor_enabled_gate_blocked_does_not_lookup_or_call(monkeypatch):
    calls = []

    def find_spec(name):
        calls.append(name)
        raise AssertionError("executor lookup must not run when gate is blocked")

    def dry_run(_source):
        return {
            "schema": "zero.runtime.recovery_dry_run.v1",
            "mode": "dry_run_simulation_only",
            "read_only": True,
            "ok": False,
            "blocked": True,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "dry_run_summary": {"status": "blocked", "would_execute_anything": False},
        }

    monkeypatch.setattr(supervisor_bridge_module.importlib.util, "find_spec", find_spec)
    monkeypatch.setattr(supervisor_bridge_module, "dry_run_runtime_recovery", dry_run)

    result = _bridge().tick(
        current_tick=19,
        recovery_activation_enabled=True,
        recovery_execution_gate_enabled=True,
        recovery_executor_enabled=True,
        recovery_admission={"allowed": True},
    ).to_dict()

    wiring = result["recovery_activation_result"]["executor_wiring_result"]
    adapter_contract = result["recovery_activation_result"]["real_executor_adapter_contract_result"]
    import_boundary = result["recovery_activation_result"]["real_executor_import_boundary_result"]
    assert calls == []
    assert adapter_contract["required_input"] == "recovery_plan_result"
    assert adapter_contract["accepts_input"] == "recovery_plan_result"
    assert adapter_contract["forbidden_inputs"] == [
        "observation_result",
        "dry_run_result",
        "execution_gate_result",
    ]
    assert adapter_contract["adapter_contract_verified"] is True
    assert adapter_contract["real_executor_invoked"] is False
    assert adapter_contract["executes_recovery"] is False
    assert adapter_contract["runtime_state_mutated"] is False
    assert adapter_contract["executable_adapter"] is False
    assert adapter_contract["execution_ready"] is False
    assert import_boundary["status"] == "real_executor_import_boundary_blocked_guard_not_ready"
    assert import_boundary["recovery_real_executor_enabled"] is True
    assert import_boundary["guard_ready"] is False
    assert import_boundary["import_attempted"] is False
    assert import_boundary["real_executor_imported"] is False
    assert import_boundary["real_executor_invoked"] is False
    assert import_boundary["executes_recovery"] is False
    assert wiring["status"] == "executor_wiring_blocked_non_executable_plan"
    assert wiring["gate_status"] == "execution_gate_blocked"
    assert wiring["execution_allowed"] is False
    assert wiring["executor_invoked"] is False
    assert wiring["executes_recovery"] is False
    assert wiring["runtime_state_mutated"] is False
    guard = result["recovery_activation_result"]["executor_invocation_guard_result"]
    assert guard["status"] == "executor_invocation_blocked"
    assert guard["conditions"]["dry_run_result_passed"] is False
    assert guard["conditions"]["execution_gate_allowed"] is False
    assert guard["invocation_allowed"] is False
    assert guard["executor_invoked"] is False
    assert guard["executes_recovery"] is False
    assert result["recovery_activation_result"]["executor_invocation_result"] == {}


@pytest.mark.parametrize(
    ("override", "failed_check"),
    [
        ({"module": "core.runtime.aer_runtime_recovery_executor"}, "module"),
        ({"callable_name": "execute"}, "callable_name"),
        ({"accepts_input": "dry_run_result"}, "accepts_input"),
    ],
)
def test_recovery_activation_invalid_adapter_contract_blocks_import_boundary(monkeypatch, override, failed_check):
    lookup_calls = []

    def planner(source, *, recovery_token=None, metadata=None):
        return {
            "contract": "aer.runtime.recovery.plan.v1",
            "recovery_token": recovery_token,
            "eligible": True,
            "status": "planned",
            "reason": source["reason"],
            "plan_steps": ["describe recovery planning for runtime_recovery_activation_planning"],
            "execution_boundary": {"execution_allowed": True},
            "executable_plan": True,
            "descriptive_only": True,
            "metadata": metadata or {},
        }

    def gate(self, *, activation_intent, admission, dry_run_result, enabled, metadata):
        return {
            "ok": True,
            "status": "execution_gate_allowed",
            "execution_gate_enabled": bool(enabled),
            "activation_intent_lineage": activation_intent,
            "admission": admission,
            "dry_run_passed": True,
            "executes_recovery": False,
            "recovery_execution_allowed": True,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "executor_invoked": False,
            "source": "runtime_supervisor_bridge",
            "metadata": metadata or {},
        }

    def find_spec(name):
        lookup_calls.append(name)
        raise AssertionError("invalid adapter contract must block import lookup")

    monkeypatch.setattr(supervisor_bridge_module, "build_recovery_plan", planner)
    monkeypatch.setattr(supervisor_bridge_module.RuntimeSupervisorBridge, "_evaluate_recovery_execution_gate", gate)
    monkeypatch.setattr(supervisor_bridge_module.importlib.util, "find_spec", find_spec)

    result = _bridge().tick(
        current_tick=19,
        recovery_activation_enabled=True,
        recovery_execution_gate_enabled=True,
        recovery_executor_enabled=True,
        recovery_admission={
            "allowed": True,
            "real_executor_adapter_contract_override": override,
        },
    ).to_dict()

    activation = result["recovery_activation_result"]
    verification = activation["real_executor_adapter_contract_verification_result"]
    import_boundary = activation["real_executor_import_boundary_result"]
    guard = activation["executor_invocation_guard_result"]

    assert lookup_calls == []
    assert guard["status"] == "executor_invocation_ready"
    assert guard["invocation_allowed"] is True
    assert verification["status"] == "real_executor_adapter_contract_verification_failed"
    assert verification["adapter_contract_verified"] is False
    assert verification["checks"][failed_check] is False
    assert failed_check in verification["missing_or_invalid"]
    assert verification["executable_adapter"] is False
    assert verification["execution_ready"] is False
    assert verification["real_executor_invoked"] is False
    assert verification["executes_recovery"] is False
    assert verification["runtime_state_mutated"] is False
    assert import_boundary["status"] == "real_executor_import_boundary_blocked_adapter_contract_invalid"
    assert import_boundary["adapter_contract_valid"] is False
    assert import_boundary["import_attempted"] is False
    assert import_boundary["real_executor_imported"] is False
    assert import_boundary["real_executor_invoked"] is False
    assert import_boundary["executes_recovery"] is False
    evidence = activation["evidence_records"][-1]["audit_lineage"]
    assert evidence["real_executor_adapter_contract_verification_status"] == "real_executor_adapter_contract_verification_failed"
    assert evidence["real_executor_adapter_contract_verification"]["adapter_contract_verified"] is False
    assert evidence["real_executor_import_boundary"]["import_attempted"] is False


def test_recovery_activation_executor_invocation_ready_still_does_not_call_executor(monkeypatch):
    lookup_calls = []

    def planner(source, *, recovery_token=None, metadata=None):
        return {
            "contract": "aer.runtime.recovery.plan.v1",
            "recovery_token": recovery_token,
            "eligible": True,
            "status": "planned",
            "reason": source["reason"],
            "plan_steps": ["describe recovery planning for runtime_recovery_activation_planning"],
            "execution_boundary": {"execution_allowed": True},
            "executable_plan": True,
            "descriptive_only": True,
            "metadata": metadata or {},
        }

    def gate(self, *, activation_intent, admission, dry_run_result, enabled, metadata):
        return {
            "ok": True,
            "status": "execution_gate_allowed",
            "execution_gate_enabled": bool(enabled),
            "activation_intent_lineage": activation_intent,
            "admission": admission,
            "dry_run_passed": True,
            "executes_recovery": False,
            "recovery_execution_allowed": True,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "executor_invoked": False,
            "source": "runtime_supervisor_bridge",
            "metadata": metadata or {},
        }

    def find_spec(name):
        lookup_calls.append(name)
        return object()

    monkeypatch.setattr(supervisor_bridge_module, "build_recovery_plan", planner)
    monkeypatch.setattr(supervisor_bridge_module.RuntimeSupervisorBridge, "_evaluate_recovery_execution_gate", gate)
    monkeypatch.setattr(supervisor_bridge_module.importlib.util, "find_spec", find_spec)

    result = _bridge().tick(
        current_tick=20,
        recovery_activation_enabled=True,
        recovery_execution_gate_enabled=True,
        recovery_executor_enabled=True,
        recovery_admission={"allowed": True, "recovery_executor": MutatingPathSentinel()},
    ).to_dict()

    activation = result["recovery_activation_result"]
    plan = activation["recovery_plan_result"]
    binding = activation["executor_binding_result"]
    wiring = activation["executor_wiring_result"]
    guard = activation["executor_invocation_guard_result"]
    import_boundary = activation["real_executor_import_boundary_result"]
    invocation = activation["executor_invocation_result"]

    assert lookup_calls == []
    assert plan["executable_plan"] is True
    assert plan["executes_recovery"] is False
    assert binding["required_input"] == "recovery_plan_result"
    assert binding["executor_available"] is False
    assert binding["execution_allowed"] is False
    assert binding["executor_invoked"] is False
    assert wiring["status"] == "executor_wiring_blocked_executor_unavailable"
    assert wiring["execution_allowed"] is False
    assert wiring["executor_invoked"] is False
    assert guard["status"] == "executor_invocation_ready"
    assert guard["invocation_allowed"] is True
    assert all(guard["conditions"].values())
    assert guard["required_input"] == "recovery_plan_result"
    assert guard["input_source"] == "recovery_plan_result"
    assert guard["executor_invoked"] is False
    assert guard["executes_recovery"] is False
    assert guard["runtime_state_mutated"] is False
    assert import_boundary["status"] == "real_executor_import_boundary_ready_not_imported"
    assert import_boundary["recovery_real_executor_enabled"] is True
    assert import_boundary["guard_ready"] is True
    assert import_boundary["adapter_contract_valid"] is True
    assert import_boundary["adapter_contract_verified"] is True
    assert import_boundary["import_boundary_ready"] is True
    assert import_boundary["import_boundary_decision"] == "ready_not_imported"
    assert import_boundary["blocked_reason"] == "waiting_import_phase"
    assert import_boundary["blocked"] is True
    assert import_boundary["import_check_allowed"] is False
    assert import_boundary["import_attempted"] is False
    assert import_boundary["real_executor_imported"] is False
    assert import_boundary["real_executor_invoked"] is False
    assert import_boundary["executes_recovery"] is False
    assert import_boundary["runtime_state_mutated"] is False
    assert invocation == {}
    evidence = activation["evidence_records"][-1]
    assert evidence["boundary_state"] == "real_executor_import_boundary_ready_not_imported"
    assert evidence["audit_lineage"]["executor_invocation_guard_status"] == "executor_invocation_ready"
    assert evidence["audit_lineage"]["executor_invocation_guard"]["invocation_allowed"] is True
    assert evidence["audit_lineage"]["executor_invocation_guard"]["executor_invoked"] is False
    assert evidence["audit_lineage"]["real_executor_import_boundary_status"] == "real_executor_import_boundary_ready_not_imported"
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["guard_ready"] is True
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["adapter_contract_valid"] is True
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["import_boundary_ready"] is True
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["import_boundary_decision"] == "ready_not_imported"
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["blocked_reason"] == "waiting_import_phase"
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["import_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["real_executor_imported"] is False
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["real_executor_invoked"] is False
    assert evidence["audit_lineage"]["real_executor_import_boundary"]["executes_recovery"] is False


def test_recovery_activation_records_real_executor_factory_boundary_without_instantiation():
    result = _bridge().tick(
        current_tick=21,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "factory_boundary"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    factory = activation["real_executor_factory_boundary_result"]

    assert factory["status"] == "real_executor_factory_boundary_disabled"
    assert factory["factory_boundary_enabled"] is False
    assert factory["factory_boundary_ready"] is False
    assert factory["factory_boundary_decision"] == "disabled"
    assert factory["blocked_reason"] == "disabled"
    assert factory["factory_creation_allowed"] is False
    assert factory["factory_attempted"] is False
    assert factory["factory_created"] is False
    assert factory["executor_instance_created"] is False
    assert factory["real_executor_imported"] is False
    assert factory["real_executor_instantiated"] is False
    assert factory["real_executor_invoked"] is False
    assert factory["executes_recovery"] is False
    assert factory["runtime_state_mutated"] is False

    evidence = activation["evidence_records"][-1]
    assert evidence["boundary_state"] == "real_executor_import_boundary_disabled"
    assert evidence["audit_lineage"]["real_executor_factory_boundary_status"] == "real_executor_factory_boundary_disabled"
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["factory_boundary_enabled"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["factory_boundary_ready"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["factory_creation_allowed"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["factory_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["factory_created"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["executor_instance_created"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["real_executor_imported"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["real_executor_invoked"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["executes_recovery"] is False
    assert evidence["audit_lineage"]["real_executor_factory_boundary"]["runtime_state_mutated"] is False
    _assert_evidence_is_non_executing(evidence)


def test_recovery_activation_records_real_executor_instance_contract_without_instantiation():
    result = _bridge().tick(
        current_tick=22,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "instance_contract"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    instance = activation["real_executor_instance_contract_result"]

    assert instance["status"] == "real_executor_instance_contract_disabled"
    assert instance["instance_contract_enabled"] is False
    assert instance["instance_contract_verified"] is False
    assert instance["instance_contract_ready"] is False
    assert instance["instance_contract_decision"] == "disabled"
    assert instance["blocked_reason"] == "disabled"
    assert instance["instance_type"] == "RuntimeRecoveryExecutor"
    assert instance["required_method"] == "execute_recovery"
    assert instance["required_input"] == "recovery_plan_result"
    assert instance["input_source"] == "recovery_plan_result"
    assert instance["instance_creation_allowed"] is False
    assert instance["instance_attempted"] is False
    assert instance["executor_instance_created"] is False
    assert instance["real_executor_imported"] is False
    assert instance["real_executor_instantiated"] is False
    assert instance["real_executor_invoked"] is False
    assert instance["executor_invoked"] is False
    assert instance["executes_recovery"] is False
    assert instance["runtime_state_mutated"] is False

    evidence = activation["evidence_records"][-1]
    assert evidence["audit_lineage"]["real_executor_instance_contract_status"] == "real_executor_instance_contract_disabled"
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["instance_contract_enabled"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["instance_contract_verified"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["instance_creation_allowed"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["instance_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["executor_instance_created"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["real_executor_instantiated"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["real_executor_invoked"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["executes_recovery"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract"]["runtime_state_mutated"] is False
    _assert_evidence_is_non_executing(evidence)

def test_recovery_activation_records_real_executor_instance_contract_verification_without_instantiation():
    result = _bridge().tick(
        current_tick=23,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "instance_contract_verification"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    verification = activation["real_executor_instance_contract_verification_result"]

    assert verification["status"] == "real_executor_instance_contract_verified"
    assert verification["verification_contract_version"] == "zero.runtime.recovery.real_executor_instance_contract_verification.v1"
    assert verification["checks"] == {
        "instance_type": True,
        "required_method": True,
        "required_input": True,
        "input_source": True,
        "execution_side_effects": True,
    }
    assert verification["missing_or_invalid"] == []
    assert verification["instance_contract_verified"] is True
    assert verification["instance_type"] == "RuntimeRecoveryExecutor"
    assert verification["required_method"] == "execute_recovery"
    assert verification["required_input"] == "recovery_plan_result"
    assert verification["input_source"] == "recovery_plan_result"
    assert verification["execution_side_effects"] == []
    assert verification["instance_attempted"] is False
    assert verification["executor_instance_created"] is False
    assert verification["real_executor_instantiated"] is False
    assert verification["real_executor_invoked"] is False
    assert verification["executor_invoked"] is False
    assert verification["executes_recovery"] is False
    assert verification["runtime_state_mutated"] is False

    evidence = activation["evidence_records"][-1]
    assert evidence["audit_lineage"]["real_executor_instance_contract_verification_status"] == "real_executor_instance_contract_verified"
    assert evidence["audit_lineage"]["real_executor_instance_contract_verification"]["instance_contract_verified"] is True
    assert evidence["audit_lineage"]["real_executor_instance_contract_verification"]["instance_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract_verification"]["executor_instance_created"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract_verification"]["real_executor_instantiated"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract_verification"]["real_executor_invoked"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract_verification"]["executes_recovery"] is False
    assert evidence["audit_lineage"]["real_executor_instance_contract_verification"]["runtime_state_mutated"] is False
    _assert_evidence_is_non_executing(evidence)

def test_recovery_activation_records_real_executor_instance_creation_boundary_without_instantiation():
    result = _bridge().tick(
        current_tick=24,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "instance_creation_boundary"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    boundary = activation["real_executor_instance_creation_boundary_result"]

    assert boundary["status"] == "real_executor_instance_creation_boundary_disabled"
    assert boundary["instance_creation_boundary_enabled"] is False
    assert boundary["instance_creation_boundary_ready"] is False
    assert boundary["instance_creation_boundary_decision"] == "disabled"
    assert boundary["blocked_reason"] == "disabled"
    assert boundary["blocked"] is True
    assert boundary["instance_contract_verified"] is True
    assert boundary["instance_contract_verification_status"] == "real_executor_instance_contract_verified"
    assert boundary["instance_type"] == "RuntimeRecoveryExecutor"
    assert boundary["required_method"] == "execute_recovery"
    assert boundary["required_input"] == "recovery_plan_result"
    assert boundary["input_source"] == "recovery_plan_result"
    assert boundary["instance_creation_allowed"] is False
    assert boundary["instance_attempted"] is False
    assert boundary["executor_instance_created"] is False
    assert boundary["real_executor_imported"] is False
    assert boundary["real_executor_instantiated"] is False
    assert boundary["real_executor_invoked"] is False
    assert boundary["executor_invoked"] is False
    assert boundary["executes_recovery"] is False
    assert boundary["runtime_state_mutated"] is False

    evidence = activation["evidence_records"][-1]
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary_status"] == "real_executor_instance_creation_boundary_disabled"
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["instance_creation_boundary_enabled"] is False
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["instance_creation_boundary_ready"] is False
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["instance_contract_verified"] is True
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["instance_creation_allowed"] is False
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["instance_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["executor_instance_created"] is False
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["real_executor_instantiated"] is False
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["real_executor_invoked"] is False
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["executes_recovery"] is False
    assert evidence["audit_lineage"]["real_executor_instance_creation_boundary"]["runtime_state_mutated"] is False
    _assert_evidence_is_non_executing(evidence)



def test_recovery_activation_records_real_executor_instance_factory_contract_without_resolution():
    result = _bridge().tick(
        current_tick=25,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "instance_factory_contract"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    contract = activation["real_executor_instance_factory_contract_result"]

    assert contract["status"] == "real_executor_instance_factory_contract_disabled"
    assert contract["factory_contract_enabled"] is False
    assert contract["factory_contract_verified"] is False
    assert contract["factory_contract_ready"] is False
    assert contract["factory_contract_decision"] == "disabled"
    assert contract["blocked_reason"] == "disabled"
    assert contract["blocked"] is True
    assert contract["instance_creation_boundary_ready"] is False
    assert contract["instance_creation_boundary_status"] == "real_executor_instance_creation_boundary_disabled"
    assert contract["factory_module"] == "core.runtime.runtime_recovery_executor"
    assert contract["factory_name"] == "RuntimeRecoveryExecutor"
    assert contract["factory_method"] == "__init__"
    assert contract["instance_type"] == "RuntimeRecoveryExecutor"
    assert contract["required_method"] == "execute_recovery"
    assert contract["accepts_input"] == "recovery_plan_result"
    assert contract["required_input"] == "recovery_plan_result"
    assert contract["input_source"] == "recovery_plan_result"
    assert contract["creation_contract_version"] == "zero.runtime.recovery.real_executor_instance_factory_contract.v1"
    assert contract["factory_available"] is False
    assert contract["factory_attempted"] is False
    assert contract["factory_created"] is False
    assert contract["instance_creation_allowed"] is False
    assert contract["instance_attempted"] is False
    assert contract["executor_instance_created"] is False
    assert contract["real_executor_imported"] is False
    assert contract["real_executor_instantiated"] is False
    assert contract["real_executor_invoked"] is False
    assert contract["executor_invoked"] is False
    assert contract["executes_recovery"] is False
    assert contract["runtime_state_mutated"] is False

    evidence = activation["evidence_records"][-1]
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_status"] == "real_executor_instance_factory_contract_disabled"
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["factory_contract_enabled"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["factory_contract_verified"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["factory_contract_ready"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["factory_module"] == "core.runtime.runtime_recovery_executor"
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["factory_name"] == "RuntimeRecoveryExecutor"
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["factory_method"] == "__init__"
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["factory_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["factory_created"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["executor_instance_created"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["real_executor_instantiated"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["real_executor_invoked"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["executes_recovery"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract"]["runtime_state_mutated"] is False
    _assert_evidence_is_non_executing(evidence)

def test_recovery_activation_records_real_executor_instance_factory_contract_verification_without_resolution():
    result = _bridge().tick(
        current_tick=26,
        recovery_activation_enabled=True,
        recovery_admission={"allowed": True, "rule": "instance_factory_contract_verification"},
    ).to_dict()

    activation = result["recovery_activation_result"]
    verification = activation["real_executor_instance_factory_contract_verification_result"]

    assert verification["status"] == "real_executor_instance_factory_contract_verified"
    assert verification["verification_contract_version"] == "zero.runtime.recovery.real_executor_instance_factory_contract_verification.v1"
    assert verification["factory_contract_verified"] is True
    assert verification["checks"] == {
        "factory_module": True,
        "factory_name": True,
        "factory_method": True,
        "instance_type": True,
        "required_method": True,
        "accepts_input": True,
        "creation_contract_version": True,
    }
    assert verification["missing_or_invalid"] == []
    assert verification["factory_module"] == "core.runtime.runtime_recovery_executor"
    assert verification["factory_name"] == "RuntimeRecoveryExecutor"
    assert verification["factory_method"] == "__init__"
    assert verification["instance_type"] == "RuntimeRecoveryExecutor"
    assert verification["required_method"] == "execute_recovery"
    assert verification["accepts_input"] == "recovery_plan_result"
    assert verification["required_input"] == "recovery_plan_result"
    assert verification["input_source"] == "recovery_plan_result"
    assert verification["creation_contract_version"] == "zero.runtime.recovery.real_executor_instance_factory_contract.v1"
    assert verification["factory_attempted"] is False
    assert verification["factory_created"] is False
    assert verification["executor_instance_created"] is False
    assert verification["real_executor_instantiated"] is False
    assert verification["real_executor_invoked"] is False
    assert verification["executor_invoked"] is False
    assert verification["executes_recovery"] is False
    assert verification["runtime_state_mutated"] is False

    evidence = activation["evidence_records"][-1]
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification_status"] == "real_executor_instance_factory_contract_verified"
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["factory_contract_verified"] is True
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["factory_module"] == "core.runtime.runtime_recovery_executor"
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["factory_name"] == "RuntimeRecoveryExecutor"
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["factory_method"] == "__init__"
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["factory_attempted"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["factory_created"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["executor_instance_created"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["real_executor_instantiated"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["real_executor_invoked"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["executes_recovery"] is False
    assert evidence["audit_lineage"]["real_executor_instance_factory_contract_verification"]["runtime_state_mutated"] is False
    _assert_evidence_is_non_executing(evidence)

