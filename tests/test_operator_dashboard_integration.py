from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
import http.cookiejar

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer
from tests.goal_operations_test_support import make_goal


def test_real_http_read_only_post_fails_closed_and_gets_do_not_mutate(tmp_path):
    _, goal, _ = make_goal(tmp_path)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False)).start()
    try:
        url = server.url.rstrip("/")
        request = Request(f"{url}/api/v1/goals/{goal['goal_id']}/pause", data=b"{}", method="POST", headers={"Content-Type": "application/json", "Origin": url})
        try: build_opener().open(request, timeout=5); raise AssertionError("POST must fail")
        except HTTPError as exc: assert exc.code == 403 and json.loads(exc.read())["error_code"] == "dashboard_read_only_mode"
    finally: server.stop()


def test_read_only_mode_rejects_every_write_route_before_routing(tmp_path):
    _, goal, _ = make_goal(tmp_path)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False)).start()
    routes = [f"/api/v1/goals/{goal['goal_id']}/{action}" for action in ("pause", "resume", "stop", "cancel", "replan")]
    routes += ["/api/v1/approvals/pending-approval/approve", "/api/v1/approvals/pending-approval/deny"]
    try:
        base = server.url.rstrip("/")
        for route in routes:
            request = Request(base + route, data=b"{}", method="POST", headers={"Content-Type": "application/json", "Origin": base})
            try: build_opener().open(request, timeout=5); raise AssertionError(f"{route} must fail")
            except HTTPError as exc:
                assert exc.code == 403
                assert json.loads(exc.read())["error_code"] == "dashboard_read_only_mode"
        app_source = (server._assets["app.js"]).read_text(encoding="utf-8")
        assert 'if (!state.status.read_only_mode)' in app_source
    finally: server.stop()


def test_real_http_pause_routes_through_controller(tmp_path):
    controller, goal, operations = make_goal(tmp_path)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0), controller=controller, operations=operations).start()
    jar = http.cookiejar.CookieJar(); opener = build_opener(HTTPCookieProcessor(jar))
    try:
        base = server.url.rstrip("/")
        session = json.loads(opener.open(f"{base}/api/v1/session", timeout=5).read())
        body = json.dumps({"operator_identity": "integration-operator", "confirmation": True, "idempotency_key": "pause-once"}).encode()
        request = Request(f"{base}/api/v1/goals/{goal['goal_id']}/pause", data=body, method="POST", headers={"Content-Type": "application/json", "Origin": base, "X-Zero-Action-Token": session["action_token"]})
        result = json.loads(opener.open(request, timeout=5).read())
        assert result["runtime_result"]["goal_status"] == "paused"
        assert controller.show(goal["goal_id"])["goal_status"] == "paused"
    finally: server.stop()
