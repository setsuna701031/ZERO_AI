from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_autonomous_checkpoint import build_runtime_loop_checkpoint_record
from core.runtime.runtime_autonomous_persistence import persist_runtime_autonomous_session
from core.runtime.runtime_operator_service import RuntimeOperatorService


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "operator-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _service(tmp_path: Path, **overrides) -> RuntimeOperatorService:
    return RuntimeOperatorService(_config(tmp_path, **overrides))


def _bad_token():
    return {
        "token_id": "bad-token",
        "token_identity": "operator",
        "purpose": "wrong",
        "runtime_enable_token_valid": True,
    }


def test_1729_start_valid_config_starts_runtime_controller(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.start()

    assert result["ok"] is True
    assert result["controller_started"] is True
    assert result["runtime_session_id"] == "operator-runtime-session"
    assert result["token"]["token_authorized"] is True
    assert result["lease"]["lease_authorized"] is True
    assert result["start_gate"]["autonomous_start_authorized"] is True
    assert result["status"]["active"] is True
    assert result["status"]["current_tick"] == 0
    assert result["status"]["current_cursor"] == "operator-cursor-0"


def test_1732_start_invalid_token_denies_without_controller(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.start(enable_token=_bad_token())

    assert result["ok"] is False
    assert result["controller_started"] is False
    assert result["denial_reason"] == "invalid_token_purpose"
    assert result["token"]["token_authorized"] is False
    assert result["status"]["stopped"] is True


def test_1735_emergency_stop_blocks_start(tmp_path: Path) -> None:
    service = _service(tmp_path)
    stop = service.request_emergency_stop()
    result = service.start()

    assert stop["emergency_stop_active"] is True
    assert result["ok"] is False
    assert result["denial_reason"] == "emergency_stop_active"
    assert result["status"]["emergency_stop_active"] is True


def test_1738_status_returns_deterministic_runtime_state(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start()

    first = service.status()
    second = service.status()

    assert first == second
    assert first["runtime_session_id"] == "operator-runtime-session"
    assert first["runtime_state"] == "active"
    assert first["last_checkpoint"] is None
    assert first["last_result"] is None


def test_1741_stop_requests_shutdown_and_preserves_checkpoint(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start()

    result = service.stop(reason="test-stop")

    assert result["ok"] is True
    assert result["shutdown_requested"] is True
    assert result["shutdown_reason"] == "test-stop"
    assert result["lease_released"] is True
    assert result["persistence"]["persisted"] is True
    assert result["checkpoint"]["runtime_session_id"] == "operator-runtime-session"
    assert result["checkpoint"]["active_cursor"] == "operator-cursor-0"
    assert result["status"]["stopped"] is True
    assert result["status"]["last_checkpoint"] == result["checkpoint"]


def test_1745_resume_valid_checkpoint_restores_runtime_state(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start()
    service.stop()

    resumed = service.resume()

    assert resumed["ok"] is True
    assert resumed["resume_gate"]["resume_authorized"] is True
    assert resumed["status"]["active"] is True
    assert resumed["status"]["runtime_session_id"] == "operator-runtime-session"
    assert resumed["status"]["current_cursor"] == "operator-cursor-0"
    assert resumed["status"]["controller_started"] is True


def test_1748_resume_invalid_checkpoint_denies(tmp_path: Path) -> None:
    path = tmp_path / "operator-checkpoint.json"
    checkpoint = build_runtime_loop_checkpoint_record(
        checkpoint_id="bad-checkpoint",
        runtime_session_id="",
        active_cursor="cursor-1",
        current_tick_index=1,
        last_completed_work_id="work-1",
        lease_id="lease-1",
        lease_expiry_tick=3,
        runtime_state="active",
    )
    assert checkpoint["valid_checkpoint"] is False
    path.write_text(json.dumps({"checkpoint": checkpoint}), encoding="utf-8")
    service = RuntimeOperatorService(_config(tmp_path, checkpoint_path=str(path)))

    result = service.resume()

    assert result["ok"] is False
    assert result["denial_reason"] == "checkpoint_invalid"
    assert result["resume_gate"]["resume_authorized"] is False


def test_1751_health_reports_runtime_readiness(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.start()
    service.stop()

    health = service.health()

    assert health["ok"] is True
    assert health["ready"] is True
    assert health["persistence_available"] is True
    assert health["checkpoint_valid"] is True
    assert health["lease_state"] in {"inactive", "checkpointed"}
    assert health["emergency_stop_active"] is False


def test_1754_cli_commands_emit_json_payloads(tmp_path: Path, capsys) -> None:
    checkpoint_path = str(tmp_path / "cli-checkpoint.json")

    start_code = zero_runtime_main(["--checkpoint-path", checkpoint_path, "start"])
    start_output = json.loads(capsys.readouterr().out)
    status_code = zero_runtime_main(["--checkpoint-path", checkpoint_path, "status"])
    status_output = json.loads(capsys.readouterr().out)
    health_code = zero_runtime_main(["--checkpoint-path", checkpoint_path, "health"])
    health_output = json.loads(capsys.readouterr().out)

    assert start_code == 0
    assert start_output["ok"] is True
    assert start_output["action"] == "start"
    assert status_code == 0
    assert status_output["action"] == "status"
    assert status_output["stopped"] is True
    assert health_code == 0
    assert health_output["action"] == "health"


def test_1760_cli_and_service_boundary_scan() -> None:
    files = [
        Path("cli/zero_runtime_cli.py"),
        Path("core/runtime/runtime_operator_service.py"),
    ]
    forbidden = [
        "import executor",
        "from executor",
        "run_one_step",
        "progress_memory",
        ".run(",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
