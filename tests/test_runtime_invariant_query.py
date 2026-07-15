from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlsplit

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer
from core.operator.runtime_operator_dashboard_api import OperatorDashboardReadService
from tests.goal_operations_test_support import byte_snapshot, make_goal


def test_runtime_invariant_query_path_is_deterministic_and_never_calls_controller(tmp_path):
    _, goal, operations = make_goal(tmp_path); reads = OperatorDashboardReadService(operations); before = byte_snapshot(tmp_path)
    first = reads.overview(); second = reads.overview()
    assert first == second
    assert reads.goal(goal["goal_id"])["goal_identity"] == goal["goal_id"]
    assert reads.timeline(goal["goal_id"])["goal_id"] == goal["goal_id"]
    assert byte_snapshot(tmp_path) == before


def test_runtime_invariant_read_only_rejects_every_post_route(tmp_path):
    _, goal, _ = make_goal(tmp_path); server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False)).start()
    routes = [f"api/v1/goals/{goal['goal_id']}/{action}" for action in ("pause", "resume", "stop", "cancel", "replan")]
    routes += ["api/v1/approvals/approval/approve", "api/v1/approvals/approval/deny"]
    try:
        origin = server.url.rstrip("/")
        target = urlsplit(server.url)
        for route in routes:
            connection = HTTPConnection(target.hostname, target.port, timeout=5)
            try:
                connection.request("POST", "/" + route, body=b"{}", headers={"Content-Type": "application/json", "Origin": origin})
                response = connection.getresponse(); body = json.loads(response.read())
                assert response.status == 403 and body["error_code"] == "dashboard_read_only_mode"
            finally: connection.close()
    finally: server.stop()
