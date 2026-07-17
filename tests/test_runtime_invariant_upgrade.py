from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer

GOAL_ID = "long-goal-9fef6559a936832b38e4"


def _sha_map(root: Path):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob("*")) if path.is_file()}


def test_runtime_invariant_frozen_v1_persisted_runtime_is_upgrade_compatible_and_read_only(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "runtime_rc_v1"
    state_root = tmp_path / "runtime-v1"; shutil.copytree(fixture, state_root)
    workspace = tmp_path / "workspace"; workspace.mkdir(); before = _sha_map(state_root)
    server = OperatorDashboardServer(OperatorDashboardConfig(str(workspace), state_root=str(state_root), port=0, enable_write_actions=False, reference_time="2026-07-13T00:00:00Z")).start()
    try:
        values = {}
        for name, path in (("overview", "api/v1/overview"), ("inspection", f"api/v1/goals/{GOAL_ID}"), ("timeline", f"api/v1/goals/{GOAL_ID}/timeline"), ("health", "api/v1/health")):
            with urlopen(server.url + path, timeout=5) as response: values[name] = json.loads(response.read())
        assert values["overview"]["contract"] == "zero.agent.goal_operations.v1"
        assert values["overview"]["goal_summaries"][0]["goal_id"] == GOAL_ID
        assert values["inspection"]["goal_identity"] == GOAL_ID
        assert values["inspection"]["reference_integrity_result"]["integrity"] is True
        assert values["timeline"]["goal_id"] == GOAL_ID
        assert values["health"]["ready"] is True
    finally: server.stop()
    assert _sha_map(state_root) == before
    assert not any(tmp_path.rglob("dashboard.*"))
