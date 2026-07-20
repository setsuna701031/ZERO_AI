def request_payload(mode="preview"):
    return {"request_id":"request-1","requested_orchestration_mode":mode,"workspace_id":"workspace-1","workspace_root_fingerprint":"root-fingerprint","scope_constraints":["src"],"authority_constraints":["bounded"],"execution_requested":False}
def upstream(schema="zero.test.v1",status="valid",**values):
    return {"schema":schema,"artifact_id":"upstream-1","fingerprint":"upstream-fingerprint","status":status,**values}
