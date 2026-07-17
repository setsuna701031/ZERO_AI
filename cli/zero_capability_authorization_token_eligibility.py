from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.runtime.runtime_capability_authorization_token_eligibility import (
    evaluate_capability_authorization_token_eligibility,
)
from core.runtime.runtime_capability_authorization_token_eligibility_validation import (
    validate_capability_authorization_token_eligibility,
)


def run(argv: list[str] | None = None) -> tuple[Any, int]:
    parser = argparse.ArgumentParser(prog="zero-capability-authorization-token-eligibility")
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--evaluated-at")
    parser.add_argument("--output")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return {"error": "invalid_arguments"}, int(exc.code)
    try:
        value = json.loads(Path(args.authorization).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"error": "invalid_json_input"}, 2
    result = evaluate_capability_authorization_token_eligibility(value, evaluated_at=args.evaluated_at)
    if args.evaluated_at is not None and "invalid_evaluated_at" in result["errors"]:
        return {"error": "invalid_evaluated_at"}, 2
    if not validate_capability_authorization_token_eligibility(result).valid:
        return {"error": "invalid_token_eligibility"}, 2
    text = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if args.output:
        try:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        except OSError:
            return {"error": "output_write_failed"}, 2
    return result, 0


def main(argv: list[str] | None = None) -> int:
    value, code = run(argv)
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
