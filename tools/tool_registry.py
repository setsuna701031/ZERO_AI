from pathlib import Path
import subprocess

from core.flask_manager import list_flask_routes, restart_flask_internal
from core.workspace_manager import safe_path


def tool_list_routes(args: dict | None = None) -> dict:
    result = list_flask_routes()
    return {
        "tool": "list_routes",
        "success": result.get("success", False),
        "data": result
    }


def tool_restart_flask(args: dict | None = None) -> dict:
    result = restart_flask_internal()
    return {
        "tool": "restart_flask",
        "success": result.get("success", False),
        "data": result
    }


def tool_read_file(args: dict | None = None) -> dict:
    args = args or {}
    file_path = str(args.get("file_path", "")).strip()

    if not file_path:
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": "file_path is required"
            }
        }

    try:
        full_path = safe_path(file_path)
    except Exception as exc:
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": str(exc)
            }
        }

    if not full_path.exists():
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": f"file not found: {file_path}"
            }
        }

    if not full_path.is_file():
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": f"not a file: {file_path}"
            }
        }

    try:
        content = full_path.read_text(encoding="utf-8")
        return {
            "tool": "read_file",
            "success": True,
            "data": {
                "file_path": file_path,
                "content": content
            }
        }
    except Exception as exc:
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": f"read file failed: {exc}"
            }
        }


def tool_write_file(args: dict | None = None) -> dict:
    args = args or {}
    path = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))

    if not path:
        return {
            "tool": "write_file",
            "success": False,
            "data": {
                "message": "path is required"
            }
        }

    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return {
            "tool": "write_file",
            "success": True,
            "data": {
                "message": f"file written: {path}",
                "path": path
            }
        }
    except Exception as exc:
        return {
            "tool": "write_file",
            "success": False,
            "data": {
                "message": str(exc)
            }
        }


def tool_run_python(args: dict | None = None) -> dict:
    args = args or {}
    path = str(args.get("path", "")).strip()

    if not path:
        return {
            "tool": "run_python",
            "success": False,
            "data": {
                "message": "path is required"
            }
        }

    try:
        file_path = safe_path(path)

        if not file_path.exists():
            return {
                "tool": "run_python",
                "success": False,
                "data": {
                    "message": f"file not found: {path}"
                }
            }

        if not file_path.is_file():
            return {
                "tool": "run_python",
                "success": False,
                "data": {
                    "message": f"not a file: {path}"
                }
            }

        result = subprocess.run(
            ["python", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        return {
            "tool": "run_python",
            "success": True,
            "data": {
                "path": path,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        }

    except Exception as exc:
        return {
            "tool": "run_python",
            "success": False,
            "data": {
                "message": str(exc)
            }
        }


TOOL_REGISTRY = {
    "list_routes": tool_list_routes,
    "restart_flask": tool_restart_flask,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "run_python": tool_run_python,
}