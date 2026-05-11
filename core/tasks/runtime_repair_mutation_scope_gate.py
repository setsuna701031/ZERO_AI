from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


DEFAULT_ALLOWED_PATHS = [
    "workspace/shared/**",
    "workspace/tasks/**",
]

DEFAULT_BLOCKED_PATHS = [
    "app.py",
    "services/system_boot.py",
    "core/planning/**",
    "core/tasks/scheduler.py",
    "core/agent/agent_loop.py",
    ".git/**",
    ".env",
]

SAFE_SCOPE_ACTIONS = [
    "inspect_runtime_state",
    "inspect_execution_log",
    "inspect_trace",
    "inspect_result",
    "propose_repair_plan",
    "prepare_code_repair",
    "generate_patch_preview",
]

BLOCKED_MUTATION_ACTIONS = [
    "apply_patch",
    "write_file",
    "delete_file",
    "run_shell_command",
    "schedule_task",
    "modify_scheduler",
    "modify_planner",
    "auto_retry",
    "auto_repair",
    "auto_apply_patch",
]


def build_runtime_repair_mutation_scope_gate(
    authorization: Any,
    *,
    target_paths: Optional[List[Any]] = None,
    requested_actions: Optional[List[Any]] = None,
    allowed_paths: Optional[List[str]] = None,
    blocked_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a deterministic mutation scope gate.

    This layer is side-effect free. It does not write files, apply patches,
    execute commands, schedule tasks, or mutate the provided authorization.
    It only decides whether a proposed repair mutation stays inside an allowed
    scope.
    """
    safe_authorization = authorization if isinstance(authorization, Mapping) else {}

    authorized = bool(safe_authorization.get("authorized", False))
    task_id = _first_nonempty(safe_authorization.get("task_id"))
    proposal_id = _first_nonempty(safe_authorization.get("proposal_id"))

    resolved_allowed_paths = _normalize_patterns(allowed_paths or DEFAULT_ALLOWED_PATHS)
    resolved_blocked_paths = _normalize_patterns(blocked_paths or DEFAULT_BLOCKED_PATHS)

    requested_path_values = _string_list(
        target_paths,
        fallback=_extract_paths_from_authorization(safe_authorization),
    )
    requested_action_values = _string_list(
        requested_actions,
        fallback=_extract_requested_actions(safe_authorization),
    )

    path_decisions = [
        _decide_path_scope(
            path,
            allowed_patterns=resolved_allowed_paths,
            blocked_patterns=resolved_blocked_paths,
        )
        for path in requested_path_values
    ]

    action_decisions = [
        _decide_action_scope(action)
        for action in requested_action_values
    ]

    blocked_reasons: List[str] = []
    if not authorized:
        blocked_reasons.append("mutation_authorization_not_granted")

    for decision in path_decisions:
        if not decision["allowed"]:
            blocked_reasons.append(f"path_blocked:{decision['path']}:{decision['reason']}")

    for decision in action_decisions:
        if not decision["allowed"]:
            blocked_reasons.append(f"action_blocked:{decision['action']}:{decision['reason']}")

    scope_allowed = authorized and not blocked_reasons

    return {
        "ok": True,
        "task_id": task_id,
        "proposal_id": proposal_id,
        "scope_status": "allowed" if scope_allowed else "blocked",
        "scope_allowed": scope_allowed,
        "authorization_granted": authorized,
        "target_paths": requested_path_values,
        "requested_actions": requested_action_values,
        "allowed_paths": resolved_allowed_paths,
        "blocked_paths": resolved_blocked_paths,
        "allowed_actions": SAFE_SCOPE_ACTIONS,
        "blocked_actions": BLOCKED_MUTATION_ACTIONS,
        "path_decisions": path_decisions,
        "action_decisions": action_decisions,
        "blocked_reasons": _unique(blocked_reasons),
        "mutation_allowed": False,
        "execution_allowed": False,
        "schedule_allowed": False,
        "allowed_next_action": "build_patch_preview" if scope_allowed else "inspect_scope_block",
        "human_summary": _build_summary(scope_allowed, blocked_reasons),
        "raw_authorization": dict(safe_authorization),
    }


def _decide_path_scope(
    path: str,
    *,
    allowed_patterns: List[str],
    blocked_patterns: List[str],
) -> Dict[str, Any]:
    normalized = _normalize_path(path)

    if not normalized:
        return {
            "path": path,
            "normalized_path": normalized,
            "allowed": False,
            "reason": "empty_path",
            "matched_allowed": "",
            "matched_blocked": "",
        }

    blocked_match = _first_matching_pattern(normalized, blocked_patterns)
    if blocked_match:
        return {
            "path": path,
            "normalized_path": normalized,
            "allowed": False,
            "reason": "blocked_path_pattern",
            "matched_allowed": "",
            "matched_blocked": blocked_match,
        }

    allowed_match = _first_matching_pattern(normalized, allowed_patterns)
    if allowed_match:
        return {
            "path": path,
            "normalized_path": normalized,
            "allowed": True,
            "reason": "allowed_path_pattern",
            "matched_allowed": allowed_match,
            "matched_blocked": "",
        }

    return {
        "path": path,
        "normalized_path": normalized,
        "allowed": False,
        "reason": "outside_allowed_paths",
        "matched_allowed": "",
        "matched_blocked": "",
    }


def _decide_action_scope(action: str) -> Dict[str, Any]:
    normalized = _normalize_action(action)

    if not normalized:
        return {
            "action": action,
            "normalized_action": normalized,
            "allowed": False,
            "reason": "empty_action",
        }

    if normalized in BLOCKED_MUTATION_ACTIONS:
        return {
            "action": action,
            "normalized_action": normalized,
            "allowed": False,
            "reason": "blocked_mutation_action",
        }

    if normalized in SAFE_SCOPE_ACTIONS:
        return {
            "action": action,
            "normalized_action": normalized,
            "allowed": True,
            "reason": "safe_scope_action",
        }

    return {
        "action": action,
        "normalized_action": normalized,
        "allowed": False,
        "reason": "unknown_action",
    }


def _extract_paths_from_authorization(authorization: Mapping[str, Any]) -> List[str]:
    for key in ("target_paths", "paths", "requested_paths", "candidate_paths"):
        value = authorization.get(key)
        paths = _string_list(value, fallback=[])
        if paths:
            return paths

    repair_intent = authorization.get("repair_intent")
    if isinstance(repair_intent, Mapping):
        for key in ("target_paths", "paths", "requested_paths", "candidate_paths"):
            paths = _string_list(repair_intent.get(key), fallback=[])
            if paths:
                return paths

    return []


def _extract_requested_actions(authorization: Mapping[str, Any]) -> List[str]:
    for key in ("requested_actions", "allowed_actions", "proposed_actions", "actions"):
        actions = _string_list(authorization.get(key), fallback=[])
        if actions:
            return actions

    repair_intent = authorization.get("repair_intent")
    if isinstance(repair_intent, Mapping):
        for key in ("requested_actions", "allowed_actions", "proposed_actions", "actions"):
            actions = _string_list(repair_intent.get(key), fallback=[])
            if actions:
                return actions

    return ["prepare_code_repair"]


def _first_matching_pattern(path: str, patterns: List[str]) -> str:
    for pattern in patterns:
        if _path_matches(path, pattern):
            return pattern
    return ""


def _path_matches(path: str, pattern: str) -> bool:
    normalized_path = _normalize_path(path)
    normalized_pattern = _normalize_path(pattern)

    if not normalized_path or not normalized_pattern:
        return False

    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized_path == prefix or normalized_path.startswith(prefix + "/")

    if normalized_pattern.endswith("/*"):
        prefix = normalized_pattern[:-2].rstrip("/")
        if not (normalized_path == prefix or normalized_path.startswith(prefix + "/")):
            return False
        remainder = normalized_path[len(prefix):].strip("/")
        return bool(remainder) and "/" not in remainder

    return normalized_path == normalized_pattern


def _normalize_patterns(patterns: List[str]) -> List[str]:
    return _unique([_normalize_path(pattern) for pattern in patterns])


def _normalize_path(path: Any) -> str:
    text = str(path or "").strip()
    if not text:
        return ""

    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")

    if len(text) >= 3 and text[1] == ":" and text[2] == "/":
        text = text[3:]

    if text.startswith("./"):
        text = text[2:]

    while text.startswith("/"):
        text = text[1:]

    return text.strip("/")


def _normalize_action(action: Any) -> str:
    return str(action or "").strip().lower()


def _string_list(value: Any, *, fallback: Optional[List[str]] = None) -> List[str]:
    if isinstance(value, list):
        return _unique([str(item).strip() for item in value if str(item or "").strip()])
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return list(fallback or [])


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _build_summary(scope_allowed: bool, blocked_reasons: List[str]) -> str:
    if scope_allowed:
        return "Mutation scope gate passed for preview-only repair routing. Mutation remains disabled until a later executor gate."
    if not blocked_reasons:
        return "Mutation scope gate blocked."
    return "Mutation scope gate blocked: " + ", ".join(_unique(blocked_reasons))


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
