from flask import Flask, jsonify, request

from core.project_agent import ProjectAgent
from core.tool_router import get_available_tools, run_tool

app = Flask(__name__)

agent = ProjectAgent(model="qwen:7b")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "ZERO Flask API is running",
        "status": "ok"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "health": "good"
    })


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "running",
        "available_tools": get_available_tools(),
        "agent_ready": True,
        "agent_model": "qwen:7b"
    })


@app.route("/echo", methods=["POST"])
def echo():
    data = request.get_json(silent=True) or {}
    return jsonify({
        "you_sent": data
    })


@app.route("/tools/run", methods=["POST"])
def tools_run():
    data = request.get_json(silent=True) or {}

    tool_name = str(data.get("tool", "")).strip()
    args = data.get("args", {}) or {}

    if not tool_name:
        return jsonify({
            "tool": "",
            "success": False,
            "data": {
                "message": "tool is required",
                "available_tools": get_available_tools()
            }
        }), 400

    result = run_tool(tool_name, args)
    return jsonify(result)


@app.route("/agent/run", methods=["POST"])
def agent_run():
    data = request.get_json(silent=True) or {}
    user_input = str(data.get("input", "")).strip()

    if not user_input:
        return jsonify({
            "success": False,
            "mode": "agent_loop",
            "input": "",
            "plan": [],
            "results": [],
            "observations": [],
            "final_answer": "input is required"
        }), 400

    result = agent.run(user_input)
    return jsonify(result)


@app.route("/hello", methods=["GET"])
def zero_route_hello():
    return jsonify({
        "route": "hello",
        "message": "ZERO auto route hello is running"
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)