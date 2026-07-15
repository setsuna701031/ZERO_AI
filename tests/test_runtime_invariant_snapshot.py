from __future__ import annotations

import json
from urllib.request import urlopen

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer
from tests.goal_operations_test_support import make_goal


def test_runtime_invariant_three_http_snapshots_and_headers_are_identical(tmp_path):
    make_goal(tmp_path); server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False)).start()
    responses = []
    try:
        for _ in range(3):
            with urlopen(server.url + "api/v1/overview", timeout=5) as response: responses.append((dict(response.headers.items()), response.read()))
    finally: server.stop()
    assert responses[0] == responses[1] == responses[2]
    headers, body = responses[0]; projection = json.loads(body)
    assert "Date" not in headers and "Server" not in headers
    assert int(headers["Content-Length"]) == len(body)
    for name in ("Content-Type", "Cache-Control", "Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options"): assert headers[name]
    for name in ("snapshot_identity", "snapshot_fingerprint", "projection_fingerprint"): assert projection[name]
