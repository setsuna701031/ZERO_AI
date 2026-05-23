from core.runtime.runtime_recovery_governance import (
    evaluate_recovery_governance,
    STATUS_ALLOWED,
    STATUS_BLOCKED,
    STATUS_REVIEW_REQUIRED,
)

def test_low_risk_recovery_allowed():
    result = evaluate_recovery_governance({})
    assert result.status == STATUS_ALLOWED

def test_medium_risk_requires_review():
    result = evaluate_recovery_governance({
        "mutation_scope": "extended"
    })
    assert result.status == STATUS_REVIEW_REQUIRED

def test_high_risk_blocked():
    result = evaluate_recovery_governance({
        "rollback_required": True
    })
    assert result.status == STATUS_BLOCKED
