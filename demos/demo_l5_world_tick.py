# demos/demo_l5_world_tick.py

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

from core.world.world_state import world_state
from core.agent.observe import observe_world


OUTPUT_PATH = "workspace/shared/auto.txt"
OUTPUT_CONTENT = "L5 auto triggered"


def get_task_from_world(world: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = world.get("data")
    if not isinstance(data, dict):
        return None

    trigger = data.get("demo_trigger")

    if isinstance(trigger, dict) and trigger.get("test") is True:
        return {
            "type": "write_file",
            "args": {
                "path": OUTPUT_PATH,
                "content": OUTPUT_CONTENT,
            },
        }

    return None


def write_file_action(path: str, content: str) -> Dict[str, Any]:
    safe_path = str(path or "").strip()

    if not safe_path:
        return {"ok": False, "error": "path is empty"}

    normalized = safe_path.replace("\\", "/")

    if not normalized.startswith("workspace/shared/"):
        return {
            "ok": False,
            "error": f"blocked unsafe path: {safe_path}",
        }

    folder = os.path.dirname(safe_path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    stamped_content = (
        f"{content}\n"
        f"timestamp={datetime.utcnow().isoformat()}\n"
    )

    with open(safe_path, "w", encoding="utf-8") as f:
        f.write(stamped_content)

    return {
        "ok": True,
        "path": safe_path,
        "content": stamped_content,
    }


def clear_demo_trigger() -> None:
    world_state.update("demo_trigger", {"test": False})


def run_l5_tick() -> None:
    print("[L5] starting loop...")
    print("[L5] waiting for demo_trigger test=True")
    print("[L5] press Ctrl+C to stop")

    while True:
        world = observe_world()
        print("[L5] world_state =", world)

        task = get_task_from_world(world)

        if task:
            print("[L5] task detected:", task)

            args = task.get("args")
            if not isinstance(args, dict):
                args = {}

            path = str(args.get("path") or OUTPUT_PATH)
            content = str(args.get("content") or OUTPUT_CONTENT)

            result = write_file_action(path, content)
            print("[L5] action result =", result)

            clear_demo_trigger()
            print("[L5] demo_trigger cleared")

        time.sleep(3)


if __name__ == "__main__":
    run_l5_tick()