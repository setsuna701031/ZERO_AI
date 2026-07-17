import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_observation_evidence_closure import close_capability_observation_evidence as build
HELP="bounded read-only observation; no filesystem mutation; no process, network, or model invocation; observation does not mean execution completion"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP)
 for n in ("authority","execution-request","bridge-closure","admission","observation-request","target-resolution","observation-result"):p.add_argument("--"+n,required=True)
 try:a=p.parse_args(argv);return build(*[_read(getattr(a,"_".join(n.split("-")))) for n in ("authority","execution-request","bridge-closure","admission","observation-request","target-resolution","observation-result")]),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
