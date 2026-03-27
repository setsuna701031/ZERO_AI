from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.system_boot import get_zero_system


def print_json(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> None:
    system = get_zero_system()

    print("ZERO Task System Ready")
    print("Commands:")
    print("/queue <goal>")
    print("/queue-list")
    print("/queue-get <id>")
    print("/queue-pause <id>")
    print("/queue-resume <id>")
    print("/queue-cancel <id>")
    print("/queue-priority <id> <priority>")
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
                goal = cmd[len("/queue ") :].strip()
                result = system.enqueue(goal)
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