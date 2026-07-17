from __future__ import annotations

import json

from core.runtime.runtime_capability_bootstrap_plan import default_policy, normalize_policy, plan_capability_bootstrap
from core.runtime.runtime_capability_detection import CapabilityDetectionOrchestrator, DetectionContext, compute_detection_fingerprint
from core.runtime.runtime_capability_detector import RuntimeCapabilityDetector
from core.runtime.runtime_capability_provider_discovery import discover_providers
from core.runtime.runtime_capability_strategy_selector import select_capability_strategy


class FakeCpu:
    detector_id = "cpu_plan"; domain = "cpu"; priority = 100; supported_platforms = ("any",)
    def __init__(self, calls): self.calls = calls
    def detect(self, context: DetectionContext):
        self.calls.append("detect")
        return {"detector_id": self.detector_id, "domain": "cpu", "status": "available", "evidence": {"logical_cores": 4}, "error_code": None, "provider": {"schema": "zero.runtime.capability_detector_provider.v1", "provider_version": 1, "detector_id": self.detector_id, "domain": "cpu", "priority": 100, "supported_platforms": ["any"]}}


def artifact_chain(*, bound=True, include_optional=False, mode=None):
    calls = []; descriptor = {"provider_id": "vendor.cpu", "detector_id": "cpu_plan", "domain": "cpu", "provider_version": "1", "priority": 100, "implementation_kind": "process_local", "source_kind": "explicit"}
    discovery = discover_providers([descriptor], domains=["cpu"])
    discovery["selected_providers"][0]["binding_status"] = "bound" if bound else "unbound"
    detection = CapabilityDetectionOrchestrator([FakeCpu(calls)]).detect(["cpu"], observed_at="fixed")
    detection["source"] = {"kind": "explicit_discovery_detection", "discovery_id": discovery["discovery_id"], "discovery_fingerprint": discovery["fingerprint"]}
    detection["fingerprint"] = compute_detection_fingerprint(detection); detection["detection_id"] = "capability-detection-" + detection["fingerprint"][:24]
    profile = RuntimeCapabilityDetector([]).detect(detected_at="fixed").to_dict()
    strategy = select_capability_strategy(profile).to_dict()
    if mode is not None:
        from core.runtime.runtime_capability_strategy import normalize_strategy
        strategy = normalize_strategy({**strategy, "recommended_mode": mode})
    provenance = {"profile_detection_id": detection["detection_id"], "profile_detection_fingerprint": detection["fingerprint"]}
    policy = default_policy()
    if not include_optional:
        policy = normalize_policy({**{k: v for k, v in policy.items() if k not in {"schema", "fingerprint"}}, "optional_domains": []})
    return discovery, detection, profile, strategy, provenance, policy, calls


def make_plan(**changes):
    d, det, p, s, provenance, policy, calls = artifact_chain(**changes)
    return plan_capability_bootstrap(discovery=d, detection=det, profile=p, strategy=s, provenance=provenance, policy=policy), (d, det, p, s, provenance, policy, calls)


def test_valid_chain_is_ready_deterministic_and_time_is_not_identity():
    plan, artifacts = make_plan()
    d, det, p, s, provenance, policy, calls = artifacts
    second = plan_capability_bootstrap(discovery=dict(reversed(list(d.items()))), detection=det, profile=p, strategy=s, provenance=provenance, policy=policy, planned_at="later")
    assert plan["readiness"] == "ready" and plan["fingerprint"] == second["fingerprint"] and plan["plan_id"] == second["plan_id"]
    assert [x["order"] for x in plan["ordered_steps"]] == list(range(len(plan["ordered_steps"])))
    assert len({x["step_id"] for x in plan["ordered_steps"]}) == len(plan["ordered_steps"])
    assert calls == ["detect"]  # artifact construction only; planning added no invocation


def test_optional_unavailable_or_unbound_is_partial_and_required_is_blocked():
    partial, _ = make_plan(include_optional=True)
    assert partial["readiness"] == "partial"
    blocked, artifacts = make_plan(bound=False)
    assert blocked["readiness"] == "blocked" and any(x["code"] == "required_provider_unbound" for x in blocked["blocked_reasons"])
    d, det, p, s, provenance, policy, _ = artifacts
    det["results"][0]["status"] = "unavailable"; det["fingerprint"] = compute_detection_fingerprint(det); det["detection_id"] = "capability-detection-" + det["fingerprint"][:24]
    provenance = {"profile_detection_id": det["detection_id"], "profile_detection_fingerprint": det["fingerprint"]}
    unavailable = plan_capability_bootstrap(discovery=d, detection=det, profile=p, strategy=s, provenance=provenance, policy=policy)
    assert unavailable["readiness"] in {"blocked", "invalid"}


def test_optional_unbound_provider_is_partial():
    _, artifacts = make_plan(); d, det, p, s, provenance, policy, _ = artifacts
    optional_descriptor = {"provider_id": "vendor.accelerator", "detector_id": "accelerator_plan", "domain": "accelerator", "provider_version": "1", "priority": 100, "implementation_kind": "process_local", "source_kind": "explicit"}
    cpu_descriptor = {"provider_id": "vendor.cpu", "detector_id": "cpu_plan", "domain": "cpu", "provider_version": "1", "priority": 100, "implementation_kind": "process_local", "source_kind": "explicit"}
    d = discover_providers([cpu_descriptor, optional_descriptor], domains=["cpu", "accelerator"])
    for selected in d["selected_providers"]: selected["binding_status"] = "bound" if selected["domain"] == "cpu" else "unbound"
    det["source"] = {"kind": "explicit_discovery_detection", "discovery_id": d["discovery_id"], "discovery_fingerprint": d["fingerprint"]}
    det["fingerprint"] = compute_detection_fingerprint(det); det["detection_id"] = "capability-detection-" + det["fingerprint"][:24]
    provenance = {"profile_detection_id": det["detection_id"], "profile_detection_fingerprint": det["fingerprint"]}
    policy = normalize_policy({**{k: v for k, v in policy.items() if k not in {"schema", "fingerprint"}}, "optional_domains": ["accelerator"]})
    plan = plan_capability_bootstrap(discovery=d, detection=det, profile=p, strategy=s, provenance=provenance, policy=policy)
    assert plan["readiness"] == "partial" and any(x["code"] == "optional_provider_unbound" for x in plan["warnings"])


def test_linkage_and_fingerprint_mismatch_fail_closed():
    plan, artifacts = make_plan(); d, det, p, s, provenance, policy, _ = artifacts
    bad = dict(det); bad["fingerprint"] = "0" * 64
    assert plan_capability_bootstrap(discovery=d, detection=bad, profile=p, strategy=s, provenance=provenance, policy=policy)["readiness"] == "invalid"
    for broken_provenance in ({**provenance, "profile_detection_id": "other"}, provenance):
        broken_d = dict(d)
        if broken_provenance is provenance: broken_d["discovery_id"] = "other"
        assert plan_capability_bootstrap(discovery=broken_d, detection=det, profile=p, strategy=s, provenance=broken_provenance, policy=policy)["readiness"] in {"blocked", "invalid"}
    bad_strategy = dict(s); bad_strategy["profile_id"] = "other"
    assert plan_capability_bootstrap(discovery=d, detection=det, profile=p, strategy=bad_strategy, provenance=provenance, policy=policy)["readiness"] == "invalid"


def test_strategy_and_offline_constraints_are_symbolic_only():
    plan, _ = make_plan(mode="cpu_only")
    assert "accelerator" not in json.dumps(plan["ordered_steps"]) and "network" not in json.dumps(plan["ordered_steps"])
    accelerator, _ = make_plan(mode="accelerator_available")
    assert accelerator["readiness"] in {"blocked", "invalid"}


def test_policy_identity_and_unsafe_values():
    first = default_policy(); second = normalize_policy(dict(reversed(list({k: v for k, v in first.items() if k not in {"schema", "fingerprint"}}.items()))))
    assert first["fingerprint"] == second["fingerprint"]
    try: normalize_policy({**first, "callback": lambda: None})
    except ValueError: pass
    else: raise AssertionError("callable policy must fail")


def test_planner_never_invokes_provider_or_executes_steps():
    _, artifacts = make_plan(); calls = artifacts[-1]; before = list(calls)
    d, det, p, s, provenance, policy, _ = artifacts
    plan = plan_capability_bootstrap(discovery=d, detection=det, profile=p, strategy=s, provenance=provenance, policy=policy)
    assert calls == before and all(x["status"] in {"planned", "blocked"} for x in plan["ordered_steps"])
    assert "object at 0x" not in json.dumps(plan)
