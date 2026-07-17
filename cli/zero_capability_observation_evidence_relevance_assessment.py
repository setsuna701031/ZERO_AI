import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_observation_evidence_relevance_assessment import build_capability_observation_evidence_relevance_assessment as build
HELP="consumes canonical observation evidence only; does not access the observed target; does not make a decision; does not authorize execution or muta"+"tion"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP)
 for n in ("acceptance","observation-closure","observation-result","observation-request","decision-question"):p.add_argument("--"+n,required=True)
 try:a=p.parse_args(argv);return build(_read(a.acceptance),_read(a.observation_closure),_read(a.observation_result),_read(a.observation_request),decision_question=_read(a.decision_question)),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
