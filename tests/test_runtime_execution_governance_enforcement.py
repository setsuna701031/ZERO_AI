from __future__ import annotations

import ast
import importlib
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_EXECUTOR = REPO_ROOT / "core" / "runtime" / "executor.py"
APPROVED_POLICY_LAYER = REPO_ROOT / "core" / "runtime" / "runtime_execution_policy.py"
APPROVED_GATEWAY = REPO_ROOT / "core" / "runtime" / "execution_gateway.py"

SCAN_ROOTS = (
    REPO_ROOT / "core",
    REPO_ROOT / "utils",
)

EXCLUDED_PARTS = {
    "__pycache__",
    "_archive_candidate",
}

FORBIDDEN_DIRECT_CALLS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "os.system",
}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return None


def _has_shell_true(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg != "shell":
            continue
        if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
            return True
    return False


def test_repo_runtime_source_has_no_illegal_execution_surfaces():
    violations: list[str] = []

    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = _call_name(node)
            if name in FORBIDDEN_DIRECT_CALLS and path != CANONICAL_EXECUTOR:
                violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}:{name}")

            if (
                _has_shell_true(node)
                and path not in {CANONICAL_EXECUTOR, APPROVED_POLICY_LAYER, APPROVED_GATEWAY}
            ):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}:shell=True")

    assert not violations


def test_illegal_subprocess_outside_executor_is_detected(tmp_path):
    illegal = tmp_path / "illegal_execution.py"
    illegal.write_text(
        "import subprocess\n"
        "def run():\n"
        "    return subprocess.run(['echo', 'bypass'])\n",
        encoding="utf-8",
    )

    tree = _parse(illegal)
    hits = [
        _call_name(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _call_name(node) in FORBIDDEN_DIRECT_CALLS
    ]

    assert hits == ["subprocess.run"]


def test_runtime_execution_request_result_registry_policy_and_risk_are_mandatory(tmp_path):
    request_module = importlib.import_module("core.runtime.runtime_execution_request")
    executor_module = importlib.import_module("core.runtime.executor")
    result_module = importlib.import_module("core.runtime.runtime_execution_result")

    request = request_module.RuntimeExecutionRequest(
        execution_type="subprocess",
        command=(sys.executable, "-c", "print('governed')"),
        working_directory=str(tmp_path),
        timeout=20,
        metadata={
            "operation": "subprocess",
            "runtime_identity": {
                "identity_id": "system:test",
                "identity_type": "SYSTEM",
                "source": "tests",
            },
            "authority_scope_id": "authority:test",
            "capability_scope_id": "capability:test",
            "provenance": {"test": "runtime_execution_governance_enforcement"},
        },
        lineage={
            "request_id": "governance-request-1",
            "execution_start_id": "execution_start:governance-request-1",
        },
        replay_id="replay:governance-request-1",
    )

    executor = executor_module.Executor(workspace_root=tmp_path)
    result = executor.execute_request(request)

    assert isinstance(result, result_module.RuntimeExecutionResult)
    assert result.status == "succeeded"
    assert result.stdout.strip() == "governed"
    assert result.metadata["policy_evaluated"] is True
    assert result.metadata["side_effect_registry_updated"] is True
    assert result.metadata["replay_tagged"] is True
    assert result.metadata["lineage_tagged"] is True
    assert result.risk_level == "MODERATE"
    assert result.risk_metadata["policy_state"] == "allowed"
    assert result.side_effects
    assert result.side_effects[0].effect_type == "subprocess"
    assert result.side_effects[0].risk_level == "MODERATE"
    assert result.side_effects[0].rollback_metadata["rollback_required"] is False
    assert result.replay_id == "replay:governance-request-1"
    assert result.lineage["request_id"] == "governance-request-1"


def test_execution_policy_layer_exposes_required_states_and_risk_levels():
    policy_module = importlib.import_module("core.runtime.runtime_execution_policy")

    assert {
        "allowed",
        "blocked",
        "requires_confirmation",
        "dry_run_only",
        "sandbox_required",
        "rollback_required",
    } <= policy_module.EXECUTION_POLICY_STATES
    assert {
        "LOW",
        "MODERATE",
        "HIGH",
        "IRREVERSIBLE",
        "EXTERNAL",
    } <= policy_module.EXECUTION_RISK_LEVELS

    decision = policy_module.ExecutionPolicyDecision(
        state="allowed",
        reason="test",
        risk_level="LOW",
        policy_source="test",
        lineage={"request_id": "r1"},
        audit_tags=("execution",),
    )
    assert decision.allowed is True


def test_policy_rejects_non_runtime_execution_request():
    policy_module = importlib.import_module("core.runtime.runtime_execution_policy")
    policy = policy_module.RuntimeExecutionPolicy()

    try:
        policy.evaluate({"execution_type": "subprocess"})
    except TypeError as exc:
        assert "RuntimeExecutionRequest is required" in str(exc)
    else:
        raise AssertionError("policy accepted a non RuntimeExecutionRequest")


def test_replay_integrity_record_makes_consistency_observable():
    replay_module = importlib.import_module("core.runtime.runtime_replay_engine")
    engine = replay_module.RuntimeReplayEngine()

    matching = engine.record_execution_result_integrity(
        original_execution_id="execution:original",
        replay_execution_id="execution:replay",
        original_result={"status": "succeeded", "stdout": "same"},
        replay_result={"status": "succeeded", "stdout": "same"},
    )
    mismatch = engine.record_execution_result_integrity(
        original_execution_id="execution:original",
        replay_execution_id="execution:replay-2",
        original_result={"status": "succeeded", "stdout": "same"},
        replay_result={"status": "failed", "stdout": "different"},
    )

    assert isinstance(matching, replay_module.RuntimeReplayIntegrityRecord)
    assert matching.integrity_verified is True
    assert matching.mismatch_reason is None
    assert mismatch.integrity_verified is False
    assert mismatch.mismatch_reason == "result_hash_mismatch"


class RuntimeExecutionGovernanceEnforcementTest(unittest.TestCase):
    def test_repo_runtime_source_has_no_illegal_execution_surfaces(self) -> None:
        test_repo_runtime_source_has_no_illegal_execution_surfaces()

    def test_illegal_subprocess_outside_executor_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_illegal_subprocess_outside_executor_is_detected(Path(root))

    def test_runtime_execution_request_result_registry_policy_and_risk_are_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_runtime_execution_request_result_registry_policy_and_risk_are_mandatory(
                Path(root)
            )

    def test_execution_policy_layer_exposes_required_states_and_risk_levels(self) -> None:
        test_execution_policy_layer_exposes_required_states_and_risk_levels()

    def test_policy_rejects_non_runtime_execution_request(self) -> None:
        test_policy_rejects_non_runtime_execution_request()

    def test_replay_integrity_record_makes_consistency_observable(self) -> None:
        test_replay_integrity_record_makes_consistency_observable()


if __name__ == "__main__":
    unittest.main()
