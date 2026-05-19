import sys

from core.runtime.execution_gateway import safe_subprocess_run


def run_python_tool(file_path: str):
    result = safe_subprocess_run(
        [sys.executable, file_path],
        capture_output=True,
        text=True,
    )
    output = result.get("stdout") or ""
    error = result.get("stderr") or ""
    if error:
        return f"ERROR:\n{error}"
    return output if output else "Program executed with no output."
