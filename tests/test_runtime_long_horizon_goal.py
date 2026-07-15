from copy import deepcopy
import json

import pytest

from core.agent.runtime_long_horizon_goal import create_long_horizon_goal, load_long_horizon_goal, save_long_horizon_goal, validate_long_horizon_goal

NOW = "2026-07-13T00:00:00Z"


def test_goal_identity_utf8_atomic_persistence_and_fingerprint(tmp_path):
    first = create_long_horizon_goal("完成一個可運行的靜態網站", workspace_root=tmp_path, target_root=tmp_path, now=NOW)
    second = create_long_horizon_goal("完成一個可運行的靜態網站", workspace_root=tmp_path, target_root=tmp_path, now=NOW)
    assert first == second and first["goal_id"].startswith("long-goal-")
    path = tmp_path / "state" / "goal.json"; save_long_horizon_goal(first, path)
    assert load_long_horizon_goal(path) == first and "靜態網站" in path.read_text(encoding="utf-8")
    assert not path.with_name(".goal.json.tmp").exists()


def test_invalid_fingerprint_and_outside_target_fail_safely(tmp_path):
    goal = create_long_horizon_goal("建立文件專案", workspace_root=tmp_path, target_root=tmp_path, now=NOW)
    broken = deepcopy(goal); broken["priority"] = "high"
    assert "long_horizon_goal_fingerprint_mismatch" in validate_long_horizon_goal(broken)
    path = tmp_path / "goal.json"; path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"): load_long_horizon_goal(path)
    outside = tmp_path.parent / "outside-goal-target"; outside.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="outside_workspace"): create_long_horizon_goal("建立文件專案", workspace_root=tmp_path, target_root=outside, now=NOW)
