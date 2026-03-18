class Router:

    def route(self, text: str):

        text = text.strip()

        # ----------------
        # built-in tools
        # ----------------

        if text.startswith("shell "):

            cmd = text.replace("shell ", "", 1)

            return {
                "type": "tool",
                "tool": "shell",
                "args": {
                    "cmd": cmd
                }
            }

        if text.startswith("pip_install "):

            pkg = text.replace("pip_install ", "", 1)

            return {
                "type": "tool",
                "tool": "pip_install",
                "args": {
                    "package": pkg
                }
            }

        if text == "list files":

            return {
                "type": "tool",
                "tool": "list_files",
                "args": {
                    "path": "."
                }
            }

        if text.startswith("read "):

            path = text.replace("read ", "", 1)

            return {
                "type": "tool",
                "tool": "read_file",
                "args": {
                    "path": path
                }
            }

        if text.startswith("run "):

            path = text.replace("run ", "", 1)

            return {
                "type": "tool",
                "tool": "run_python",
                "args": {
                    "path": path
                }
            }

        # ----------------
        # fallback
        # ----------------

        return {
            "type": "chat",
            "text": text
        }