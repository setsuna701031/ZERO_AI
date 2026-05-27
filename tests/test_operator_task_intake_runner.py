from __future__ import annotations

import json

from core.operator.operator_runner import result_to_json, run_operator_task
from core.runtime.execution_authority import normalize_authority_metadata, validate_authority_metadata
from core.runtime.runtime_transaction_registry import list_transactions
from scripts.run_operator_task import main


def test_cli_task_payload_can_create_operator_run() -> None:
    result = run_operator_task("scan operator serialization contract", repo_root=_repo(), dry_run=True)

    assert result["operator_run_id"].startswith("codex_operator_run:")
    assert result["edit_plan"]


def test_dry_run_does_not_mutation() -> None:
    before = tuple(tx.transaction_id for tx in list_transactions())
    result = run_operator_task("scan core operator", repo_root=_repo(), dry_run=True, allow_paths=["core/operator"])
    after = tuple(tx.transaction_id for tx in list_transactions())

    assert result["dry_run"] is True
    assert result["verification_results"] == []
    assert before == after


def test_allow_path_scope_takes_effect() -> None:
    result = run_operator_task("operator tests", repo_root=_repo(), dry_run=True, allow_paths=["core/operator"])

    assert result["selected_files"]
    assert all(path == "core/operator" or path.startswith("core/operator/") for path in result["selected_files"])


def test_runner_does_not_auto_commit_push() -> None:
    result = run_operator_task("operator smoke test", repo_root=_repo(), dry_run=True)

    assert result["git_commit"] is False
    assert result["git_push"] is False


def test_runner_result_json_serializable() -> None:
    result = run_operator_task("operator json serialization", repo_root=_repo(), dry_run=True)
    encoded = result_to_json(result)

    assert json.loads(encoded)["operator_run_id"] == result["operator_run_id"]


def test_missing_task_text_fails() -> None:
    try:
        run_operator_task("", repo_root=_repo(), dry_run=True)
    except ValueError as exc:
        assert "task text" in str(exc)
    else:
        raise AssertionError("missing task should fail")


def test_cli_missing_task_text_fails() -> None:
    try:
        main([])
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("missing CLI task should fail")


def test_operator_context_is_not_authority() -> None:
    metadata = normalize_authority_metadata(context={"operator_context": {"task": "x"}}, task={}, step={})
    validation = validate_authority_metadata(metadata, surface="operator_apply_edit")

    assert validation["ok"] is False


def _repo() -> str:
    return "E:\\zero_ai"
