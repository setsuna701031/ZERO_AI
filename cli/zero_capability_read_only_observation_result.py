import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_read_only_observation_result import build_capability_read_only_observation_result as build
HELP="bounded read-only observation; no filesystem mutation; no process, network, or model invocation; observation does not mean execution completion"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);p.add_argument("--admission",required=True);p.add_argument("--observation-request",required=True);p.add_argument("--target-resolution",required=True)
 try:a=p.parse_args(argv);return build(_read(a.admission),_read(a.observation_request),_read(a.target_resolution)),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
