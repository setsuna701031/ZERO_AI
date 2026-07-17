from copy import deepcopy

from core.runtime.runtime_capability_activation_authorization_request import create_authorization_review_request
from core.runtime.runtime_capability_activation_authorization_review_decision import build_capability_activation_authorization_review_decision
from tests.test_runtime_capability_activation_authorization_request import allowed_gate

NOW = "2026-07-17T05:00:00Z"

def request():
    gate, metadata = allowed_gate()
    return create_authorization_review_request(gate_decision=gate, authorization_metadata=metadata)

def build(value=None, **changes):
    args = {"authorization_review_request": request() if value is None else value, "decision":"approved", "reviewer_id":" reviewer-1 ", "decision_reason":" approved after review ", "reviewed_at":NOW}
    args.update(changes)
    return build_capability_activation_authorization_review_decision(**args)

def test_approved_is_a_decision_record_not_runtime_authority():
    value = build()
    assert value["approved"] is True
    assert all(value[k] is False for k in ("active_authorization_created","token_issued","runtime_activated","execution_authority_granted"))
    assert value["reviewer_id"] == "reviewer-1" and value["decision_reason"] == "approved after review"

def test_decision_identity_is_stable_and_inputs_are_detached():
    original = request(); copy = deepcopy(original)
    one = build(original); two = build(dict(reversed(list(original.items()))))
    original["policy"]["safe_metadata"]["contract"] = "changed"
    assert one == two and copy != original

def test_each_explicit_decision_has_exactly_one_state_flag():
    for decision in ("approved","denied","blocked","invalid"):
        value = build(decision=decision)
        assert sum(value[name] is True for name in ("approved","denied","blocked","invalid")) == 1
        assert value[decision] is True

def test_malformed_request_and_bad_reviewer_fail_closed():
    invalid = build({}, reviewer_id=[])
    assert invalid["invalid"] and set(invalid["errors"]) >= {"invalid_request","invalid_reviewer"}
