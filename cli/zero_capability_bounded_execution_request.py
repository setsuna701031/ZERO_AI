import argparse,json
from cli.zero_capability_execution_session_admission import _read,_finish
from core.runtime.runtime_capability_bounded_execution_request import build_capability_bounded_execution_request
def run(argv=None):
    p=argparse.ArgumentParser(description="Build a declarative bounded execution request; this does not execute it.");p.add_argument("--authority","--input",dest="input");p.add_argument("--operation-class",required=True);p.add_argument("--target-json",required=True);p.add_argument("--parameters-json",default="{}");p.add_argument("--request-ordinal",type=int,default=1);p.add_argument("--output")
    try:a=p.parse_args(argv);return _finish(build_capability_bounded_execution_request(_read(a.input),operation_class=a.operation_class,target_descriptor=json.loads(a.target_json),bounded_parameters=json.loads(a.parameters_json),request_ordinal=a.request_ordinal),a.output)
    except (OSError,UnicodeError,json.JSONDecodeError,TypeError,ValueError):return {"error":"invalid_json_input"},2
def main(argv=None):r,c=run(argv);print(json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False));return c
if __name__=="__main__":raise SystemExit(main())
