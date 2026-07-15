from __future__ import annotations

import json
from urllib.request import urlopen

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer
from tests.goal_operations_test_support import make_goal


def test_runtime_invariant_all_projection_endpoints_are_deterministic_over_ten_queries(tmp_path):
    _, goal, _ = make_goal(tmp_path)
    paths = ("api/v1/overview", f"api/v1/goals/{goal['goal_id']}", f"api/v1/goals/{goal['goal_id']}/timeline", "api/v1/health", "api/v1/pending-approvals")
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False)).start()
    try:
        for path in paths:
            responses = []
            for _ in range(10):
                with urlopen(server.url + path, timeout=5) as response: responses.append((dict(response.headers.items()), response.read()))
            assert all(item == responses[0] for item in responses)
            headers, body = responses[0]; projection = json.loads(body)
            assert int(headers["Content-Length"]) == len(body)
            for name in ("Content-Type", "Cache-Control", "Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options"): assert headers[name]
            for name in ("snapshot_identity", "snapshot_fingerprint", "projection_fingerprint"): assert projection[name]
    finally: server.stop()
