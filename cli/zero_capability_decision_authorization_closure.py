import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_decision_authorization_closure import close_capability_decision_authorization as build
HELP="bounded decision governance only; does not execute the decision; does not authorize filesystem muta"+"tion; does not authorize process, network, or model invocation; authorization only permits a later control-plane review stage"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);names=("authority","execution-request","observation-closure","readiness-closure","review-request","eligibility","policy","authorization")
 for n in names:p.add_argument("--"+n,required=True)
 try:a=p.parse_args(argv);return build(*[_read(getattr(a,"_".join(n.split("-")))) for n in names]),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
