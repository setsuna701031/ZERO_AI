from pathlib import Path

targets = [
    Path("core/runtime/step_executor.py"),
    Path("core/runtime/task_runner.py"),
    Path("core/tasks/scheduler.py"),
]

for path in targets:
    text = path.read_text(encoding="utf-8")
    print("\n====", path, "====")
    for i, line in enumerate(text.splitlines(), start=1):
        if (
            "def execute_step" in line
            or "execute_step(" in line
            or "return {" in line
            or '"ok": False' in line
            or "'ok': False" in line
            or "blocked_reason" in line
            or '"reason"' in line
            or "'reason'" in line
        ):
            print(f"{i}: {line}")