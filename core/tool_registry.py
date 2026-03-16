from pathlib import Path

from core.flask_manager import list_flask_routes, restart_flask_internal


BASE_DIR = Path(__file__).resolve().parent.parent


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

    full_path = (BASE_DIR / file_path).resolve()

    try:
        full_path.relative_to(BASE_DIR.resolve())
    except Exception:
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": "file path out of project scope"
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


TOOL_REGISTRY = {
    "list_routes": tool_list_routes,
    "restart_flask": tool_restart_flask,
    "read_file": tool_read_file,
}