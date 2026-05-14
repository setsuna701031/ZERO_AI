from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
    create_mutation_session,
    read_mutation_session,
    validate_mutation_file_count,
    validate_mutation_path,
    write_mutation_session,
)


def test_create_mutation_session_contract() -> None:
    scope = MutationScope(
        allowed_paths=("core/runtime", "tests"),
        denied_paths=("core/secrets",),
        max_files_changed=3,
    )

    session = create_mutation_session(
        intent="Add sandbox contract",
        initiator="manual",
        reason="Stabilize controlled mutation flow",
        scope=scope,
        risk_level=MutationRiskLevel.MEDIUM,
        approval_mode=MutationApprovalMode.REVIEW_REQUIRED,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        sandbox_run_id="run-123",
        metadata={"track": "controlled-mutation-sandbox"},
    )

    data = session.to_dict()

    assert session.session_id.startswith("mutation-session-")
    assert data["intent"] == "Add sandbox contract"
    assert data["scope"]["allowed_paths"] == ("core/runtime", "tests")
    assert data["risk_level"] == "medium"
    assert data["approval_mode"] == "review_required"
    assert data["verification"] == "targeted_tests"
    assert data["sandbox_run_id"] == "run-123"
    assert data["metadata"]["track"] == "controlled-mutation-sandbox"


def test_write_and_read_mutation_session(tmp_path: Path) -> None:
    session = create_mutation_session(
        intent="Persist mutation session",
        initiator="test",
        reason="Verify session roundtrip",
        scope=MutationScope(allowed_paths=("core/runtime",)),
        risk_level=MutationRiskLevel.LOW,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.NONE,
    )

    path = write_mutation_session(session, tmp_path)
    loaded = read_mutation_session(path)

    assert loaded.session_id == session.session_id
    assert loaded.intent == session.intent
    assert loaded.scope.allowed_paths == ("core/runtime",)
    assert loaded.risk_level == MutationRiskLevel.LOW
    assert loaded.approval_mode == MutationApprovalMode.AUTO
    assert loaded.verification == MutationVerificationRequirement.NONE


def test_mutation_path_validation_allows_scoped_paths() -> None:
    scope = MutationScope(
        allowed_paths=("core/runtime", "tests/*"),
        denied_paths=("core/runtime/secrets",),
    )

    assert validate_mutation_path("core/runtime/mutation_session.py", scope)
    assert validate_mutation_path("tests/test_mutation_session.py", scope)


def test_mutation_path_validation_denies_out_of_scope_paths() -> None:
    scope = MutationScope(
        allowed_paths=("core/runtime",),
        denied_paths=("core/runtime/secrets",),
    )

    assert not validate_mutation_path("README.md", scope)
    assert not validate_mutation_path("core/runtime/secrets/token.py", scope)


def test_mutation_path_validation_rejects_escape_paths() -> None:
    scope = MutationScope(allowed_paths=("core/runtime",))

    with pytest.raises(ValueError):
        validate_mutation_path("../outside.py", scope)


def test_mutation_scope_requires_allowed_paths() -> None:
    with pytest.raises(ValueError):
        create_mutation_session(
            intent="Bad session",
            initiator="test",
            reason="Missing allowed paths",
            scope=MutationScope(allowed_paths=()),
        )


def test_mutation_file_count_limit() -> None:
    scope = MutationScope(
        allowed_paths=("core/runtime",),
        max_files_changed=2,
    )

    assert validate_mutation_file_count(
        ["core/runtime/a.py", "core/runtime/b.py"],
        scope,
    )
    assert not validate_mutation_file_count(
        ["core/runtime/a.py", "core/runtime/b.py", "core/runtime/c.py"],
        scope,
    )