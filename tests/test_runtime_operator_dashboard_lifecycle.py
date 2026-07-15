from __future__ import annotations

import socket
import threading
import time
from urllib.request import urlopen

import pytest

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_lifecycle_transitions_are_bounded_and_idempotent(tmp_path):
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False))
    assert server.status.server_state == "created"
    server.start()
    assert server.status.server_state == "running"
    thread = server._thread
    server.request_stop(); server.shutdown(); server.close()
    assert server.join(timeout=0.1)
    assert server.status.server_state == "stopped"
    assert thread is not None and not thread.is_alive()
    with pytest.raises(ValueError, match="already_started"):
        server.start()


def test_port_is_immediately_reusable_and_bind_failure_fails_closed(tmp_path):
    port = _free_port()
    first = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=port)).start()
    second = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=port))
    with pytest.raises(ValueError, match="bind_failure"):
        second.start()
    assert second.status.server_state == "failed"
    assert second.status.last_error_category == "bind_failure"
    first.stop()
    replacement = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=port)).start()
    replacement.stop()
    assert replacement.status.server_state == "stopped"


def test_shutdown_completes_while_real_request_is_in_flight(tmp_path):
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False))
    original = server.read_service.overview
    entered = threading.Event()
    def slow_overview():
        entered.set(); time.sleep(0.35); return original()
    server.read_service.overview = slow_overview
    server.start()
    request = threading.Thread(target=lambda: urlopen(server.url + "api/v1/overview", timeout=3).read(), daemon=True)
    request.start(); assert entered.wait(2)
    started = time.monotonic(); server.stop(); elapsed = time.monotonic() - started
    request.join(2)
    assert elapsed < 2 and server.status.server_state == "stopped"
    assert not any(item.name == "zero-operator-dashboard" and item.is_alive() for item in threading.enumerate())
