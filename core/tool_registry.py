import subprocess

from core.flask_manager import list_flask_routes, restart_flask_internal
from core.llm import LLMClient
from core.workspace_manager import safe_path


# -----------------------------
# Flask tools
# -----------------------------

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


# -----------------------------
# Filesystem tools
# -----------------------------

def tool_list_files(args: dict | None = None) -> dict:
    args = args or {}
    path = str(args.get("path", ".")).strip()

    try:
        target_path = safe_path(path)

        if not target_path.exists():
            return {
                "tool": "list_files",
                "success": False,
                "data": {"message": f"path not found: {path}"}
            }

        items = []

        for item in sorted(target_path.iterdir()):
            items.append({
                "name": item.name,
                "path": str(item).replace("\\", "/"),
                "type": "dir" if item.is_dir() else "file"
            })

        return {
            "tool": "list_files",
            "success": True,
            "data": {
                "path": path,
                "items": items
            }
        }

    except Exception as exc:
        return {
            "tool": "list_files",
            "success": False,
            "data": {"message": str(exc)}
        }


def tool_read_file(args: dict | None = None) -> dict:
    args = args or {}
    path = str(args.get("path", "")).strip()

    try:
        file_path = safe_path(path)

        content = file_path.read_text(encoding="utf-8")

        return {
            "tool": "read_file",
            "success": True,
            "data": {
                "path": path,
                "content": content
            }
        }

    except Exception as exc:
        return {
            "tool": "read_file",
            "success": False,
            "data": {"message": str(exc)}
        }


def tool_write_file(args: dict | None = None) -> dict:
    args = args or {}

    path = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))

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
            "data": {"message": str(exc)}
        }


# -----------------------------
# Python execution
# -----------------------------

def tool_run_python(args: dict | None = None) -> dict:
    args = args or {}
    path = str(args.get("path", "")).strip()

    try:
        file_path = safe_path(path)

        result = subprocess.run(
            ["python", str(file_path)],
            capture_output=True,
            text=True
        )

        return {
            "tool": "run_python",
            "success": result.returncode == 0,
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
            "data": {"message": str(exc)}
        }


# -----------------------------
# Code generation
# -----------------------------

def tool_generate_python(args: dict | None = None) -> dict:
    args = args or {}

    task = str(args.get("task", "")).strip()
    filename = str(args.get("filename", "")).strip()

    llm = LLMClient()

    prompt = f"""
Write a complete Python script.

Task:
{task}

Rules:
- Return ONLY Python code
- No explanations
- No markdown
- Must run directly

Example:
print("hello world")
"""

    raw = llm.generate(prompt)

    code = llm.extract_python_code(raw)

    return {
        "tool": "generate_python",
        "success": True,
        "data": {
            "filename": filename,
            "code": code,
            "raw": raw
        }
    }


# -----------------------------
# NEW: shell tool
# -----------------------------

def tool_shell(args: dict | None = None) -> dict:
    args = args or {}

    cmd = str(args.get("cmd", "")).strip()

    if not cmd:
        return {
            "tool": "shell",
            "success": False,
            "data": {"message": "cmd required"}
        }

    try:

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )

        return {
            "tool": "shell",
            "success": result.returncode == 0,
            "data": {
                "cmd": cmd,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        }

    except Exception as exc:

        return {
            "tool": "shell",
            "success": False,
            "data": {"message": str(exc)}
        }


# -----------------------------
# NEW: pip install tool
# -----------------------------

def tool_pip_install(args: dict | None = None) -> dict:
    args = args or {}

    package = str(args.get("package", "")).strip()

    if not package:
        return {
            "tool": "pip_install",
            "success": False,
            "data": {"message": "package required"}
        }

    try:

        result = subprocess.run(
            ["pip", "install", package],
            capture_output=True,
            text=True
        )

        return {
            "tool": "pip_install",
            "success": result.returncode == 0,
            "data": {
                "package": package,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        }

    except Exception as exc:

        return {
            "tool": "pip_install",
            "success": False,
            "data": {"message": str(exc)}
        }


# -----------------------------
# Tool registry
# -----------------------------

TOOL_REGISTRY = {

    "list_routes": tool_list_routes,
    "restart_flask": tool_restart_flask,

    "list_files": tool_list_files,
    "read_file": tool_read_file,
    "write_file": tool_write_file,

    "run_python": tool_run_python,
    "generate_python": tool_generate_python,

    "shell": tool_shell,
    "pip_install": tool_pip_install,
}