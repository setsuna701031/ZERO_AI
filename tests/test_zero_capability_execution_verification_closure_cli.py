import json
from cli.zero_capability_execution_verification_closure import run
from tests.test_runtime_capability_execution_session_admission import admission
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_controlled_execution_outcome import outcome
def test_cli(tmp_path):
    vals=[admission(),authority(),request(),outcome()];paths=[]
    for i,v in enumerate(vals):p=tmp_path/f"{i}.json";p.write_text(json.dumps(v),encoding="utf-8");paths.append(str(p))
    r,c=run(["--session-admission",paths[0],"--authority",paths[1],"--request",paths[2],"--outcome",paths[3]]);assert c==0 and r["closed"]
