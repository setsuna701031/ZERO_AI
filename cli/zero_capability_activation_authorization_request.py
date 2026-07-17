from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_activation_authorization_request import FUTURE_CONSUMERS,MODES,REVIEWER_CLASSES,create_authorization_review_request,default_policy,review_activation_authorization
from core.runtime.runtime_capability_activation_authorization_request_validation import validate_authorization_review
from core.runtime.runtime_capability_activation_gate import AUTHORIZATION_CLASSES
def _read(path:str)->Any:return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def run(argv:list[str]|None=None)->tuple[Any,int]:
    parser=argparse.ArgumentParser(prog="zero-capability-activation-authorization-request");sub=parser.add_subparsers(dest="command",required=True)
    for name in ("review","validate","explain"):sub.add_parser(name).add_argument("json_file")
    for name in ("modes","defaults","reviewer-classes","authorization-classes","future-consumers"):sub.add_parser(name)
    try:args=parser.parse_args(argv)
    except SystemExit as exc:return {"error":"invalid_arguments"},int(exc.code)
    if args.command=="modes":return {"modes":sorted(MODES)},0
    if args.command=="defaults":return default_policy(),0
    if args.command=="reviewer-classes":return {"reviewer_classes":sorted(REVIEWER_CLASSES)},0
    if args.command=="authorization-classes":return {"authorization_classes":sorted(AUTHORIZATION_CLASSES)},0
    if args.command=="future-consumers":return {"future_consumers":sorted(FUTURE_CONSUMERS)},0
    try:value=_read(args.json_file)
    except (OSError,UnicodeError,json.JSONDecodeError):return {"error":"invalid_json_input"},2
    if args.command=="validate":
        result=validate_authorization_review(value);return {"valid":result.valid,"errors":list(result.errors)},0 if result.valid else 2
    if args.command=="explain":
        result=validate_authorization_review(value);return {"valid":result.valid,"review_status":value.get("review_status") if isinstance(value,dict) else None,"reviewable":value.get("reviewable") if isinstance(value,dict) else False,"blockers":value.get("blockers",[]) if isinstance(value,dict) else [],"warnings":value.get("warnings",[]) if isinstance(value,dict) else [],"validation_errors":list(result.errors)},0 if result.valid else 2
    try:
        gate=value["gate_decision"];metadata=value.get("authorization_metadata") or gate["authorization_request"]
        request=value.get("request") or create_authorization_review_request(gate_decision=gate,authorization_metadata=metadata,mode=value.get("review_mode","evaluate_review"),reviewer_class=value.get("reviewer_class","capability_runtime_activation_reviewer_v1"),future_consumer=value.get("future_consumer","capability_runtime_activation_authorization_reviewer_v1"),policy=value.get("policy"),caller_metadata=value.get("caller_metadata"))
        review=review_activation_authorization(request,gate_decision=gate,authorization_metadata=metadata);return review,0 if review["review_status"] in {"validated","reviewable","blocked","rejected"} else 2
    except (KeyError,TypeError,ValueError):return {"error":"invalid_review_input"},2
def main(argv:list[str]|None=None)->int:
    value,code=run(argv);print(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False));return code
if __name__=="__main__":raise SystemExit(main())
