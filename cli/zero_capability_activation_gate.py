from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from core.runtime.runtime_capability_activation_gate import AUTHORIZATION_CLASSES, FUTURE_CONSUMERS, MODES, create_activation_gate_request, default_policy, evaluate_activation_gate
from core.runtime.runtime_capability_activation_gate_validation import validate_activation_gate_decision

def _read(path: str) -> Any: return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def run(argv: list[str] | None = None) -> tuple[Any, int]:
    parser=argparse.ArgumentParser(prog="zero-capability-activation-gate"); sub=parser.add_subparsers(dest="command", required=True)
    for name in ("gate","validate","explain"): sub.add_parser(name).add_argument("json_file")
    for name in ("modes","defaults","authorization-classes","future-consumers"): sub.add_parser(name)
    try: args=parser.parse_args(argv)
    except SystemExit as exc: return {"error":"invalid_arguments"}, int(exc.code)
    if args.command=="modes": return {"modes":sorted(MODES)},0
    if args.command=="defaults": return default_policy(),0
    if args.command=="authorization-classes": return {"authorization_classes":sorted(AUTHORIZATION_CLASSES)},0
    if args.command=="future-consumers": return {"future_consumers":sorted(FUTURE_CONSUMERS)},0
    try: value=_read(args.json_file)
    except (OSError, UnicodeError, json.JSONDecodeError): return {"error":"invalid_json_input"},2
    if args.command=="validate":
        result=validate_activation_gate_decision(value); return {"valid":result.valid,"errors":list(result.errors)},0 if result.valid else 2
    if args.command=="explain":
        result=validate_activation_gate_decision(value); return {"valid":result.valid,"gate_status":value.get("gate_status") if isinstance(value,dict) else None,"allowed":value.get("allowed") if isinstance(value,dict) else False,"blockers":value.get("blockers",[]) if isinstance(value,dict) else [],"warnings":value.get("warnings",[]) if isinstance(value,dict) else [],"validation_errors":list(result.errors)},0 if result.valid else 2
    try:
        artifacts={k:value[k] for k in ("admission_decision","consumption_result","lease","integration","runtime_context")}; handoff=value.get("activation_handoff") or artifacts["admission_decision"].get("activation_handoff")
        request=value.get("request") or create_activation_gate_request(admission_decision=artifacts["admission_decision"],activation_handoff=handoff,consumption_result=artifacts["consumption_result"],lease=artifacts["lease"],integration=artifacts["integration"],runtime_context=artifacts["runtime_context"],mode=value.get("gate_mode","evaluate_gate"),authorization_class=value.get("requested_authorization_class","capability_runtime_activation_authorization_v1"),future_consumer=value.get("requested_future_activation_consumer","capability_runtime_activation_controller_v1"),policy=value.get("policy"),caller_metadata=value.get("caller_metadata"))
        decision=evaluate_activation_gate(request,activation_handoff=handoff,**artifacts); return decision,0 if decision["gate_status"] in {"validated","allowed","blocked","rejected"} else 2
    except (KeyError, TypeError, ValueError): return {"error":"invalid_gate_input"},2
def main(argv: list[str] | None=None) -> int:
    value,code=run(argv); print(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)); return code
if __name__=="__main__": raise SystemExit(main())
