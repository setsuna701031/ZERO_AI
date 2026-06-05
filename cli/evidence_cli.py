from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.tasks.engineering_evidence_observability import EngineeringEvidenceObservability
from core.tasks.engineering_evidence_repository import EngineeringEvidenceRepository
from core.tasks.engineering_evidence_state import EngineeringEvidenceState


EVIDENCE_CLI_SCHEMA = "zero.evidence_cli.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _workspace_dir() -> str:
    return os.environ.get("ZERO_WORKSPACE", "workspace")


def _workspace_root(repo_root: Path) -> Path:
    workspace = Path(_workspace_dir())
    if workspace.is_absolute():
        return workspace
    return repo_root / workspace


def _evidence_store_path(repo_root: Path) -> Path:
    override = os.environ.get("ZERO_EVIDENCE_STORE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else repo_root / path
    if os.environ.get("ZERO_WORKSPACE"):
        return _workspace_root(repo_root) / "engineering_evidence.json"
    return repo_root / "runtime" / "evidence" / "evidence.json"


def _repository(repo_root: Path) -> EngineeringEvidenceRepository:
    return EngineeringEvidenceRepository(repo_root, storage_path=_evidence_store_path(repo_root))


def _evidence_state(repo_root: Path) -> EngineeringEvidenceState:
    return EngineeringEvidenceState(repo_root, evidence_repository=_repository(repo_root))


def _evidence_observability(repo_root: Path) -> EngineeringEvidenceObservability:
    repository = _repository(repo_root)
    return EngineeringEvidenceObservability(
        repo_root,
        evidence_repository=repository,
        evidence_state=EngineeringEvidenceState(repo_root, evidence_repository=repository),
    )


def _parse_create_fields(argv: list[str]) -> dict[str, Any]:
    fields: dict[str, Any] = {"metadata": {"source": "evidence_cli"}}
    name_parts: list[str] = []
    option_map = {
        "--id": "evidence_id",
        "--artifact": "artifact_id",
        "--artifact-id": "artifact_id",
        "--goal": "goal_id",
        "--goal-id": "goal_id",
        "--portfolio": "portfolio_id",
        "--portfolio-id": "portfolio_id",
        "--program": "program_id",
        "--program-id": "program_id",
        "--type": "evidence_type",
        "--evidence-type": "evidence_type",
        "--path": "evidence_path",
        "--evidence-path": "evidence_path",
        "--created-at": "created_at",
        "--state": "state",
    }
    index = 2
    while index < len(argv):
        token = argv[index]
        if token == "--archived":
            fields.setdefault("metadata", {})["archived"] = True
            index += 1
            continue
        key = option_map.get(token)
        if key and index + 1 < len(argv):
            value = argv[index + 1]
            if key == "state":
                fields.setdefault("metadata", {})["state"] = value
            elif key == "created_at":
                try:
                    fields[key] = float(value)
                except ValueError:
                    fields[key] = value
            else:
                fields[key] = value
            index += 2
            continue
        name_parts.append(token)
        index += 1
    fields["evidence_name"] = " ".join(name_parts).strip() or _clean_text(fields.get("evidence_path"), "Untitled evidence")
    return fields


def _handle_create(argv: list[str], repo_root: Path) -> bool:
    if len(argv) < 3 or argv[1] != "create":
        return False
    try:
        evidence = _repository(repo_root).create_evidence(_parse_create_fields(argv))
    except ValueError as exc:
        _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": False, "created": False, "error": str(exc)})
        return True
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": True, "created": True, "evidence": evidence})
    return True


def _handle_list(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "list":
        return False
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": True, "evidence": _repository(repo_root).list_evidence()})
    return True


def _handle_show(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "show":
        return False
    evidence = _repository(repo_root).get_evidence(argv[2])
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": evidence is not None, "evidence_id": argv[2], "evidence": evidence or {}})
    return True


def _handle_delete(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "delete":
        return False
    result = _repository(repo_root).delete_evidence(argv[2])
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": bool(result.get("ok")), "evidence_delete": result})
    return True


def _handle_state(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "state":
        return False
    result = _evidence_state(repo_root).evaluate_evidence_state()
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": bool(result.get("ok")), "evidence_state": result})
    return True


def _handle_summary(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "summary":
        return False
    result = _evidence_state(repo_root).summarize_evidence()
    _print_json(
        {
            "schema": EVIDENCE_CLI_SCHEMA,
            "ok": bool(result.get("ok")),
            "evidence_summary": result,
            "policy_summary": result.get("policy_summary") or {},
        }
    )
    return True


def _handle_tree(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "tree":
        return False
    result = _evidence_observability(repo_root).build_evidence_tree_summary()
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": bool(result.get("ok")), "evidence_tree": result})
    return True


def _handle_observability(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 2 or argv[1] != "observability":
        return False
    result = _evidence_observability(repo_root).calculate_rollup_metrics()
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": bool(result.get("ok")), "evidence_observability": result})
    return True


def _handle_list_artifact(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "list-artifact":
        return False
    evidence = _repository(repo_root).list_artifact_evidence(argv[2])
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": True, "artifact_id": argv[2], "evidence": evidence})
    return True


def _handle_list_goal(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "list-goal":
        return False
    evidence = _repository(repo_root).list_goal_evidence(argv[2])
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": True, "goal_id": argv[2], "evidence": evidence})
    return True


def _handle_list_portfolio(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "list-portfolio":
        return False
    evidence = _repository(repo_root).list_portfolio_evidence(argv[2])
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": True, "portfolio_id": argv[2], "evidence": evidence})
    return True


def _handle_list_program(argv: list[str], repo_root: Path) -> bool:
    if len(argv) != 3 or argv[1] != "list-program":
        return False
    evidence = _repository(repo_root).list_program_evidence(argv[2])
    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": True, "program_id": argv[2], "evidence": evidence})
    return True


def try_handle_evidence_command(argv: list[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item).strip() for item in argv if str(item).strip()]
    if not clean_argv or clean_argv[0].lower() != "evidence":
        return False
    normalized = [clean_argv[0].lower(), *[item.lower() if index == 1 else item for index, item in enumerate(clean_argv[1:], start=1)]]

    for handler in (
        _handle_create,
        _handle_list,
        _handle_show,
        _handle_delete,
        _handle_state,
        _handle_summary,
        _handle_tree,
        _handle_observability,
        _handle_list_artifact,
        _handle_list_goal,
        _handle_list_portfolio,
        _handle_list_program,
    ):
        if handler(normalized, repo_root):
            return True

    _print_json({"schema": EVIDENCE_CLI_SCHEMA, "ok": False, "error": "unknown_evidence_command"})
    return True


__all__ = ["EVIDENCE_CLI_SCHEMA", "try_handle_evidence_command"]
