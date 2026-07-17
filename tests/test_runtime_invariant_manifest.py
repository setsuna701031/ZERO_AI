from __future__ import annotations

import hashlib

from core.agent.runtime_goal_operations_snapshot import byte_invariance_manifest, load_goal_sources
from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer
from tests.goal_operations_test_support import make_waiting_goal


def _sha256_map(config):
    result = {}
    for kind, roots in byte_invariance_manifest(load_goal_sources(config)).items():
        for root in roots:
            candidates = sorted(root.rglob("*")) if root.is_dir() else [root]
            for path in candidates:
                if path.is_file(): result[f"{kind}:{path.resolve()}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_runtime_invariant_cross_root_persisted_manifest_is_100_percent_equal(tmp_path):
    _, _, operations = make_waiting_goal(tmp_path); before = _sha256_map(operations.config)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(tmp_path), port=0, enable_write_actions=False), operations=operations).start(); server.stop()
    after = _sha256_map(operations.config)
    assert before
    assert after == before
