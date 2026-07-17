from __future__ import annotations

import copy
from hashlib import sha256

from core.runtime.runtime_controlled_execution_activation import activate_controlled_execution
from tests.test_runtime_executor_admission_token import NOW, inputs


def test_complete_dry_run_reads_snapshot_and_changes_nothing(tmp_path):
    target = tmp_path / "workspace"; target.mkdir(); file = target / "a.txt"; file.write_text("before", encoding="utf-8")
    p, r, q = inputs(tmp_path); before_inputs = copy.deepcopy((p, r, q))
    before_names = sorted(str(x.relative_to(tmp_path)) for x in tmp_path.rglob("*"))
    before_hash = sha256(file.read_bytes()).hexdigest()
    first = activate_controlled_execution(p, r, q, target_root=tmp_path, now=NOW)
    second = activate_controlled_execution(p, r, q, target_root=tmp_path, now=NOW)
    after_names = sorted(str(x.relative_to(tmp_path)) for x in tmp_path.rglob("*"))
    assert first["activation_status"] == "completed" and first["dry_run_completed"] is True
    assert first["activation_id"] == second["activation_id"] and (p, r, q) == before_inputs
    assert sha256(file.read_bytes()).hexdigest() == before_hash and before_names == after_names
    entry = first["snapshot_manifest"]["entries"][0]
    assert entry["content_hash_sha256"] == before_hash and entry["read_status"] == "read"
    operation = first["dry_run_mutation_plan"]["operations"][0]
    assert operation["mutation_ready"] is False
    assert operation["patch_text_generated"] is False and operation["replacement_content_generated"] is False
    assert first["validation_evidence"]["project_validation_executed"] is False
    assert first["validation_evidence"]["project_validation_passed"] is None
    assert first["rollback_prepared_state"]["rollback_ready"] is False
    for key in ("active_execution_ready", "execution_allowed", "file_mutation_performed",
                "patch_applied", "validation_executed", "rollback_executed", "commit_performed"):
        assert first[key] is False


def test_missing_file_is_explicit_but_directory_and_unsafe_paths_block(tmp_path):
    p, r, q = inputs(tmp_path)
    missing = activate_controlled_execution(p, r, q, target_root=tmp_path, now=NOW)
    assert missing["activation_status"] == "completed"
    assert missing["snapshot_manifest"]["entries"][0]["read_status"] == "missing"
    folder = tmp_path / "workspace"; folder.mkdir()
    p["allowed_files"] = ["workspace"]
    r["validated_scope"] = ["workspace"]; q["acknowledged_scope"] = ["workspace"]
    blocked = activate_controlled_execution(p, r, q, target_root=tmp_path, now=NOW)
    assert blocked["activation_status"] == "blocked"
    assert any("directory_not_allowed" in reason for reason in blocked["reasons"])


def test_symlink_escape_is_blocked_when_supported(tmp_path):
    outside = tmp_path / "outside"; outside.mkdir(); (outside / "x.txt").write_text("x")
    link = tmp_path / "link"
    try: link.symlink_to(outside, target_is_directory=True)
    except OSError: return
    p, r, q = inputs(tmp_path); p["allowed_files"] = ["link/x.txt"]
    r["validated_scope"] = ["link/x.txt"]; q["acknowledged_scope"] = ["link/x.txt"]
    result = activate_controlled_execution(p, r, q, target_root=tmp_path, now=NOW)
    assert result["activation_status"] == "blocked"

