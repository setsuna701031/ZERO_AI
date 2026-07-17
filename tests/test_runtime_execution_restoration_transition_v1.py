from core.runtime.runtime_state_names import (
    SESSION_RESTORED,
    SESSION_RUNNING,
    SESSION_SEALED,
)

from core.runtime.runtime_transition_guard import (
    guard_runtime_transition,
)


def test_runtime_execution_restoration_transition_chain():
    seal_restore = guard_runtime_transition(
        SESSION_SEALED,
        SESSION_RESTORED,
    )

    assert seal_restore["transition_guarded"] is True

    restored_running = guard_runtime_transition(
        SESSION_RESTORED,
        SESSION_RUNNING,
    )

    assert restored_running["transition_guarded"] is True