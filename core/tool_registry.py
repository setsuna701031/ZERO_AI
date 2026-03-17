import subprocess

from core.flask_manager import list_flask_routes, restart_flask_internal
from core.llm import LLMClient
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


def tool_list_files(args: dict | None = None) -> dict:
    args = args or {}
    path = str(args.get("path", ".")).strip()

    try:
        target_path = safe_path(path)

        if not target_path.exists():
            return {
                "tool": "list_files",
                "success": False,
                "data": {
                    "message": f"path not found: {path}",
                    "path": path
                }
            }

        if not target_path.is_dir():
            return {
                "tool": "list_files",
                "success": False,
                "data": {
                    "message": f"not a directory: {path}",
                    "path": path
                }
            }

        root_path = safe_path(".")
        items = []

        for item in sorted(target_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                rel_path = str(item.relative_to(root_path)).replace("\\", "/")
            except Exception:
                rel_path = str(item).replace("\\", "/")

            items.append({
                "name": item.name,
                "path": rel_path,
                "type": "dir" if item.is_dir() else "file"
            })

        return {
            "tool": "list_files",
            "success": True,
            "data": {
                "path": path,
                "items": items,
                "count": len(items)
            }
        }

    except Exception as exc:
        return {
            "tool": "list_files",
            "success": False,
            "data": {
                "message": str(exc),
                "path": path
            }
        }


def tool_read_file(args: dict | None = None) -> dict:
    args = args or {}
    path = str(args.get("path", "")).strip()

    if not path:
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": "path is required"
            }
        }

    try:
        file_path = safe_path(path)
    except Exception as exc:
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": str(exc),
                "path": path
            }
        }

    if not file_path.exists():
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": f"file not found: {path}",
                "path": path
            }
        }

    if not file_path.is_file():
        return {
            "tool": "read_file",
            "success": False,
            "data": {
                "message": f"not a file: {path}",
                "path": path
            }
        }

    try:
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
            "data": {
                "message": f"read file failed: {exc}",
                "path": path
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
                "message": str(exc),
                "path": path
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
                    "message": f"file not found: {path}",
                    "path": path
                }
            }

        if not file_path.is_file():
            return {
                "tool": "run_python",
                "success": False,
                "data": {
                    "message": f"not a file: {path}",
                    "path": path
                }
            }

        result = subprocess.run(
            ["python", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        success = result.returncode == 0

        return {
            "tool": "run_python",
            "success": success,
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
                "message": str(exc),
                "path": path
            }
        }


def tool_generate_python(args: dict | None = None) -> dict:
    args = args or {}

    task = str(args.get("task", "")).strip()
    filename = str(args.get("filename", "")).strip()
    model = str(args.get("model", "qwen:7b")).strip() or "qwen:7b"

    if not task:
        return {
            "tool": "generate_python",
            "success": False,
            "data": {
                "message": "task is required"
            }
        }

    llm = LLMClient(model=model)

    prompt = f"""
You are a Python code generator.

Task:
{task}

Target filename:
{filename if filename else "unknown"}

Rules:
1. Return ONLY full Python code.
2. Do not explain anything.
3. Do not use markdown.
4. Do not use code fences.
5. The code must run directly as a complete .py file.
6. Keep the program simple and practical.
7. Prefer only Python standard library unless the task clearly requires something else.
8. If the request is just to print text, return a minimal runnable script.

Example valid output:
print("hello world")

Return Python code only.
""".strip()

    code = llm.generate(prompt).strip()

    if not code:
        return {
            "tool": "generate_python",
            "success": False,
            "data": {
                "message": "LLM returned empty code"
            }
        }

    if code.startswith("LLM_ERROR:"):
        return {
            "tool": "generate_python",
            "success": False,
            "data": {
                "message": code
            }
        }

    if "```" in code:
        code = code.replace("```python", "")
        code = code.replace("```", "").strip()

    if not code.strip():
        return {
            "tool": "generate_python",
            "success": False,
            "data": {
                "message": "generated code became empty after cleanup"
            }
        }

    return {
        "tool": "generate_python",
        "success": True,
        "data": {
            "task": task,
            "filename": filename,
            "code": code,
            "model": model
        }
    }


TOOL_REGISTRY = {
    "list_routes": tool_list_routes,
    "restart_flask": tool_restart_flask,
    "list_files": tool_list_files,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "run_python": tool_run_python,
    "generate_python": tool_generate_python,
}