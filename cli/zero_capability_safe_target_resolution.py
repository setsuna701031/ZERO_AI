import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_safe_target_resolution import build_capability_safe_target_resolution as build
HELP="bounded read-only observation; no filesystem mutation; no process, network, or model invocation; observation does not mean execution completion"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);p.add_argument("--admission",required=True);p.add_argument("--observation-request",required=True)
 try:a=p.parse_args(argv);return build(_read(a.admission),_read(a.observation_request)),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
