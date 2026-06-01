from core.tasks.work_package_execution_guard import validate_execute_target


def test_execute_requires_workspace_scope():
    assert validate_execute_target('workspace/test.txt') is True


def test_execute_blocks_core_files():
    assert validate_execute_target('core/agent/agent_loop.py') is False


def test_execute_blocks_tests_files():
    assert validate_execute_target('tests/test_x.py') is False
