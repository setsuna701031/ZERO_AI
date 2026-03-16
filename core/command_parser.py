from __future__ import annotations


class CommandParser:
    def parse(self, command: str) -> dict:
        raw = command.strip()

        if not raw:
            return {
                "route_type": "empty",
                "action": None,
                "args": {},
                "original_text": raw,
            }

        if raw.startswith("RUN_SHELL "):
            value = raw[len("RUN_SHELL "):].strip()
            return {
                "route_type": "tool",
                "action": "run_shell",
                "args": {"command": value},
                "original_text": raw,
            }

        if raw.startswith("WRITE_FILE "):
            value = raw[len("WRITE_FILE "):].strip()
            if "::" in value:
                path, content = value.split("::", 1)
                return {
                    "route_type": "tool",
                    "action": "write_file",
                    "args": {
                        "path": path.strip(),
                        "content": content.lstrip(),
                    },
                    "original_text": raw,
                }

        if raw.startswith("RUN_PYTHON "):
            value = raw[len("RUN_PYTHON "):].strip()
            return {
                "route_type": "tool",
                "action": "run_python",
                "args": {"path": value},
                "original_text": raw,
            }

        if raw.startswith("DEBUG_PYTHON "):
            value = raw[len("DEBUG_PYTHON "):].strip()
            return {
                "route_type": "debug",
                "action": "debug_python",
                "args": {"path": value},
                "original_text": raw,
            }

        if raw.startswith("DEBUG_PROJECT "):
            value = raw[len("DEBUG_PROJECT "):].strip()
            return {
                "route_type": "agent",
                "action": "debug_project",
                "args": {"path": value},
                "original_text": raw,
            }

        if raw.startswith("READ_FILE "):
            value = raw[len("READ_FILE "):].strip()
            return {
                "route_type": "tool",
                "action": "read_file",
                "args": {"path": value},
                "original_text": raw,
            }

        if raw.startswith("LIST_FILES "):
            value = raw[len("LIST_FILES "):].strip() or "."
            return {
                "route_type": "tool",
                "action": "list_files",
                "args": {"path": value},
                "original_text": raw,
            }

        if raw.startswith("SEARCH_CODE "):
            value = raw[len("SEARCH_CODE "):].strip()
            return {
                "route_type": "tool",
                "action": "search_code",
                "args": {"keyword": value, "path": "."},
                "original_text": raw,
            }

        return {
            "route_type": "chat",
            "action": "respond",
            "args": {},
            "original_text": raw,
        }