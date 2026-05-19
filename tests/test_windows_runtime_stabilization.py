from __future__ import annotations

import copy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_detects_broken_venv_launcher_base_interpreter(tmp_path: Path) -> None:
    from core.runtime.windows_runtime_stabilization import (
        inspect_python_launcher_consistency,
    )

    venv_dir = tmp_path / ".venv"
    launcher = _touch(venv_dir / "Scripts" / "python.exe")
    missing_base = tmp_path / "missing" / "Python311" / "python.exe"
    (venv_dir / "pyvenv.cfg").write_text(
        f"home = {missing_base.parent}\n"
        f"executable = {missing_base}\n",
        encoding="utf-8",
    )

    result = inspect_python_launcher_consistency(
        python_launcher_path=launcher,
        venv_dir=venv_dir,
    )

    assert result["launcher_valid"] is True
    assert result["base_interpreter_missing"] is True
    assert result["expected_base_interpreter"] == str(missing_base)
    assert {
        "kind": "base_interpreter_missing",
        "path": str(missing_base),
    } in result["blocking_issues"]


def test_detects_invalid_windows_python_launcher_paths() -> None:
    from core.runtime.windows_runtime_stabilization import (
        inspect_python_launcher_consistency,
    )

    result = inspect_python_launcher_consistency(
        python_launcher_path="relative\\bad|path\\not-python.cmd",
    )

    assert result["launcher_valid"] is False
    assert "invalid_windows_path_characters" in result["launcher_invalid_reasons"]
    assert "not_python_launcher_name" in result["launcher_invalid_reasons"]
    assert "path_not_absolute" in result["launcher_invalid_reasons"]
    assert result["blocking_issues"][0]["kind"] == "invalid_python_launcher"


def test_detects_inconsistent_bundled_python_execution_paths(tmp_path: Path) -> None:
    from core.runtime.windows_runtime_stabilization import (
        inspect_python_launcher_consistency,
    )

    launcher = _touch(tmp_path / "venv" / "Scripts" / "python.exe")
    base = _touch(tmp_path / "base" / "python.exe")
    bundled = _touch(tmp_path / "bundle-a" / "python.exe")
    expected_bundled = tmp_path / "bundle-b" / "python.exe"

    result = inspect_python_launcher_consistency(
        python_launcher_path=launcher,
        expected_base_interpreter=base,
        bundled_python_path=bundled,
        expected_bundled_python_path=expected_bundled,
    )

    assert result["launcher_valid"] is True
    assert result["base_interpreter_missing"] is False
    assert result["bundled_python_detected"] is True
    assert result["bundled_python_inconsistent"] is True
    assert {
        "kind": "bundled_python_inconsistent",
        "expected": str(expected_bundled),
        "actual": str(bundled),
    } in result["blocking_issues"]


def test_cli_json_safety_detects_circular_reference_hazards() -> None:
    from core.runtime.windows_runtime_stabilization import inspect_cli_json_safety

    payload: dict = {"result": []}
    payload["result"].append(payload)

    result = inspect_cli_json_safety(payload)

    assert result["json_safe"] is False
    assert result["circular_reference_risk"] is True
    assert result["circular_reference_paths"] == ["$.result[0]->$"]
    assert result["blocking_issues"][0]["kind"] == "cli_json_circular_reference"


def test_cli_json_safety_accepts_plain_payloads_and_does_not_mutate() -> None:
    from core.runtime.windows_runtime_stabilization import inspect_cli_json_safety

    payload = {"ok": True, "items": [{"value": 1}]}
    before = copy.deepcopy(payload)

    result = inspect_cli_json_safety(payload)

    assert result["json_safe"] is True
    assert result["circular_reference_risk"] is False
    assert result["blocking_issues"] == []
    assert payload == before


def test_smoke_execution_blockers_collect_runtime_json_and_command_issues() -> None:
    from core.runtime.windows_runtime_stabilization import (
        inspect_smoke_execution_blockers,
    )

    result = inspect_smoke_execution_blockers(
        launcher_report={
            "launcher_valid": False,
            "launcher_path": "C:\\missing\\python.exe",
            "base_interpreter_missing": True,
            "expected_base_interpreter": "C:\\missing-base\\python.exe",
            "bundled_python_inconsistent": True,
            "expected_bundled_python_path": "C:\\expected\\python.exe",
            "bundled_python_path": "C:\\actual\\python.exe",
        },
        json_report={
            "json_safe": False,
            "circular_reference_risk": True,
            "serialization_error": "ValueError: Circular reference detected",
        },
        smoke_commands=["", ["python", ""], ["python", "-m", "pytest"]],
        required_paths=["C:\\missing-required"],
    )

    blocker_kinds = [item["kind"] for item in result["smoke_blockers"]]
    assert result["smoke_ready"] is False
    assert blocker_kinds == [
        "python_launcher_blocked",
        "base_interpreter_missing",
        "bundled_python_inconsistent",
        "cli_json_not_safe",
        "invalid_smoke_command",
        "invalid_smoke_command",
        "required_path_missing",
    ]


def test_build_windows_runtime_report_is_stable_for_clean_environment(tmp_path: Path) -> None:
    from core.runtime.windows_runtime_stabilization import build_windows_runtime_report

    launcher = _touch(tmp_path / "venv" / "Scripts" / "python.exe")
    base = _touch(tmp_path / "base" / "python.exe")
    bundled = _touch(tmp_path / "bundle" / "python.exe")
    required = _touch(tmp_path / "tests" / "smoke.py")

    kwargs = {
        "python_launcher_path": launcher,
        "expected_base_interpreter": base,
        "bundled_python_path": bundled,
        "expected_bundled_python_path": bundled,
        "cli_payload": {"ok": True},
        "smoke_commands": [["python", "-m", "pytest"]],
        "required_paths": [required],
    }
    first = build_windows_runtime_report(**kwargs)
    second = build_windows_runtime_report(**kwargs)

    assert first == second
    assert first["report_id"].startswith("windows-runtime-stabilization-")
    assert first["launcher_valid"] is True
    assert first["base_interpreter_missing"] is False
    assert first["bundled_python_detected"] is True
    assert first["circular_reference_risk"] is False
    assert first["json_safe"] is True
    assert first["smoke_blockers"] == []
    assert first["blocking_issues"] == []
    assert first["runtime_environment_score"] == 1.0


def test_build_windows_runtime_report_surfaces_blocking_issues(tmp_path: Path) -> None:
    from core.runtime.windows_runtime_stabilization import build_windows_runtime_report

    launcher = _touch(tmp_path / "venv" / "Scripts" / "python.exe")
    missing_base = tmp_path / "missing" / "python.exe"
    payload: dict = {"self": None}
    payload["self"] = payload

    report = build_windows_runtime_report(
        python_launcher_path=launcher,
        expected_base_interpreter=missing_base,
        cli_payload=payload,
        smoke_commands=[[]],
    )

    assert report["launcher_valid"] is True
    assert report["base_interpreter_missing"] is True
    assert report["circular_reference_risk"] is True
    assert report["json_safe"] is False
    assert report["smoke_blockers"]
    assert report["blocking_issues"]
    assert report["runtime_environment_score"] < 1.0


def test_inspect_windows_runtime_environment_returns_component_reports(tmp_path: Path) -> None:
    from core.runtime.windows_runtime_stabilization import (
        inspect_windows_runtime_environment,
    )

    launcher = _touch(tmp_path / "venv" / "Scripts" / "python.exe")
    base = _touch(tmp_path / "base" / "python.exe")

    result = inspect_windows_runtime_environment(
        python_launcher_path=launcher,
        expected_base_interpreter=base,
        cli_payload={"ok": True},
        smoke_commands=["python -m pytest"],
    )

    assert sorted(result) == ["json", "launcher", "smoke"]
    assert result["launcher"]["launcher_valid"] is True
    assert result["json"]["json_safe"] is True
    assert result["smoke"]["smoke_ready"] is True
