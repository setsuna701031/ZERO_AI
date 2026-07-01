from pathlib import Path


STANDARD = Path("docs/aer_domain_lifecycle_standard.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

FORBIDDEN_IMPLEMENTATION_TOKENS = (
    "execute_resume(",
    "recover(",
    "schedule(",
    "dispatch(",
    "operate(",
    "persist(",
    "audit(",
    "journal(",
    "replay(",
    "subprocess",
    "open(",
    "write(",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_137_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 137")
    end = text.find("## Package 138", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_standard_document_exists():
    assert STANDARD.exists()


def test_all_lifecycle_phases_are_present_in_order():
    text = _text(STANDARD)
    phases = (
        "1. Blueprint",
        "2. Contract",
        "3. Validation",
        "4. Builder / Planning",
        "5. Consumer Boundary",
        "6. Closure Review",
        "7. Integration Blueprint",
        "8. Next Domain",
    )
    positions = [text.index(phase) for phase in phases]
    assert positions == sorted(positions)


def test_lifecycle_matrix_exists_with_required_columns():
    text = _text(STANDARD)
    assert "## Lifecycle Matrix" in text
    assert "| Phase | Owner | Allowed | Forbidden | Exit Gate |" in text
    for phase in (
        "| Blueprint |",
        "| Contract |",
        "| Validation |",
        "| Builder / Planning |",
        "| Consumer Boundary |",
        "| Closure Review |",
        "| Integration Blueprint |",
        "| Next Domain |",
    ):
        assert phase in text


def test_lifecycle_matrix_requires_every_fixed_phase():
    text = _text(STANDARD)
    matrix = text.split("## Lifecycle Matrix", 1)[1].split("## GO Criteria", 1)[0]
    required_rows = (
        "| Blueprint |",
        "| Contract |",
        "| Validation |",
        "| Builder / Planning |",
        "| Consumer Boundary |",
        "| Closure Review |",
        "| Integration Blueprint |",
        "| Next Domain |",
    )
    for row in required_rows:
        assert matrix.count(row) == 1
    assert "the Lifecycle Matrix contains every required phase as a row" in text
    assert "the Lifecycle Matrix is missing no required phase" in text
    assert "the Lifecycle Matrix omits Blueprint, Contract, Validation, Builder / Planning, Consumer Boundary, Closure Review, Integration Blueprint, or Next Domain" in text


def test_consumer_boundary_rules_are_present():
    text = _text(STANDARD)
    assert "## Consumer Boundary Rule" in text
    assert "Consumers may consume only public summaries or explicit public handoffs" in text
    assert "Consumers must not consume Builder internals" in text
    assert "Consumers must not bypass Contract or Validation" in text


def test_closure_review_no_go_handling_is_present():
    text = _text(STANDARD)
    assert "## Closure Review Rule" in text
    assert "Closure Review is the domain seal gate" in text
    assert "Any NO-GO must be resolved by one complete architecture-resolution package, not piecemeal patches" in text


def test_integration_blueprint_rule_is_present():
    text = _text(STANDARD)
    assert "## Integration Blueprint Rule" in text
    assert "Integration Blueprint is the only phase that may describe handoff to the next domain" in text
    assert "It must not implement the next domain" in text


def test_dependency_rule_is_present():
    text = _text(STANDARD)
    assert "## Dependency Rule" in text
    assert "Upstream and downstream dependencies must be explicit" in text
    assert "must not import or call downstream domains unless its own integration contract explicitly allows it" in text


def test_forbidden_drift_rules_are_present():
    text = _text(STANDARD)
    assert "## Forbidden Drift" in text
    assert "No hidden execution is allowed inside contract, validation, builder, consumer, closure, or integration blueprint phases" in text
    assert "No scheduler, recovery, dispatcher, operator, persistence, audit, or journal behavior is allowed unless the current domain explicitly owns it" in text


def test_future_domain_guidance_includes_required_domains():
    text = _text(STANDARD)
    assert "## Future-Domain Guidance" in text
    assert "All future AER v2 domains must follow this Lifecycle Standard" in text
    assert "single lifecycle standard for all AER v2 domains" in text
    assert "not a Runtime Resume-specific standard" in text
    for domain in (
        "Runtime Recovery",
        "Scheduler",
        "Persistence",
        "Audit",
        "Journal",
        "Operator",
        "Dispatcher",
    ):
        assert domain in text


def test_go_decision_and_next_package_are_present():
    text = _text(STANDARD)
    assert "Final decision: GO" in text
    assert "Next package: Package 138: Runtime Recovery Blueprint" in text


def test_package_sequence_contains_package_137_and_package_138_next():
    entry = _package_137_entry()
    assert "## Package 137" in entry
    assert "Package 137: AER Domain Lifecycle Standard" in entry
    assert "documentation and seal only" in entry
    assert "formalizes the AER Domain Lifecycle Standard" in entry
    assert "single Lifecycle Standard for all AER v2 domains" in entry
    assert "must not modify runtime code" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 138: Runtime Recovery Blueprint" in entry


def test_no_runtime_behavior_files_are_referenced_as_modified():
    text = _text(STANDARD)
    entry = _package_137_entry()
    combined = f"{text}\n{entry}"
    assert "core/runtime/" not in combined
    assert "core\\runtime\\" not in combined


def test_forbidden_implementation_tokens_are_absent_from_standard_and_sequence_entry():
    text = _text(STANDARD)
    entry = _package_137_entry()
    combined = f"{text}\n{entry}"
    for token in FORBIDDEN_IMPLEMENTATION_TOKENS:
        assert token not in combined
