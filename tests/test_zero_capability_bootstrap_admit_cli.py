from __future__ import annotations
import json
from cli.zero_capability_bootstrap_admit import run
from core.runtime.runtime_capability_bootstrap_admission import create_admission_request
from tests.test_runtime_capability_bootstrap_admission import chain
def test_bounded_metadata_commands():
 assert run(["modes"])[0]["modes"]==["evaluate_admission","prepare_activation_handoff","validate_only"] and run(["future-consumers"])[0]["future_consumers"]==["capability_runtime_activation_gate_v1"] and run(["defaults"])[0]["mode"]=="evaluate_admission"
def test_admit_validate_explain(tmp_path):
 r,l,i,c=chain();q=create_admission_request(consumption_result=r,lease=l,integration=i,runtime_context=c,mode="prepare_activation_handoff");p=tmp_path/"in.json";p.write_text(json.dumps({"request":q,"consumption_result":r,"lease":l,"integration":i,"runtime_context":c}),encoding="utf-8");d,code=run(["admit",str(p)]);assert code==0 and d["admitted"]
 out=tmp_path/"out.json";out.write_text(json.dumps(d),encoding="utf-8");assert run(["validate",str(out)])[0]["valid"] and run(["explain",str(out)])[0]["token_issued"] is False
