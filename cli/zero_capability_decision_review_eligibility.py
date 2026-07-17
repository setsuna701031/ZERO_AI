import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_decision_review_eligibility import build_capability_decision_review_eligibility as build
HELP="bounded decision governance only; does not execute the decision; does not authorize filesystem muta"+"tion; does not authorize process, network, or model invocation; authorization only permits a later control-plane review stage"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);p.add_argument("--review-request",required=True);p.add_argument("--readiness-closure",required=True)
 try:a=p.parse_args(argv);return build(_read(a.review_request),_read(a.readiness_closure)),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
