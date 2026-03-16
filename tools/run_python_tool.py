import subprocess
import sys


def run_python_tool(file_path: str):
    """
    執行指定的 Python 檔案
    """

    try:

        result = subprocess.run(
            [sys.executable, file_path],
            capture_output=True,
            text=True
        )

        output = result.stdout
        error = result.stderr

        if error:
            return f"ERROR:\n{error}"

        return output if output else "Program executed with no output."

    except Exception as e:
        return f"Execution failed: {str(e)}"