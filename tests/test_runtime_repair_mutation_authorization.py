from core.tasks.runtime_repair_mutation_authorization import (
    build_runtime_repair_mutation_authorization,
)


def test_mutation_authorization_blocks_unapproved_confirmation():
    result = build_runtime_repair_mutation_authorization(
        {
            "task_id": "task-1",
            "proposal_id": "proposal-1",
            "approved": False,
            "proposal_allowed": True,
            "mutation_allowed_after_confirmation": True,
        }
    )

    assert result["authorized"] is False
    assert result["authorization_status"] == "blocked"
    assert "confirmation_not_approved" in result["reasons"]


def test_mutation_authorization_blocks_when_mutation_not_allowed():
    result = build_runtime_repair_mutation_authorization(
        {
            "approved": True,
            "proposal_allowed": True,
            "mutation_allowed_after_confirmation": False,
        }
    )

    assert result["authorized"] is False
    assert (
        "mutation_not_allowed_after_confirmation"
        in result["reasons"]
    )


def test_mutation_authorization_authorizes_valid_confirmation():
    result = build_runtime_repair_mutation_authorization(
        {
            "task_id": "task-2",
            "proposal_id": "proposal-2",
            "approved": True,
            "proposal_allowed": True,
            "mutation_allowed_after_confirmation": True,
            "allowed_next_actions": [
                "prepare_code_repair",
                "inspect_trace",
            ],
        }
    )

    assert result["authorized"] is True
    assert result["authorization_status"] == "authorized"
    assert result["allowed_actions"] == [
        "prepare_code_repair",
        "inspect_trace",
    ]
