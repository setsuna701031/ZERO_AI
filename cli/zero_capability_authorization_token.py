from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.runtime.runtime_capability_authorization_token import create_capability_authorization_token
from core.runtime.runtime_capability_authorization_token_validation import validate_capability_authorization_token

def run(argv: list[str] | None = None) -> tuple[Any, int]:
    parser = argparse.ArgumentParser(prog="zero-capability-authorization-token")
    parser.add_argument("--preparation", required=True)
    parser.add_argument("--created-at")
    parser.add_argument("--expires-at")
    parser.add_argument("--ttl-seconds", type=int)
    parser.add_argument("--output")
    try: args = parser.parse_args(argv)
    except SystemExit as exc: return {"error": "invalid_arguments"}, int(exc.code)
    try: value = json.loads(Path(args.preparation).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError): return {"error": "invalid_json_input"}, 2
    result = create_capability_authorization_token(value, created_at=args.created_at, expires_at=args.expires_at, token_ttl_seconds=args.ttl_seconds)
    for code in ("invalid_created_at", "invalid_expires_at", "invalid_token_ttl", "ttl_mismatch"):
        if code in result["errors"] and ((code == "invalid_created_at" and args.created_at is not None) or (code == "invalid_expires_at" and args.expires_at is not None) or code in ("invalid_token_ttl", "ttl_mismatch")):
            return {"error": code}, 2
    if not validate_capability_authorization_token(result).valid: return {"error": "invalid_authorization_token"}, 2
    text = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if args.output:
        try: Path(args.output).write_text(text + "\n", encoding="utf-8")
        except OSError: return {"error": "output_write_failed"}, 2
    return result, 0

def main(argv: list[str] | None = None) -> int:
    value, code = run(argv)
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return code

if __name__ == "__main__": raise SystemExit(main())
