# core/agent/observe.py

from core.world.world_state import world_state


def observe_world():
    """
    目前先做最小版本：
    - 沒有 camera 也沒關係
    - 先回傳 world_state（未來可接 sensor）
    """

    state = world_state.get()

    # TODO: 之後這裡可以接 camera / file watcher / event
    return state