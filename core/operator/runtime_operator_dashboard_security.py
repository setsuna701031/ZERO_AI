from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
import secrets
import time
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlsplit

from core.runtime.runtime_operator_session import fingerprint

CONTRACT = "zero.operator.dashboard_security.v1"
IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")


class DashboardSecurityError(ValueError):
    def __init__(self, code: str, status: int = 403):
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class OperatorDashboardSecurityPolicy:
    host: str = "127.0.0.1"
    port: int = 8765
    allowed_origins: tuple[str, ...] = ()
    token_ttl_seconds: int = 900

    def __post_init__(self) -> None:
        origins = self.allowed_origins or (
            f"http://127.0.0.1:{self.port}",
            f"http://localhost:{self.port}",
            f"http://[::1]:{self.port}",
        )
        object.__setattr__(self, "allowed_origins", tuple(origins))

    @property
    def policy_fingerprint(self) -> str:
        return fingerprint({"contract": CONTRACT, "host": self.host, "port": self.port,
                            "allowed_origins": self.allowed_origins,
                            "token_ttl_seconds": self.token_ttl_seconds})

    def validate_host(self, value: str | None) -> None:
        raw = (value or "").strip().casefold()
        allowed = {f"127.0.0.1:{self.port}", f"localhost:{self.port}", f"[::1]:{self.port}"}
        if raw not in allowed:
            raise DashboardSecurityError("invalid_host")

    def validate_origin(self, value: str | None) -> None:
        if not value or value.rstrip("/") not in {item.rstrip("/") for item in self.allowed_origins}:
            raise DashboardSecurityError("invalid_origin")

    @staticmethod
    def validate_identifier(value: Any, name: str) -> str:
        text = str(value or "")
        if not IDENTITY_RE.fullmatch(text):
            raise DashboardSecurityError(f"invalid_{name}", 400)
        return text

    @staticmethod
    def validate_static_target(raw_path: str, allowlist: Mapping[str, Any]) -> str:
        decoded = unquote(urlsplit(raw_path).path)
        if decoded in {"", "/"}:
            decoded = "/index.html"
        if "\\" in decoded or "\x00" in decoded or ".." in decoded.split("/"):
            raise DashboardSecurityError("static_path_rejected", 404)
        name = decoded.lstrip("/")
        if name not in allowlist or "/" in name:
            raise DashboardSecurityError("static_asset_not_found", 404)
        return name

    @staticmethod
    def redact(value: Any, key: str = "") -> Any:
        lowered = key.casefold()
        if any(term in lowered for term in ("token", "secret", "password", "authorization", "cookie")):
            return "<redacted>" if value is not None else None
        if isinstance(value, Mapping):
            return {str(k): OperatorDashboardSecurityPolicy.redact(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [OperatorDashboardSecurityPolicy.redact(item, key) for item in value]
        if isinstance(value, str):
            return re.sub(r"(?i)(?:[A-Z]:[\\/][^\s\"']+|(?<![\w.])/(?:[^\s\"']+/)+[^\s\"']*)", "<redacted-path>", value)
        return value


class ActionTokenManager:
    """Process-local, restart-invalidated, bounded confirmation sessions."""

    def __init__(self, ttl_seconds: int, *, max_sessions: int = 128, clock: Callable[[], float] | None = None):
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._clock = clock or time.time
        self._secret = secrets.token_bytes(32)
        self._sessions: dict[str, tuple[str, float]] = {}

    def issue(self) -> tuple[str, str, int]:
        self._purge()
        session_id = secrets.token_urlsafe(24)
        expires = self._clock() + self.ttl_seconds
        token = self._sign(session_id, expires)
        self._sessions[session_id] = (hashlib.sha256(token.encode()).hexdigest(), expires)
        while len(self._sessions) > self.max_sessions:
            self._sessions.pop(next(iter(self._sessions)))
        return session_id, token, int(expires)

    def verify(self, session_id: str | None, token: str | None) -> None:
        self._purge()
        record = self._sessions.get(session_id or "")
        if not record or not token:
            raise DashboardSecurityError("invalid_action_token")
        claimed = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(record[0], claimed):
            raise DashboardSecurityError("invalid_action_token")

    def _sign(self, session_id: str, expires: float) -> str:
        payload = f"{session_id}.{int(expires)}"
        signature = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def _purge(self) -> None:
        now = self._clock()
        self._sessions = {key: value for key, value in self._sessions.items() if value[1] > now}


SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

__all__ = ["ActionTokenManager", "CONTRACT", "DashboardSecurityError",
           "OperatorDashboardSecurityPolicy", "SECURITY_HEADERS"]
