from flask import Flask, jsonify, request

from agent_loop import AgentLoop

app = Flask(__name__)

agent = AgentLoop()


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "ZERO Flask API is running",
        "status": "ok",
        "service": "ZERO Agent",
        "version": "v1",
        "available_routes": [
            "/",
            "/health",
            "/chat",
            "/route",
            "/tools",
        ]
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "agent": "ZERO",
        "router": "loaded",
        "tool_registry": "loaded",
    })


@app.route("/chat", methods=["POST"])
def chat():
    """
    POST /chat
    body:
    {
        "message": "查一下台北今天天氣"
    }
    """
    data = request.get_json(silent=True) or {}
    user_input = str(data.get("message", "")).strip()

    if not user_input:
        return jsonify({
            "success": False,
            "error": "Missing required field: message"
        }), 400

    result = agent.run(user_input)

    return jsonify({
        "success": result.get("success", False),
        "type": result.get("type"),
        "user_input": result.get("user_input"),
        "final_answer": result.get("final_answer"),
        "route_result": result.get("route_result"),
        "tool_name": result.get("tool_name"),
        "tool_params": result.get("tool_params"),
        "tool_result": result.get("tool_result"),
        "error": result.get("error"),
    })


@app.route("/route", methods=["POST"])
def route_only():
    """
    只看 Router 判斷結果，不執行工具
    POST /route
    body:
    {
        "message": "搜尋 Python requests 教學"
    }
    """
    data = request.get_json(silent=True) or {}
    user_input = str(data.get("message", "")).strip()

    if not user_input:
        return jsonify({
            "success": False,
            "error": "Missing required field: message"
        }), 400

    route_result = agent.router.route(user_input)

    return jsonify({
        "success": True,
        "user_input": user_input,
        "route_result": route_result,
    })


@app.route("/tools", methods=["GET"])
def list_tools():
    return jsonify({
        "success": True,
        "tools": agent.tool_registry.list_tool_names(),
        "tool_definitions": agent.tool_registry.list_tool_definitions(),
    })


@app.route("/tools/<tool_name>", methods=["POST"])
def execute_tool(tool_name):
    """
    直接執行指定工具
    POST /tools/web_search
    body:
    {
        "query": "RTX 3060 VRAM 幾 GB",
        "max_results": 3,
        "category": "general"
    }
    """
    data = request.get_json(silent=True) or {}

    result = agent.tool_registry.execute_tool(tool_name, data)

    status_code = 200 if result.get("success", False) else 400
    return jsonify(result), status_code


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)