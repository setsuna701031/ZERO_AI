import ast
from pathlib import Path

from core.runtime import aer_runtime_recovery_gateway as gateway


MODULE_PATH = Path("core/runtime/aer_runtime_recovery_gateway.py")
DOC_PATH = Path("docs/aer_evolution_v2_package_sequence.md")
REVIEW_PATH = Path("docs/runtime_recovery_gateway_disabled_admission_review.md")
ADMISSION_EVALUATION_ORDER = [
    "kill_switch",
    "disabled_gate",
    "future_admission_policy_reserved",
    "future_runtime_authorization_reserved",
    "future_recovery_execution_reserved",
]
RESERVED_POLICY_RESULT = {
    "enabled": False,
    "policy_status": "reserved",
    "policy_version": "v1_reserved",
    "reason": "future_package",
    "admission_granted": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}
RESERVED_AUTHORIZATION_RESULT = {
    "enabled": False,
    "authorization_status": "reserved",
    "authorization_version": "v1_reserved",
    "reason": "future_package",
    "admission_granted": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}
RESERVED_RECOVERY_EXECUTION_RESULT = {
    "enabled": False,
    "execution_status": "reserved",
    "execution_version": "v1_reserved",
    "reason": "future_package",
    "admission_granted": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}


def _gateway_result(**overrides):
    params = {
        "request_id": "request-252",
        "surface_id": "surface-252",
        "response_id": "response-252",
        "runtime_identity": {"runtime": "test", "labels": ("gateway", "disabled")},
        "recovery_reason": "disabled gateway admission review",
        "recovery_context": {"package": 252},
        "metadata": {"review": "disabled_admission"},
    }
    params.update(overrides)
    return gateway.prepare_runtime_recovery_gateway(
        **params,
    )


def test_public_api_and_all_are_strict():
    assert gateway.__all__ == ["prepare_runtime_recovery_gateway"]
    public_names = [
        name
        for name in dir(gateway)
        if not name.startswith("_") and name.startswith(("prepare", "build", "create"))
    ]
    assert public_names == ["prepare_runtime_recovery_gateway"]


def test_gateway_result_contains_surface_integration_result():
    result = _gateway_result()

    assert result["gateway_status"] == "kill_switch_blocked"
    assert result["admission_granted"] is False
    assert "surface_integration_result" in result
    surface_integration = result["surface_integration_result"]
    assert set(("request_result", "surface_result", "response_result")) <= set(surface_integration)


def test_default_kill_switch_blocks_before_disabled_admission():
    result = _gateway_result()

    assert result["admission_evaluation_order"] == ADMISSION_EVALUATION_ORDER
    assert result["admission_blocking_stage"] == "kill_switch"
    assert result["admission_denied_before_policy"] is True
    assert result["kill_switch_enabled"] is True
    assert result["kill_switch_blocked"] is True
    assert result["disabled_admission_blocked"] is False
    assert result["gateway_status"] == "kill_switch_blocked"
    assert result["admission_granted"] is False
    assert result["execution_allowed"] is False
    assert result["recovery_enabled"] is False


def test_disabled_kill_switch_still_denies_admission():
    result = _gateway_result(kill_switch_enabled=False)

    assert result["admission_evaluation_order"] == ADMISSION_EVALUATION_ORDER
    assert result["admission_blocking_stage"] == "disabled_gate"
    assert result["admission_denied_before_policy"] is True
    assert result["future_packages_must_extend_admission_chain"] is True
    assert result["future_packages_may_reorder_admission_chain"] is False
    assert result["kill_switch_enabled"] is False
    assert result["kill_switch_blocked"] is False
    assert result["disabled_admission_blocked"] is True
    assert result["gateway_status"] == "disabled"
    assert result["admission_granted"] is False
    assert result["execution_allowed"] is False
    assert result["recovery_enabled"] is False
    assert "surface_integration_result" in result


def test_reserved_policy_result_is_disabled_data_only():
    result = _gateway_result()

    assert result["policy_result"] == RESERVED_POLICY_RESULT
    assert result["policy_result"]["admission_granted"] is False
    assert result["policy_result"]["execution_allowed"] is False
    assert result["policy_result"]["recovery_enabled"] is False
    assert result["policy_result"]["runtime_state_mutated"] is False
    assert result["admission_granted"] is False
    assert result["execution_allowed"] is False
    assert result["recovery_enabled"] is False
    assert result["runtime_state_mutated"] is False


def test_reserved_authorization_result_is_disabled_data_only():
    result = _gateway_result()

    assert result["authorization_result"] == RESERVED_AUTHORIZATION_RESULT
    assert result["authorization_result"]["admission_granted"] is False
    assert result["authorization_result"]["execution_allowed"] is False
    assert result["authorization_result"]["recovery_enabled"] is False
    assert result["authorization_result"]["runtime_state_mutated"] is False
    assert result["admission_granted"] is False
    assert result["execution_allowed"] is False
    assert result["recovery_enabled"] is False
    assert result["runtime_state_mutated"] is False
    assert result["admission_evaluation_order"] == ADMISSION_EVALUATION_ORDER


def test_reserved_recovery_execution_result_is_disabled_data_only():
    result = _gateway_result()

    assert result["recovery_execution_result"] == RESERVED_RECOVERY_EXECUTION_RESULT
    assert result["recovery_execution_result"]["admission_granted"] is False
    assert result["recovery_execution_result"]["execution_allowed"] is False
    assert result["recovery_execution_result"]["recovery_enabled"] is False
    assert result["recovery_execution_result"]["runtime_state_mutated"] is False
    assert result["admission_granted"] is False
    assert result["execution_allowed"] is False
    assert result["recovery_enabled"] is False
    assert result["runtime_state_mutated"] is False
    assert result["admission_evaluation_order"] == ADMISSION_EVALUATION_ORDER


def test_execution_enablement_and_mutation_are_false_everywhere():
    result = _gateway_result()
    surface_integration = result["surface_integration_result"]

    for layer in (
        result,
        surface_integration,
        surface_integration["request_result"],
        surface_integration["surface_result"],
        surface_integration["response_result"],
    ):
        assert layer["execution_allowed"] is False
        assert layer["recovery_enabled"] is False
        assert layer["runtime_state_mutated"] is False


def test_gateway_runtime_wiring_flags_are_false():
    result = _gateway_result()

    assert result["hooks_registered"] is False
    assert result["binding_applied"] is False
    assert result["endpoint_invoked"] is False
    assert result["events_emitted"] is False
    assert result["runtime_caller_wired"] is False
    assert result["second_execution_path_created"] is False


def test_forbidden_runtime_imports_are_absent():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    assert imports == [
        "__future__",
        "core.runtime.aer_runtime_recovery_surface_integration",
    ]

    forbidden = (
        "scheduler",
        "taskrunner",
        "task_runner",
        "operator",
        "dispatcher",
        "supervisor",
        "watchdog",
        "native",
        "runtime_supervisor_bridge",
        "subprocess",
        "filesystem",
        "audit",
        "journal",
        "persistence",
    )
    assert not any(any(term in module for term in forbidden) for module in imports)


def test_no_runtime_supervisor_bridge_reference_or_extra_public_wrappers():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    public_functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]

    assert "runtime_supervisor_bridge" not in source
    assert public_functions == ["prepare_runtime_recovery_gateway"]


def test_docs_record_package_252_and_next_package_253():
    sequence = DOC_PATH.read_text(encoding="utf-8")
    review = REVIEW_PATH.read_text(encoding="utf-8")

    assert "## Package 252" in sequence
    assert "Final decision: GO. Next package: Package 253." in sequence
    assert "Future Package 253 may add kill-switch integration, still disabled." in review


def test_docs_record_package_253_and_next_package_254():
    sequence = DOC_PATH.read_text(encoding="utf-8")
    review = REVIEW_PATH.read_text(encoding="utf-8")

    assert "## Package 253" in sequence
    assert "Final decision: GO. Next package: Package 254." in sequence
    assert "kill switch has priority over disabled admission" in review
    assert "Future packages must extend this chain rather than reorder it." in sequence


def test_docs_record_package_254_and_next_package_255():
    sequence = DOC_PATH.read_text(encoding="utf-8")
    review = REVIEW_PATH.read_text(encoding="utf-8")

    assert "## Package 254" in sequence
    assert "Final decision: GO. Next package: Package 255." in sequence
    assert "Admission policy stage is reserved." in review
    assert "Policy result is disabled data only." in review


def test_docs_record_package_255_and_next_package_256():
    sequence = DOC_PATH.read_text(encoding="utf-8")
    review = REVIEW_PATH.read_text(encoding="utf-8")

    assert "## Package 255" in sequence
    assert "Final decision: GO. Next package: Package 256." in sequence
    assert "Runtime authorization stage is reserved." in review
    assert "Authorization result is disabled data only." in review


def test_docs_record_package_256_and_next_package_257():
    sequence = DOC_PATH.read_text(encoding="utf-8")
    review = REVIEW_PATH.read_text(encoding="utf-8")

    assert "## Package 256" in sequence
    assert "Final decision: GO. Next package: Package 257." in sequence
    assert "Recovery execution stage is reserved." in review
    assert "Recovery execution result is disabled data only." in review
