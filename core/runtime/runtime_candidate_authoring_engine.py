from __future__ import annotations

import ast
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, parse_time, time_text

REQUEST_CONTRACT = "zero.runtime.candidate_authoring_request.v1"
OUTPUT_CONTRACT = "zero.runtime.candidate_authoring_output.v1"
SUPPORTED_STRATEGIES = {"append_text", "replace_exact_text", "create_text_file", "document_template", "python_import_safe_edit"}
DOCUMENT_TEMPLATES = {"title", "purpose", "status", "validation"}
DEFAULT_LIMITS = {"maximum_files": 20, "maximum_file_bytes": 262144, "maximum_total_bytes": 1048576, "maximum_questions": 8}
FORBIDDEN_INSTRUCTION_KEYS = {"memory", "memory_content", "command", "shell", "argv", "callable", "subprocess", "code_generator"}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _safe_relative(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ":" in text or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe_relative_path")
    return path.as_posix()


def _unsafe(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def _allowed(relative: str, scopes: list[str]) -> bool:
    return any(relative == scope or relative.startswith(scope.rstrip("/") + "/") for scope in scopes)


def _expires(now: Any, seconds: int = 900) -> str:
    return time_text(parse_time(now) + timedelta(seconds=seconds))


def create_authoring_request(*, goal: Mapping[str, Any], session: Mapping[str, Any], authoring_instruction: Mapping[str, Any],
                             repository_context_references: list[Mapping[str, Any]], inspect_evidence_references: list[Mapping[str, Any]],
                             now: Any = None, expires_at: Any = None, limits: Mapping[str, Any] | None = None) -> dict[str, Any]:
    goal_value, session_value, instruction = _mapping(goal), _mapping(session), _mapping(authoring_instruction)
    strategy = instruction.get("authoring_strategy") or instruction.get("strategy")
    target_files = deepcopy(instruction.get("target_files") or goal_value.get("target_scope") or [])
    value = {
        "contract": REQUEST_CONTRACT,
        "request_id": "",
        "goal_id": goal_value.get("goal_id"), "session_id": session_value.get("session_id"), "mission_id": goal_value.get("mission_id"),
        "goal_type": goal_value.get("goal_type"), "approved_scope": deepcopy(goal_value.get("target_scope") or []),
        "excluded_scope": deepcopy(goal_value.get("excluded_scope") or instruction.get("excluded_scope") or []), "target_files": target_files,
        "repository_context_references": deepcopy(repository_context_references), "inspect_evidence_references": deepcopy(inspect_evidence_references),
        "acceptance_criteria": deepcopy(goal_value.get("acceptance_criteria") or instruction.get("acceptance_criteria") or []),
        "validation_requirements": deepcopy(goal_value.get("validation_requirements") or instruction.get("validation_requirements") or []),
        "operator_constraints": deepcopy(instruction.get("operator_constraints") or []), "authoring_strategy": strategy,
        "authoring_instruction": instruction, "limits": {**DEFAULT_LIMITS, **_mapping(limits)}, "created_at": time_text(now),
        "expires_at": time_text(expires_at) if expires_at else _expires(now),
    }
    value["request_id"] = f"authoring-request-{fingerprint(value)[:20]}"
    value["fingerprint"] = fingerprint(value)
    return value


def _questions(reasons: list[str], limit: int) -> list[str]:
    prompts = {
        "target_file_required": "Which approved target file should be changed?", "modification_content_required": "What exact content should be authored?",
        "exact_text_required": "What exact existing text should be replaced?", "replacement_text_required": "What exact replacement text should be used?",
        "validation_requirements_required": "Which validation requirement must the candidate satisfy?", "acceptance_criteria_required": "Which acceptance criterion defines success?",
        "unsupported_strategy": "Which supported bounded authoring strategy should be used?", "inspect_evidence_required": "Inspect the target and provide its controlled evidence reference.",
    }
    return [prompts.get(reason, f"Resolve authoring constraint: {reason}.") for reason in sorted(set(reasons))[:max(1, limit)]]


def _output(request: Mapping[str, Any], status: str, operations: list[dict[str, Any]], reasons: list[str], warnings: list[str] | None = None) -> dict[str, Any]:
    req = _mapping(request)
    sources = []
    for item in list(req.get("repository_context_references") or []) + list(req.get("inspect_evidence_references") or []):
        ref = _mapping(item)
        sources.append({key: ref.get(key) for key in ("reference", "relative_path", "sha256") if ref.get(key) is not None})
    value = {"contract": OUTPUT_CONTRACT, "output_id": "", "request_id": req.get("request_id"), "status": status,
             "candidate_operations": deepcopy(operations), "rationale_summary": "Bounded deterministic authoring from immutable goal instructions and controlled inspect evidence.",
             "validation_plan": deepcopy(req.get("validation_requirements") or []),
             "unresolved_questions": _questions(reasons, int(_mapping(req.get("limits")).get("maximum_questions") or 8)) if status != "candidate_ready" else [],
             "source_references": sources, "warnings": sorted(set((warnings or []) + reasons)), "workspace_mutated": False,
             "session_created": False, "queue_created": False, "transaction_invoked": False}
    value["output_id"] = f"authoring-output-{fingerprint(value)[:20]}"
    value["fingerprint"] = fingerprint(value)
    return value


def author_candidate(request: Mapping[str, Any], *, workspace_root: Any, now: Any = None) -> dict[str, Any]:
    req, reasons = _mapping(request), []
    if req.get("contract") != REQUEST_CONTRACT: reasons.append("invalid_authoring_request_contract")
    if req.get("fingerprint") != fingerprint({k: v for k, v in req.items() if k != "fingerprint"}): reasons.append("authoring_request_fingerprint_mismatch")
    try:
        if parse_time(now) >= parse_time(req.get("expires_at")): reasons.append("authoring_request_expired")
    except (TypeError, ValueError): reasons.append("invalid_authoring_expiration")
    instruction = _mapping(req.get("authoring_instruction")); strategy = req.get("authoring_strategy")
    if FORBIDDEN_INSTRUCTION_KEYS.intersection(instruction): reasons.append("forbidden_instruction_source")
    if strategy not in SUPPORTED_STRATEGIES: reasons.append("unsupported_strategy")
    if not req.get("acceptance_criteria"): reasons.append("acceptance_criteria_required")
    if not req.get("validation_requirements"): reasons.append("validation_requirements_required")
    targets = list(req.get("target_files") or [])
    if not targets: reasons.append("target_file_required")
    limits = {**DEFAULT_LIMITS, **_mapping(req.get("limits"))}
    if len(targets) > int(limits["maximum_files"]): reasons.append("authoring_file_count_limit_exceeded")
    if reasons: return _output(req, "unsupported" if reasons == ["unsupported_strategy"] else "clarification_required", [], reasons)
    root = Path(workspace_root).resolve(strict=True)
    try:
        scopes = [_safe_relative(item) for item in req.get("approved_scope") or []]
        excluded = [_safe_relative(item) for item in req.get("excluded_scope") or []]
        targets = [_safe_relative(item) for item in targets]
    except ValueError as exc:
        return _output(req, "clarification_required", [], [str(exc)])
    evidence = {_mapping(item).get("relative_path"): _mapping(item) for item in req.get("inspect_evidence_references") or []}
    operations, total = [], 0
    for relative in targets:
        local_reasons = []
        if not _allowed(relative, scopes): local_reasons.append("scope_mismatch")
        if any(relative == item or relative.startswith(item.rstrip("/") + "/") for item in excluded): local_reasons.append("excluded_scope_violation")
        path = (root / relative).resolve(strict=False)
        if not path.is_relative_to(root): local_reasons.append("path_escape")
        cursor = root
        for part in PurePosixPath(relative).parts:
            cursor /= part
            if cursor.exists() and _unsafe(cursor): local_reasons.append("symlink_or_reparse_forbidden"); break
        exists = path.is_file()
        item = evidence.get(relative, {})
        original = ""; raw = b""
        if strategy != "create_text_file":
            if not item: local_reasons.append("inspect_evidence_required")
            if not exists: local_reasons.append("target_file_not_found")
            if exists:
                try: raw = path.read_bytes(); original = raw.decode("utf-8-sig")
                except (OSError, UnicodeError): local_reasons.append("invalid_utf8_target")
                if len(raw) > int(limits["maximum_file_bytes"]): local_reasons.append("file_bytes_limit_exceeded")
                if item.get("sha256") != sha256(raw).hexdigest(): local_reasons.append("stale_original_fingerprint")
        elif exists: local_reasons.append("create_would_overwrite_existing_file")
        content, operation = None, "replace"
        if strategy == "append_text":
            addition = instruction.get("append_text")
            if not isinstance(addition, str) or not addition: local_reasons.append("modification_content_required")
            else: content = original + addition
        elif strategy == "replace_exact_text":
            old, new = instruction.get("exact_text"), instruction.get("replacement_text")
            if not isinstance(old, str) or not old: local_reasons.append("exact_text_required")
            if not isinstance(new, str): local_reasons.append("replacement_text_required")
            if isinstance(old, str) and old:
                matches = original.count(old)
                if matches == 0: local_reasons.append("exact_text_zero_matches")
                elif matches != 1: local_reasons.append("exact_text_multiple_matches")
                elif isinstance(new, str): content = original.replace(old, new, 1)
        elif strategy == "create_text_file":
            body = instruction.get("content")
            if not isinstance(body, str): local_reasons.append("modification_content_required")
            else: content, operation = body, "create"
        elif strategy == "document_template":
            template = instruction.get("template")
            if template not in DOCUMENT_TEMPLATES: local_reasons.append("document_template_not_allowed")
            fields = _mapping(instruction.get("fields"))
            if template in DOCUMENT_TEMPLATES:
                body = fields.get(template)
                if not isinstance(body, str) or not body: local_reasons.append("modification_content_required")
                else: content = original + f"\n## {template.title()}\n\n{body}\n"
        elif strategy == "python_import_safe_edit":
            statement = instruction.get("import_statement")
            if not isinstance(statement, str) or not statement.strip(): local_reasons.append("modification_content_required")
            else:
                try:
                    tree = ast.parse(statement.strip() + "\n")
                    if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.Import, ast.ImportFrom)): raise ValueError
                    content = statement.strip() + "\n" + original
                    ast.parse(content)
                except (SyntaxError, ValueError): local_reasons.append("invalid_python_import_candidate")
        if content is not None:
            encoded = content.encode("utf-8"); total += len(encoded)
            if len(encoded) > int(limits["maximum_file_bytes"]): local_reasons.append("candidate_file_bytes_limit_exceeded")
        if local_reasons: reasons.extend(local_reasons); continue
        operation_item = {"relative_path": relative, "operation": operation, "content": content,
                          "expected_original_sha256": sha256(raw).hexdigest() if exists else None,
                          "expected_original_size": len(raw) if exists else None, "candidate_sha256": sha256(content.encode("utf-8")).hexdigest(),
                          "strategy": strategy}
        if strategy == "replace_exact_text":
            operation_item["original_fragment"] = instruction["exact_text"]
            operation_item["original_fragment_fingerprint"] = fingerprint(instruction["exact_text"])
        operations.append(operation_item)
    if total > int(limits["maximum_total_bytes"]): reasons.append("candidate_total_bytes_limit_exceeded")
    if reasons: return _output(req, "clarification_required", [], reasons)
    return _output(req, "candidate_ready", operations, [])


def _validate_artifact(value: Mapping[str, Any], contract: str, identity_key: str | None = None, identity: Any = None, now: Any = None) -> list[str]:
    item, reasons = _mapping(value), []
    if item.get("contract") != contract: reasons.append("invalid_authoring_artifact_contract")
    if item.get("fingerprint") != fingerprint({k: v for k, v in item.items() if k != "fingerprint"}): reasons.append("authoring_artifact_fingerprint_mismatch")
    if identity_key and identity is not None and item.get(identity_key) != identity: reasons.append("authoring_artifact_identity_mismatch")
    if contract == REQUEST_CONTRACT:
        try:
            if parse_time(now) >= parse_time(item.get("expires_at")): reasons.append("authoring_request_expired")
        except (TypeError, ValueError): reasons.append("invalid_authoring_expiration")
    return reasons


def save_authoring_artifact(value: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists() and _unsafe(destination): raise ValueError("unsafe_authoring_artifact_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination.parent): raise ValueError("unsafe_authoring_artifact_directory")
    item = _mapping(value)
    contract = item.get("contract")
    if contract not in {REQUEST_CONTRACT, OUTPUT_CONTRACT}: raise ValueError("invalid_authoring_artifact_contract")
    if _validate_artifact(item, contract, now=item.get("created_at")): raise ValueError("invalid_authoring_artifact")
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination)
    return item


def load_authoring_artifact(path: Any, *, expected_contract: str | None = None, expected_identity: Any = None, now: Any = None) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source): raise ValueError("unsafe_authoring_artifact_path")
    try: item = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_authoring_artifact_json") from exc
    contract = expected_contract or item.get("contract")
    identity_key = "request_id" if contract == REQUEST_CONTRACT else "output_id"
    reasons = _validate_artifact(item, contract, identity_key, expected_identity, now)
    if reasons: raise ValueError(";".join(sorted(set(reasons))))
    return item


__all__ = ["DEFAULT_LIMITS", "DOCUMENT_TEMPLATES", "OUTPUT_CONTRACT", "REQUEST_CONTRACT", "SUPPORTED_STRATEGIES",
           "author_candidate", "create_authoring_request", "load_authoring_artifact", "save_authoring_artifact"]
