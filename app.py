from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.system_boot import get_zero_system


def print_json(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def parse_queue_body(body: str) -> Tuple[str, List[str], int, int]:
    """
    支援格式：
    /queue 任務A
    /queue 任務B depends task_0001
    /queue 任務C depends task_0001 task_0002 retry 2
    /queue 任務D retry 3 delay 2
    /queue 任務E depends task_0001 retry 2 delay 1

    規則：
    - depends 後面直到 retry/delay 結束前，都是 dependency ids
    - retry <n>
    - delay <n> 代表 retry_delay_ticks
    """
    text = str(body or "").strip()
    if not text:
        return "", [], 0, 0

    tokens = text.split()
    goal_tokens: List[str] = []
    dependencies: List[str] = []
    max_retries = 0
    retry_delay_ticks = 0

    mode = "goal"
    i = 0

    while i < len(tokens):
        token = tokens[i]
        lower = token.lower()

        if lower == "depends":
            mode = "depends"
            i += 1
            continue

        if lower == "retry":
            mode = "goal"
            if i + 1 < len(tokens):
                try:
                    max_retries = int(tokens[i + 1])
                except Exception:
                    max_retries = 0
                i += 2
                continue
            break

        if lower == "delay":
            mode = "goal"
            if i + 1 < len(tokens):
                try:
                    retry_delay_ticks = int(tokens[i + 1])
                except Exception:
                    retry_delay_ticks = 0
                i += 2
                continue
            break

        if mode == "depends":
            dependencies.append(token)
        else:
            goal_tokens.append(token)

        i += 1

    goal = " ".join(goal_tokens).strip()
    return goal, dependencies, max_retries, retry_delay_ticks


def main() -> None:
    system = get_zero_system()

    print("ZERO Task System Ready")
    print("Commands:")
    print("/queue <goal>")
    print("/queue <goal> depends <task_id...>")
    print("/queue <goal> retry <n> delay <ticks>")
    print("/queue <goal> depends <task_id...> retry <n> delay <ticks>")
    print("/queue-list")
    print("/queue-get <id>")
    print("/queue-pause <id>")
    print("/queue-resume <id>")
    print("/queue-cancel <id>")
    print("/queue-priority <id> <priority>")
    print("/tick")
    print("/tick <count>")
    print("/run <count>")
    print("/health")
    print("/exit")

    try:
        while True:
            cmd = input("ZERO> ").strip()

            if not cmd:
                continue

            if cmd == "/exit":
                break

            if cmd.startswith("/queue "):
                body = cmd[len("/queue ") :].strip()
                goal, dependencies, max_retries, retry_delay_ticks = parse_queue_body(body)

                if not goal:
                    print("Usage: /queue <goal> [depends <task_id...>] [retry <n>] [delay <ticks>]")
                    continue

                result = system.enqueue(
                    goal,
                    dependencies=dependencies,
                    max_retries=max_retries,
                    retry_delay_ticks=retry_delay_ticks,
                )
                print_json(result)
                continue

            if cmd == "/queue-list":
                result = system.queue_list()
                print_json(result)
                continue

            if cmd.startswith("/queue-get "):
                qid = cmd[len("/queue-get ") :].strip()
                result = system.queue_get(qid)
                print_json(result)
                continue

            if cmd.startswith("/queue-pause "):
                qid = cmd[len("/queue-pause ") :].strip()
                result = system.queue_pause(qid)
                print_json(result)
                continue

            if cmd.startswith("/queue-resume "):
                qid = cmd[len("/queue-resume ") :].strip()
                result = system.queue_resume(qid)
                print_json(result)
                continue

            if cmd.startswith("/queue-cancel "):
                qid = cmd[len("/queue-cancel ") :].strip()
                result = system.queue_cancel(qid)
                print_json(result)
                continue

            if cmd.startswith("/queue-priority "):
                body = cmd[len("/queue-priority ") :].strip()
                parts = body.split()

                if len(parts) != 2:
                    print("Usage: /queue-priority <id> <priority>")
                    continue

                qid = parts[0].strip()

                try:
                    priority = int(parts[1].strip())
                except ValueError:
                    print("priority must be an integer")
                    continue

                result = system.queue_reprioritize(qid, priority)
                print_json(result)
                continue

            if cmd == "/tick":
                result = system.scheduler.run_once()
                print_json(result)
                continue

            if cmd.startswith("/tick "):
                raw = cmd[len("/tick ") :].strip()

                try:
                    count = int(raw)
                except ValueError:
                    print("Usage: /tick <count>")
                    continue

                if count <= 0:
                    print("count must be > 0")
                    continue

                last_result = None
                for i in range(count):
                    last_result = system.scheduler.run_once()
                    print(f"--- tick {i + 1} ---")
                    print_json(last_result)

                if last_result is None:
                    print("No tick executed.")
                continue

            if cmd.startswith("/run "):
                raw = cmd[len("/run ") :].strip()

                try:
                    count = int(raw)
                except ValueError:
                    print("Usage: /run <count>")
                    continue

                if count <= 0:
                    print("count must be > 0")
                    continue

                last_result = None
                for i in range(count):
                    last_result = system.scheduler.run_once()
                    status = str(last_result.get("status", "")).strip().lower()

                    print(f"--- tick {i + 1} ---")
                    print_json(last_result)

                    if status == "idle":
                        break

                if last_result is None:
                    print("No run executed.")
                continue

            if cmd == "/health":
                result = system.health()
                print_json(result)
                continue

            print("Unknown command")

    except KeyboardInterrupt:
        print()
    except Exception as e:
        print("Error:", e)
    finally:
        try:
            system.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()