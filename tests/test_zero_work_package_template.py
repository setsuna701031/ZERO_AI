from pathlib import Path


def test_zero_work_package_template_exists_and_contains_required_sections():
    template_path = Path("docs/zero_work_package_template.md")

    assert template_path.exists()

    template = template_path.read_text(encoding="utf-8")
    required_terms = [
        "ZERO Work Package Template v1",
        "ZERO Work Package Constitution v1",
        "Package Title",
        "Objective",
        "Scope",
        "Files",
        "Tasks",
        "Validation",
        "Required short validation",
        "Local-only long validation",
        "Package-Specific Rules",
        "Non-mainline Issue Reporting",
        "Completion Report Format",
        "Do not modify the execution environment",
    ]

    for term in required_terms:
        assert term in template
