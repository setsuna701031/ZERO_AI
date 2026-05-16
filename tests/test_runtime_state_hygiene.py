from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from app import print_json
from core.tasks.runtime_audit_artifact import build_runtime_audit_artifact
from core.tasks.runtime_audit_registry import RuntimeAuditRegistry
from core.tasks.runtime_replay_snapshot import build_runtime_replay_snapshot
from core.tasks.runtime_state_hygiene import (
    clone_runtime_export,
    freeze_runtime_export,
    make_json_safe,
    safe_deepcopy,
)


class SampleObject:
    def __init__(self) -> None:
        self.name = "sample"
        self.path = Path("workspace/sample.txt")


class BadDeepcopy:
    def __deepcopy__(self, memo):  # type: ignore[no-untyped-def]
        raise RuntimeError("copy denied")


def test_cli_print_json_preserves_normal_dict_and_list_output():
    payload = {"items": [{"name": "alpha"}, ["beta", 3]], "ok": True}
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        print_json(payload)

    assert json.loads(output.getvalue()) == payload


def test_make_json_safe_handles_core_container_and_scalar_types():
    value = {
        "none": None,
        "scalar": 3,
        "tuple": ("a", Path("workspace/a.txt")),
        "set": {"b", "a"},
        "error": ValueError("bad value"),
    }

    safe = make_json_safe(value)

    assert safe["none"] is None
    assert safe["scalar"] == 3
    assert safe["tuple"] == ["a", "workspace\\a.txt"] or safe["tuple"] == ["a", "workspace/a.txt"]
    assert sorted(safe["set"]) == ["a", "b"]
    assert safe["error"] == {"error_type": "ValueError", "error": "bad value"}
    json.dumps(safe)


def test_make_json_safe_handles_object_dict_and_circular_reference():
    obj = SampleObject()
    circular = {"obj": obj}
    circular["self"] = circular

    safe = make_json_safe(circular)

    assert safe["obj"]["object_type"] == "SampleObject"
    assert safe["obj"]["attributes"]["name"] == "sample"
    assert safe["self"] == "<circular-ref:$>"
    json.dumps(safe)


def test_make_json_safe_nested_circular_reference_includes_path_placeholder():
    root = {"outer": {"items": []}}
    root["outer"]["items"].append({"back": root["outer"]})

    safe = make_json_safe(root)

    assert safe["outer"]["items"][0]["back"] == "<circular-ref:$.outer>"
    json.dumps(safe)


def test_cli_print_json_handles_circular_dict_without_value_error():
    payload = {"result": {"items": []}}
    payload["result"]["items"].append(payload["result"])
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        print_json(payload)

    parsed = json.loads(output.getvalue())
    assert parsed["result"]["items"][0] == "<circular-ref:$.result>"


def test_safe_deepcopy_falls_back_when_deepcopy_fails():
    value = {"bad": BadDeepcopy()}

    copied = safe_deepcopy(value)

    assert copied["bad"]["object_type"] == "BadDeepcopy"
    json.dumps(copied)


def test_freeze_and_clone_runtime_export_isolate_mutation():
    source = {"items": [{"path": Path("workspace/out.txt")}]} 

    frozen = freeze_runtime_export(source)
    clone = clone_runtime_export(frozen)
    source["items"][0]["path"] = Path("mutated.txt")
    clone["items"][0]["path"] = "caller-mutated"

    assert frozen["items"][0]["path"] == "workspace\\out.txt" or frozen["items"][0]["path"] == "workspace/out.txt"
    assert clone["items"][0]["path"] == "caller-mutated"
    assert frozen["items"][0]["path"] != "caller-mutated"


def test_snapshot_uses_hygiene_for_raw_task_isolation_and_json_safety():
    task = {
        "task_id": "task-hygiene",
        "status": "running",
        "goal": "isolate",
        "runtime_trace": [{"event": "runtime_step_started", "path": Path("workspace/run.txt")}],
        "custom": {"path": Path("workspace/raw.txt")},
    }

    snapshot = build_runtime_replay_snapshot(task)
    task["custom"]["path"] = Path("mutated.txt")
    task["runtime_trace"][0]["event"] = "mutated"

    assert snapshot["raw_task"]["custom"]["path"] == "workspace\\raw.txt" or snapshot["raw_task"]["custom"]["path"] == "workspace/raw.txt"
    assert snapshot["normalized_events"][0]["raw"]["event"] == "runtime_step_started"
    json.dumps(snapshot)


def test_artifact_and_registry_use_hygiene_for_mutation_isolation():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-artifact-hygiene",
            "status": "running",
            "goal": "artifact",
            "runtime_trace": [{"event": "runtime_step_started"}],
        }
    )
    artifact = build_runtime_audit_artifact(snapshot)
    snapshot["timeline"].append({"event": "mutated"})
    artifact["timeline"].append({"event": "caller-mutated"})

    registry = RuntimeAuditRegistry()
    registered = registry.register_runtime_audit_artifact(artifact)
    artifact["status"] = "mutated"
    artifact["timeline"].append({"event": "after-register"})

    loaded = registry.get_runtime_audit_artifact(registered["artifact_id"])
    loaded["timeline"].append({"event": "loaded-mutated"})
    loaded_again = registry.get_runtime_audit_artifact(registered["artifact_id"])

    assert registered["status"] == "running"
    assert loaded_again["status"] == "running"
    assert len(loaded_again["timeline"]) == len(registered["timeline"])
    json.dumps(loaded_again)
