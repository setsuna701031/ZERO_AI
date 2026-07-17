from __future__ import annotations
from core.runtime.runtime_capability_bootstrap_admission import admit_capability_bootstrap,create_admission_request,default_policy
from core.runtime.runtime_capability_bootstrap_consumer import ProcessLocalLeaseRegistry,consume_capability_bootstrap,create_consumption_request
from tests.test_runtime_capability_bootstrap_consumer import accepted
def chain():
 i,c=accepted();r=ProcessLocalLeaseRegistry();o=create_consumption_request(integration=i,runtime_context=c,mode="open_readonly_lease");leased=consume_capability_bootstrap(o,integration=i,runtime_context=c,registry=r);q=create_consumption_request(integration=i,runtime_context=c,mode="consume_context",lease_id=leased["lease"]["lease_id"]);consumed=consume_capability_bootstrap(q,integration=i,runtime_context=c,registry=r);return consumed,leased["lease"],i,c
def test_policy_request_decision_and_handoff_deterministic():
 result,lease,i,c=chain();a=create_admission_request(consumption_result=result,lease=lease,integration=i,runtime_context=c,mode="prepare_activation_handoff",requested_at="a");b=create_admission_request(consumption_result=dict(reversed(list(result.items()))),lease=dict(reversed(list(lease.items()))),integration=i,runtime_context=c,mode="prepare_activation_handoff",requested_at="b")
 assert default_policy()==default_policy() and a["request_id"]==b["request_id"]
 x=admit_capability_bootstrap(a,consumption_result=result,lease=lease,integration=i,runtime_context=c,evaluated_at="a");y=admit_capability_bootstrap(b,consumption_result=result,lease=lease,integration=i,runtime_context=c,evaluated_at="b")
 assert x["admitted"] and x["decision_id"]==y["decision_id"] and x["activation_handoff"]["handoff_id"]==y["activation_handoff"]["handoff_id"]
 assert not any((x["runtime_started"],x["authorization_issued"],x["token_issued"])) and set(x["invocation_evidence"].values())=={0}
def test_validate_only_has_no_handoff_and_failures_block():
 result,lease,i,c=chain();q=create_admission_request(consumption_result=result,lease=lease,integration=i,runtime_context=c,mode="validate_only");d=admit_capability_bootstrap(q,consumption_result=result,lease=lease,integration=i,runtime_context=c);assert d["admission_status"]=="validated" and d["activation_handoff"] is None
 revoked=dict(lease);revoked["lease_status"]="revoked";revoked["revocation_status"]="revoked";q=create_admission_request(consumption_result=result,lease=revoked,integration=i,runtime_context=c);assert not admit_capability_bootstrap(q,consumption_result=result,lease=revoked,integration=i,runtime_context=c)["admitted"]
 q=create_admission_request(consumption_result=result,lease=None,integration=i,runtime_context=c);assert "missing_lease" in admit_capability_bootstrap(q,consumption_result=result,lease=None,integration=i,runtime_context=c)["blockers"]
def test_partial_policy_and_safety_requirements():
 result,lease,i,c=chain();warned=dict(result);warned["warnings"]=["partial"]
 from core.runtime.runtime_capability_bootstrap_consumer import _identified as identify_consumption
 warned.pop("consumption_id");warned.pop("fingerprint");warned=identify_consumption(warned,"consumption_id","capability-consumption-",frozenset({"consumed_at"}))
 q=create_admission_request(consumption_result=warned,lease=lease,integration=i,runtime_context=c);assert not admit_capability_bootstrap(q,consumption_result=warned,lease=lease,integration=i,runtime_context=c)["admitted"]
 p=default_policy();p.pop("policy_id");p.pop("fingerprint");p["allow_partial_consumption"]=True
 from core.runtime.runtime_capability_bootstrap_admission import _identified
 p=_identified(p,"policy_id","capability-admission-policy-");q=create_admission_request(consumption_result=warned,lease=lease,integration=i,runtime_context=c,policy=p);d=admit_capability_bootstrap(q,consumption_result=warned,lease=lease,integration=i,runtime_context=c);assert d["admitted"] and d["warnings"]==["partial"]
 bad=dict(c);bad["available_domains"]=[];q=create_admission_request(consumption_result=result,lease=lease,integration=i,runtime_context=bad,policy=p);assert not admit_capability_bootstrap(q,consumption_result=result,lease=lease,integration=i,runtime_context=bad)["admitted"]
