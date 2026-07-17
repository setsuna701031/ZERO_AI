from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_activation_authorization_review_decision import build_capability_activation_authorization_review_decision
from core.runtime.runtime_capability_activation_authorization_review_decision_validation import validate_capability_activation_authorization_review_decision

def run(argv: list[str] | None = None) -> tuple[Any, int]:
    parser = argparse.ArgumentParser(prog="zero-capability-activation-authorization-review-decision")
    parser.add_argument("--request", required=True); parser.add_argument("--decision", required=True)
    parser.add_argument("--reviewer-id", required=True); parser.add_argument("--reason", required=True)
    parser.add_argument("--reviewed-at"); parser.add_argument("--output")
    try: args = parser.parse_args(argv)
    except SystemExit as exc: return {"error":"invalid_arguments"}, int(exc.code)
    try: request = json.loads(Path(args.request).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError): return {"error":"invalid_json_input"}, 2
    result = build_capability_activation_authorization_review_decision(authorization_review_request=request, decision=args.decision, reviewer_id=args.reviewer_id, decision_reason=args.reason, reviewed_at=args.reviewed_at)
    valid = validate_capability_activation_authorization_review_decision(result).valid
    text = json.dumps(result, sort_keys=True, separators=(",",":"), ensure_ascii=False)
    if args.output:
        try: Path(args.output).write_text(text + "\n", encoding="utf-8")
        except OSError: return {"error":"output_write_failed"}, 2
    return result, 0 if valid and result["decision"] != "invalid" else 2

def main(argv: list[str] | None = None) -> int:
    value, code = run(argv); print(json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False)); return code
if __name__ == "__main__": raise SystemExit(main())
