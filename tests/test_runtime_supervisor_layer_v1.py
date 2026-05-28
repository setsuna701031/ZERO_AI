from __future__ import annotations

from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_session_lease import (
    RuntimeSessionLeaseRegistry,
    SESSION_STATUS_TRANSFERRED,
)
from core.runtime.runtime_supervisor import (
    SUPERVISOR_CASE_STATUS_ESCALATED,
    SUPERVISOR_CASE_STATUS_FROZEN,
    SUPERVISOR_CASE_STATUS_IGNORED,
    SUPERVISOR_CASE_STATUS_RECOVERY_QUEUED,
    SUPERVISOR_CASE_STATUS_TAKEOVER_COMPLETED,
    SUPERVISOR_DECISION_FREEZE,
    SUPERVISOR_DECISION_IGNORE,
    SUPERVISOR_DECISION_RECOVER,
    SUPERVISOR_DECISION_TAKEOVER,
    RuntimeSupervisor,
    RuntimeSupervisorPolicy,
)


def test_supervisor_queues_recoverable_incident(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {"ok": True, "status": "completed"},
    )
    supervisor = RuntimeSupervisor.with_workspace(
        tmp_path / "supervisor",
        orchestrator=orchestrator,
    )

    case = supervisor.process_incident(
        {
            "incident_id": "incident-1",
            "incident_type": "runtime_session_stalled",
            "source_session_id": "session-1",
            "task_id": "task-1",
        },
        current_tick=1,
    )

    assert case.decision == SUPERVISOR_DECISION_RECOVER
    assert case.status == SUPERVISOR_CASE_STATUS_RECOVERY_QUEUED
    assert case.recovery_ticket["source_session_id"] == "session-1"


def test_supervisor_takes_over_zombie_session(tmp_path):
    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(tmp_path / "lease")
    lease_registry.register_session("session-2", task_id="task-2", current_tick=1)
    lease_registry.acquire_lease("session-2", "owner-a", current_tick=1)

    supervisor = RuntimeSupervisor.with_workspace(
        tmp_path / "supervisor",
        lease_registry=lease_registry,
    )

    case = supervisor.process_incident(
        {
            "incident_id": "incident-2",
            "incident_type": "runtime_session_zombie",
            "source_session_id": "session-2",
            "task_id": "task-2",
        },
        current_tick=2,
    )

    assert case.decision == SUPERVISOR_DECISION_TAKEOVER
    assert case.status == SUPERVISOR_CASE_STATUS_TAKEOVER_COMPLETED
    assert case.takeover_lease["owner_id"] == "runtime-supervisor"
    assert lease_registry.get_session("session-2").status == SESSION_STATUS_TRANSFERRED


def test_supervisor_freezes_critical_incident_and_escalates(tmp_path):
    supervisor = RuntimeSupervisor.with_workspace(tmp_path / "supervisor")

    case = supervisor.process_incident(
        {
            "incident_id": "incident-3",
            "incident_type": "runtime_integrity_mismatch",
            "source_session_id": "session-3",
            "task_id": "task-3",
        },
        current_tick=3,
    )

    assert case.decision == SUPERVISOR_DECISION_FREEZE
    assert case.status == SUPERVISOR_CASE_STATUS_ESCALATED
    assert case.freeze_record["source_session_id"] == "session-3"


def test_supervisor_ignored_policy(tmp_path):
    policy = RuntimeSupervisorPolicy(
        ignored_incident_types={"noise_incident"},
    )
    supervisor = RuntimeSupervisor.with_workspace(
        tmp_path / "supervisor",
        policy=policy,
    )

    case = supervisor.process_incident(
        {
            "incident_id": "incident-4",
            "incident_type": "noise_incident",
            "source_session_id": "session-4",
        },
        current_tick=4,
    )

    assert case.decision == SUPERVISOR_DECISION_IGNORE
    assert case.status == SUPERVISOR_CASE_STATUS_IGNORED


def test_supervisor_escalates_unknown_incident(tmp_path):
    supervisor = RuntimeSupervisor.with_workspace(tmp_path / "supervisor")

    case = supervisor.process_incident(
        {
            "incident_id": "incident-5",
            "incident_type": "unknown_runtime_failure",
            "source_session_id": "session-5",
        },
        current_tick=5,
    )

    assert case.status == SUPERVISOR_CASE_STATUS_ESCALATED


def test_supervisor_persists_cases(tmp_path):
    supervisor = RuntimeSupervisor.with_workspace(tmp_path / "supervisor")

    case = supervisor.intake_incident(
        {
            "incident_id": "incident-6",
            "incident_type": "runtime_session_stalled",
            "source_session_id": "session-6",
        },
        current_tick=6,
    )

    reloaded = RuntimeSupervisor.with_workspace(tmp_path / "supervisor")

    assert reloaded.get_case(case.case_id).incident_id == "incident-6"


def test_manual_freeze_case(tmp_path):
    supervisor = RuntimeSupervisor.with_workspace(tmp_path / "supervisor")
    case = supervisor.intake_incident(
        {
            "incident_id": "incident-7",
            "incident_type": "runtime_session_stalled",
            "source_session_id": "session-7",
        },
        current_tick=7,
    )

    frozen = supervisor.freeze_case(case.case_id, current_tick=8)

    assert frozen.status == SUPERVISOR_CASE_STATUS_FROZEN
    assert frozen.freeze_record["case_id"] == case.case_id
