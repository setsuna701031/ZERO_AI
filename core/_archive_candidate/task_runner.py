from __future__ import annotations

from core.command_parser import CommandParser


class TaskRunner:
    def __init__(self, executor) -> None:
        self.executor = executor
        self.command_parser = CommandParser()

    def run_steps(self, steps: list[str]) -> str:
        logs: list[str] = []

        for i, step in enumerate(steps, start=1):
            logs.append(f"=== Step {i} ===")
            logs.append(step)

            route = self.command_parser.parse(step)
            result = self.executor.execute(route)

            logs.append(str(result))
            logs.append("")

        return "\n".join(logs)