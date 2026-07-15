from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); return int(sock.getsockname()[1])


def _wait_ready(port: int) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2): return
        except OSError: time.sleep(0.05)
    raise AssertionError("dashboard did not become ready")


@pytest.mark.parametrize("read_only", [False, True])
def test_real_cli_console_interrupt_exits_cleanly_and_releases_port(tmp_path, read_only):
    port = _free_port(); command = [sys.executable, "-m", "cli.zero_dashboard", "--workspace-root", str(tmp_path), "--port", str(port), "--no-browser"]
    if read_only: command.append("--read-only")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags)
    try:
        _wait_ready(port)
        if os.name == "nt": process.send_signal(signal.CTRL_BREAK_EVENT)
        else: process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=8)
    finally:
        if process.poll() is None: process.kill(); process.wait()
    assert process.returncode == 0
    assert "stopped" in stdout.casefold() and "traceback" not in (stdout + stderr).casefold()
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); probe.bind(("127.0.0.1", port))


def test_same_port_can_complete_two_full_cli_start_interrupt_cycles(tmp_path):
    port = _free_port()
    for _ in range(2):
        command = [sys.executable, "-m", "cli.zero_dashboard", "--workspace-root", str(tmp_path), "--port", str(port), "--no-browser", "--read-only"]
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0))
        try:
            _wait_ready(port)
            process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
            stdout, stderr = process.communicate(timeout=8)
        finally:
            if process.poll() is None: process.kill(); process.wait()
        assert process.returncode == 0 and "stopped" in stdout.casefold()
        assert "traceback" not in stderr.casefold()
