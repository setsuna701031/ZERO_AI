from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer
from tests.goal_operations_test_support import byte_snapshot, make_goal


def test_real_socket_polling_twenty_rounds_is_deterministic_and_read_only(tmp_path):
    make_goal(tmp_path); before = byte_snapshot(tmp_path)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False)).start()
    try:
        bodies = {path: [] for path in ("overview", "health", "pending-approvals")}
        for _ in range(20):
            for path in bodies:
                with urlopen(f"{server.url}api/v1/{path}", timeout=5) as response:
                    bodies[path].append(response.read())
        assert all(len(set(values)) == 1 for values in bodies.values())
    finally:
        server.stop()
    assert byte_snapshot(tmp_path) == before
    assert not any(Path(tmp_path).rglob("dashboard.*"))


def test_polling_lifecycle_is_single_bounded_abortable_loop():
    source = Path("operator_dashboard/app.js").read_text(encoding="utf-8")
    assert "function startPolling(" in source and "function stopPolling(" in source and "function refreshOnce(" in source
    assert "if (state.refreshPromise)" in source and "state.refreshQueued = true" in source
    assert "new AbortController()" in source and "state.controller.abort()" in source
    assert "Math.min(60000" in source and "Math.min(state.failures, 3)" in source
    assert "setInterval(" not in source and "location.reload(" not in source
    assert source.count("state.timer = setTimeout") == 1
