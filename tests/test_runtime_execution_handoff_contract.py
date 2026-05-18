from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF_PATH = REPO_ROOT / "core" / "runtime" / "runtime_execution_handoff.py"

FORBIDDEN_IMPORTS = (
    "core.tasks.scheduler",
    "core.tasks.scheduler_core",
    "core.runtime.executor",
    "core.runtime.mutation_runtime_pipeline",
    "core.runtime.mutation_patch_apply",
    "core.runtime.runtime_recovery_coordinator",
    "core.runtime.runtime_recovery_policy",
    "core.runtime.runtime_replay_engine",
)

FORBIDDEN_METHODS = (
    "enqueue",
    "execute",
    "mutate",
    "recover",
    "replay",
)


def _handoff_imports() -> list[str]:
    tree = ast.parse(HANDOFF_PATH.read_text(encoding="utf-8"), filename=str(HANDOFF_PATH))
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
            continue

        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
            imports.extend(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )

    return imports


def test_runtime_execution_handoff_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_execution_handoff")

    assert module.__all__ == ["RuntimeExecutionHandoffRecord"]


def test_runtime_execution_handoff_record_shape_defaults_to_not_executed():
    module = importlib.import_module("core.runtime.runtime_execution_handoff")

    record = module.RuntimeExecutionHandoffRecord(
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        bridge_status="bridge_accepted",
        adapter_status="adapter_ready",
        authority_scope="dry_run",
        risk_level="low",
        metadata={"source": "test"},
    )

    assert record.request_id == "request-1"
    assert record.trace_id == "trace-1"
    assert record.lease_id == "lease-1"
    assert record.grant_id == "grant-1"
    assert record.bridge_status == "bridge_accepted"
    assert record.adapter_status == "adapter_ready"
    assert record.authority_scope == "dry_run"
    assert record.risk_level == "low"
    assert record.queue_admission_id is None
    assert record.queue_admission_status is None
    assert record.enqueue_id is None
    assert record.enqueue_status is None
    assert record.executed is False
    assert record.enqueued is False
    assert record.scheduler_touched is False
    assert record.metadata == {"source": "test"}


def test_runtime_execution_handoff_record_can_capture_rejection_lineage():
    module = importlib.import_module("core.runtime.runtime_execution_handoff")

    record = module.RuntimeExecutionHandoffRecord(
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        bridge_status="bridge_rejected",
        adapter_status="adapter_rejected",
        authority_scope="none",
        risk_level="unknown",
    )

    assert record.bridge_status == "bridge_rejected"
    assert record.adapter_status == "adapter_rejected"
    assert record.executed is False
    assert record.enqueued is False
    assert record.scheduler_touched is False


def test_runtime_execution_handoff_record_can_capture_queue_admission_lineage():
    module = importlib.import_module("core.runtime.runtime_execution_handoff")

    record = module.RuntimeExecutionHandoffRecord(
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        bridge_status="bridge_accepted",
        adapter_status="adapter_ready",
        authority_scope="read_only",
        risk_level="low",
        queue_admission_id="queue_admission:request-1",
        queue_admission_status="queue_admission_accepted",
    )

    assert record.queue_admission_id == "queue_admission:request-1"
    assert record.queue_admission_status == "queue_admission_accepted"
    assert record.enqueued is False
    assert record.executed is False
    assert record.scheduler_touched is False


def test_runtime_execution_handoff_record_can_capture_controlled_enqueue_lineage():
    module = importlib.import_module("core.runtime.runtime_execution_handoff")

    record = module.RuntimeExecutionHandoffRecord(
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        bridge_status="bridge_accepted",
        adapter_status="adapter_ready",
        authority_scope="dry_run",
        risk_level="low",
        queue_admission_id="queue_admission:request-1",
        queue_admission_status="queue_admission_accepted",
        enqueue_id="controlled_enqueue:request-1",
        enqueue_status="controlled_enqueue_accepted",
        enqueued=True,
        executed=False,
        scheduler_touched=True,
    )

    assert record.enqueue_id == "controlled_enqueue:request-1"
    assert record.enqueue_status == "controlled_enqueue_accepted"
    assert record.enqueued is True
    assert record.scheduler_touched is True
    assert record.executed is False


def test_runtime_execution_handoff_does_not_import_scheduler_internals():
    imports = _handoff_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_execution_handoff must not import scheduler/runtime internals:\n"
        + "\n".join(violations)
    )


def test_runtime_execution_handoff_record_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_execution_handoff")
    public_names = {
        name
        for name in dir(module.RuntimeExecutionHandoffRecord)
        if not name.startswith("_")
    }

    assert not (public_names & set(FORBIDDEN_METHODS))
