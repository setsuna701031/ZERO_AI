import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_bounded_observation_request import build_capability_bounded_observation_request as build
HELP="bounded read-only observation; no filesystem mutation; no process, network, or model invocation; observation does not mean execution completion"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);p.add_argument("--admission",required=True);p.add_argument("--request",required=True);p.add_argument("--observation-kind",required=True);p.add_argument("--relative-target",required=True);p.add_argument("--limits",required=True)
 try:a=p.parse_args(argv);return build(_read(a.admission),_read(a.request),observation_kind=a.observation_kind,relative_target=a.relative_target,limits=_read(a.limits)),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
