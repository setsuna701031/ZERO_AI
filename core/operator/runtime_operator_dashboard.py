from __future__ import annotations

from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

from core.agent.runtime_goal_controller import RuntimeGoalController
from core.agent.runtime_goal_operations import GoalOperationsConfig, GoalOperationsService
from core.operator.runtime_operator_dashboard_actions import OperatorDashboardActionService
from core.operator.runtime_operator_dashboard_api import OperatorDashboardReadService
from core.operator.runtime_operator_dashboard_security import (
    ActionTokenManager, DashboardSecurityError, OperatorDashboardSecurityPolicy, SECURITY_HEADERS,
)
from core.runtime.runtime_operator_session import fingerprint, parse_time, time_text

CONTRACT = "zero.operator.dashboard.v1"
VERSION = "1.1"
STATIC_ASSETS = {"index.html": "text/html; charset=utf-8", "styles.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}
GOAL_ROUTE = re.compile(r"^/api/v1/goals/([A-Za-z0-9][A-Za-z0-9._:@-]{0,127})(?:/(timeline|pause|resume|stop|cancel|replan))?$")
APPROVAL_ROUTE = re.compile(r"^/api/v1/approvals/([A-Za-z0-9][A-Za-z0-9._:@-]{0,127})/(approve|deny)$")


@dataclass(frozen=True)
class OperatorDashboardTimeProvider:
    reference_time: str | None = None

    def __post_init__(self) -> None:
        if self.reference_time is not None:
            parse_time(self.reference_time)

    def now(self) -> str | None:
        return self.reference_time

    def text(self) -> str:
        return self.reference_time if self.reference_time is not None else time_text(None)

    def epoch(self) -> float:
        return parse_time(self.reference_time).timestamp() if self.reference_time is not None else time.time()


@dataclass(frozen=True)
class OperatorDashboardConfig:
    workspace_root: str
    state_root: str | None = None
    host: str = "127.0.0.1"
    port: int = 8765
    static_assets_path: str | None = None
    poll_interval_hint: int = 5
    request_body_size_limit: int = 32_768
    allowed_origins: tuple[str, ...] = ()
    action_token_ttl: int = 900
    enable_write_actions: bool = True
    debug: bool = False
    runtime_budget_limit: int = 4
    reference_time: str | None = None
    allow_unsafe_host: bool = False

    def __post_init__(self) -> None:
        workspace = Path(self.workspace_root).resolve(strict=True)
        if not workspace.is_dir(): raise ValueError("dashboard_workspace_root_not_directory")
        if self.host not in {"127.0.0.1", "localhost", "::1"} and not self.allow_unsafe_host:
            raise ValueError("dashboard_non_loopback_host_rejected")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 0 <= self.port <= 65535:
            raise ValueError("invalid_dashboard_port")
        if not 2 <= self.poll_interval_hint <= 60: raise ValueError("invalid_dashboard_poll_interval")
        if not 1024 <= self.request_body_size_limit <= 1_048_576: raise ValueError("invalid_dashboard_body_limit")
        if not 30 <= self.action_token_ttl <= 86_400: raise ValueError("invalid_dashboard_token_ttl")
        if self.reference_time is not None: parse_time(self.reference_time)
        assets = Path(self.static_assets_path) if self.static_assets_path else Path(__file__).resolve().parents[2] / "operator_dashboard"
        object.__setattr__(self, "workspace_root", str(workspace))
        object.__setattr__(self, "state_root", str(Path(self.state_root).resolve(strict=False)) if self.state_root else None)
        object.__setattr__(self, "static_assets_path", str(assets.resolve(strict=False)))
        object.__setattr__(self, "allowed_origins", tuple(self.allowed_origins))

    @property
    def configuration_fingerprint(self) -> str:
        value = asdict(self); value["workspace_root"] = "<workspace-root>"; value["state_root"] = "<runtime-state-root>" if self.state_root else None; value["static_assets_path"] = "<static-assets>"
        return fingerprint(value)


@dataclass
class OperatorDashboardStatus:
    configured_host: str
    configured_port: int
    bound_port: int | None
    read_only_mode: bool
    write_actions_enabled: bool
    static_assets_valid: bool
    operations_surface_available: bool
    goal_store_readable: bool
    runtime_state_readable: bool
    server_state: str = "created"
    started_timestamp: str | None = None
    request_count: int = 0
    read_request_count: int = 0
    write_request_count: int = 0
    failed_request_count: int = 0
    last_error_category: str | None = None
    security_policy_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = {"contract": CONTRACT, "version": VERSION, **asdict(self)}
        value["status_fingerprint"] = fingerprint(value)
        return value


class _DashboardHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"
    daemon_threads = True
    block_on_close = False

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class OperatorDashboardServer:
    def __init__(self, config: OperatorDashboardConfig, *, controller: RuntimeGoalController | None = None,
                 operations: GoalOperationsService | None = None):
        if not isinstance(config, OperatorDashboardConfig): raise TypeError("dashboard_config_required")
        self.config = config
        effective_reference_time = config.reference_time if config.reference_time is not None else (operations.config.reference_time if operations is not None else None)
        self.time_provider = OperatorDashboardTimeProvider(effective_reference_time)
        self.controller = controller
        operations_config = GoalOperationsConfig(config.workspace_root, state_root=(str(controller.agent_state_root) if controller else config.state_root), runtime_budget_limit=config.runtime_budget_limit, reference_time=effective_reference_time)
        self.operations = operations or GoalOperationsService(operations_config)
        self.read_service = OperatorDashboardReadService(self.operations)
        controller_source = controller or (lambda: RuntimeGoalController(workspace_root=config.workspace_root, state_root=config.state_root, now=self.time_provider.now()))
        self.action_service = OperatorDashboardActionService(controller_source, self.read_service, enabled=config.enable_write_actions, time_provider=self.time_provider.now)
        self.security = OperatorDashboardSecurityPolicy(config.host, config.port, config.allowed_origins, config.action_token_ttl)
        self.tokens = ActionTokenManager(config.action_token_ttl, clock=self.time_provider.epoch)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._status_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._shutdown_lock = threading.Lock()
        self._stopped = threading.Event()
        self._assets = self._validate_assets()
        health_ok = True
        try: self.read_service.health()
        except (OSError, ValueError, json.JSONDecodeError): health_ok = False
        self.status = OperatorDashboardStatus(config.host, config.port, None, not config.enable_write_actions,
            config.enable_write_actions, len(self._assets) == len(STATIC_ASSETS), health_ok, health_ok, health_ok,
            security_policy_fingerprint=self.security.policy_fingerprint)

    def _validate_assets(self) -> dict[str, Path]:
        root = Path(str(self.config.static_assets_path)).resolve(strict=False); result = {}
        for name in STATIC_ASSETS:
            path = (root / name).resolve(strict=False)
            if path.parent != root or not path.is_file(): continue
            result[name] = path
        return result

    def start(self) -> "OperatorDashboardServer":
        with self._lifecycle_lock:
            if self.status.server_state != "created":
                raise ValueError("dashboard_server_already_started")
            self.status.server_state = "starting"
            if len(self._assets) != len(STATIC_ASSETS):
                self.status.server_state = "failed"
                self.status.last_error_category = "static_asset_missing"
                raise ValueError("static_asset_missing")
            try:
                httpd = _DashboardHTTPServer((self.config.host, self.config.port), self._handler_type())
            except OSError as exc:
                self.status.server_state = "failed"
                self.status.last_error_category = "bind_failure"
                raise ValueError("dashboard_server_bind_failure") from exc
            self._httpd = httpd
            actual_port = int(httpd.server_address[1])
            self.security = OperatorDashboardSecurityPolicy(self.config.host, actual_port, self.config.allowed_origins, self.config.action_token_ttl)
            self.status.bound_port = actual_port
            self.status.started_timestamp = self.time_provider.text()
            self.status.security_policy_fingerprint = self.security.policy_fingerprint
            self._stopped.clear()
            self._thread = threading.Thread(target=self._run_server, name="zero-operator-dashboard", daemon=True)
            self.status.server_state = "running"
            self._thread.start()
            return self

    def _run_server(self) -> None:
        try:
            httpd = self._httpd
            if httpd is not None:
                httpd.serve_forever(poll_interval=0.1)
        except Exception:
            with self._lifecycle_lock:
                if self.status.server_state not in {"stopping", "stopped"}:
                    self.status.server_state = "failed"
                    self.status.last_error_category = "serve_failure"
        finally:
            self._stopped.set()

    def serve_forever(self) -> None:
        self.serve()

    def serve(self) -> None:
        if self.status.server_state == "created":
            self.start()
        while not self._stopped.wait(0.2):
            thread = self._thread
            if thread is None or not thread.is_alive():
                break

    def request_stop(self) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        with self._shutdown_lock:
            with self._lifecycle_lock:
                state = self.status.server_state
                if state == "stopped":
                    return
                if state == "created":
                    self.status.server_state = "stopped"
                    self._stopped.set()
                    return
                self.status.server_state = "stopping"
                httpd = self._httpd
            try:
                if httpd is not None and self._thread is not threading.current_thread():
                    httpd.shutdown()
            finally:
                self.close()
                self.join(timeout=5.0)
                with self._lifecycle_lock:
                    self.status.server_state = "stopped"
                    self._stopped.set()

    def close(self) -> None:
        with self._lifecycle_lock:
            httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.server_close()

    def join(self, timeout: float = 5.0) -> bool:
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))
        stopped = thread is None or not thread.is_alive()
        if stopped:
            self._thread = None
        return stopped

    def stop(self) -> None:
        self.shutdown()

    @property
    def url(self) -> str:
        port = self.status.bound_port or self.config.port
        host = "[::1]" if self.config.host == "::1" else self.config.host
        return f"http://{host}:{port}/"

    def status_dict(self) -> dict[str, Any]:
        with self._status_lock:
            return self.status.to_dict()

    def _count(self, *, write: bool, failed: bool = False, error: str | None = None) -> None:
        with self._status_lock:
            self.status.request_count += 1
            if write: self.status.write_request_count += 1
            else: self.status.read_request_count += 1
            if failed: self.status.failed_request_count += 1; self.status.last_error_category = error

    def _handler_type(self):
        dashboard = self
        class Handler(BaseHTTPRequestHandler):
            server_version = "ZEROOperatorDashboard/1.1"
            sys_version = ""

            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                self._dispatch_get()

            def do_POST(self) -> None:
                self._dispatch_post()

            def do_HEAD(self) -> None:
                self._error("method_not_allowed", HTTPStatus.METHOD_NOT_ALLOWED, write=False, extra_headers={"Allow": "GET, POST"})

            def do_PUT(self) -> None: self.do_HEAD()
            def do_PATCH(self) -> None: self.do_HEAD()
            def do_DELETE(self) -> None: self.do_HEAD()
            def do_OPTIONS(self) -> None: self.do_HEAD()

            def _validate_host(self) -> None:
                dashboard.security.validate_host(self.headers.get("Host"))

            def _dispatch_get(self) -> None:
                try:
                    self._validate_host(); path = urlsplit(self.path).path
                    if path == "/api/v1/session":
                        session_id, token, expires = dashboard.tokens.issue()
                        self._json({"contract": "zero.operator.dashboard_session.v1", "action_token": token, "expires_at_epoch": expires,
                                    "write_actions_enabled": dashboard.config.enable_write_actions},
                                   extra_headers={"Set-Cookie": f"zero_dashboard_session={session_id}; Path=/; HttpOnly; SameSite=Strict"}, redact=False)
                    elif path == "/api/v1/overview": self._json(dashboard.read_service.overview())
                    elif path == "/api/v1/health": self._json(dashboard.read_service.health())
                    elif path == "/api/v1/pending-approvals": self._json(dashboard.read_service.pending_approvals())
                    elif path == "/api/v1/dashboard-status": self._json(dashboard.status_dict())
                    else:
                        match = GOAL_ROUTE.fullmatch(path)
                        if match and not match.group(2): self._json(dashboard.read_service.goal(match.group(1)))
                        elif match and match.group(2) == "timeline": self._json(dashboard.read_service.timeline(match.group(1)))
                        elif path.startswith("/api/"): raise DashboardSecurityError("api_endpoint_not_found", 404)
                        else: self._static(path)
                    dashboard._count(write=False)
                except Exception as exc: self._safe_exception(exc, write=False)

            def _dispatch_post(self) -> None:
                try:
                    self._validate_host(); dashboard.security.validate_origin(self.headers.get("Origin"))
                    if not dashboard.config.enable_write_actions: raise DashboardSecurityError("dashboard_read_only_mode", 403)
                    if (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold() != "application/json":
                        raise DashboardSecurityError("invalid_content_type", 415)
                    dashboard.tokens.verify(self._cookie("zero_dashboard_session"), self.headers.get("X-Zero-Action-Token"))
                    body = self._body(); path = urlsplit(self.path).path
                    match = GOAL_ROUTE.fullmatch(path); approval = APPROVAL_ROUTE.fullmatch(path)
                    if match and match.group(2) in {"pause", "resume", "stop", "cancel", "replan"}:
                        action, resource = match.group(2), match.group(1)
                        allowed = {"operator_identity", "confirmation", "idempotency_key"} | ({"reason"} if action == "replan" else set())
                    elif approval:
                        resource, action = approval.group(1), approval.group(2)
                        allowed = {"operator_identity", "confirmation", "idempotency_key", "goal_id", "milestone_id", "entry_id", "expected_scope_fingerprint", "reason"}
                    else: raise DashboardSecurityError("api_endpoint_not_found", 404)
                    unknown = set(body) - allowed
                    if unknown: raise DashboardSecurityError("unknown_request_field", 400)
                    dashboard.security.validate_identifier(body.get("operator_identity"), "operator_identity")
                    dashboard.security.validate_identifier(body.get("idempotency_key"), "idempotency_key")
                    result = dashboard.action_service.execute(str(action), str(resource), body)
                    self._json(result, HTTPStatus.OK); dashboard._count(write=True)
                except Exception as exc: self._safe_exception(exc, write=True)

            def _body(self) -> dict[str, Any]:
                raw_length = self.headers.get("Content-Length")
                try: length = int(raw_length or "-1")
                except ValueError: raise DashboardSecurityError("invalid_content_length", 400)
                if length < 0: raise DashboardSecurityError("content_length_required", 411)
                if length > dashboard.config.request_body_size_limit: raise DashboardSecurityError("request_body_too_large", 413)
                raw = self.rfile.read(length)
                try: value = json.loads(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError): raise DashboardSecurityError("invalid_json", 400)
                if not isinstance(value, dict): raise DashboardSecurityError("json_object_required", 400)
                return value

            def _cookie(self, name: str) -> str | None:
                for item in (self.headers.get("Cookie") or "").split(";"):
                    key, separator, value = item.strip().partition("=")
                    if separator and key == name: return value
                return None

            def _static(self, path: str) -> None:
                name = dashboard.security.validate_static_target(path, dashboard._assets)
                data = dashboard._assets[name].read_bytes()
                self.send_response_only(HTTPStatus.OK); self._headers(STATIC_ASSETS[name], len(data)); self.end_headers(); self.wfile.write(data)

            def _json(self, value: Mapping[str, Any], status: int = HTTPStatus.OK, *, extra_headers: Mapping[str, str] | None = None, redact: bool = True) -> None:
                safe = dashboard.security.redact(value) if redact else dict(value)
                data = (json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                self.send_response_only(status); self._headers("application/json; charset=utf-8", len(data), extra_headers); self.end_headers(); self.wfile.write(data)

            def _headers(self, content_type: str, length: int, extra: Mapping[str, str] | None = None) -> None:
                self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(length))
                for key, value in SECURITY_HEADERS.items(): self.send_header(key, value)
                for key, value in (extra or {}).items(): self.send_header(key, value)

            def _safe_exception(self, exc: Exception, *, write: bool) -> None:
                if isinstance(exc, DashboardSecurityError): code, status = exc.code, exc.status
                else:
                    code = str(exc) if isinstance(exc, (ValueError, OSError, KeyError)) else "internal_dashboard_error"
                    status = _error_status(code)
                self._error(code, status, write=write)

            def _error(self, code: str, status: int, *, write: bool, extra_headers: Mapping[str, str] | None = None) -> None:
                correlation = "dashboard-" + secrets.token_hex(8)
                payload = {"contract": "zero.operator.dashboard_error.v1", "version": VERSION, "error_code": code,
                           "message": _safe_message(code), "resource_identity": urlsplit(self.path).path,
                           "retryable": status >= 500, "correlation_identity": correlation}
                dashboard._count(write=write, failed=True, error=code)
                self._json(payload, status, extra_headers=extra_headers)

        return Handler


def _error_status(code: str) -> int:
    if "not_found" in code: return 404
    if code in {"invalid_content_type"}: return 415
    if "read_only" in code or "token" in code or "origin" in code or "host" in code or "confirmation" in code: return 403
    if "terminal" in code or "transition" in code or "conflict" in code or "not_paused" in code or "not_waiting" in code: return 409
    if "critical" in code or "corrupt" in code or "fingerprint_mismatch" in code: return 503
    return 400


def _safe_message(code: str) -> str:
    messages = {
        "goal_not_found": "The requested goal was not found.", "approval_not_found": "The requested approval was not found.",
        "dashboard_read_only_mode": "Write actions are disabled.", "invalid_action_token": "The action session is invalid or expired.",
        "invalid_origin": "The request origin is not allowed.", "invalid_host": "The request host is not allowed.",
        "request_body_too_large": "The request body exceeds the configured limit.", "invalid_json": "The request body is not valid JSON.",
        "operator_confirmation_required": "Explicit operator confirmation is required.",
    }
    return messages.get(code, "The dashboard request could not be completed safely.")


__all__ = ["CONTRACT", "VERSION", "OperatorDashboardConfig", "OperatorDashboardServer", "OperatorDashboardTimeProvider",
           "OperatorDashboardStatus", "OperatorDashboardReadService", "OperatorDashboardActionService",
           "OperatorDashboardSecurityPolicy"]
