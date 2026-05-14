from core.runtime.step_handlers import GovernedRepairMutationStepHandler


class _Executor:
    tool_registry = None


def test_governed_repair_mutation_defaults_are_conservative_for_core_file():
    handler = GovernedRepairMutationStepHandler(_Executor())

    step = {
        "id": "repair_policy_smoke",
        "type": "governed_repair_mutation",
        "task_id": "task_policy_smoke",
        "proposal_id": "proposal_policy_smoke",
        "goal": "policy smoke",
        "mutation": {
            "op_type": "write_file",
            "target_path": "core/runtime/step_handlers.py",
            "content": "# smoke\n",
        },
        "workspace_root": ".",
        "dry_run": True,
    }

    result = handler.handle(step, task={}, context={}, previous_result=None)

    assert result["ok"] is False
    assert result["error"]["type"] == "governed_repair_mutation_failed"
    assert "not_committed" in result["error"]["message"]


def test_governed_repair_mutation_blocks_without_explicit_scope_even_for_docs():
    handler = GovernedRepairMutationStepHandler(_Executor())

    step = {
        "id": "repair_policy_docs_smoke",
        "type": "governed_repair_mutation",
        "task_id": "task_policy_docs_smoke",
        "proposal_id": "proposal_policy_docs_smoke",
        "goal": "policy smoke docs",
        "mutation": {
            "op_type": "write_file",
            "target_path": "docs/repair_policy_smoke.md",
            "content": "# smoke\n",
        },
        "workspace_root": ".",
        "auto_approve": True,
        "skip_verification": True,
        "dry_run": True,
    }

    result = handler.handle(step, task={}, context={}, previous_result=None)

    assert result["ok"] is False
    assert result["error"]["type"] == "governed_repair_mutation_failed"
