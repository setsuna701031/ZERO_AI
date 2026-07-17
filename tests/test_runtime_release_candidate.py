from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from cli.zero_runtime_release_gate import RELEASE_GATE_GROUPS
from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_daemon_state import CONTRACT as DAEMON_CONTRACT
from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService
from core.agent.runtime_goal_operations_snapshot import CONTRACT as OPERATIONS_CONTRACT
from core.agent.runtime_long_horizon_goal import CONTRACT as GOAL_CONTRACT
from core.operator.runtime_operator_dashboard import CONTRACT as DASHBOARD_CONTRACT, VERSION as DASHBOARD_VERSION
from core.runtime.runtime_event_bus import CONTRACT as EVENT_BUS_CONTRACT
from core.runtime.runtime_mission_execution_approval_flow import CONTRACT as APPROVAL_CONTRACT
from core.runtime.runtime_mission_model import CONTRACT as MISSION_CONTRACT
from core.runtime.runtime_release_report import generate_runtime_release_report
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "runtime_rc_v1"
EXPECTED_COMPONENTS = {
    "Runtime Invariants", "Dashboard Tests", "Goal Runtime Tests", "Goal Operations Tests",
    "Daemon Tests", "Approval Tests", "CLI Tests",
}
FREEZE_SCAN_PATTERNS = (
    "core/runtime/runtime_version.py",
    "core/agent/runtime_long_horizon_goal.py",
    "core/agent/runtime_goal_controller.py",
    "core/agent/runtime_goal_daemon*.py",
    "core/agent/runtime_goal_operations*.py",
    "core/operator/runtime_operator_dashboard*.py",
    "core/runtime/runtime_mission_execution_approval_flow.py",
    "core/runtime/runtime_mission_*.py",
    "core/runtime/runtime_activity_memory_query.py",
    "core/runtime/runtime_event_bus.py",
    "core/runtime/runtime_release_report.py",
    "cli/zero_runtime_release_gate.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_runtime_v1_release_candidate_freeze_bundle(tmp_path):
    assert RUNTIME_KERNEL_VERSION == "6.0.0" and RUNTIME_ABI_VERSION == "1.0"
    assert GOAL_CONTRACT == "zero.agent.long_horizon_goal.v1"
    assert callable(RuntimeGoalController)
    assert DAEMON_CONTRACT == "zero.agent.goal_daemon.v1"
    assert OPERATIONS_CONTRACT == "zero.agent.goal_operations.v1"
    assert DASHBOARD_CONTRACT == "zero.operator.dashboard.v1" and DASHBOARD_VERSION == "1.1"
    assert APPROVAL_CONTRACT == "zero.runtime.mission_execution_approval_flow.v1"
    assert MISSION_CONTRACT == "zero.runtime.mission.v1"
    assert EVENT_BUS_CONTRACT == "zero.runtime.event_bus.v1"

    manifest = json.loads((FIXTURE / "fixture-manifest.json").read_text(encoding="utf-8"))
    assert manifest["fixture_version"] == "runtime-rc-v1" and manifest["immutable"] is True
    before = {name: _sha256(FIXTURE / name) for name in manifest["files"]}
    assert before == manifest["files"]
    workspace = tmp_path / "workspace"; workspace.mkdir()
    operations = GoalOperationsService(GoalOperationsConfig(str(workspace), state_root=str(FIXTURE), reference_time="2026-07-13T00:00:00Z"))
    overview = operations.overview().to_dict()
    assert overview["goal_summaries"][0]["goal_id"] == "long-goal-9fef6559a936832b38e4"
    assert {name: _sha256(FIXTURE / name) for name in manifest["files"]} == before

    first = generate_runtime_release_report(ROOT)
    second = generate_runtime_release_report(ROOT)
    assert first.to_json() == second.to_json()
    assert first.runtime_version == "1.0.0-rc.1"
    assert first.manifest_version == "zero.runtime.freeze-manifest.v1"
    assert first.invariant_version == "zero.runtime.invariants.v1"
    assert first.dashboard_version == "1.1" and first.contract_version == "1.0"
    assert first.upgrade_fixture_version == "runtime-rc-v1"
    assert re.fullmatch(r"[0-9a-f]{40}", first.git_commit)

    assert {name for name, _patterns in RELEASE_GATE_GROUPS} == EXPECTED_COMPONENTS
    for _name, patterns in RELEASE_GATE_GROUPS:
        assert any(any(ROOT.glob(pattern)) for pattern in patterns)

    for name in ("ZERO_RUNTIME_V1_RELEASE_CANDIDATE.md", "ZERO_RUNTIME_V1_FREEZE_MANIFEST.md", "ZERO_RUNTIME_V1_BASELINE.md"):
        assert (ROOT / "docs" / name).is_file()

    forbidden = re.compile(r"\b(?:TO" + r"DO|FIX" + r"ME|X" + r"XX)\b|place" + r"holder|mock" + r"-only|Not" + r"Implemented", re.IGNORECASE)
    scanned: set[Path] = set()
    for pattern in FREEZE_SCAN_PATTERNS:
        scanned.update(ROOT.glob(pattern))
    assert scanned
    assert not {str(path.relative_to(ROOT)): forbidden.findall(path.read_text(encoding="utf-8")) for path in scanned if forbidden.search(path.read_text(encoding="utf-8"))}
