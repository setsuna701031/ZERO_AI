from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


IGNORED_TEST_TAXONOMY = {
    "tests/task/test_task_models.py": "legacy",
    "tests/task/test_task_storage.py": "legacy",
    "tests/test_chat.py": "external",
    "tests/test_llm_tool_decision.py": "legacy",
    "tests/test_memory.py": "legacy",
    "tests/test_memory_engine.py": "legacy",
    "tests/test_repo_edit_agent_bridge.py": "integration",
    "tests/test_repo_edit_agent_review_adapter.py": "integration",
    "tests/test_repo_edit_integration.py": "integration",
    "tests/test_repo_edit_review_flow.py": "integration",
    "tests/test_repo_edit_task_intent.py": "integration",
    "tests/test_repo_edit_tool.py": "integration",
    "tests/test_router.py": "legacy",
}


VALID_CATEGORIES = {
    "legacy",
    "external",
    "integration",
}


def test_ignored_tests_have_taxonomy_categories() -> None:
    assert IGNORED_TEST_TAXONOMY

    for path, category in IGNORED_TEST_TAXONOMY.items():
        assert category in VALID_CATEGORIES, path


def test_ignored_tests_still_exist_until_migrated_or_removed() -> None:
    missing = []

    for path in IGNORED_TEST_TAXONOMY:
        if not (REPO_ROOT / path).exists():
            missing.append(path)

    assert missing == []


def test_pytest_ini_tracks_all_ignored_taxonomy_tests() -> None:
    pytest_ini = REPO_ROOT / "pytest.ini"
    content = pytest_ini.read_text(encoding="utf-8")

    missing = []

    for path in IGNORED_TEST_TAXONOMY:
        expected = f"--ignore={path}"
        if expected not in content:
            missing.append(expected)

    assert missing == []