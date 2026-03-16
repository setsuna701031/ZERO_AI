class Router:
    def route(self, text: str) -> dict:
        text = text.strip()

        if not text:
            return {"type": "empty"}

        if text == "help":
            return {"type": "help"}

        if text == "exit":
            return {"type": "exit"}

        if text == "restart flask":
            return {"type": "command", "action": "restart_flask"}

        if text == "stop flask api":
            return {"type": "command", "action": "stop_flask"}

        if text == "build flask api":
            return {"type": "command", "action": "build_flask_api"}

        if text == "list flask routes":
            return {"type": "command", "action": "list_flask_routes"}

        if text.startswith("add flask post route "):
            route_name = text.replace("add flask post route ", "", 1).strip()
            return {
                "type": "command",
                "action": "add_flask_route",
                "route_name": route_name,
                "method": "POST",
            }

        if text.startswith("add flask route "):
            route_name = text.replace("add flask route ", "", 1).strip()
            return {
                "type": "command",
                "action": "add_flask_route",
                "route_name": route_name,
                "method": "GET",
            }

        if text.startswith("remove flask route "):
            route_name = text.replace("remove flask route ", "", 1).strip()
            return {
                "type": "command",
                "action": "remove_flask_route",
                "route_name": route_name,
            }

        return {"type": "unknown", "text": text}