import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_bounded_decision_review_request import build_capability_bounded_decision_review_request as build
HELP="bounded decision governance only; does not execute the decision; does not authorize filesystem muta"+"tion; does not authorize process, network, or model invocation; authorization only permits a later control-plane review stage"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP)
 for n in ("readiness-closure","decision-proposal","requested-scope","requested-permissions"):p.add_argument("--"+n,required=True)
 p.add_argument("--requested-effect-class",required=True)
 try:a=p.parse_args(argv);return build(_read(a.readiness_closure),_read(a.decision_proposal),requested_scope=_read(a.requested_scope),requested_effect_class=a.requested_effect_class,requested_permissions=_read(a.requested_permissions)),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
