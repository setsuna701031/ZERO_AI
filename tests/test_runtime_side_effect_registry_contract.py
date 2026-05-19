from __future__ import annotations

import importlib


def test_runtime_side_effect_registry_records_immutable_effects():
    module = importlib.import_module("core.runtime.runtime_side_effect_registry")
    registry = module.RuntimeSideEffectRegistry()

    record = registry.register(
        effect_type="command_execution",
        source_execution_id="execution-1",
        verified=True,
        rollbackable=False,
        artifact_path=None,
        metadata={"command": "echo ok"},
    )

    assert isinstance(record, module.RuntimeSideEffectRecord)
    assert record.effect_id == "side_effect:execution-1:1"
    assert record.effect_type == "command_execution"
    assert record.source_execution_id == "execution-1"
    assert record.verified is True
    assert record.rollbackable is False
    assert record.metadata == {"command": "echo ok"}
    assert registry.list_records() == (record,)


def test_runtime_side_effect_registry_derives_file_mutation_from_plan_result():
    module = importlib.import_module("core.runtime.runtime_side_effect_registry")
    registry = module.RuntimeSideEffectRegistry()

    records = registry.register_plan_result(
        source_execution_id="execution-1",
        plan_result={
            "final_round_result": {
                "results": [
                    {
                        "action": "write_file",
                        "status": "done",
                        "path": "out.txt",
                        "resolved_path": "/tmp/out.txt",
                    }
                ]
            }
        },
    )

    assert len(records) == 1
    assert records[0].effect_type == "file_mutation"
    assert records[0].verified is True
    assert records[0].rollbackable is True
    assert records[0].artifact_path == "/tmp/out.txt"
