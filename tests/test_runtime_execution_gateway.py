from __future__ import annotations

import sys

from core.runtime.execution_gateway import safe_subprocess_run


def test_safe_subprocess_run_success_list_command() -> None:
    result = safe_subprocess_run(
        [sys.executable, "-c", "print('hello')"],
        shell=False,
    )

    assert result["ok"] is True
    assert result["returncode"] == 0
    assert result["stdout"].strip() == "hello"
    assert result["stderr"] == ""
    assert result["shell"] is False
    assert result["error"] is None


def test_safe_subprocess_run_failure_list_command() -> None:
    result = safe_subprocess_run(
        [sys.executable, "-c", "import sys; sys.exit(7)"],
        shell=False,
    )

    assert result["ok"] is False
    assert result["returncode"] == 7
    assert result["shell"] is False


def test_safe_subprocess_run_shell_true_is_visible() -> None:
    result = safe_subprocess_run(
        "echo hello",
        shell=True,
    )

    assert result["shell"] is True
    assert "command" in result
    assert "stdout" in result
    assert "stderr" in result


def test_safe_subprocess_run_timeout_returns_contract() -> None:
    result = safe_subprocess_run(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        timeout=0.1,
    )

    assert result["ok"] is False
    assert result["returncode"] is None
    assert result["error"] is not None
    assert "timeout" in result["error"]