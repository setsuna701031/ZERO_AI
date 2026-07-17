from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_active_authorization_eligibility import evaluate_capability_active_authorization_eligibility
from core.runtime.runtime_capability_active_authorization_eligibility_validation import validate_capability_active_authorization_eligibility

def run(argv:list[str]|None=None)->tuple[Any,int]:
    parser=argparse.ArgumentParser(prog="zero-capability-active-authorization-eligibility")
    parser.add_argument("--decision",required=True);parser.add_argument("--evaluated-at");parser.add_argument("--output")
    try:args=parser.parse_args(argv)
    except SystemExit as exc:return {"error":"invalid_arguments"},int(exc.code)
    try:value=json.loads(Path(args.decision).read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
    result=evaluate_capability_active_authorization_eligibility(value,evaluated_at=args.evaluated_at)
    if not validate_capability_active_authorization_eligibility(result).valid:return result,2
    text=json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    if args.output:
        try:Path(args.output).write_text(text+"\n",encoding="utf-8")
        except OSError:return {"error":"output_write_failed"},2
    return result,0 if "invalid_timestamp" not in result["errors"] else 2

def main(argv:list[str]|None=None)->int:
    value,code=run(argv);print(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False));return code
if __name__=="__main__":raise SystemExit(main())
