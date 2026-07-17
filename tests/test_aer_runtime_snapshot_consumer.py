import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_snapshot_consumer as consumer_module
from core.runtime.aer_runtime_snapshot import (
    SNAPSHOT_CONTRACT,
    build_snapshot_from_resume_summary,
    validate_snapshot,
)
from core.runtime.aer_runtime_snapshot_consumer import (
    consume_snapshot,
    snapshot_consumer_to_summary,
)


CONSUMER_MODULE = Path("core/runtime/aer_runtime_snapshot_consumer.py")


def _resume_summary(**overrides):
    summary = {
        "contract": "aer.runtime.resume_summary.v1",
        "valid": True,
        "outcome": "continue",
        "status": "valid",
        "reason": None,
    }
    summary.update(overrides)
    return summary


def _snapshot(**overrides):
    snapshot = build_snapshot_from_resume_summary(_resume_summary())
    snapshot.update(overrides)
    return snapshot


def test_runtime_snapshot_consumer_module_exists():
    assert CONSUMER_MODULE.exists()


def test_runtime_snapshot_consumer_public_api_is_minimal():
    assert consumer_module.__all__ == [
        "consume_snapshot",
        "snapshot_consumer_to_summary",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(consumer_module, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_functions == set(consumer_module.__all__)


def test_runtime_snapshot_consumer_has_no_forbidden_imports_or_surface_tokens():
    text = CONSUMER_MODULE.read_text(encoding="utf-8")

    for token in (
        "import os",
        "import random",
        "import time",
        "import uuid",
        "uuid4",
        "scheduler",
        "operator",
        "dispatcher",
        "persistence",
        "persist",
        "audit",
        "journal",
        "recovery",
        "resume_runtime",
        "recover_runtime",
        "execute",
        "replay",
        "build_snapshot",
        "runtime_mainline",
        "task_runner",
        "event_log",
    ):
        assert token not in text


def test_valid_snapshot_is_accepted_descriptively():
    snapshot = _snapshot()

    result = consume_snapshot(snapshot)

    assert result == {
        "contract": "aer.runtime.snapshot.consumer_result.v1",
        "accepted": True,
        "rejected": False,
        "status": "accepted",
        "reason": "accepted",
        "snapshot_contract": SNAPSHOT_CONTRACT,
        "snapshot_id": snapshot["snapshot_id"],
        "lineage": {
            "source_valid": True,
            "source_outcome": "continue",
            "source_status": "valid",
        },
        "validation": validate_snapshot(snapshot),
        "descriptive_only": True,
    }


def test_consumer_orchestrates_snapshot_public_api_without_rewriting_domain_logic():
    text = CONSUMER_MODULE.read_text(encoding="utf-8")

    assert "_validate_snapshot(snapshot)" in text
    for token in (
        "hashlib",
        "json",
        "sha256",
        "snapshot-v1-",
        "VALIDATION_ERROR_CATEGORIES",
        "SNAPSHOT_FIELDS",
        "REQUIRED_RESUME_SUMMARY_FIELDS",
        "_snapshot_id_for_body",
        "_validation_failure_category",
        "_snapshot_field_types_are_valid",
    ):
        assert token not in text


def test_invalid_snapshot_is_rejected_without_repair():
    snapshot = _snapshot()
    snapshot["snapshot_id"] = "tampered"

    result = consume_snapshot(snapshot)

    assert result["accepted"] is False
    assert result["rejected"] is True
    assert result["status"] == "rejected"
    assert result["reason"] == "Identity Error"
    assert result["snapshot_id"] == "tampered"
    assert result["validation"]["valid"] is False
    assert result["validation"]["category"] == "Identity Error"
    assert result["validation"]["auto_repair_allowed"] is False


def test_consumer_accepts_only_snapshot_v1_contract():
    snapshot = _snapshot()
    snapshot["contract"] = "aer.runtime.snapshot.v2"

    result = consume_snapshot(snapshot)

    assert result["accepted"] is False
    assert result["rejected"] is True
    assert result["snapshot_contract"] == "aer.runtime.snapshot.v2"
    assert result["validation"]["category"] in {"Version Error", "Identity Error"}


def test_identity_and_lineage_are_preserved():
    snapshot = build_snapshot_from_resume_summary(
        _resume_summary(valid=False, status="invalid", reason="invalid marker")
    )

    result = consume_snapshot(snapshot)
    summary = snapshot_consumer_to_summary(result)

    assert result["snapshot_id"] == snapshot["snapshot_id"]
    assert result["lineage"] == {
        "source_valid": False,
        "source_outcome": "continue",
        "source_status": "invalid",
    }
    assert summary["snapshot_id"] == snapshot["snapshot_id"]
    assert summary["lineage"] == result["lineage"]


def test_consumer_output_is_deterministic_for_same_input():
    snapshot = _snapshot()

    assert consume_snapshot(snapshot) == consume_snapshot(snapshot)


def test_consumer_does_not_mutate_input():
    snapshot = _snapshot(metadata={"nested": {"value": 1}})
    before = copy.deepcopy(snapshot)

    consume_snapshot(snapshot)

    assert snapshot == before


def test_summary_generation_is_projection_only():
    result = consume_snapshot(_snapshot())

    summary = snapshot_consumer_to_summary(result)

    assert summary == {
        "contract": "aer.runtime.snapshot.consumer_result.v1",
        "accepted": True,
        "rejected": False,
        "status": "accepted",
        "reason": "accepted",
        "snapshot_contract": SNAPSHOT_CONTRACT,
        "snapshot_id": result["snapshot_id"],
        "lineage": result["lineage"],
    }


def test_no_runtime_integration_or_gateway_is_introduced():
    text = CONSUMER_MODULE.read_text(encoding="utf-8")

    forbidden_domain_calls = (
        "run_step",
        "step_executor",
        "schedule",
        "dispatch",
        "decide",
        "save",
        "write",
        "append",
        "open(",
        "Path(",
        "environ",
        "getenv",
    )

    for token in forbidden_domain_calls:
        assert token not in text

    for public_name in consumer_module.__all__:
        source = inspect.getsource(getattr(consumer_module, public_name))
        assert source.count("return ") == 1
        assert "yield" not in source
