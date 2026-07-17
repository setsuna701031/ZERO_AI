from core.runtime.runtime_capability_runtime_activation_admission_handoff import create_capability_runtime_activation_admission_handoff as build
from tests.test_runtime_capability_runtime_activation_admission import admission
def admission_handoff(value=None,at="2099-07-17T06:03:24Z",recipient="runtime-activation-consumer"):return build(admission() if value is None else value,handed_off_at=at,recipient_id=recipient)
def test_handoff_safe():
 x=admission_handoff();assert x["handed_off"] and x["runtime_admission_handed_off"] and not x["handoff_delivered"] and not x["runtime_activated"]
def test_recipient_boundary():assert admission_handoff(recipient=" https://host ")["blocked"] and admission_handoff(at="2099-07-17T06:03:53Z")["expired"]
