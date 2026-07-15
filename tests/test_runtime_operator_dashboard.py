from __future__ import annotations

import json
import hashlib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer, OperatorDashboardTimeProvider
from core.agent.runtime_goal_operations_snapshot import byte_invariance_manifest, load_goal_sources
from tests.goal_operations_test_support import byte_snapshot, make_goal


def get(server, path):
    with urlopen(server.url.rstrip("/") + path, timeout=5) as response:
        return response.status, response.headers, response.read()


def test_shared_time_provider_drives_status_and_operations_reference(tmp_path):
    reference = "2026-07-13T08:30:00Z"
    provider = OperatorDashboardTimeProvider(reference)
    assert provider.now() == reference and provider.text() == reference
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, reference_time=reference))
    assert server.time_provider is not None
    assert server.operations.config.reference_time == reference
    server.start()
    try: assert server.status.started_timestamp == reference
    finally: server.stop()


def sha256_persisted_manifest(operations_config):
    result = {}
    for logical_root, paths in byte_invariance_manifest(load_goal_sources(operations_config)).items():
        for root in paths:
            candidates = sorted(root.rglob("*")) if root.is_dir() else [root]
            for path in candidates:
                if path.is_file(): result[f"{logical_root}:{path.resolve()}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_dashboard_start_stop_without_get_leaves_full_persisted_sha256_manifest_equal(tmp_path):
    _, _, operations = make_goal(tmp_path)
    before = sha256_persisted_manifest(operations.config)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0), operations=operations)
    server.start(); server.stop()
    after = sha256_persisted_manifest(operations.config)
    assert after == before


def test_dashboard_start_get_stop_does_not_change_any_persisted_file(tmp_path):
    _, goal, _ = make_goal(tmp_path)
    before = byte_snapshot(tmp_path)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False))
    try:
        server.start()
        for path in ("/", "/styles.css", "/app.js", "/api/v1/overview", f"/api/v1/goals/{goal['goal_id']}", f"/api/v1/goals/{goal['goal_id']}/timeline", "/api/v1/health", "/api/v1/pending-approvals", "/api/v1/dashboard-status"):
            status, headers, body = get(server, path); assert status == 200 and body; assert headers["X-Content-Type-Options"] == "nosniff"
    finally: server.stop()
    assert byte_snapshot(tmp_path) == before
    assert not list(tmp_path.rglob("dashboard.db"))
    assert not list(tmp_path.rglob("dashboard.json"))
    assert not list(tmp_path.rglob("dashboard.cache"))


def test_repeated_overview_is_byte_deterministic(tmp_path):
    make_goal(tmp_path); server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False)).start()
    try:
        responses = [get(server, "/api/v1/overview") for _ in range(3)]
        bodies = [item[2] for item in responses]
        headers = [dict(item[1].items()) for item in responses]
        assert bodies[0] == bodies[1] == bodies[2]
        assert headers[0] == headers[1] == headers[2]
        assert "Date" not in headers[0] and "Server" not in headers[0]
        assert headers[0]["Content-Type"] == "application/json; charset=utf-8"
        assert int(headers[0]["Content-Length"]) == len(bodies[0])
        assert headers[0]["Cache-Control"] == "no-store"
        assert headers[0]["Content-Security-Policy"] == "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        assert headers[0]["Referrer-Policy"] == "no-referrer"
        assert headers[0]["X-Content-Type-Options"] == "nosniff"
        assert headers[0]["X-Frame-Options"] == "DENY"
        projections = [json.loads(body) for body in bodies]
        for key in ("snapshot_identity", "snapshot_fingerprint", "projection_fingerprint"):
            assert projections[0][key] == projections[1][key] == projections[2][key]
    finally: server.stop()


def test_static_traversal_and_missing_goal_are_safe_errors(tmp_path):
    make_goal(tmp_path); server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0)).start()
    try:
        for path in ("/%2e%2e/index.html", "/api/v1/goals/missing"):
            try: get(server, path); raise AssertionError("request should fail")
            except HTTPError as exc:
                body = exc.read().decode(); assert exc.code == 404; assert "Traceback" not in body; assert str(tmp_path) not in body
    finally: server.stop()
