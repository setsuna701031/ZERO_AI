from __future__ import annotations

from copy import deepcopy

from core.agent.runtime_goal_operations_snapshot import CONTRACT, validate_projection
from tests.goal_operations_test_support import make_goal


def test_runtime_invariant_same_persisted_state_has_stable_and_valid_fingerprints(tmp_path):
    _, _, operations = make_goal(tmp_path); values = [operations.overview().to_dict() for _ in range(3)]
    for field in ("snapshot_identity", "snapshot_fingerprint", "projection_fingerprint"): assert len({value[field] for value in values}) == 1
    assert validate_projection(values[0], CONTRACT) == []
    tampered = deepcopy(values[0]); tampered["total_goal_count"] += 1
    assert "operations_projection_fingerprint_mismatch" in validate_projection(tampered, CONTRACT)
