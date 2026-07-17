import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_decision_readiness_closure import close_capability_decision_readiness as build
HELP="consumes canonical observation evidence only; does not access the observed target; does not make a decision; does not authorize execution or muta"+"tion"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);names=("authority","execution-request","bridge-closure","observation-closure","acceptance","relevance","sufficiency","readiness")
 for n in names:p.add_argument("--"+n,required=True)
 try:a=p.parse_args(argv);return build(*[_read(getattr(a,"_".join(n.split("-")))) for n in names]),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
