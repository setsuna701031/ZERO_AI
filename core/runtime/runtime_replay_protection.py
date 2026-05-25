from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any


class RuntimeReplayNonceStore:
    """In-memory nonce ownership boundary for worker evidence replay protection.

    This store deliberately stays small and local.  It separates nonce ownership
    from timestamp validation so the verifier does not own replay state directly.
    A durable store can replace this class later without changing verifier or
    loader contracts.
    """

    SCHEMA = "zero.runtime.replay_nonce_store.v1"

    def __init__(self, initial_nonces: Any | None = None) -> None:
        self._seen: set[str] = set()
        if isinstance(initial_nonces, (set, list, tuple)):
            self._seen.update(_text(item) for item in initial_nonces if _text(item))

    def check(self, nonce: str) -> dict[str, Any]:
        nonce_text = _text(nonce)
        reasons: list[str] = []
        if not nonce_text:
            reasons.append("missing_nonce")
        elif nonce_text in self._seen:
            reasons.append("reused_nonce")
        return {
            "ok": not reasons,
            "schema": self.SCHEMA,
            "nonce": nonce_text,
            "seen": nonce_text in self._seen if nonce_text else False,
            "reasons": sorted(set(reasons)),
        }

    def consume(self, nonce: str) -> dict[str, Any]:
        checked = self.check(nonce)
        if checked["ok"]:
            self._seen.add(checked["nonce"])
            checked["consumed"] = True
        else:
            checked["consumed"] = False
        return checked

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": self.SCHEMA,
            "nonces": sorted(self._seen),
            "count": len(self._seen),
        }


class RuntimeReplayProtection:
    """Timestamp freshness and nonce replay boundary for worker evidence."""

    SCHEMA = "zero.runtime.replay_protection.v1"

    def __init__(
        self,
        *,
        freshness_window_seconds: int = 300,
        future_skew_seconds: int = 30,
        now: datetime | str | None = None,
        nonce_store: RuntimeReplayNonceStore | None = None,
    ) -> None:
        self.freshness_window_seconds = max(0, int(freshness_window_seconds))
        self.future_skew_seconds = max(0, int(future_skew_seconds))
        self._now = _parse_timestamp(now) if now is not None else None
        self.nonce_store = nonce_store or RuntimeReplayNonceStore()

    def verify(self, evidence: Any, *, consume: bool = True) -> dict[str, Any]:
        payload = copy.deepcopy(evidence) if isinstance(evidence, dict) else {}
        reasons: list[str] = []

        timestamp_text = _text(payload.get("timestamp") or payload.get("issued_at"))
        if not timestamp_text:
            reasons.append("missing_timestamp")
            issued_at = None
        else:
            issued_at = _parse_timestamp(timestamp_text)
            if issued_at is None:
                reasons.append("invalid_timestamp")

        nonce = _text(payload.get("nonce") or payload.get("evidence_id"))
        nonce_check = self.nonce_store.check(nonce)
        reasons.extend(nonce_check.get("reasons", []))

        now = self.now()
        if issued_at is not None:
            if issued_at < now - timedelta(seconds=self.freshness_window_seconds):
                reasons.append("stale_timestamp")
            if issued_at > now + timedelta(seconds=self.future_skew_seconds):
                reasons.append("future_timestamp")

        ok = not reasons
        consumed = False
        if ok and consume:
            consumed_result = self.nonce_store.consume(nonce)
            consumed = bool(consumed_result.get("consumed"))
            if not consumed_result.get("ok"):
                reasons.extend(consumed_result.get("reasons", []))
                ok = False

        return {
            "ok": ok,
            "schema": self.SCHEMA,
            "timestamp": timestamp_text,
            "nonce": nonce,
            "now": now.isoformat(),
            "freshness_window_seconds": self.freshness_window_seconds,
            "future_skew_seconds": self.future_skew_seconds,
            "consumed": consumed,
            "nonce_store_schema": self.nonce_store.SCHEMA,
            "reasons": sorted(set(reasons)),
        }

    def now(self) -> datetime:
        return self._now or datetime.now(UTC)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": self.SCHEMA,
            "freshness_window_seconds": self.freshness_window_seconds,
            "future_skew_seconds": self.future_skew_seconds,
            "now": self.now().isoformat(),
            "nonce_store": self.nonce_store.snapshot(),
        }


def _parse_timestamp(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = ["RuntimeReplayNonceStore", "RuntimeReplayProtection"]
