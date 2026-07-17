from __future__ import annotations

import pytest

from core.operator.runtime_operator_dashboard_security import ActionTokenManager, DashboardSecurityError
from core.operator.runtime_operator_dashboard import OperatorDashboardTimeProvider
from core.runtime.runtime_mission_execution_approval_flow import execute_approved_mission, review_mission_execution_plan
from core.runtime.runtime_natural_language_mission_bootstrap import run_natural_language_mission


def test_runtime_invariant_action_token_ttl_fails_closed_on_reference_clock():
    clock = [100.0]; tokens = ActionTokenManager(30, clock=lambda: clock[0]); session, token, _ = tokens.issue()
    clock[0] = 129.0; tokens.verify(session, token); clock[0] = 130.0
    with pytest.raises(DashboardSecurityError, match="invalid_action_token"): tokens.verify(session, token)


def test_runtime_invariant_shared_reference_time_is_exact():
    reference = "2026-07-13T08:30:00Z"; provider = OperatorDashboardTimeProvider(reference)
    assert provider.now() == provider.text() == reference
    assert provider.epoch() == 1783931400.0


def test_runtime_invariant_expired_approval_fails_before_mission_mutation(tmp_path):
    created = "2026-07-13T00:00:00Z"; expired = "2026-07-14T00:00:00Z"
    artifact = run_natural_language_mission("create ttl-proof.txt with content safe", workspace_root=tmp_path, now=created)
    approval = review_mission_execution_plan(artifact["artifact_path"], decision="approve", operator_id="release-gate", now=created)
    assert approval["expires_at"]
    with pytest.raises(ValueError, match="approval_expired"): execute_approved_mission(artifact["artifact_path"], operator_id="release-gate", now=expired)
    assert not (tmp_path / "ttl-proof.txt").exists()
