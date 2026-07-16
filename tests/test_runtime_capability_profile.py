from core.runtime.runtime_capability_profile import RuntimeCapabilityProfile


def _content():
    return {"storage": [{"path": "z"}, {"path": "a"}], "accelerators": [], "available_tools": [{"name": "pytest"}, {"name": "git"}], "installed_models": [], "constraints": [], "diagnostics": []}


def test_identity_ignores_detection_time_and_serialization_is_detached():
    first = RuntimeCapabilityProfile.create(_content(), detected_at="2026-01-01T00:00:00Z")
    second = RuntimeCapabilityProfile.create(_content(), detected_at="2026-01-02T00:00:00Z")
    assert first["profile_id"] == second["profile_id"]
    assert first["fingerprint"] == second["fingerprint"]
    value = first.to_dict(); value["storage"].append({"path": "changed"})
    assert len(first["storage"]) == 2
    assert [entry["path"] for entry in first["storage"]] == ["a", "z"]


def test_non_json_values_are_rejected_at_profile_boundary():
    content = _content(); content["constraints"] = [{"bad": {1, 2}}]
    try: RuntimeCapabilityProfile.create(content)
    except TypeError: pass
    else: raise AssertionError("set must not cross the canonical profile boundary")
