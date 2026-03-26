def parse_intent(question: str) -> dict:
    text = (question or "").strip()
    lower = text.lower()

    if not text:
        return {
            "intent": "empty",
            "tool": None,
            "args": {}
        }

    # list flask routes
    if "list flask routes" in lower:
        return {
            "intent": "tool_call",
            "tool": "list_routes",
            "args": {}
        }

    if "flask" in lower and ("route" in lower or "routes" in lower):
        return {
            "intent": "tool_call",
            "tool": "list_routes",
            "args": {}
        }

    # restart flask
    if "restart flask" in lower:
        return {
            "intent": "tool_call",
            "tool": "restart_flask",
            "args": {}
        }

    if "restart" in lower and "flask" in lower:
        return {
            "intent": "tool_call",
            "tool": "restart_flask",
            "args": {}
        }

    # read_file：只接受明確的檔案讀取指令
    if text.startswith("讀取 "):
        file_path = text.replace("讀取 ", "", 1).strip()
        return {
            "intent": "tool_call",
            "tool": "read_file",
            "args": {
                "file_path": file_path
            }
        }

    if text.startswith("讀檔 "):
        file_path = text.replace("讀檔 ", "", 1).strip()
        return {
            "intent": "tool_call",
            "tool": "read_file",
            "args": {
                "file_path": file_path
            }
        }

    if lower.startswith("read file "):
        file_path = text[len("read file "):].strip()
        return {
            "intent": "tool_call",
            "tool": "read_file",
            "args": {
                "file_path": file_path
            }
        }

    if lower.startswith("read docs/"):
        file_path = text[len("read "):].strip()
        return {
            "intent": "tool_call",
            "tool": "read_file",
            "args": {
                "file_path": file_path
            }
        }

    if lower.startswith("read core/"):
        file_path = text[len("read "):].strip()
        return {
            "intent": "tool_call",
            "tool": "read_file",
            "args": {
                "file_path": file_path
            }
        }

    if lower.startswith("read app.py"):
        file_path = text[len("read "):].strip()
        return {
            "intent": "tool_call",
            "tool": "read_file",
            "args": {
                "file_path": file_path
            }
        }

    return {
        "intent": "chat",
        "tool": None,
        "args": {}
    }