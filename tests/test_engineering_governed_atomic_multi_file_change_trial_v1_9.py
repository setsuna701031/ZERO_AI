from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core.engineering.engineering_governed_workspace_mutation_executor import execute_pipeline, validate_only
from core.engineering.engineering_workspace_mutation_executor_common import sha_bytes, workspace_fingerprint, canonical_json
from core.engineering.engineering_workspace_mutation_transaction_store import store_paths

TARGETS = (
    "core/engineering/engineering_workspace_mutation_executor_admission.py",
    "core/engineering/engineering_workspace_mutation_commit_gate.py",
)
SENTINEL = "core/engineering/sentinel_third_file.py"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel in TARGETS + (SENTINEL,):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel == SENTINEL:
            path.write_text("sentinel\n", encoding="utf-8")
        else:
            path.write_text((Path.cwd() / rel).read_text(encoding="utf-8"), encoding="utf-8")
    return root


def _fp(root: Path, rel: str) -> str:
    return sha_bytes((root / rel).read_bytes())


def _payload(root: Path, rel: str, tag: str) -> str:
    return (root / rel).read_text(encoding="utf-8") + f"\n# v1.9 isolated governed trial payload: {tag}\n"


def _ops(root: Path, *, bad_second_after: bool = False, first_before: str | None = None, second_before: str | None = None):
    payloads = [_payload(root, TARGETS[0], "admission"), _payload(root, TARGETS[1], "commit-gate")]
    after = [sha_bytes(payloads[0].encode()), sha_bytes(payloads[1].encode())]
    if bad_second_after:
        after[1] = sha_bytes(b"wrong-postcondition")
    return [
        {
            "operation_id": "v1-9-op-001-admission-scope-hardening",
            "operation_type": "replace_text_file",
            "target_path": TARGETS[0],
            "proposed_content": payloads[0],
            "expected_before_fingerprint": first_before or _fp(root, TARGETS[0]),
            "expected_after_fingerprint": after[0],
            "operation_fingerprint": sha_bytes(canonical_json({"order": 0, "target": TARGETS[0], "after": after[0]}).encode()),
        },
        {
            "operation_id": "v1-9-op-002-commit-gate-scope-hardening",
            "operation_type": "replace_text_file",
            "target_path": TARGETS[1],
            "proposed_content": payloads[1],
            "expected_before_fingerprint": second_before or _fp(root, TARGETS[1]),
            "expected_after_fingerprint": after[1],
            "operation_fingerprint": sha_bytes(canonical_json({"order": 1, "target": TARGETS[1], "after": after[1]}).encode()),
        },
    ]


def _handoff(root: Path, ops, *, human=True, scope=None, tx="v1-9-atomic-two-file"):
    scope = scope if scope is not None else {
        "status": "valid",
        "proposal_id": "proposal-v1-9-atomic-two-file",
        "transaction_id": tx,
        "authorized_operation_ids": [op["operation_id"] for op in ops],
        "authorized_target_paths": [op["target_path"] for op in ops],
        "authorized_operation_types": [op["operation_type"] for op in ops],
        "operation_count": len(ops),
        "decision": "approved",
    }
    return {
        "schema": "zero.engineering.mutation_executor_handoff.v1",
        "status": "handed_off",
        "handoff_id": f"handoff-{tx}",
        "fingerprint": sha_bytes(canonical_json({"tx": tx, "ops": [op["operation_fingerprint"] for op in ops]}).encode()),
        "workspace_id": "ws-v1-9",
        "workspace_root_fingerprint": workspace_fingerprint(root),
        "human_mutation_authorization_obtained": human,
        "transaction_planning_completed": True,
        "transaction_execution_authorized": False,
        "authorization_decision": {"status": "valid", "decision": "approved" if human else "missing"},
        "authorization_verification": {"status": "valid", "verified": human},
        "authorized_scope": scope,
        "authorization_token": {"token_id": f"atok-{tx}", "token_purpose": "workspace_mutation_transaction_admission", "use_limit": 1, "token_consumed": False},
        "preparation_token": {"token_id": f"ptok-{tx}", "use_limit": 1, "token_consumed": False},
        "transaction_package": {"schema": "zero.engineering.mutation_transaction_package.v1", "status": "packaged", "transaction_package_id": tx, "fingerprint": sha_bytes(canonical_json(ops).encode()), "operations": ops},
        "operations": ops,
        **{name: False for name in ("mutation_executor_invoked", "transaction_started", "backup_created", "commit_started", "commit_completed", "rollback_performed", "recovery_performed", "mutation_performed", "filesystem_write_performed", "patch_applied", "git_invoked", "shell_invoked", "runtime_kernel_invoked", "authorization_token_consumed", "preparation_token_consumed")},
    }


def _manifest(root, out):
    return json.loads((store_paths(type("B", (), {"root_path": root})(), out["transaction_store"]["transaction_id"])["manifest"]).read_text())


def test_authorized_atomic_two_file_production_change_succeeds(tmp_path):
    root = _root(tmp_path); before = [_fp(root, t) for t in TARGETS]; sentinel = _fp(root, SENTINEL)
    ops = _ops(root); out = execute_pipeline(_handoff(root, ops), root, True)
    assert out["result"]["status"] == "succeeded"
    assert out["executor_admission"]["operation_count"] == 2
    assert out["commit_gate"]["status"] == "authorized"
    assert out["atomic_commit"]["committed_operation_ids"] == [op["operation_id"] for op in ops]
    assert [_fp(root, t) for t in TARGETS] == [op["expected_after_fingerprint"] for op in ops]
    assert _fp(root, SENTINEL) == sentinel
    assert _manifest(root, out)["state"] == "post_commit_verified"
    assert out["execution_closure"]["status"] == "closed"
    assert before != [_fp(root, t) for t in TARGETS]


def test_missing_human_authorization_fails_closed(tmp_path):
    root = _root(tmp_path); before = [_fp(root, t) for t in TARGETS]
    out = execute_pipeline(_handoff(root, _ops(root), human=False), root, True)
    assert out["executor_admission"]["status"] != "admitted"
    assert [_fp(root, t) for t in TARGETS] == before
    assert "transaction_store" not in out


def test_partial_authorization_fails_closed(tmp_path):
    root = _root(tmp_path); ops = _ops(root); before = [_fp(root, t) for t in TARGETS]
    scope = {"status": "valid", "authorized_operation_ids": [ops[0]["operation_id"]], "authorized_target_paths": [TARGETS[0]], "authorized_operation_types": ["replace_text_file"], "operation_count": 1}
    out = validate_only(_handoff(root, ops, scope=scope), root)
    assert out["executor_admission"]["status"] != "admitted"
    assert any("scope_mismatch" in code or "count_mismatch" in code for code in out["executor_admission"]["reason_codes"])
    assert [_fp(root, t) for t in TARGETS] == before


def test_wrong_second_target_fails_closed(tmp_path):
    root = _root(tmp_path); ops = _ops(root); before = [_fp(root, t) for t in TARGETS]; sentinel = _fp(root, SENTINEL)
    bad = dict(ops[1]); bad["target_path"] = SENTINEL
    out = execute_pipeline(_handoff(root, [ops[0], bad]), root, True)
    assert out["live_precondition"]["status"] != "satisfied"
    assert [_fp(root, t) for t in TARGETS] == before and _fp(root, SENTINEL) == sentinel


def test_first_precondition_mismatch_fails_closed(tmp_path):
    root = _root(tmp_path); before = [_fp(root, t) for t in TARGETS]
    out = execute_pipeline(_handoff(root, _ops(root, first_before="bad")), root, True)
    assert out["live_precondition"]["status"] == "not_satisfied"
    assert [_fp(root, t) for t in TARGETS] == before


def test_second_precondition_mismatch_fails_closed(tmp_path):
    root = _root(tmp_path); before = [_fp(root, t) for t in TARGETS]
    out = execute_pipeline(_handoff(root, _ops(root, second_before="bad")), root, True)
    assert out["live_precondition"]["status"] == "not_satisfied"
    assert [_fp(root, t) for t in TARGETS] == before


def test_mid_transaction_second_operation_failure_rolls_back_both(tmp_path, monkeypatch):
    root = _root(tmp_path); before = [_fp(root, t) for t in TARGETS]; ops = _ops(root)
    original = Path.replace; calls = {"count": 0}
    def fail_second_staged_replace(self, target):
        if str(self).endswith("staged-1.txt"):
            calls["count"] += 1
            raise OSError("deterministic second operation failure")
        return original(self, target)
    monkeypatch.setattr(Path, "replace", fail_second_staged_replace)
    out = execute_pipeline(_handoff(root, ops, tx="v1-9-mid-fail"), root, True)
    assert calls["count"] == 1
    assert out["atomic_commit"]["status"] == "partially_committed"
    assert out["rollback"]["status"] == "rolled_back"
    assert out["result"]["status"] == "failed_rolled_back"
    assert [_fp(root, t) for t in TARGETS] == before
    assert not (root / ".zero" / "transactions" / out["transaction_store"]["transaction_id"] / "commit.marker.json").exists()


def test_duplicate_execution_fails_closed(tmp_path):
    root = _root(tmp_path); ops = _ops(root); h = _handoff(root, ops)
    first = execute_pipeline(h, root, True); second = execute_pipeline(h, root, True)
    assert first["result"]["status"] == "succeeded"
    assert second.get("result", {}).get("status") != "succeeded"
    assert second["live_precondition"]["status"] == "not_satisfied"


def test_workspace_escape_fails_closed(tmp_path):
    root = _root(tmp_path); before = [_fp(root, t) for t in TARGETS]
    for target in ("../outside.py", str(tmp_path / "outside.py")):
        ops = _ops(root); ops[1] = {**ops[1], "target_path": target}
        assert validate_only(_handoff(root, ops, tx="escape" + sha_bytes(target.encode())[:8]), root)["executor_admission"]["status"] != "admitted"
    assert [_fp(root, t) for t in TARGETS] == before


def test_unexpected_third_operation_fails_closed(tmp_path):
    root = _root(tmp_path); before = [_fp(root, t) for t in TARGETS]; ops = _ops(root)
    third = {**ops[0], "operation_id": "third", "target_path": SENTINEL, "expected_before_fingerprint": _fp(root, SENTINEL), "proposed_content": "mutate\n", "expected_after_fingerprint": sha_bytes(b"mutate\n")}
    scope = {"status": "valid", "authorized_operation_ids": [op["operation_id"] for op in ops], "authorized_target_paths": list(TARGETS), "authorized_operation_types": ["replace_text_file", "replace_text_file"], "operation_count": 2}
    out = validate_only(_handoff(root, ops + [third], scope=scope), root)
    assert out["executor_admission"]["status"] != "admitted"
    assert [_fp(root, t) for t in TARGETS] == before


def test_deterministic_ordering(tmp_path):
    root = _root(tmp_path); ops1 = _ops(root); ops2 = _ops(root)
    assert [op["operation_id"] for op in ops1] == [op["operation_id"] for op in ops2]
    assert [op["operation_fingerprint"] for op in ops1] == [op["operation_fingerprint"] for op in ops2]
    out = execute_pipeline(_handoff(root, ops1, tx="order"), root, True)
    journal = json.loads((root / ".zero" / "transactions" / out["transaction_store"]["transaction_id"] / "journal.json").read_text())
    assert [e["operation_id"] for e in journal["entries"] if e["phase"] == "after_commit"] == [op["operation_id"] for op in ops1]


def test_verification_failure_is_visible_and_rolls_back(tmp_path):
    root = _root(tmp_path); before = [_fp(root, t) for t in TARGETS]
    out = execute_pipeline(_handoff(root, _ops(root, bad_second_after=True), tx="bad-post"), root, True)
    assert out["staging"]["status"] == "failed"
    assert out["result"]["status"] == "failed_rolled_back"
    assert [_fp(root, t) for t in TARGETS] == before
