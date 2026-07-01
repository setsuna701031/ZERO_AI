from pathlib import Path


def test_zero_work_package_constitution_exists_and_contains_required_sections():
    constitution_path = Path("docs/zero_work_package_constitution.md")

    assert constitution_path.exists()

    constitution = constitution_path.read_text(encoding="utf-8")
    required_terms = [
        "ZERO Work Package Constitution v1",
        "Package Boundary Rules",
        "Architecture Rules",
        "Execution Environment Rule",
        "Validation Rules",
        "Engineering Discipline Rules",
        "Output Rules",
        "Non-mainline Issue Reporting",
        "Do not install Python packages",
        "Long validation must be handed back for local execution",
        "Future Runtime Module Rule",
    ]

    for term in required_terms:
        assert term in constitution
