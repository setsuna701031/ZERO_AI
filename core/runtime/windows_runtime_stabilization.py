from __future__ import annotations

import hashlib
import json
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "windows_runtime_stabilization.v1"

_WINDOWS_INVALID_CHARS = set('<>"|?*')
_PYTHON_LAUNCHER_NAMES = {"python.exe", "pythonw.exe", "py.exe"}


def inspect_python_launcher_consistency(
    *,
    python_launcher_path: str | Path | None = None,
    venv_dir: str | Path | None = None,
    expected_base_interpreter: str | Path | None = None,
    bundled_python_path: str | Path | None = None,
    expected_bundled_python_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Inspect Windows Python launcher/base interpreter consistency without executing it."""

    launcher = _path_text(python_launcher_path)
    venv = _path_text(venv_dir)
    expected_base = _path_text(expected_base_interpreter)
    bundled = _path_text(bundled_python_path)
    expected_bundled = _path_text(expected_bundled_python_path)

    if not expected_base and venv:
        expected_base = _base_interpreter_from_pyvenv_cfg(Path(venv) / "pyvenv.cfg")
    if not launcher and venv:
        launcher = str(Path(venv) / "Scripts" / "python.exe")

    launcher_invalid_reasons = _invalid_windows_python_path_reasons(launcher)
    launcher_exists = bool(launcher) and Path(launcher).exists()
    base_missing = bool(expected_base) and not Path(expected_base).exists()
    bundled_detected = bool(bundled) and Path(bundled).exists()
    bundled_inconsistent = (
        bool(bundled and expected_bundled)
        and _normalize_path(bundled) != _normalize_path(expected_bundled)
    )

    blocking_issues: List[Dict[str, Any]] = []
    if not launcher or launcher_invalid_reasons or not launcher_exists:
        blocking_issues.append(
            {
                "kind": "invalid_python_launcher",
                "path": launcher,
                "reasons": launcher_invalid_reasons
                + ([] if launcher_exists else ["launcher_missing"]),
            }
        )
    if base_missing:
        blocking_issues.append(
            {
                "kind": "base_interpreter_missing",
                "path": expected_base,
            }
        )
    if bundled_inconsistent:
        blocking_issues.append(
            {
                "kind": "bundled_python_inconsistent",
                "expected": expected_bundled,
                "actual": bundled,
            }
        )

    return {
        "launcher_path": launcher,
        "venv_dir": venv,
        "expected_base_interpreter": expected_base,
        "launcher_valid": bool(launcher) and launcher_exists and not launcher_invalid_reasons,
        "launcher_exists": launcher_exists,
        "launcher_invalid_reasons": launcher_invalid_reasons,
        "base_interpreter_missing": base_missing,
        "bundled_python_path": bundled,
        "expected_bundled_python_path": expected_bundled,
        "bundled_python_detected": bundled_detected,
        "bundled_python_inconsistent": bundled_inconsistent,
        "blocking_issues": blocking_issues,
    }


def inspect_cli_json_safety(payload: Any) -> Dict[str, Any]:
    """Detect circular-reference and JSON serialization hazards for CLI output."""

    circular_paths = _detect_circular_paths(payload)
    serialization_error = ""
    json_safe = False
    try:
        json.dumps(payload, sort_keys=True, default=str)
        json_safe = not circular_paths
    except (TypeError, ValueError) as exc:
        serialization_error = f"{type(exc).__name__}: {exc}"

    blocking_issues: List[Dict[str, Any]] = []
    if circular_paths:
        blocking_issues.append(
            {
                "kind": "cli_json_circular_reference",
                "paths": circular_paths,
            }
        )
    if serialization_error:
        blocking_issues.append(
            {
                "kind": "cli_json_serialization_error",
                "error": serialization_error,
            }
        )

    return {
        "json_safe": json_safe,
        "circular_reference_risk": bool(circular_paths),
        "circular_reference_paths": circular_paths,
        "serialization_error": serialization_error,
        "blocking_issues": blocking_issues,
    }


def inspect_smoke_execution_blockers(
    *,
    launcher_report: Mapping[str, Any] | None = None,
    json_report: Mapping[str, Any] | None = None,
    smoke_commands: Iterable[Any] | None = None,
    required_paths: Iterable[str | Path] | None = None,
) -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    launcher = launcher_report if isinstance(launcher_report, Mapping) else {}
    json_safety = json_report if isinstance(json_report, Mapping) else {}

    if launcher.get("launcher_valid") is False:
        blockers.append(
            {
                "kind": "python_launcher_blocked",
                "path": _text(launcher.get("launcher_path")),
            }
        )
    if launcher.get("base_interpreter_missing") is True:
        blockers.append(
            {
                "kind": "base_interpreter_missing",
                "path": _text(launcher.get("expected_base_interpreter")),
            }
        )
    if launcher.get("bundled_python_inconsistent") is True:
        blockers.append(
            {
                "kind": "bundled_python_inconsistent",
                "expected": _text(launcher.get("expected_bundled_python_path")),
                "actual": _text(launcher.get("bundled_python_path")),
            }
        )
    if json_safety.get("json_safe") is False:
        blockers.append(
            {
                "kind": "cli_json_not_safe",
                "circular_reference_risk": bool(json_safety.get("circular_reference_risk")),
                "error": _text(json_safety.get("serialization_error")),
            }
        )

    for index, command in enumerate(smoke_commands or []):
        if not _valid_smoke_command(command):
            blockers.append(
                {
                    "kind": "invalid_smoke_command",
                    "index": index,
                    "command": _stable_repr(command),
                }
            )

    for path in required_paths or []:
        text = _path_text(path)
        if not text or not Path(text).exists():
            blockers.append(
                {
                    "kind": "required_path_missing",
                    "path": text,
                }
            )

    return {
        "smoke_blockers": blockers,
        "smoke_ready": not blockers,
    }


def inspect_windows_runtime_environment(
    *,
    python_launcher_path: str | Path | None = None,
    venv_dir: str | Path | None = None,
    expected_base_interpreter: str | Path | None = None,
    bundled_python_path: str | Path | None = None,
    expected_bundled_python_path: str | Path | None = None,
    cli_payload: Any = None,
    smoke_commands: Iterable[Any] | None = None,
    required_paths: Iterable[str | Path] | None = None,
) -> Dict[str, Any]:
    launcher_report = inspect_python_launcher_consistency(
        python_launcher_path=python_launcher_path,
        venv_dir=venv_dir,
        expected_base_interpreter=expected_base_interpreter,
        bundled_python_path=bundled_python_path,
        expected_bundled_python_path=expected_bundled_python_path,
    )
    json_report = inspect_cli_json_safety({} if cli_payload is None else cli_payload)
    smoke_report = inspect_smoke_execution_blockers(
        launcher_report=launcher_report,
        json_report=json_report,
        smoke_commands=smoke_commands,
        required_paths=required_paths,
    )
    return {
        "launcher": launcher_report,
        "json": json_report,
        "smoke": smoke_report,
    }


def build_windows_runtime_report(
    *,
    python_launcher_path: str | Path | None = None,
    venv_dir: str | Path | None = None,
    expected_base_interpreter: str | Path | None = None,
    bundled_python_path: str | Path | None = None,
    expected_bundled_python_path: str | Path | None = None,
    cli_payload: Any = None,
    smoke_commands: Iterable[Any] | None = None,
    required_paths: Iterable[str | Path] | None = None,
) -> Dict[str, Any]:
    environment = inspect_windows_runtime_environment(
        python_launcher_path=python_launcher_path,
        venv_dir=venv_dir,
        expected_base_interpreter=expected_base_interpreter,
        bundled_python_path=bundled_python_path,
        expected_bundled_python_path=expected_bundled_python_path,
        cli_payload=cli_payload,
        smoke_commands=smoke_commands,
        required_paths=required_paths,
    )
    launcher = environment["launcher"]
    json_report = environment["json"]
    smoke = environment["smoke"]
    blocking_issues = _stable_issues(
        [
            *launcher.get("blocking_issues", []),
            *json_report.get("blocking_issues", []),
            *smoke.get("smoke_blockers", []),
        ]
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "",
        "launcher_valid": bool(launcher.get("launcher_valid")),
        "base_interpreter_missing": bool(launcher.get("base_interpreter_missing")),
        "bundled_python_detected": bool(launcher.get("bundled_python_detected")),
        "bundled_python_inconsistent": bool(launcher.get("bundled_python_inconsistent")),
        "circular_reference_risk": bool(json_report.get("circular_reference_risk")),
        "smoke_blockers": smoke.get("smoke_blockers", []),
        "json_safe": bool(json_report.get("json_safe")),
        "runtime_environment_score": _runtime_environment_score(
            launcher=launcher,
            json_report=json_report,
            smoke=smoke,
            blocking_issues=blocking_issues,
        ),
        "blocking_issues": blocking_issues,
        "details": environment,
    }
    report["report_id"] = _report_id(report)
    return report


def _base_interpreter_from_pyvenv_cfg(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    values: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip()
    executable = values.get("executable", "")
    if executable:
        return executable
    home = values.get("home", "")
    if home:
        return str(Path(home) / "python.exe")
    return ""


def _invalid_windows_python_path_reasons(path: str) -> List[str]:
    if not path:
        return ["path_empty"]
    reasons: List[str] = []
    try:
        windows_path = PureWindowsPath(path)
    except Exception as exc:
        return [f"path_parse_error:{type(exc).__name__}"]
    parts = windows_path.parts
    for part in parts:
        if part.endswith(":"):
            continue
        if any(char in _WINDOWS_INVALID_CHARS for char in part):
            reasons.append("invalid_windows_path_characters")
            break
    name = windows_path.name.lower()
    if name and name not in _PYTHON_LAUNCHER_NAMES:
        reasons.append("not_python_launcher_name")
    if not windows_path.is_absolute():
        reasons.append("path_not_absolute")
    return reasons


def _detect_circular_paths(value: Any) -> List[str]:
    paths: List[str] = []

    def visit(item: Any, path: str, seen: Dict[int, str]) -> None:
        if not isinstance(item, (dict, list, tuple, set, frozenset)):
            return
        item_id = id(item)
        if item_id in seen:
            paths.append(f"{path}->{seen[item_id]}")
            return
        next_seen = dict(seen)
        next_seen[item_id] = path
        if isinstance(item, dict):
            for key, child in item.items():
                visit(child, _child_path(path, key), next_seen)
        else:
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]", next_seen)

    visit(value, "$", {})
    return sorted(paths)


def _child_path(path: str, key: Any) -> str:
    text = _text(key).replace("\\", "\\\\").replace("'", "\\'")
    if text.isidentifier():
        return f"{path}.{text}"
    return f"{path}['{text}']"


def _valid_smoke_command(command: Any) -> bool:
    if isinstance(command, str):
        return bool(command.strip())
    if isinstance(command, (list, tuple)):
        return bool(command) and all(_text(part) for part in command)
    return False


def _runtime_environment_score(
    *,
    launcher: Mapping[str, Any],
    json_report: Mapping[str, Any],
    smoke: Mapping[str, Any],
    blocking_issues: List[Dict[str, Any]],
) -> float:
    checks = [
        bool(launcher.get("launcher_valid")),
        not bool(launcher.get("base_interpreter_missing")),
        bool(launcher.get("bundled_python_detected")) or not _text(launcher.get("bundled_python_path")),
        not bool(launcher.get("bundled_python_inconsistent")),
        bool(json_report.get("json_safe")),
        not bool(json_report.get("circular_reference_risk")),
        not bool(smoke.get("smoke_blockers")),
    ]
    passed = sum(1 for item in checks if item)
    penalty = min(len(blocking_issues), len(checks))
    return round(max(0.0, (passed - penalty * 0.25) / len(checks)), 4)


def _stable_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    normalized = [
        issue
        for issue in (_json_safe_issue(item) for item in issues)
        if issue
    ]
    return sorted(normalized, key=lambda item: _stable_hash(item))


def _json_safe_issue(issue: Any) -> Dict[str, Any]:
    if not isinstance(issue, Mapping):
        return {}
    return json.loads(json.dumps(dict(issue), sort_keys=True, default=str))


def _report_id(report: Mapping[str, Any]) -> str:
    payload = {
        "launcher_valid": report.get("launcher_valid"),
        "base_interpreter_missing": report.get("base_interpreter_missing"),
        "bundled_python_detected": report.get("bundled_python_detected"),
        "bundled_python_inconsistent": report.get("bundled_python_inconsistent"),
        "circular_reference_risk": report.get("circular_reference_risk"),
        "json_safe": report.get("json_safe"),
        "smoke_blockers": report.get("smoke_blockers", []),
        "blocking_issues": report.get("blocking_issues", []),
    }
    return "windows-runtime-stabilization-" + _stable_hash(payload)[:16]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_repr(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _path_text(value: str | Path | None) -> str:
    return str(value or "").strip()


def _normalize_path(value: str) -> str:
    return str(Path(value)).casefold()


def _text(value: Any) -> str:
    return str(value or "").strip()
