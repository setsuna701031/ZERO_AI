from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_active_authorization import create_capability_active_authorization
from core.runtime.runtime_capability_active_authorization_validation import validate_capability_active_authorization

def run(argv: list[str] | None = None) -> tuple[Any, int]:
    parser = argparse.ArgumentParser(prog="zero-capability-active-authorization")
    parser.add_argument("--preparation", required=True); parser.add_argument("--authorized-at"); parser.add_argument("--expires-at"); parser.add_argument("--ttl-seconds", type=int); parser.add_argument("--output")
    try: args = parser.parse_args(argv)
    except SystemExit as exc: return {"error": "invalid_arguments"}, int(exc.code)
    try: value = json.loads(Path(args.preparation).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError): return {"error": "invalid_json_input"}, 2
    result = create_capability_active_authorization(value, authorized_at=args.authorized_at, expires_at=args.expires_at, authorization_ttl_seconds=args.ttl_seconds)
    if not validate_capability_active_authorization(result).valid: return {"error": "invalid_authorization"}, 2
    text = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if args.output:
        try: Path(args.output).write_text(text + "\n", encoding="utf-8")
        except OSError: return {"error": "output_write_failed"}, 2
    input_errors = {"invalid_authorized_at", "invalid_expires_at", "invalid_ttl", "ttl_mismatch"}
    return result, 2 if input_errors & set(result["errors"]) else 0

def main(argv: list[str] | None = None) -> int:
    value, code = run(argv); print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)); return code
if __name__ == "__main__": raise SystemExit(main())
