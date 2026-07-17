import ast
from pathlib import Path

from core.runtime import aer_runtime_recovery_surface_integration as integration


MODULE_PATH = Path("core/runtime/aer_runtime_recovery_surface_integration.py")
DOC_PATH = Path("docs/aer_evolution_v2_package_sequence.md")
REVIEW_PATH = Path("docs/runtime_recovery_surface_integration_disabled_review.md")


def test_public_api_and_all_are_strict():
    assert integration.__all__ == ["prepare_runtime_recovery_surface_integration"]
    public_names = [
        name
        for name in dir(integration)
        if not name.startswith("_") and name.startswith(("prepare", "build", "create"))
    ]
    assert public_names == ["prepare_runtime_recovery_surface_integration"]


def test_integration_result_contains_disabled_sub_results():
    result = integration.prepare_runtime_recovery_surface_integration(
        request_id="request-251",
        surface_id="surface-251",
        response_id="response-251",
        runtime_identity={"runtime": "test", "labels": ("disabled", "plain")},
        recovery_reason="disabled integration review",
        recovery_context={"attempt": 251},
        metadata={"package": 251},
    )

    assert result["request_result"]["request_id"] == "request-251"
    assert result["surface_result"]["surface_id"] == "surface-251"
    assert result["response_result"]["response_id"] == "response-251"
    assert set(("request_result", "surface_result", "response_result")) <= set(result)
    assert result["standalone_runtime_recovery_entry_point"] is False
    assert result["runtime_caller_wired"] is False


def test_execution_enablement_and_mutation_are_false_everywhere():
    result = integration.prepare_runtime_recovery_surface_integration(
        request_id="request-251",
        surface_id="surface-251",
        response_id="response-251",
        recovery_reason="disabled integration review",
    )

    for layer in (
        result,
        result["request_result"],
        result["surface_result"],
        result["response_result"],
    ):
        assert layer["execution_allowed"] is False
        assert layer["recovery_enabled"] is False
        assert layer["runtime_state_mutated"] is False


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
        "core.runtime.aer_runtime_recovery_canonical_request",
        "core.runtime.aer_runtime_recovery_canonical_response",
        "core.runtime.aer_runtime_recovery_canonical_surface",
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


def test_no_extra_public_prepare_build_create_wrappers():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    public_functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]
    assert public_functions == ["prepare_runtime_recovery_surface_integration"]


def test_runtime_supervisor_bridge_is_not_referenced():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "runtime_supervisor_bridge" not in source


def test_docs_record_package_251_and_next_package_252():
    sequence = DOC_PATH.read_text(encoding="utf-8")
    review = REVIEW_PATH.read_text(encoding="utf-8")

    assert "## Package 251" in sequence
    assert "Final decision: GO. Next package: Package 252." in sequence
    assert "Package 252 may add admission / kill-switch integration, still disabled." in review
