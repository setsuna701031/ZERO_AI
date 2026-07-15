from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.operator.runtime_operator_dashboard_security import ActionTokenManager, DashboardSecurityError, OperatorDashboardSecurityPolicy


def test_security_policy_rejects_host_origin_and_traversal():
    policy = OperatorDashboardSecurityPolicy(port=8765)
    policy.validate_host("localhost:8765")
    policy.validate_origin("http://127.0.0.1:8765")
    with pytest.raises(DashboardSecurityError, match="invalid_host"): policy.validate_host("evil.example")
    with pytest.raises(DashboardSecurityError, match="invalid_origin"): policy.validate_origin("https://evil.example")
    for path in ("/../index.html", "/%2e%2e/index.html", "/C:/Windows/system.ini", "/nested/app.js"):
        with pytest.raises(DashboardSecurityError): policy.validate_static_target(path, {"index.html": object(), "app.js": object()})


def test_action_token_is_process_local_and_constant_time_validated():
    manager = ActionTokenManager(30)
    session, token, _ = manager.issue()
    manager.verify(session, token)
    with pytest.raises(DashboardSecurityError): manager.verify(session, token + "x")
    with pytest.raises(DashboardSecurityError): ActionTokenManager(30).verify(session, token)


def test_action_token_ttl_uses_injected_clock_and_fails_closed():
    now = [1000.0]; manager = ActionTokenManager(30, clock=lambda: now[0])
    session, token, expires = manager.issue(); assert expires == 1030
    now[0] = 1029.0; manager.verify(session, token)
    now[0] = 1030.0
    with pytest.raises(DashboardSecurityError, match="invalid_action_token"): manager.verify(session, token)


def test_recursive_redaction_hides_sensitive_data_and_paths():
    value = OperatorDashboardSecurityPolicy.redact({"nested": {"access_token": "abc", "message": r"failed at E:\zero_ai\secret.json"}})
    assert value["nested"]["access_token"] == "<redacted>"
    assert "E:\\zero_ai" not in value["nested"]["message"]


def test_frontend_uses_safe_dom_and_no_persisted_browser_state():
    source = (Path(__file__).resolve().parents[1] / "operator_dashboard" / "app.js").read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "localStorage", "sessionStorage", "eval("):
        assert forbidden not in source
