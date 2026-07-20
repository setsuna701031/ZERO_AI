from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engineering.engineering_governed_workspace_mutation_executor import execute_pipeline, validate_only
from core.engineering.engineering_workspace_mutation_executor_common import safe_rel_path, sha_bytes, workspace_fingerprint

TARGET = "core/engineering/engineering_workspace_mutation_executor_common.py"
OLD = "if str(rel)=='.zero' or str(rel).startswith(TX_PARENT) or str(rel).startswith('.zero/transactions/'): rs.append('path_escape')"
NEW = "if str(rel)=='.zero' or str(rel)==TX_PARENT or str(rel).startswith(TX_PARENT + '/'): rs.append('path_escape')"


def _analysis(before_fp: str) -> dict:
    return {
        "analysis_id": "analysis-v1-8-safe-rel-path-boundary",
        "selected_production_file": TARGET,
        "observed_defect": "safe_rel_path rejects valid sibling paths whose names merely start with .zero/transactions",
        "evidence_demonstrating_defect": {"input": ".zero/transactions-log/report.txt", "before": "path_escape"},
        "bounded_repair_scope": "replace the overbroad prefix check with exact transaction directory or child matching",
        "expected_behavior_before_repair": ".zero/transactions-log/report.txt is rejected",
        "expected_behavior_after_repair": ".zero/transactions-log/report.txt is admitted while .zero/transactions/x remains rejected",
        "focused_verification_command": "python -m pytest tests/test_engineering_governed_production_repair_trial_v1_8.py -q",
        "rollback_expectations": "transaction backup captures the previous file and rollback is available on failed commit semantics",
        "prohibited_files_and_boundaries": ["Runtime Kernel", "authorization policy", "frozen schemas", "canonical identity", "canonical fingerprint"],
        "target_pre_fingerprint": before_fp,
    }


def _workspace(tmp_path: Path, *, old: bool = True) -> Path:
    root = tmp_path / "workspace"
    target = root / TARGET
    target.parent.mkdir(parents=True)
    source = Path(TARGET).read_text(encoding="utf-8")
    if old and OLD not in source:
        source = source.replace(NEW, OLD)
    with target.open("xb") as handle:
        handle.write(source.encode("utf-8"))
    with (root / "sentinel.txt").open("xb") as handle:
        handle.write(b"sentinel\n")
    return root


def _handoff(root: Path, content: str, before_fp: str, after_fp: str, *, target: str = TARGET, human: bool = True, tx: str = "txpkg-v1-8") -> dict:
    analysis = _analysis(before_fp)
    proposal_id = "proposal-v1-8-safe-rel-path-boundary"
    operation = {
        "operation_id": "op-v1-8-repair-safe-rel-path-boundary",
        "operation_type": "replace_text_file",
        "target_path": target,
        "expected_before_fingerprint": before_fp,
        "proposed_content": content,
        "expected_after_fingerprint": after_fp,
        "operation_fingerprint": sha_bytes((target + after_fp).encode()),
        "allowed_operation": "replace_text_file",
        "bounded_scope": "single existing production Python file under core/engineering",
    }
    return {
        "schema": "zero.engineering.mutation_executor_handoff.v1",
        "status": "handed_off",
        "handoff_id": "handoff-v1-8-safe-rel-path-boundary",
        "fingerprint": sha_bytes(json.dumps({"analysis": analysis["analysis_id"], "target": target, "tx": tx}, sort_keys=True).encode()),
        "workspace_id": "ws-v1-8",
        "workspace_root_fingerprint": workspace_fingerprint(root),
        "analysis": analysis,
        "proposal": {"proposal_id": proposal_id, "analysis_id": analysis["analysis_id"], "target_path": target, "expected_pre_fingerprint": before_fp, "expected_post_fingerprint": after_fp},
        "human_mutation_authorization_obtained": human,
        "human_authorization": {"authorized": human, "proposal_id": proposal_id, "target_path": TARGET, "positive_authorization_text": "AUTHORIZED v1.8 governed production repair"} if human else None,
        "authorization_verification": {"status": "verified"} if human and target == TARGET else {"status": "failed"},
        "authorization_decision": {"status": "authorized"} if human and target == TARGET else {"status": "failed"},
        "authorized_scope": {"status": "valid", "target_path": TARGET} if target == TARGET else {"status": "invalid", "target_path": TARGET},
        "transaction_planning_completed": True,
        "transaction_execution_authorized": False,
        "authorization_token": {"token_id": "atok-v1-8", "token_purpose": "workspace_mutation_transaction_admission", "use_limit": 1, "token_consumed": False},
        "preparation_token": {"token_id": "ptok-v1-8", "use_limit": 1, "token_consumed": False},
        "transaction_package": {"schema": "zero.engineering.mutation_transaction_package.v1", "status": "packaged", "transaction_package_id": tx, "fingerprint": sha_bytes(tx.encode()), "workspace_id": "ws-v1-8", "workspace_root_fingerprint": workspace_fingerprint(root), "operations": [operation]},
        "operations": [operation],
        **{k: False for k in ("authorization_token_consumed", "preparation_token_consumed", "mutation_executor_invoked", "transaction_started", "backup_created", "commit_started", "commit_completed", "rollback_performed", "recovery_performed", "mutation_performed", "filesystem_write_performed", "patch_applied", "git_invoked", "shell_invoked", "runtime_kernel_invoked", "network_invoked", "model_invoked", "adapter_invoked")},
    }


def _repair_payload(root: Path):
    target = root / TARGET
    before = target.read_text(encoding="utf-8")
    after = before.replace(OLD, NEW)
    return before, after, sha_bytes(before.encode()), sha_bytes(after.encode())


def test_authorized_production_repair_succeeds(tmp_path):
    root = _workspace(tmp_path)
    before, after, before_fp, after_fp = _repair_payload(root)
    assert before != after
    out = execute_pipeline(_handoff(root, after, before_fp, after_fp), root, True)
    assert out["result"]["status"] == "succeeded"
    assert sha_bytes((root / TARGET).read_bytes()) == after_fp
    assert (root / "sentinel.txt").read_text(encoding="utf-8") == "sentinel\n"
    assert safe_rel_path(".zero/transactions-log/report.txt") == (True, [])
    assert safe_rel_path(".zero/transactions/report.txt")[0] is False
    txdir = root / out["transaction_store"]["relative_transaction_directory"]
    assert (txdir / "manifest.json").exists() and (txdir / "journal.json").exists() and (txdir / "commit.marker.json").exists()
    assert out["execution_closure"]["status"] == "closed"


def test_missing_human_authorization_fails_closed(tmp_path):
    root = _workspace(tmp_path); before, after, before_fp, after_fp = _repair_payload(root)
    out = execute_pipeline(_handoff(root, after, before_fp, after_fp, human=False), root, True)
    assert out["executor_admission"]["status"] != "admitted"
    assert sha_bytes((root / TARGET).read_bytes()) == before_fp
    assert "execution_closure" not in out


def test_duplicate_execution_fails_closed(tmp_path):
    root = _workspace(tmp_path); before, after, before_fp, after_fp = _repair_payload(root); h = _handoff(root, after, before_fp, after_fp)
    first = execute_pipeline(h, root, True); second = execute_pipeline(h, root, True)
    assert first["result"]["status"] == "succeeded"
    assert second["failure"]["failure_code"] == "precondition_mismatch"
    assert "atomic_commit" not in second
    assert sha_bytes((root / TARGET).read_bytes()) == after_fp


@pytest.mark.parametrize("bad", ["../escape.py", "/tmp/escape.py"])
def test_workspace_escape_fails_closed(tmp_path, bad):
    root = _workspace(tmp_path); before, after, before_fp, after_fp = _repair_payload(root)
    out = validate_only(_handoff(root, after, before_fp, after_fp, target=bad), root)
    assert out["executor_admission"]["status"] != "admitted"


def test_wrong_target_scope_mismatch_fails_closed(tmp_path):
    root = _workspace(tmp_path); before, after, before_fp, after_fp = _repair_payload(root)
    out = execute_pipeline(_handoff(root, after, before_fp, after_fp, target="core/engineering/not_the_authorized_target.py"), root, True)
    assert out["executor_admission"]["status"] != "admitted"
    assert sha_bytes((root / TARGET).read_bytes()) == before_fp


def test_precondition_fingerprint_mismatch_fails_closed(tmp_path):
    root = _workspace(tmp_path); before, after, before_fp, after_fp = _repair_payload(root)
    out = execute_pipeline(_handoff(root, after, "0" * 64, after_fp), root, True)
    assert out["live_precondition"]["status"] == "not_satisfied"
    assert sha_bytes((root / TARGET).read_bytes()) == before_fp


def test_verification_failure_is_visible(tmp_path):
    root = _workspace(tmp_path); before, after, before_fp, after_fp = _repair_payload(root)
    out = execute_pipeline(_handoff(root, after, before_fp, sha_bytes(b"wrong"), tx="txpkg-v1-8-verification-fail"), root, True)
    assert out["result"]["status"] == "failed_rolled_back"
    assert out["execution_closure"]["status"] == "closed"
    assert out["post_commit_verification"]["status"] == "not_verified"
