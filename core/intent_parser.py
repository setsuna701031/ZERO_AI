def parse_intent(question: str) -> dict:
    text = (question or "").strip()
    lower = text.lower()

    if not text:
        return {
            "intent": "empty",
            "tool": None,
            "args": {}
        }

    # list routes
    if "flask" in lower and ("route" in lower or "routes" in lower):
        return {
            "intent": "tool_call",
            "tool": "list_routes",
            "args": {}
        }

    if "list routes" in lower:
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

    # read file
    if "read " in lower:
        file_path = text.split(" ", 1)[1].strip()
        return {
            "intent": "tool_call",
            "tool": "read_file",
            "args": {
                "file_path": file_path
            }
        }

    if "docs/" in lower:
        return {
            "intent": "tool_call",
            "tool": "read_file",
            "args": {
                "file_path": text
            }
        }

    return {
        "intent": "chat",
        "tool": None,
        "args": {}
    }