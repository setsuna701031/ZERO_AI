from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
from typing import Any, Mapping


CONTRACT = "zero.runtime.transactional_active_execution.v1"
REQUEST_CONTRACT = "zero.runtime.active_executor_invocation_request.v1"
BUNDLE_CONTRACT = "zero.runtime.candidate_mutation_bundle.v1"
AUTHORIZATION_CONTRACT = "zero.runtime.active_execution_authorization.v1"
_PROFILES = {"none", "python_compile", "focused_pytest", "python_compile_then_focused_pytest"}
_RESERVED = {"CON", "PRN", "AUX", "NUL", *{f"COM{i}" for i in range(1, 10)}, *{f"LPT{i}" for i in range(1, 10)}}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _root_identity(path: Path) -> str:
    return str(path).replace("\\", "/").casefold()


def _is_reparse(path: Path) -> bool:
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return True


def _safe_relative(value: Any) -> str:
    if not isinstance(value, str) or value != value.rstrip(" ."):
        return ""
    text = value.strip().replace("\\", "/")
    path = PurePosixPath(text)
    if (not text or text in {".", "/"} or text.startswith(("//", "\\\\", "\\\\?\\", "\\\\.\\"))
            or Path(text).is_absolute() or path.is_absolute() or ".." in path.parts
            or any(char in text for char in "*?:")
            or any(part.split(".")[0].upper() in _RESERVED for part in path.parts)):
        return ""
    return text


def _resolve_safe(root: Path, relative: str, *, allow_missing: bool = True) -> tuple[Path | None, str]:
    candidate = root / Path(relative)
    current = root
    try:
        for part in Path(relative).parts:
            current = current / part
            if current.exists() and (current.is_symlink() or _is_reparse(current)):
                return None, "symlink_or_reparse_point"
        resolved = candidate.resolve(strict=not allow_missing)
        if os.path.commonpath([str(root), str(resolved)]) != str(root):
            return None, "target_root_escape"
        return candidate, ""
    except (OSError, RuntimeError, ValueError):
        return None, "unsafe_or_unresolvable_path"


def _file_state(path: Path, *, include_bytes: bool = False) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "file_type": "missing", "size": 0, "sha256": "", "bytes": b"" if include_bytes else None}
    if path.is_symlink() or _is_reparse(path):
        return {"exists": True, "file_type": "unsafe", "size": None, "sha256": "", "bytes": None}
    if not path.is_file():
        return {"exists": True, "file_type": "directory" if path.is_dir() else "special", "size": None, "sha256": "", "bytes": None}
    info = path.stat()
    if getattr(info, "st_nlink", 1) != 1:
        return {"exists": True, "file_type": "hardlink_ambiguous", "size": info.st_size,
                "sha256": "", "bytes": None}
    data = path.read_bytes()
    return {"exists": True, "file_type": "file", "size": len(data), "sha256": sha256(data).hexdigest(), "bytes": data if include_bytes else None}


def _directory_snapshot(parents: set[Path]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for parent in sorted(parents, key=lambda item: str(item).casefold()):
        if not parent.exists() or not parent.is_dir() or parent.is_symlink() or _is_reparse(parent):
            continue
        for child in sorted(parent.iterdir(), key=lambda item: item.name.casefold()):
            state = _file_state(child, include_bytes=True)
            result[str(child)] = state
    return result


def _restore_environment(before: Mapping[str, Mapping[str, Any]], parents: set[Path], candidate_paths: set[Path]) -> list[dict[str, Any]]:
    restored: list[dict[str, Any]] = []
    current = _directory_snapshot(parents)
    all_paths = set(before) | set(current)
    for raw in sorted(all_paths, reverse=True):
        path = Path(raw)
        if path in candidate_paths:
            continue
        prior = before.get(raw)
        try:
            if prior is None:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
                elif path.is_dir() and not path.is_symlink():
                    path.rmdir()
                else:
                    raise RuntimeError("unexpected_path_not_safely_removable")
            elif prior.get("file_type") == "file":
                _atomic_write(path, bytes(prior.get("bytes") or b""), suffix="environment-rollback")
            elif prior.get("file_type") == "directory" and not path.exists():
                raise RuntimeError("removed_directory_not_automatically_recreated")
            restored.append({"path": raw, "restored": True})
        except Exception as exc:
            restored.append({"path": raw, "restored": False, "error": type(exc).__name__})
    return restored


def _atomic_write(path: Path, data: bytes, *, suffix: str) -> None:
    stage = path.with_name(f".{path.name}.{suffix}.tmp")
    if stage.exists():
        raise RuntimeError("staging_path_exists")
    try:
        with stage.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if sha256(stage.read_bytes()).hexdigest() != sha256(data).hexdigest():
            raise RuntimeError("staging_hash_mismatch")
        os.replace(stage, path)
    finally:
        if stage.exists():
            stage.unlink()


def _base_result(base: Mapping[str, Any], status: str, reasons: list[str]) -> dict[str, Any]:
    return {
        **deepcopy(dict(base)), "transaction_status": status,
        "pre_mutation_verification": {}, "snapshot": {}, "mutation_result": {},
        "validation_result": {}, "commit_decision": {"committed": False},
        "rollback_result": {}, "final_file_states": [],
        "transaction_committed": False, "file_mutation_performed": False,
        "validation_executed": False, "validation_passed": None,
        "rollback_executed": False, "rollback_verified": None,
        "git_commit_performed": False, "scope_expanded": False,
        "critical_failure": status == "rollback_failed", "reasons": deepcopy(reasons),
        "audit_record": {"event_type": f"transactional_execution_{status}",
                         "transaction_id": base["transaction_id"], "reasons": deepcopy(reasons)},
    }


def _validate_time(record: Mapping[str, Any], start: str, end: str, now: datetime,
                   label: str, max_seconds: int | None, reasons: list[str]) -> None:
    try:
        started, expires = _parse_time(record.get(start)), _parse_time(record.get(end))
        if expires <= started or (max_seconds is not None and (expires - started).total_seconds() > max_seconds):
            reasons.append(f"invalid_{label}_lifetime")
        if now >= expires:
            reasons.append(f"{label}_expired")
    except (TypeError, ValueError):
        reasons.append(f"invalid_{label}_time")


def execute_transactional_active_plan(
    active_authorization_result: Mapping[str, Any], invocation_request: Mapping[str, Any],
    candidate_bundle: Mapping[str, Any], *, target_root: Any,
    transaction_workspace_root: Any, now: Any = None,
    runtime_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    auth, request, bundle = map(_mapping, (active_authorization_result, invocation_request, candidate_bundle))
    config = _mapping(runtime_config)
    reasons: list[str] = []
    try:
        current = _parse_time(now if now is not None else datetime.now(timezone.utc))
    except (TypeError, ValueError):
        current = datetime.min.replace(tzinfo=timezone.utc)
        reasons.append("invalid_now")
    try:
        root = Path(target_root).resolve(strict=True)
        if not root.is_dir() or root.is_symlink() or _is_reparse(root):
            raise ValueError
    except (OSError, RuntimeError, TypeError, ValueError):
        root = None
        reasons.append("invalid_target_root")
    try:
        workspace = Path(transaction_workspace_root).resolve(strict=False)
        if root and (workspace == root or root in workspace.parents):
            reasons.append("workspace_inside_target_root")
        current_path = workspace
        while not current_path.exists() and current_path != current_path.parent:
            current_path = current_path.parent
        if not current_path.exists() or current_path.is_symlink() or _is_reparse(current_path):
            reasons.append("unsafe_workspace_root")
        if workspace.exists() and (not workspace.is_dir() or workspace.is_symlink() or _is_reparse(workspace)):
            reasons.append("unsafe_workspace_root")
    except (OSError, RuntimeError, TypeError):
        workspace = Path(".")
        reasons.append("unsafe_workspace_root")

    if (auth.get("contract") != AUTHORIZATION_CONTRACT or auth.get("authorization_status") != "authorized"
            or auth.get("authorization_valid") is not True or auth.get("active_execution_prepared") is not True):
        reasons.append("active_authorization_not_prepared")
    if any(auth.get(key) is not False for key in (
            "active_execution_ready", "execution_allowed", "file_mutation_allowed",
            "patch_application_allowed", "validation_execution_allowed",
            "rollback_execution_allowed", "commit_allowed")):
        reasons.append("unsafe_authorization_state")
    if auth.get("required_next_boundary") != "active_executor_invocation_gate":
        reasons.append("invalid_next_boundary")
    if request.get("contract") != REQUEST_CONTRACT:
        reasons.append("invalid_invocation_contract")
    if request.get("requested_mode") != "transactional_active_execution":
        reasons.append("invalid_requested_mode")
    for key in ("acknowledged_transactional_execution", "acknowledged_automatic_rollback",
                "acknowledged_no_git_commit", "acknowledged_no_scope_expansion"):
        if request.get(key) is not True:
            reasons.append(f"{key}_required")
    if bundle.get("contract") != BUNDLE_CONTRACT:
        reasons.append("invalid_candidate_bundle_contract")
    chain = {
        "authorization_result_id": auth.get("authorization_result_id"),
        "authorization_id": auth.get("authorization_id"),
        "controlled_execution_result_id": auth.get("controlled_execution_result_id"),
        "token_id": auth.get("token_id"), "plan_id": auth.get("plan_id"),
        "review_result_id": auth.get("review_result_id"), "operator_id": auth.get("operator_id"),
    }
    for key, expected in chain.items():
        if str(request.get(key) or "") != str(expected or ""):
            reasons.append(f"{key}_mismatch")
    if (request.get("candidate_bundle_id") != bundle.get("candidate_bundle_id")
            or bundle.get("authorization_result_id") != auth.get("authorization_result_id")
            or bundle.get("plan_id") != auth.get("plan_id")):
        reasons.append("candidate_binding_mismatch")
    identity = _root_identity(root) if root else ""
    if request.get("target_root_identity") != identity or bundle.get("target_root_identity") != identity:
        reasons.append("target_root_identity_mismatch")
    raw_bundle = deepcopy(bundle)
    supplied_fingerprint = raw_bundle.pop("bundle_fingerprint", None)
    if supplied_fingerprint != _fingerprint(raw_bundle) or request.get("candidate_bundle_fingerprint") != supplied_fingerprint:
        reasons.append("candidate_bundle_fingerprint_mismatch")
    if bundle.get("scope_fingerprint") != _fingerprint(auth.get("authorized_scope", [])):
        reasons.append("scope_fingerprint_mismatch")
    _validate_time(request, "requested_at", "expires_at", current, "invocation", 300, reasons)
    _validate_time(bundle, "created_at", "expires_at", current, "bundle", None, reasons)
    _validate_time(auth, "authorized_at", "expires_at", current, "authorization", 600, reasons)
    try:
        if _parse_time(request.get("expires_at")) > _parse_time(auth.get("expires_at")):
            reasons.append("invocation_extends_authorization")
    except (TypeError, ValueError):
        pass

    files = bundle.get("files")
    if not isinstance(files, list) or not files:
        reasons.append("candidate_files_required")
        files = []
    normalized: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    allowed = {str(item).replace("\\", "/").casefold() for item in auth.get("authorized_scope", []) if isinstance(item, str)}
    for raw_item in files:
        item = _mapping(raw_item)
        relative = _safe_relative(item.get("relative_path"))
        collision_key = relative.casefold()
        if not relative or collision_key in seen or collision_key not in allowed:
            reasons.append("invalid_or_unapproved_candidate_path")
            continue
        seen.add(collision_key)
        operation = item.get("operation")
        if operation not in {"create", "replace", "delete"}:
            reasons.append("invalid_candidate_operation")
        content = item.get("candidate_content")
        if operation in {"create", "replace"}:
            if item.get("candidate_content_encoding") != "utf-8":
                reasons.append("invalid_candidate_content_encoding")
            if not isinstance(content, str):
                reasons.append("candidate_content_required")
            else:
                data = content.encode("utf-8")
                try:
                    maximum = int(item.get("maximum_size") or 1_048_576)
                except (TypeError, ValueError):
                    maximum = 0
                if len(data) > maximum or sha256(data).hexdigest() != item.get("candidate_content_hash"):
                    reasons.append("candidate_content_mismatch")
        elif content is not None:
            reasons.append("delete_content_must_be_null")
        normalized.append((relative, item))
    bounded_scope = [relative for relative, _ in normalized]
    if request.get("acknowledged_scope") != bounded_scope:
        reasons.append("acknowledged_scope_mismatch")
    profile = request.get("validation_profile_id")
    if profile not in _PROFILES or bundle.get("validation_profile_id", profile) != profile:
        reasons.append("invalid_validation_profile")
    if profile == "none" and bundle.get("project_validation_required") is not False:
        reasons.append("validation_required_forbids_none")
    approved_tests = bundle.get("approved_test_files", [])
    if profile in {"focused_pytest", "python_compile_then_focused_pytest"}:
        if (not isinstance(approved_tests, list) or not approved_tests
                or any(not _safe_relative(path) or not path.startswith("tests/test_") or not path.endswith(".py")
                       for path in approved_tests)):
            reasons.append("invalid_approved_test_files")
        elif any(path not in bundle.get("validation_scope", approved_tests) for path in approved_tests):
            reasons.append("test_path_outside_validation_scope")

    transaction_seed = {"invocation_request_id": request.get("invocation_request_id"),
                        "candidate_bundle_id": bundle.get("candidate_bundle_id"),
                        "bundle_fingerprint": supplied_fingerprint,
                        "authorization_result_id": auth.get("authorization_result_id"),
                        "target_root_identity": identity}
    transaction_id = f"transaction-{_fingerprint(transaction_seed)[:16]}"
    gate = {"invocation_gate_status": "admitted" if not reasons else "denied",
            "transaction_entry_ready": not reasons, "transaction_id": transaction_id,
            "bounded_scope": bounded_scope, "candidate_bundle_id": bundle.get("candidate_bundle_id", ""),
            "validation_profile_id": profile, "expires_at": request.get("expires_at")}
    base = {"contract": CONTRACT, "transaction_id": transaction_id,
            "invocation_request_id": request.get("invocation_request_id", ""),
            "authorization_result_id": auth.get("authorization_result_id", ""),
            "plan_id": auth.get("plan_id", ""), "operator_id": auth.get("operator_id", ""),
            "target_root_identity": identity, "candidate_bundle_id": bundle.get("candidate_bundle_id", ""),
            "validation_profile_id": profile, "invocation_gate": gate}
    if reasons or root is None:
        return _base_result(base, "blocked", reasons)

    candidate_paths: set[Path] = set()
    parents: set[Path] = set()
    pre_states: list[dict[str, Any]] = []
    for relative, item in normalized:
        path, error = _resolve_safe(root, relative)
        if error or path is None:
            reasons.append(f"unsafe_path:{relative}:{error}")
            continue
        candidate_paths.add(path)
        parents.add(path.parent)
        state = _file_state(path, include_bytes=False)
        expected = _mapping(item.get("expected_pre_state"))
        valid = state["file_type"] in {"file", "missing"} and state["exists"] is expected.get("expected_exists")
        if state["exists"]:
            valid = (valid and isinstance(expected.get("expected_sha256"), str)
                     and expected.get("expected_sha256") == state["sha256"])
            if "expected_size" in expected:
                valid = valid and expected.get("expected_size") == state["size"]
        if item.get("operation") == "create" and state["exists"]:
            valid = False
        if item.get("operation") in {"replace", "delete"} and not state["exists"]:
            valid = False
        if not valid:
            reasons.append(f"pre_state_mismatch:{relative}")
        pre_states.append({"path": relative, **{key: value for key, value in state.items() if key != "bytes"},
                           "verified": valid})
    if reasons:
        result = _base_result(base, "blocked", reasons)
        result["pre_mutation_verification"] = {"passed": False, "states": pre_states}
        result["final_file_states"] = pre_states
        return result

    environment_before = _directory_snapshot(parents)
    listing_before_fingerprint = _fingerprint({
        key: {field: value for field, value in state.items() if field != "bytes"}
        for key, state in environment_before.items()})
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        transaction_dir = workspace / transaction_id
        transaction_dir.mkdir(exist_ok=False)
    except (OSError, RuntimeError):
        result = _base_result(base, "blocked", ["transaction_workspace_creation_failed"])
        result["pre_mutation_verification"] = {"passed": True, "states": pre_states}
        return result

    snapshots: list[dict[str, Any]] = []
    snapshot_complete = True
    try:
        for index, (relative, _) in enumerate(normalized):
            target = root / relative
            state = _file_state(target, include_bytes=True)
            snapshot_file = transaction_dir / f"snapshot-{index}.bin"
            if state["exists"]:
                snapshot_file.write_bytes(bytes(state["bytes"] or b""))
                if sha256(snapshot_file.read_bytes()).hexdigest() != state["sha256"]:
                    raise RuntimeError("snapshot_hash_mismatch")
            snapshots.append({"path": relative, "originally_existed": state["exists"],
                              "original_sha256": state["sha256"], "original_size": state["size"],
                              "snapshot_file": str(snapshot_file) if state["exists"] else "",
                              "rollback_action": "restore_original_bytes" if state["exists"] else "delete_created_file"})
    except Exception:
        snapshot_complete = False
    snapshot = {"snapshot_id": f"transaction-snapshot-{_fingerprint(snapshots)[:16]}",
                "transaction_id": transaction_id, "workspace": str(transaction_dir),
                "entries": snapshots, "snapshot_complete": snapshot_complete,
                "rollback_ready": snapshot_complete and len(snapshots) == len(normalized),
                "directory_listing_before_fingerprint": listing_before_fingerprint}
    if not snapshot["rollback_ready"]:
        result = _base_result(base, "blocked", ["recoverable_snapshot_incomplete"])
        result["pre_mutation_verification"] = {"passed": True, "states": pre_states}
        result["snapshot"] = snapshot
        return result

    mutated: list[str] = []
    validation_result: dict[str, Any] = {}
    failure_reason = ""
    try:
        for relative, item in normalized:
            target = root / relative
            operation = item["operation"]
            if operation in {"create", "replace"}:
                data = item["candidate_content"].encode("utf-8")
                _atomic_write(target, data, suffix=transaction_id)
                post = _file_state(target)
                if (post["file_type"] != "file" or post["sha256"] != item["candidate_content_hash"]
                        or post["size"] != len(data)):
                    raise RuntimeError("post_write_verification_failed")
            else:
                target.unlink()
                if target.exists():
                    raise RuntimeError("delete_verification_failed")
            mutated.append(relative)

        compile_checks: list[dict[str, Any]] = []
        test_evidence: dict[str, Any] = {}
        validation_passed = True
        validation_executed = profile != "none"
        if profile in {"python_compile", "python_compile_then_focused_pytest"}:
            for relative, item in normalized:
                if relative.endswith(".py") and item["operation"] != "delete":
                    try:
                        source = (root / relative).read_text(encoding="utf-8")
                        compile(source, relative, "exec")
                        compile_checks.append({"path": relative, "passed": True})
                    except Exception as exc:
                        compile_checks.append({"path": relative, "passed": False,
                                               "error_type": type(exc).__name__})
                        validation_passed = False
        if validation_passed and profile in {"focused_pytest", "python_compile_then_focused_pytest"}:
            timeout = float(config.get("validation_timeout", 60))
            env = {"PYTHONIOENCODING": "utf-8", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *approved_tests, "-q"],
                    cwd=root, capture_output=True, text=True, timeout=timeout,
                    shell=False, env=env, check=False,
                )
                stdout, stderr = completed.stdout[-4000:], completed.stderr[-4000:]
                test_evidence = {"focused_test_files": deepcopy(approved_tests),
                                 "exit_status": completed.returncode, "stdout_summary": stdout,
                                 "stderr_summary": stderr,
                                 "output_truncated": len(completed.stdout) > 4000 or len(completed.stderr) > 4000}
                validation_passed = completed.returncode == 0
            except subprocess.TimeoutExpired:
                test_evidence = {"focused_test_files": deepcopy(approved_tests),
                                 "exit_status": "timeout", "stdout_summary": "",
                                 "stderr_summary": "validation_timeout", "output_truncated": False}
                validation_passed = False
            except Exception as exc:
                test_evidence = {"focused_test_files": deepcopy(approved_tests),
                                 "exit_status": "crash", "stdout_summary": "",
                                 "stderr_summary": type(exc).__name__, "output_truncated": False}
                validation_passed = False
        validation_result = {"validation_profile_id": profile,
                             "validation_started_at": current.replace(microsecond=0).isoformat(),
                             "validation_finished_at": current.replace(microsecond=0).isoformat(),
                             "validation_executed": validation_executed,
                             "compile_checks": compile_checks, **test_evidence,
                             "validation_passed": validation_passed}
        validation_result["evidence_hash"] = _fingerprint(validation_result)
        if not validation_passed:
            raise RuntimeError("validation_failed")

        environment_after = _directory_snapshot(parents)
        outside_before = {key: value for key, value in environment_before.items() if Path(key) not in candidate_paths}
        outside_after = {key: value for key, value in environment_after.items() if Path(key) not in candidate_paths}
        comparable = lambda values: {key: {k: v for k, v in state.items() if k != "bytes"}
                                     for key, state in values.items()}
        if comparable(outside_before) != comparable(outside_after):
            raise RuntimeError("unexpected_scope_outside_change")

        final_states = [{"path": relative, **{key: value for key, value in _file_state(root / relative).items()
                                               if key != "bytes"}} for relative, _ in normalized]
        listing_after_fingerprint = _fingerprint(comparable(environment_after))
        result = _base_result(base, "committed", [])
        result.update({
            "pre_mutation_verification": {"passed": True, "states": pre_states},
            "snapshot": snapshot, "mutation_result": {"succeeded": True, "paths": mutated},
            "validation_result": validation_result,
            "commit_decision": {"committed": True, "reason": "all_transaction_invariants_satisfied"},
            "rollback_result": {"executed": False}, "final_file_states": final_states,
            "directory_listing_after_fingerprint": listing_after_fingerprint,
            "transaction_committed": True, "file_mutation_performed": bool(mutated),
            "validation_executed": validation_result["validation_executed"],
            "validation_passed": True, "audit_record": {
                "event_type": "transactional_execution_committed", "transaction_id": transaction_id,
                "authorization_result_id": auth.get("authorization_result_id"),
                "invocation_request_id": request.get("invocation_request_id"),
                "candidate_bundle_id": bundle.get("candidate_bundle_id"),
                "snapshot_id": snapshot["snapshot_id"], "validation_evidence_hash": validation_result["evidence_hash"],
                "final_state_fingerprint": _fingerprint(final_states), "git_commit_performed": False,
            },
        })
        return result
    except Exception as exc:
        failure_reason = str(exc) or type(exc).__name__

    rollback_entries: list[dict[str, Any]] = []
    rollback_ok = True
    for entry in reversed(snapshots):
        target = root / entry["path"]
        try:
            if entry["originally_existed"]:
                snapshot_bytes = Path(entry["snapshot_file"]).read_bytes()
                _atomic_write(target, snapshot_bytes, suffix=f"{transaction_id}-rollback")
                state = _file_state(target)
                restored = state["exists"] and state["sha256"] == entry["original_sha256"]
            else:
                if target.exists():
                    if target.is_dir() or target.is_symlink():
                        raise RuntimeError("unsafe_created_target_during_rollback")
                    target.unlink()
                restored = not target.exists()
            rollback_ok = rollback_ok and restored
            rollback_entries.append({"path": entry["path"], "restored": restored})
        except Exception as exc:
            rollback_ok = False
            rollback_entries.append({"path": entry["path"], "restored": False,
                                     "error_type": type(exc).__name__})
    environment_restores = _restore_environment(environment_before, parents, candidate_paths)
    rollback_ok = rollback_ok and all(item["restored"] for item in environment_restores)
    final_states = [{"path": relative, **{key: value for key, value in _file_state(root / relative).items()
                                           if key != "bytes"}} for relative, _ in normalized]
    status = "rolled_back" if rollback_ok else "rollback_failed"
    result = _base_result(base, status, [f"transaction_failure:{failure_reason}"])
    result.update({
        "pre_mutation_verification": {"passed": True, "states": pre_states}, "snapshot": snapshot,
        "mutation_result": {"succeeded": False, "paths_mutated_before_failure": mutated},
        "validation_result": validation_result or {"validation_executed": False, "validation_passed": None},
        "rollback_result": {"executed": True, "verified": rollback_ok,
                            "entries": rollback_entries, "environment_restores": environment_restores},
        "final_file_states": final_states, "file_mutation_performed": bool(mutated),
        "validation_executed": validation_result.get("validation_executed", False),
        "validation_passed": validation_result.get("validation_passed"),
        "rollback_executed": True, "rollback_verified": rollback_ok,
        "critical_failure": not rollback_ok,
        "audit_record": {"event_type": f"transactional_execution_{status}",
                         "transaction_id": transaction_id,
                         "authorization_result_id": auth.get("authorization_result_id"),
                         "invocation_request_id": request.get("invocation_request_id"),
                         "candidate_bundle_id": bundle.get("candidate_bundle_id"),
                         "snapshot_id": snapshot["snapshot_id"],
                         "rollback_verified": rollback_ok, "git_commit_performed": False,
                         "reasons": [f"transaction_failure:{failure_reason}"]},
    })
    return result


__all__ = ["AUTHORIZATION_CONTRACT", "BUNDLE_CONTRACT", "CONTRACT", "REQUEST_CONTRACT",
           "execute_transactional_active_plan"]
