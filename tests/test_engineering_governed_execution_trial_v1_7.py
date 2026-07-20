from __future__ import annotations

from pathlib import Path

from core.engineering.engineering_governed_workspace_mutation_executor import execute_pipeline, validate_only
from core.engineering.engineering_workspace_mutation_executor_common import sha_bytes
from tests.engineering_workspace_mutation_executor_fixtures import handoff


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "sentinel.txt").write_text("sentinel\n", encoding="utf-8")
    return tmp_path


def _trial_handoff(root: Path, target: str = "trial_artifact.txt", content: str = "governed\n") -> dict:
    op = {
        "operation_id": "op-trial",
        "operation_type": "create_text_file",
        "target_path": target,
        "proposed_content": content,
        "expected_after_fingerprint": sha_bytes(content.encode("utf-8")),
        "operation_fingerprint": "opfp-trial",
    }
    payload = handoff(root, [op])
    payload.update(
        {
            "handoff_id": "handoff-trial-v1-7",
            "fingerprint": "handoff-fp-trial-v1-7",
            "request_id": "request-trial-v1-7",
            "session_id": "session-trial-v1-7",
            "authorization_verification": {"status": "verified"},
            "authorization_decision": {"status": "authorized"},
            "authorized_scope": {"status": "valid", "target_paths": [target]},
        }
    )
    payload["authorization_token"].update(
        {
            "request_id": "request-trial-v1-7",
            "session_id": "session-trial-v1-7",
            "transaction_package_id": payload["transaction_package"]["transaction_package_id"],
            "authorized_target_paths": [target],
        }
    )
    payload["preparation_token"].update(
        {
            "request_id": "request-trial-v1-7",
            "session_id": "session-trial-v1-7",
            "transaction_package_id": payload["transaction_package"]["transaction_package_id"],
        }
    )
    payload["transaction_package"].update(
        {
            "request_id": "request-trial-v1-7",
            "session_id": "session-trial-v1-7",
        }
    )
    return payload


def test_authorized_execution_verification_evidence_and_closure(tmp_path):
    root = _workspace(tmp_path)
    out = execute_pipeline(_trial_handoff(root), root, True)

    assert out["executor_admission"]["status"] == "admitted"
    assert out["result"]["status"] == "succeeded"
    assert out["post_commit_verification"]["status"] == "verified"
    assert out["execution_evidence"]["status"] == "recorded"
    assert out["execution_closure"]["status"] == "closed"
    assert (root / "trial_artifact.txt").read_text(encoding="utf-8") == "governed\n"
    assert not (root / "sentinel.txt").read_text(encoding="utf-8") != "sentinel\n"


def test_unauthorized_execution_rejected(tmp_path):
    root = _workspace(tmp_path)
    payload = _trial_handoff(root)
    payload["human_mutation_authorization_obtained"] = False

    out = validate_only(payload, root)

    assert out["executor_admission"]["status"] == "not_admitted"
    assert "human_authorization_missing" in out["executor_admission"]["reason_codes"]
    assert not (root / "trial_artifact.txt").exists()


def test_duplicate_execution_rejected_closed(tmp_path):
    root = _workspace(tmp_path)
    payload = _trial_handoff(root)

    first = execute_pipeline(payload, root, True)
    second = execute_pipeline(payload, root, True)

    assert first["result"]["status"] == "succeeded"
    assert second["failure"]["status"] == "failed"
    assert second["failure"]["failure_code"] == "precondition_mismatch"
    assert "target_exists" in second["live_precondition"]["reason_codes"]


def test_workspace_escape_rejected(tmp_path):
    root = _workspace(tmp_path)
    payload = _trial_handoff(root, target="../outside.txt")

    out = validate_only(payload, root)

    assert out["executor_admission"]["status"] == "not_admitted"
    assert "path_escape" in out["executor_admission"]["reason_codes"]
    assert not (tmp_path.parent / "outside.txt").exists()


def test_wrong_target_rejected_by_authorized_scope_validation(tmp_path):
    root = _workspace(tmp_path)
    payload = _trial_handoff(root)
    payload["authorized_scope"] = {"status": "invalid", "target_paths": ["different.txt"]}

    out = validate_only(payload, root)

    assert out["executor_admission"]["status"] == "not_admitted"
    assert "authorized_scope_invalid" in out["executor_admission"]["reason_codes"]
    assert not (root / "trial_artifact.txt").exists()
