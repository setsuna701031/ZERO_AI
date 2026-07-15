from __future__ import annotations

from pathlib import Path


def test_incremental_regions_own_fingerprints_and_fixed_dom_identity():
    source = Path("operator_dashboard/app.js").read_text(encoding="utf-8")
    for field in ("lastOverviewFingerprint", "lastGoalsFingerprint", "lastHealthFingerprint", "lastPendingApprovalsFingerprint", "currentSelectedGoalId", "currentFilter"):
        assert field in source
    assert "if (overviewFingerprint !== state.lastOverviewFingerprint) renderOverview" in source
    assert "if (goalsFingerprint !== state.lastGoalsFingerprint) renderGoals" in source
    assert "if (healthFingerprint !== state.lastHealthFingerprint) renderHealth" in source
    assert "if (approvalsFingerprint !== state.lastPendingApprovalsFingerprint) renderApprovals" in source
    assert 'byId("lastUpdated").textContent' in source
    assert '.innerHTML' not in source
    assert 'byId("main").replaceChildren' not in source
    assert 'byId("metricGrid"); root.replaceChildren' not in source
    assert 'byId("goalList"); root.replaceChildren' not in source


def test_ui_safety_and_motion_contracts():
    html = Path("operator_dashboard/index.html").read_text(encoding="utf-8")
    script = Path("operator_dashboard/app.js").read_text(encoding="utf-8")
    css = Path("operator_dashboard/styles.css").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html
    assert "eval(" not in script
    assert not any(marker in script for marker in ("Bearer ey", "sk-", "actionToken: \""))
    assert "@media(prefers-reduced-motion:reduce)" in css
    for selector in (".topbar", ".brand", "#main", ":root"):
        assert f"{selector}{{animation:" not in css
