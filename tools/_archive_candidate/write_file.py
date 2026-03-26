from core.workspace_manager import safe_path


def run(args):

    path = args.get("path")
    content = args.get("content", "")

    if not path:
        return {
            "success": False,
            "message": "path is required"
        }

    try:
        file_path = safe_path(path)

        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "success": True,
            "message": f"file written: {path}"
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }