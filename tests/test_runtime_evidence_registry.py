from __future__ import annotations

import inspect

from core.runtime.runtime_evidence_registry import (
    get_evidence_type,
    list_evidence_types,
    normalize_evidence_type,
    register_evidence_type,
)


def test_builtin_evidence_types_exist() -> None:
    types = {item["evidence_type"]: item for item in list_evidence_types()}

    for evidence_type in (
        "code_chain_repair_report",
        "runtime_transition",
        "recovery_report",
        "mutation_audit",
        "task_report",
    ):
        assert evidence_type in types
        assert types[evidence_type]["builtin"] is True
        assert types[evidence_type]["description"]

    assert types["code_chain_repair_report"]["schema_hint"] == "code_chain_repair_result_report_v1"


def test_normalize_evidence_type_handles_aliases_and_unknown_values() -> None:
    assert normalize_evidence_type("Code Chain Repair Result Report") == "code_chain_repair_report"
    assert normalize_evidence_type("code_chain_repair_result_report") == "code_chain_repair_report"
    assert normalize_evidence_type(" Future Recovery Evidence!! ") == "future_recovery_evidence"
    assert normalize_evidence_type("") == ""

    assert get_evidence_type("future_recovery_evidence") == {}


def test_register_evidence_type_adds_catalog_metadata_without_execution() -> None:
    item = register_evidence_type(
        "Future Recovery Evidence",
        "Future recovery evidence placeholder.",
        schema_hint="future_recovery_v1",
    )

    assert item == {
        "evidence_type": "future_recovery_evidence",
        "description": "Future recovery evidence placeholder.",
        "schema_hint": "future_recovery_v1",
        "builtin": False,
    }
    assert get_evidence_type("future recovery evidence") == item


def test_evidence_registry_is_catalog_only() -> None:
    import core.runtime.runtime_evidence_registry as registry
    from core.agent import agent_loop
    from core.tasks import scheduler

    source = inspect.getsource(registry)
    agent_loop_source = inspect.getsource(agent_loop)
    scheduler_source = inspect.getsource(scheduler)

    assert "StepExecutor" not in source
    assert "AgentLoop" not in source
    assert "execute_code_chain_attempt" not in source
    assert "autonomous_repair_loop" not in source
    assert "status = \"ok\"" not in source
    assert "runtime_evidence_registry" not in agent_loop_source
    assert "runtime_evidence_registry" not in scheduler_source
