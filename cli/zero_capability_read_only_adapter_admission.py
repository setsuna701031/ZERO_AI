import argparse,json
from cli.zero_capability_execution_session_admission import _read
from core.runtime.runtime_capability_read_only_adapter_admission import build_capability_read_only_adapter_admission as build
HELP="bounded read-only observation; no filesystem mutation; no process, network, or model invocation; observation does not mean execution completion"
def run(argv=None):
 p=argparse.ArgumentParser(description=HELP);p.add_argument("--authority",required=True);p.add_argument("--request",required=True);p.add_argument("--bridge-closure",required=True);p.add_argument("--workspace-root",required=True)
 try:a=p.parse_args(argv);return build(_read(a.authority),_read(a.request),_read(a.bridge_closure),workspace_root_descriptor={"path":a.workspace_root}),0
 except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
