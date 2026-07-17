import inspect
from pathlib import Path

import core.runtime.aer_runtime_snapshot_consumer as consumer_module


REVIEW = Path("docs/aer_runtime_snapshot_consumer_closure_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
CONSUMER_MODULE = Path("core/runtime/aer_runtime_snapshot_consumer.py")


def test_runtime_snapshot_consumer_closure_review_exists_and_has_required_scope():
    assert REVIEW.exists()

    text = REVIEW.read_text(encoding="utf-8")

    for token in (
        "Runtime Snapshot Consumer Closure Review",
        "public API",
        "ownership",
        "read-only",
        "projection-only",
        "no gateway",
        "single source of domain logic",
        "integration readiness",
        "Domain Complete",
        "Integration Ready",
        "Remaining Domains",
        "GO / NO-GO",
        "Final decision:",
        "no piecemeal patches",
        "Package 124 sequence entry",
    ):
        assert token in text


def test_runtime_snapshot_consumer_closure_review_final_decision_is_unambiguous():
    text = REVIEW.read_text(encoding="utf-8")

    assert text.count("Final decision:") == 1
    assert text.rstrip().endswith("Final decision: GO") or text.rstrip().endswith("Final decision: NO-GO")


def test_runtime_snapshot_consumer_closure_review_public_api_and_ownership_are_sealed():
    text = REVIEW.read_text(encoding="utf-8")

    for token in (
        "consume_snapshot",
        "snapshot_consumer_to_summary",
        "No extra public API is approved",
        "snapshot acceptance",
        "validator invocation",
        "snapshot inspection",
        "snapshot projection",
        "consumer summary generation",
        "runtime resume",
        "runtime recovery",
        "scheduler",
        "operator",
        "dispatcher",
        "persistence",
        "audit",
        "journal",
        "snapshot building",
        "runtime execution",
    ):
        assert token in text


def test_runtime_snapshot_consumer_closure_review_single_source_and_readiness_are_sealed():
    text = REVIEW.read_text(encoding="utf-8")

    for token in (
        "consumer may call Snapshot public APIs",
        "must not duplicate Snapshot builder/validator logic",
        "must not invent domain rules",
        "Snapshot remains the owner",
        "Resume Integration may begin next",
        "consumes the Runtime Snapshot Consumer public result",
        "orchestration-only",
        "Domain Complete and Integration Ready are not equivalent",
        "Is the Runtime Snapshot Consumer Domain complete?",
        "Is the Runtime Snapshot Consumer ready to participate in Runtime Integration?",
        "What responsibilities remain outside the Consumer Domain?",
        "GO means only: The Consumer Domain is complete.",
        "does not certify that downstream Runtime domains are complete",
        "not by piecemeal patches",
    ):
        assert token in text


def test_runtime_snapshot_consumer_closure_review_lists_remaining_domains():
    text = REVIEW.read_text(encoding="utf-8")

    for domain in (
        "Runtime Resume",
        "Runtime Recovery",
        "Scheduler Integration",
        "Operator Integration",
        "Dispatcher Integration",
    ):
        assert domain in text


def test_runtime_snapshot_consumer_module_exists_and_public_api_is_closed():
    assert CONSUMER_MODULE.exists()
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


def test_consumer_does_not_introduce_callable_runtime_integration_behavior():
    text = CONSUMER_MODULE.read_text(encoding="utf-8")

    forbidden_callable_tokens = (
        "resume(",
        "resume_runtime(",
        "recover(",
        "recover_runtime(",
        "schedule(",
        "operator(",
        "dispatch(",
        "persist(",
        "audit(",
        "journal(",
        "execute(",
        "run_step(",
        "build_snapshot(",
    )

    for token in forbidden_callable_tokens:
        assert token not in text


def test_package_sequence_contains_package_124_closure_review():
    assert PACKAGE_SEQUENCE.exists()

    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")

    assert "Package 124: Runtime Snapshot Consumer Closure Review" in text
    assert "docs/aer_runtime_snapshot_consumer_closure_review.md" in text
    assert "tests/test_aer_runtime_snapshot_consumer_closure_review.py" in text
    assert "documentation + seal test only" in text
    assert "Resume Integration may begin in the next package" in text
    assert "GO certifies only that the Consumer Domain is complete" in text
    assert "does not certify downstream Runtime domains as complete" in text
    assert "no piecemeal patches" in text
