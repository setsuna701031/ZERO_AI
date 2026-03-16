from flask import Flask, jsonify, request
from core.ai_handler import handle_ai_ask
from core.tool_router import get_available_tools
from core.llm_client import OLLAMA_BASE_URL, OLLAMA_MODEL

app = Flask(__name__)


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
        "zero_core": "running",
        "flask": "ok",
        "version": "v0.1.0",
        "tools": get_available_tools(),
        "llm_backend": "ollama",
        "llm_base_url": OLLAMA_BASE_URL,
        "llm_model": OLLAMA_MODEL,
    })


@app.route("/echo", methods=["POST"])
def echo():
    data = request.get_json(silent=True) or {}
    return jsonify({
        "you_sent": data
    })


@app.route("/ai/ask", methods=["POST"])
def ai_ask():
    data = request.get_json(silent=True) or {}
    result = handle_ai_ask(data)
    return jsonify(result)


# ZERO_AUTO_ROUTES_START


@app.route("/hello", methods=["GET"])
def zero_route_hello():
    return jsonify({
        "route": "hello",
        "message": "ZERO auto route hello is running"
    })


@app.route("/test_verify", methods=["GET"])
def zero_route_test_verify():
    return jsonify({
        "route": "test_verify",
        "message": "ZERO 自動路由 test_verify 正在執行"
    })


@app.route("/echo_data", methods=["POST"])
def zero_post_route_echo_data():
    data = request.get_json(silent=True) or {}
    return jsonify({
        "route": "echo_data",
        "received": data
    })


# ZERO_AUTO_ROUTES_END


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)