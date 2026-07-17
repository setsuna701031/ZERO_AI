from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access


ROOT = Path(__file__).resolve().parents[1]
AUDITED = (
    "core/runtime/runtime_ownership.py",
    "core/runtime/runtime_mutation_authority.py",
    "core/runtime/runtime_mutation_gateway.py",
    "core/runtime/runtime_dispatcher.py",
    "core/runtime/task_runtime.py",
    "core/runtime/task_runner.py",
)


def test_system_is_not_a_policy_wildcard() -> None:
    allowed = {
        (resource, action)
        for resource in RuntimeResource
        for action in RuntimeAction
        if can_access(RuntimeOwner.SYSTEM, resource, action)
    }
    assert allowed
    assert allowed != {(resource, action) for resource in RuntimeResource for action in RuntimeAction}
    assert can_access(RuntimeOwner.SYSTEM, RuntimeResource.QUEUE_STATE, RuntimeAction.WRITE) is False
    assert can_access(RuntimeOwner.SYSTEM, RuntimeResource.ORCHESTRATION_STATE, RuntimeAction.DISPATCH) is False


def test_audited_system_paths_have_no_wildcard_capability_defaults() -> None:
    sources = {path: (ROOT / path).read_text(encoding="utf-8-sig") for path in AUDITED}
    mutation_authority = sources["core/runtime/runtime_mutation_authority.py"]
    assert 'allowed_operations: tuple[str, ...] = ("*",)' not in mutation_authority
    assert 'allowed_targets: tuple[str, ...] = ("*",)' not in mutation_authority
    assert "return True" not in "\n".join(
        line for line in sources["core/runtime/runtime_ownership.py"].splitlines()
        if "SYSTEM" in line
    )


def test_closure_report_covers_non_mainline_issue_classes() -> None:
    report = (ROOT / "docs/runtime_system_wildcard_closure.md").read_text(encoding="utf-8")
    for issue in (
        "hidden SYSTEM paths",
        "implicit elevation",
        "authority drift",
        "ownership drift",
        "recovery bypass",
        "rollback bypass",
    ):
        assert issue in report
