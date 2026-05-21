from __future__ import annotations

from core.runtime.runtime_bypass_audit import audit_runtime_texts
from core.runtime.runtime_freeze_hardening import RuntimeFreezeHardeningController
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


def test_bypass_audit_detects_direct_kernel_authority_bypass() -> None:
    report = audit_runtime_texts(
        {
            "core/runtime/governed_mutation_runtime.py": "\n".join(
                [
                    "def bad(payload):",
                    "    verify_runtime_seal(payload)",
                    "    validate_abi('runtime_replay_artifact', payload)",
                    "    check_runtime_compatibility(payload)",
                    "    self.evidence = {}",
                ]
            )
        }
    )

    payload = report.to_dict()

    assert report.passed is False
    assert payload["error_count"] == 4
    assert {finding["rule_id"] for finding in payload["findings"]} == {
        "direct_seal_verification",
        "direct_abi_validation",
        "direct_compatibility_check",
        "manual_evidence_assignment",
    }


def test_bypass_audit_respects_authority_modules() -> None:
    report = audit_runtime_texts(
        {
            "core/runtime/runtime_artifact_gate.py": "verify_runtime_seal(payload)\nvalidate_abi(name, payload)\ncheck_runtime_compatibility(payload)",
            "core/runtime/runtime_evidence_authority.py": "self.evidence = {}",
        }
    )

    assert report.passed is True
    assert report.to_dict()["error_count"] == 0


def test_freeze_hardening_serialization_manifest_is_deterministic() -> None:
    controller = RuntimeFreezeHardeningController()
    left = controller.build_serialization_manifest(
        {"runtime_probe": {"z": 1, "a": {"b": 2}}}
    )
    right = controller.build_serialization_manifest(
        {"runtime_probe": {"a": {"b": 2}, "z": 1}}
    )

    assert left.deterministic is True
    assert left.to_dict()["fingerprints"] == right.to_dict()["fingerprints"]
    assert left.to_dict()["runtime_version"] == RUNTIME_KERNEL_VERSION
    assert left.to_dict()["abi_version"] == RUNTIME_ABI_VERSION


def test_freeze_hardening_report_passes_clean_authority_routed_texts() -> None:
    controller = RuntimeFreezeHardeningController()
    report = controller.audit_texts(
        {
            "core/runtime/runtime_kernel_subsystems.py": "artifact_gate.inspect(payload, artifact_type='runtime_replay_artifact')\nRuntimeEvidenceAuthority(evidence_id='evidence:1')",
        },
        artifacts={"runtime_replay_artifact": {"replay_id": "r1", "session_snapshot": {}, "journal_records": []}},
    )
    payload = report.to_dict()

    assert report.passed is True
    assert payload["bypass_audit"]["passed"] is True
    assert payload["serialization_manifest"]["deterministic"] is True
    assert all(item["allowed"] is True for item in payload["artifact_gate_reports"])


def test_freeze_hardening_report_blocks_bypass_texts() -> None:
    controller = RuntimeFreezeHardeningController()
    report = controller.audit_texts(
        {
            "core/runtime/governed_mutation_runtime.py": "def drift(payload):\n    check_runtime_compatibility(payload)\n",
        }
    )

    assert report.passed is False
    assert report.to_dict()["bypass_audit"]["findings"][0]["rule_id"] == "direct_compatibility_check"
