from __future__ import annotations

import json
import mimetypes
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = Path(__file__).resolve().parent
ASSET_DIR = REPO_ROOT / "assets" / "persona" / "zero_v1"
HOST = "127.0.0.1"
PORT = 7861

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ui.digital_human_shell import get_digital_human_shell_state, run_digital_human_shell_command


class DigitalHumanHandler(BaseHTTPRequestHandler):
    server_version = "ZERO-DigitalHumanShell/1.0"

    def do_GET(self) -> None:
        try:
            if self.path in {"/", "/digital-human"}:
                self._send_file(UI_DIR / "digital_human.html")
                return

            if self.path == "/api/digital-human/status":
                self._send_json(get_digital_human_shell_state())
                return

            if self.path.startswith("/assets/persona/zero_v1/"):
                filename = self.path.split("/assets/persona/zero_v1/", 1)[1]
                self._send_file((ASSET_DIR / filename).resolve())
                return

            self._send_json({"ok": False, "error": "not found"}, status=404)
        except Exception as exc:
            self._send_error(exc)

    def do_POST(self) -> None:
        try:
            if self.path != "/api/digital-human/command":
                self._send_json({"ok": False, "error": "not found"}, status=404)
                return

            payload = self._read_json()
            command = str(payload.get("command") or "").strip() if isinstance(payload, dict) else ""
            self._send_json(run_digital_human_shell_command(command))
        except Exception as exc:
            self._send_error(exc)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def _send_file(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            self._send_json({"ok": False, "error": "file not found"}, status=404)
            return

        allowed_roots = [UI_DIR.resolve(), ASSET_DIR.resolve()]
        if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
            self._send_json({"ok": False, "error": "file denied"}, status=403)
            return

        data = resolved.read_bytes()
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: Dict[str, Any], *, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, exc: Exception) -> None:
        self._send_json(
            {
                "ok": False,
                "shell": "digital_human_ui_shell",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
            status=500,
        )


def main() -> int:
    print("ZERO Digital Human UI Shell")
    print(f"URL: http://{HOST}:{PORT}/digital-human")
    server = ThreadingHTTPServer((HOST, PORT), DigitalHumanHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
