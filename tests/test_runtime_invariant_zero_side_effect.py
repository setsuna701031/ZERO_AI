from __future__ import annotations

import hashlib
from urllib.request import urlopen

from core.agent.runtime_goal_operations_snapshot import byte_invariance_manifest, load_goal_sources
from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer
from tests.goal_operations_test_support import make_goal


def _manifest(config):
    result = {}
    for logical_root, roots in byte_invariance_manifest(load_goal_sources(config)).items():
        for root in roots:
            paths = sorted(root.rglob("*")) if root.is_dir() else [root]
            for path in paths:
                if path.is_file(): result[f"{logical_root}:{path.resolve()}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_runtime_invariant_dashboard_start_stop_and_get_are_zero_side_effect(tmp_path):
    _, _, operations = make_goal(tmp_path); before = _manifest(operations.config)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False), operations=operations).start()
    try:
        with urlopen(server.url + "api/v1/overview", timeout=5) as response: assert response.status == 200
    finally: server.stop()
    assert _manifest(operations.config) == before
    assert not any(tmp_path.rglob("dashboard.db"))
    assert not any(tmp_path.rglob("dashboard.json"))
    assert not any(tmp_path.rglob("dashboard.cache"))
