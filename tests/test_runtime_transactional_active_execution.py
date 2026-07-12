from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path

import pytest

import core.runtime.runtime_transactional_active_execution as runtime
from core.runtime.runtime_transactional_active_execution import (
    AUTHORIZATION_CONTRACT, BUNDLE_CONTRACT, CONTRACT, REQUEST_CONTRACT,
    execute_transactional_active_plan,
)


NOW = "2026-07-10T12:00:00+00:00"


def digest(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return sha256(data).hexdigest()


def canonical_fingerprint(value: dict) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def candidate(path: str, operation: str, *, before: str | None = None,
              content: str | None = None) -> dict:
    expected = {"expected_exists": before is not None}
    if before is not None:
        expected.update(expected_sha256=digest(before), expected_size=len(before.encode()))
    return {
        "relative_path": path, "operation": operation,
        "expected_pre_state": expected,
        "candidate_content_encoding": "utf-8",
        "candidate_content": content,
        "candidate_content_hash": digest(content) if content is not None else None,
        "maximum_size": 100_000,
        "validation_requirements": [],
    }


def records(tmp_path: Path, files: list[dict], *, profile: str = "none",
            project_validation_required: bool = False,
            approved_tests: list[str] | None = None) -> tuple[dict, dict, dict, Path, Path]:
    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    workspace = tmp_path / "workspace"
    identity = str(target.resolve()).replace("\\", "/").casefold()
    scope = [item["relative_path"].replace("\\", "/") for item in files]
    auth = {
        "contract": AUTHORIZATION_CONTRACT,
        "authorization_result_id": "authorization-result-one",
        "authorization_id": "authorization-one",
        "authorization_status": "authorized", "authorization_valid": True,
        "active_execution_prepared": True, "active_execution_ready": False,
        "execution_allowed": False, "file_mutation_allowed": False,
        "patch_application_allowed": False, "validation_execution_allowed": False,
        "rollback_execution_allowed": False, "commit_allowed": False,
        "required_next_boundary": "active_executor_invocation_gate",
        "controlled_execution_result_id": "controlled-one", "token_id": "token-one",
        "plan_id": "plan-one", "review_result_id": "review-one",
        "operator_id": "operator-one", "authorized_scope": scope,
        "authorized_at": NOW,
        "expires_at": "2026-07-10T12:10:00+00:00",
    }
    bundle = {
        "contract": BUNDLE_CONTRACT, "candidate_bundle_id": "bundle-one",
        "plan_id": auth["plan_id"],
        "authorization_result_id": auth["authorization_result_id"],
        "target_root_identity": identity, "scope_fingerprint": canonical_fingerprint(scope),
        "created_at": NOW,
        "expires_at": "2026-07-10T12:05:00+00:00",
        "files": copy.deepcopy(files), "validation_profile_id": profile,
        "project_validation_required": project_validation_required,
        "approved_test_files": copy.deepcopy(approved_tests or []),
        "validation_scope": copy.deepcopy(approved_tests or []),
    }
    bundle["bundle_fingerprint"] = canonical_fingerprint(bundle)
    request = {
        "contract": REQUEST_CONTRACT, "invocation_request_id": "invocation-one",
        "authorization_result_id": auth["authorization_result_id"],
        "authorization_id": auth["authorization_id"],
        "controlled_execution_result_id": auth["controlled_execution_result_id"],
        "token_id": auth["token_id"], "plan_id": auth["plan_id"],
        "review_result_id": auth["review_result_id"], "operator_id": auth["operator_id"],
        "requested_mode": "transactional_active_execution",
        "requested_at": NOW,
        "expires_at": "2026-07-10T12:04:00+00:00",
        "target_root_identity": identity, "acknowledged_scope": scope,
        "candidate_bundle_id": bundle["candidate_bundle_id"],
        "candidate_bundle_fingerprint": bundle["bundle_fingerprint"],
        "validation_profile_id": profile,
        "acknowledged_transactional_execution": True,
        "acknowledged_automatic_rollback": True,
        "acknowledged_no_git_commit": True,
        "acknowledged_no_scope_expansion": True,
    }
    return auth, request, bundle, target, workspace


def execute(records_value, **kwargs):
    auth, request, bundle, target, workspace = records_value
    return execute_transactional_active_plan(
        auth, request, bundle, target_root=target,
        transaction_workspace_root=workspace, now=NOW, **kwargs)


def test_replace_compile_commits_with_complete_evidence_and_snapshot(tmp_path):
    values = records(tmp_path, [candidate("module.py", "replace", before="x = 1\n", content="x = 2\n")],
                     profile="python_compile", project_validation_required=True)
    target = values[3]; (target / "module.py").write_bytes(b"x = 1\n")
    original_inputs = copy.deepcopy(values[:3])
    result = execute(values)
    assert result["transaction_status"] == "committed"
    assert (target / "module.py").read_text(encoding="utf-8") == "x = 2\n"
    snapshot = result["snapshot"]
    assert snapshot["rollback_ready"] is True
    assert Path(snapshot["entries"][0]["snapshot_file"]).read_bytes() == b"x = 1\n"
    assert snapshot["entries"][0]["original_sha256"] == digest("x = 1\n")
    assert result["validation_result"]["compile_checks"] == [{"path": "module.py", "passed": True}]
    assert result["final_file_states"][0]["sha256"] == digest("x = 2\n")
    assert result["transaction_committed"] is True
    assert result["git_commit_performed"] is False
    assert values[:3] == original_inputs
    assert result["audit_record"]["snapshot_id"] == snapshot["snapshot_id"]


@pytest.mark.parametrize(("operation", "before", "after"), [
    ("create", None, "created\n"),
    ("replace", "old\n", "new\n"),
    ("delete", "remove\n", None),
])
def test_each_supported_mutation_commits(tmp_path, operation, before, after):
    item = candidate("file.txt", operation, before=before,
                     content=after if operation != "delete" else None)
    values = records(tmp_path, [item])
    path = values[3] / "file.txt"
    if before is not None:
        path.write_bytes(before.encode("utf-8"))
    result = execute(values)
    assert result["transaction_status"] == "committed"
    assert path.exists() is (after is not None)
    if after is not None:
        assert path.read_text(encoding="utf-8") == after


def test_multi_file_transaction_commits_atomically(tmp_path):
    files = [candidate("a.txt", "replace", before="a", content="A"),
             candidate("b.txt", "create", content="B"),
             candidate("c.txt", "delete", before="c")]
    values = records(tmp_path, files)
    (values[3] / "a.txt").write_bytes(b"a"); (values[3] / "c.txt").write_bytes(b"c")
    result = execute(values)
    assert result["transaction_status"] == "committed"
    assert (values[3] / "a.txt").read_text() == "A"
    assert (values[3] / "b.txt").read_text() == "B"
    assert not (values[3] / "c.txt").exists()
    assert len(result["snapshot"]["entries"]) == 3


@pytest.mark.parametrize(("target", "updates", "reason"), [
    ("auth", {"authorization_status": "invalid"}, "active_authorization_not_prepared"),
    ("auth", {"expires_at": NOW}, "authorization_expired"),
    ("request", {"expires_at": NOW}, "invocation_expired"),
    ("request", {"requested_at": "2026-07-10T11:50:00+00:00"}, "invalid_invocation_lifetime"),
    ("bundle", {"expires_at": NOW}, "bundle_expired"),
    ("request", {"plan_id": "wrong"}, "plan_id_mismatch"),
    ("request", {"authorization_id": "wrong"}, "authorization_id_mismatch"),
    ("request", {"token_id": "wrong"}, "token_id_mismatch"),
    ("request", {"operator_id": "wrong"}, "operator_id_mismatch"),
    ("request", {"target_root_identity": "wrong"}, "target_root_identity_mismatch"),
    ("bundle", {"bundle_fingerprint": "bad"}, "candidate_bundle_fingerprint_mismatch"),
    ("bundle", {"scope_fingerprint": "bad"}, "scope_fingerprint_mismatch"),
    ("request", {"validation_profile_id": "arbitrary_command"}, "invalid_validation_profile"),
])
def test_gate_and_expiration_denials_are_stable(tmp_path, target, updates, reason):
    values = list(records(tmp_path, [candidate("file.txt", "create", content="x")]))
    {"auth": values[0], "request": values[1], "bundle": values[2]}[target].update(updates)
    result = execute(tuple(values))
    assert result["transaction_status"] == "blocked"
    assert reason in result["reasons"]
    assert result["file_mutation_performed"] is False
    assert result["rollback_executed"] is False


def refresh_bundle(values):
    bundle, request = values[2], values[1]
    bundle.pop("bundle_fingerprint", None)
    bundle["bundle_fingerprint"] = canonical_fingerprint(bundle)
    request["candidate_bundle_fingerprint"] = bundle["bundle_fingerprint"]
    request["acknowledged_scope"] = [item["relative_path"].replace("\\", "/") for item in bundle["files"]]


@pytest.mark.parametrize("unsafe", [
    "../escape.txt", "C:/absolute.txt", "//server/share.txt", "\\\\?\\C:\\x.txt",
    "\\\\.\\device", "name:stream", "CON", "NUL.txt", "AUX", "PRN",
    "COM1", "LPT1", "file.", "file ", "*.txt", "file?.txt", ".",
])
def test_unsafe_windows_paths_and_scope_expansion_are_blocked(tmp_path, unsafe):
    values = list(records(tmp_path, [candidate("safe.txt", "create", content="x")]))
    values[2]["files"][0]["relative_path"] = unsafe
    refresh_bundle(values)
    result = execute(tuple(values))
    assert result["transaction_status"] == "blocked"
    assert "invalid_or_unapproved_candidate_path" in result["reasons"]
    assert not (tmp_path / "escape.txt").exists()


def test_duplicate_and_case_collision_are_blocked(tmp_path):
    files = [candidate("a.txt", "create", content="a"),
             candidate("A.TXT", "create", content="b")]
    values = records(tmp_path, files)
    result = execute(values)
    assert result["transaction_status"] == "blocked"
    assert "invalid_or_unapproved_candidate_path" in result["reasons"]


def test_non_utf8_declared_encoding_is_blocked(tmp_path):
    values = list(records(tmp_path, [candidate("a.txt", "create", content="a")]))
    values[2]["files"][0]["candidate_content_encoding"] = "base64"
    refresh_bundle(values)
    result = execute(tuple(values))
    assert result["transaction_status"] == "blocked"
    assert "invalid_candidate_content_encoding" in result["reasons"]


def test_slash_collision_is_blocked(tmp_path):
    files = [candidate("dir/a.txt", "create", content="a"),
             candidate("dir\\a.txt", "create", content="b")]
    values = records(tmp_path, files)
    (values[3] / "dir").mkdir()
    assert execute(values)["transaction_status"] == "blocked"


def test_pre_state_hash_exists_and_missing_mismatches_never_mutate(tmp_path):
    values = records(tmp_path, [candidate("a.txt", "replace", before="expected", content="new")])
    path = values[3] / "a.txt"; path.write_text("external")
    result = execute(values)
    assert result["transaction_status"] == "blocked" and path.read_text() == "external"
    values = records(tmp_path / "second", [candidate("missing.txt", "replace", before="old", content="new")])
    result = execute(values)
    assert result["transaction_status"] == "blocked" and not (values[3] / "missing.txt").exists()
    values = records(tmp_path / "third", [candidate("exists.txt", "create", content="new")])
    path = values[3] / "exists.txt"; path.write_text("already")
    result = execute(values)
    assert result["transaction_status"] == "blocked" and path.read_text() == "already"


def test_directory_symlink_and_reparse_like_targets_are_blocked(tmp_path):
    values = records(tmp_path, [candidate("folder", "replace", before="x", content="y")])
    (values[3] / "folder").mkdir()
    assert execute(values)["transaction_status"] == "blocked"
    outside = tmp_path / "outside"; outside.mkdir(); (outside / "x.txt").write_text("x")
    link_values = records(tmp_path / "links", [candidate("link/x.txt", "replace", before="x", content="y")])
    try:
        (link_values[3] / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink unavailable")
    result = execute(link_values)
    assert result["transaction_status"] == "blocked"
    assert (outside / "x.txt").read_text() == "x"


def test_hard_link_ambiguity_is_blocked_when_supported(tmp_path):
    values = records(tmp_path, [candidate("linked.txt", "replace", before="same", content="new")])
    original = values[3] / "linked.txt"; alias = values[3] / "alias.txt"
    original.write_bytes(b"same")
    try:
        alias.hardlink_to(original)
    except OSError:
        pytest.skip("hard links unavailable")
    result = execute(values)
    assert result["transaction_status"] == "blocked"
    assert original.read_bytes() == b"same" and alias.read_bytes() == b"same"


def test_compile_failure_rolls_back_replace_exact_bytes(tmp_path):
    original = "value = 1\n"
    values = records(tmp_path, [candidate("module.py", "replace", before=original, content="def broken(:\n")],
                     profile="python_compile", project_validation_required=True)
    path = values[3] / "module.py"; path.write_bytes(original.encode())
    result = execute(values)
    assert result["transaction_status"] == "rolled_back"
    assert result["validation_executed"] is True and result["validation_passed"] is False
    assert result["rollback_executed"] is True and result["rollback_verified"] is True
    assert path.read_bytes() == original.encode()
    assert result["final_file_states"][0]["sha256"] == digest(original)


def test_create_failure_removes_created_file_and_delete_failure_restores_file(tmp_path):
    create_values = records(tmp_path, [candidate("new.py", "create", content="def broken(:")],
                            profile="python_compile", project_validation_required=True)
    create_result = execute(create_values)
    assert create_result["transaction_status"] == "rolled_back"
    assert not (create_values[3] / "new.py").exists()

    delete_values = records(tmp_path / "delete", [candidate("old.py", "delete", before="x = 1\n")],
                            profile="focused_pytest", project_validation_required=True,
                            approved_tests=["tests/test_failure.py"])
    (delete_values[3] / "old.py").write_bytes(b"x = 1\n")
    tests = delete_values[3] / "tests"; tests.mkdir()
    (tests / "test_failure.py").write_text("def test_failure(): assert False\n")
    result = execute(delete_values, runtime_config={"validation_timeout": 10})
    assert result["transaction_status"] == "rolled_back"
    assert (delete_values[3] / "old.py").read_bytes() == b"x = 1\n"


def test_focused_pytest_passes_with_fixed_arguments(tmp_path):
    values = records(tmp_path, [candidate("module.py", "replace", before="x=1\n", content="x=2\n")],
                     profile="focused_pytest", project_validation_required=True,
                     approved_tests=["tests/test_allowed.py"])
    (values[3] / "module.py").write_bytes(b"x=1\n")
    tests = values[3] / "tests"; tests.mkdir()
    (tests / "test_allowed.py").write_text("def test_allowed(): assert True\n")
    result = execute(values, runtime_config={"validation_timeout": 10})
    assert result["transaction_status"] == "committed"
    assert result["validation_result"]["focused_test_files"] == ["tests/test_allowed.py"]
    assert result["validation_result"]["exit_status"] == 0


@pytest.mark.parametrize("bad_test", [
    "tests/not_a_test.py", "../tests/test_escape.py", "tests/test_x.py -s",
    "tests/test_x.py;whoami", "tests/test_x.py --pdb",
])
def test_unapproved_test_paths_arguments_and_shell_metacharacters_are_blocked(tmp_path, bad_test):
    values = records(tmp_path, [candidate("a.py", "create", content="x=1\n")],
                     profile="focused_pytest", project_validation_required=True,
                     approved_tests=[bad_test])
    result = execute(values)
    assert result["transaction_status"] == "blocked"
    assert "invalid_approved_test_files" in result["reasons"]


def test_pytest_timeout_rolls_back(tmp_path):
    values = records(tmp_path, [candidate("a.py", "create", content="x=1\n")],
                     profile="focused_pytest", project_validation_required=True,
                     approved_tests=["tests/test_slow.py"])
    tests = values[3] / "tests"; tests.mkdir()
    (tests / "test_slow.py").write_text("import time\ndef test_slow(): time.sleep(2)\n")
    result = execute(values, runtime_config={"validation_timeout": 0.05})
    assert result["transaction_status"] == "rolled_back"
    assert result["validation_result"]["exit_status"] == "timeout"
    assert not (values[3] / "a.py").exists()


def test_second_mutation_failure_restores_first(monkeypatch, tmp_path):
    values = records(tmp_path, [candidate("a.txt", "replace", before="a", content="A"),
                                candidate("b.txt", "replace", before="b", content="B")])
    (values[3] / "a.txt").write_bytes(b"a"); (values[3] / "b.txt").write_bytes(b"b")
    original = runtime._atomic_write
    calls = 0
    def fail_second(path, data, *, suffix):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second write failure")
        return original(path, data, suffix=suffix)
    monkeypatch.setattr(runtime, "_atomic_write", fail_second)
    result = execute(values)
    assert result["transaction_status"] == "rolled_back"
    assert (values[3] / "a.txt").read_text() == "a"
    assert (values[3] / "b.txt").read_text() == "b"


def test_post_write_hash_failure_rolls_back(monkeypatch, tmp_path):
    values = records(tmp_path, [candidate("a.txt", "replace", before="old", content="new")])
    path = values[3] / "a.txt"; path.write_text("old")
    original_state = runtime._file_state
    injected = False
    def mismatched(value, *, include_bytes=False):
        nonlocal injected
        state = original_state(value, include_bytes=include_bytes)
        if value == path and state.get("sha256") == digest("new") and not include_bytes and not injected:
            injected = True
            state["sha256"] = "0" * 64
        return state
    monkeypatch.setattr(runtime, "_file_state", mismatched)
    result = execute(values)
    assert result["transaction_status"] == "rolled_back"
    assert path.read_text() == "old"


def test_snapshot_incomplete_prevents_mutation(monkeypatch, tmp_path):
    values = records(tmp_path, [candidate("a.txt", "replace", before="old", content="new")])
    path = values[3] / "a.txt"; path.write_text("old")
    original = Path.write_bytes
    def fail_snapshot(self, data):
        if self.name.startswith("snapshot-"):
            raise OSError("snapshot unavailable")
        return original(self, data)
    monkeypatch.setattr(Path, "write_bytes", fail_snapshot)
    result = execute(values)
    assert result["transaction_status"] == "blocked"
    assert path.read_text() == "old"
    assert result["file_mutation_performed"] is False


def test_rollback_failure_is_critical_and_visible(monkeypatch, tmp_path):
    values = records(tmp_path, [candidate("a.py", "replace", before="x=1\n", content="def broken(:\n")],
                     profile="python_compile", project_validation_required=True)
    path = values[3] / "a.py"; path.write_bytes(b"x=1\n")
    original = runtime._atomic_write
    calls = 0
    def fail_rollback(target, data, *, suffix):
        nonlocal calls
        calls += 1
        if "rollback" in suffix:
            raise OSError("rollback unavailable")
        return original(target, data, suffix=suffix)
    monkeypatch.setattr(runtime, "_atomic_write", fail_rollback)
    result = execute(values)
    assert result["transaction_status"] == "rollback_failed"
    assert result["critical_failure"] is True
    assert result["rollback_executed"] is True and result["rollback_verified"] is False


def test_unexpected_scope_outside_create_is_detected_and_restored(tmp_path):
    values = records(tmp_path, [candidate("module.py", "replace", before="x=1\n", content="x=2\n")],
                     profile="focused_pytest", project_validation_required=True,
                     approved_tests=["tests/test_side_effect.py"])
    (values[3] / "module.py").write_bytes(b"x=1\n")
    tests = values[3] / "tests"; tests.mkdir()
    (tests / "test_side_effect.py").write_text(
        "from pathlib import Path\ndef test_side_effect(): Path('unexpected.txt').write_text('bad')\n")
    result = execute(values, runtime_config={"validation_timeout": 10})
    assert result["transaction_status"] == "rolled_back"
    assert not (values[3] / "unexpected.txt").exists()
    assert (values[3] / "module.py").read_text() == "x=1\n"


def test_unexpected_empty_directory_is_detected_and_removed(tmp_path):
    values = records(tmp_path, [candidate("module.py", "replace", before="x=1\n", content="x=2\n")],
                     profile="focused_pytest", project_validation_required=True,
                     approved_tests=["tests/test_directory_effect.py"])
    (values[3] / "module.py").write_bytes(b"x=1\n")
    tests = values[3] / "tests"; tests.mkdir()
    (tests / "test_directory_effect.py").write_text(
        "from pathlib import Path\ndef test_effect(): Path('unexpected-dir').mkdir()\n")
    result = execute(values, runtime_config={"validation_timeout": 10})
    assert result["transaction_status"] == "rolled_back"
    assert not (values[3] / "unexpected-dir").exists()


def test_workspace_inside_target_and_workspace_symlink_are_blocked(tmp_path):
    values = records(tmp_path, [candidate("a.txt", "create", content="a")])
    inside = values[3] / "workspace"
    result = execute_transactional_active_plan(values[0], values[1], values[2],
        target_root=values[3], transaction_workspace_root=inside, now=NOW)
    assert result["transaction_status"] == "blocked"
    outside = tmp_path / "outside"; outside.mkdir(); link = tmp_path / "workspace-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink unavailable")
    result = execute_transactional_active_plan(values[0], values[1], values[2],
        target_root=values[3], transaction_workspace_root=link, now=NOW)
    assert result["transaction_status"] == "blocked"


def test_runtime_source_has_only_bounded_subprocess_and_no_forbidden_operations():
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "git commit" not in source and "git checkout" not in source and "git reset" not in source
    assert "pip install" not in source and "requests." not in source
    assert "eval(" not in source
    assert "subprocess.run" in source
    assert "timeout=timeout" in source


def test_transaction_identity_is_deterministic_and_result_leaks_no_candidate_content(tmp_path):
    first_values = records(tmp_path, [candidate("a.txt", "create", content="secret-candidate")])
    first = execute(first_values)
    repeat_values = (*first_values[:4], tmp_path / "other-workspace")
    repeated = execute(repeat_values)
    assert first["transaction_id"].startswith("transaction-")
    assert repeated["transaction_id"] == first["transaction_id"]
    serialized = json.dumps(first, ensure_ascii=False)
    assert "secret-candidate" not in serialized
    assert "patch_text" not in serialized and "replacement_content" not in serialized
