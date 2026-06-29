from __future__ import annotations

import pytest

from core.engineering.verification_routing import (

    build_verification_evidence,
    build_verification_route,
    classify_verification_command,
    validate_verification_route_contract,
)
pytestmark = [pytest.mark.contract]



def test_verification_route_is_verification_only_and_requires_runtime_authority() -> None:
    profile = {
        "profile_id": "verification-profile-1",
        "proposal_id": "diff-proposal-1",
        "plan_id": "impacted-file-plan-1",
        "commands": [
            {
                "command": "python -m pytest tests/test_example.py",
                "purpose": "run targeted regression test",
            }
        ],
    }

    route = build_verification_route(profile)
    payload = route.to_dict()

    assert payload["route_id"].startswith("verification-route-")
    assert payload["source_profile_id"] == "verification-profile-1"
    assert payload["proposal_id"] == "diff-proposal-1"
    assert payload["plan_id"] == "impacted-file-plan-1"
    assert payload["metadata"]["verification_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["patch_apply_allowed"] is False
    assert payload["metadata"]["execution_authority_owned_by_runtime"] is True
    assert payload["metadata"]["canonical_success"] is False
    assert validate_verification_route_contract(payload) is True


def test_verification_route_rejects_unsafe_or_unapproved_commands() -> None:
    allowed, reason, classification = classify_verification_command(
        "python -m pytest tests/test_example.py"
    )
    assert allowed is True
    assert classification == "verification"
    assert reason

    blocked_commands = [
        "git push",
        "python -m pytest tests && git commit -m bad",
        "Remove-Item .\\core\\runtime\\executor.py",
        "pip install unknown-package",
        "python script.py > output.txt",
    ]

    for command in blocked_commands:
        allowed, reason, classification = classify_verification_command(command)
        assert allowed is False
        assert classification == "blocked"
        assert reason


def test_verification_route_contract_rejects_blocked_command_payload() -> None:
    profile = {
        "profile_id": "verification-profile-2",
        "proposal_id": "diff-proposal-2",
        "plan_id": "impacted-file-plan-2",
        "commands": ["git push"],
    }

    route = build_verification_route(profile)
    payload = route.to_dict()

    assert payload["commands"][0]["allowed"] is False
    assert validate_verification_route_contract(payload) is False


def test_verification_evidence_is_not_runtime_canonical_success() -> None:
    profile = {
        "profile_id": "verification-profile-3",
        "proposal_id": "diff-proposal-3",
        "plan_id": "impacted-file-plan-3",
        "commands": ["python -m compileall core/runtime core/tasks core/engineering"],
    }
    route = build_verification_route(profile)
    command = route.commands[0]

    evidence = build_verification_evidence(
        route,
        [
            {
                "command_id": command.command_id,
                "command": command.command,
                "returncode": 0,
                "stdout": "ok",
                "stderr": "",
            }
        ],
    )
    payload = evidence.to_dict()

    assert payload["evidence_id"].startswith("verification-evidence-")
    assert payload["status"] == "passed"
    assert payload["metadata"]["verification_evidence_only"] is True
    assert payload["metadata"]["runtime_evidence_required_for_canonical_success"] is True
    assert payload["metadata"]["canonical_success"] is False
    assert "runtime_evidence_id" not in payload
    assert "governed_mutation_lineage" not in payload


def test_verification_evidence_rejects_results_outside_route() -> None:
    profile = {
        "profile_id": "verification-profile-4",
        "proposal_id": "diff-proposal-4",
        "plan_id": "impacted-file-plan-4",
        "commands": ["python -m pytest tests/test_example.py"],
    }
    route = build_verification_route(profile)

    with pytest.raises(ValueError, match="command_result_not_in_route"):
        build_verification_evidence(
            route,
            [
                {
                    "command_id": "verification-command-not-in-route",
                    "returncode": 0,
                }
            ],
        )
