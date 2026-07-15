from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import threading
import webbrowser

from core.operator.runtime_operator_dashboard import OperatorDashboardConfig, OperatorDashboardServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m cli.zero_dashboard", description="ZERO Operator Dashboard v1.1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--state-root")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--reference-time", help=argparse.SUPPRESS)
    parser.add_argument("--unsafe-non-loopback", action="store_true", help=argparse.SUPPRESS)
    return parser


def _summary(value: dict[str, object]) -> str:
    if value.get("server_state") == "running":
        return f"ZERO Operator Dashboard\nURL: http://127.0.0.1:{value.get('bound_port')}/\nMode: {'read-only' if value.get('read_only_mode') else 'operator actions enabled'}"
    return (f"ZERO Operator Dashboard status\nHost: {value.get('configured_host')}\nPort: {value.get('configured_port')}\n"
            f"Mode: {'read-only' if value.get('read_only_mode') else 'operator actions enabled'}\n"
            f"Static assets: {'ready' if value.get('static_assets_valid') else 'invalid'}\n"
            f"Operations surface: {'ready' if value.get('operations_surface_available') else 'unavailable'}")


def _interrupt_dashboard(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    values = list(argv) if argv is not None else sys.argv[1:]
    try:
        if threading.current_thread() is threading.main_thread() and hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _interrupt_dashboard)
        args = build_parser().parse_args(values)
        config = OperatorDashboardConfig(workspace_root=str(Path(args.workspace_root)), state_root=args.state_root,
            host=args.host, port=args.port, enable_write_actions=not args.read_only,
            allow_unsafe_host=args.unsafe_non_loopback, reference_time=args.reference_time)
        server = OperatorDashboardServer(config)
        if args.status:
            status = server.status_dict()
            print(json.dumps(status, ensure_ascii=False, sort_keys=True) if args.json_output else _summary(status))
            return 0 if status["static_assets_valid"] and status["operations_surface_available"] else 3
        server.start(); status = server.status_dict()
        print(json.dumps(status, ensure_ascii=False, sort_keys=True) if args.json_output else _summary(status), flush=True)
        if not args.no_browser:
            threading.Thread(target=webbrowser.open, args=(server.url,), name="zero-dashboard-browser", daemon=True).start()
        try:
            server.serve()
        except KeyboardInterrupt:
            server.request_stop()
        finally:
            server.shutdown()
        if not args.json_output:
            print("ZERO Operator Dashboard stopped.", flush=True)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        category = str(exc) if isinstance(exc, ValueError) else "dashboard_start_failure"
        payload = {"contract": "zero.operator.dashboard_cli_error.v1", "error": category}
        print(json.dumps(payload, ensure_ascii=False) if "--json" in values else f"Error: {category}", file=sys.stderr)
        return 2


if __name__ == "__main__": raise SystemExit(main())

__all__ = ["build_parser", "main"]
