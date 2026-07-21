from __future__ import annotations
import argparse,json,os,tempfile
from pathlib import Path
from core.engineering.engineering_governed_explicit_merge import *
from core.engineering.engineering_governed_explicit_pull_request import STORE_FILES as PR_FILES
from core.engineering.engineering_runtime_session_store import load_session_store,write_session_artifact
class Adapter:
 def __init__(self,path):self.path=Path(path);self.s=json.loads(self.path.read_text(encoding="utf-8"));self.provider_name=self.s["provider_name"]
 def inspect_merge(self,o,n,p):
  pr=next((x for x in self.s["pull_requests"] if x["provider_pr_id"]==p),{});b=self.s["branches"];return {**pr,"repository_id":self.s["repository"]["repository_id"],"exists":bool(pr),"source_exists":pr.get("source_branch") in b,"target_exists":pr.get("target_branch") in b,"source_head":b.get(pr.get("source_branch")),"target_head":b.get(pr.get("target_branch")),"has_changes":b.get(pr.get("source_branch"))!=b.get(pr.get("target_branch")),"conflict_status":pr.get("conflict_status","clean")}
 def perform_merge(self,r):
  pr=next(x for x in self.s["pull_requests"] if x["provider_pr_id"]==r["provider_pr_id"]);sha=pr["merge_commit_sha"];self.s["branches"][r["target_branch"]]=sha;pr.update({"merged":True,"closed":False,"state":"merged","merge_method":"merge_commit","target_head":sha,"source_reachable":True,"source_deleted":False,"unrelated_branch_changed":False})
  fd,tmp=tempfile.mkstemp(prefix=".merge-provider-",suffix=".json",dir=self.path.parent)
  try:
   with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:json.dump(self.s,f,sort_keys=True,separators=(",",":"));f.write("\n");f.flush();os.fsync(f.fileno())
   os.replace(tmp,self.path)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
  return {"merged":True,"state":"merged","merge_commit_sha":sha}
 def inspect_merge_result(self,o,n,p):
  pr=next((x for x in self.s["pull_requests"] if x["provider_pr_id"]==p),{});return {**pr,"repository_id":self.s["repository"]["repository_id"],"target_head":self.s["branches"].get(pr.get("target_branch"))}
def parser():
 p=argparse.ArgumentParser(prog="zero_engineering_runtime_merge",description="Explicit governed merge; no stage defaults to mutation.");p.add_argument("--store",required=True);p.add_argument("--session",required=True);p.add_argument("--provider-state",required=True);s=p.add_subparsers(dest="command",required=True);x=s.add_parser("prepare");x.add_argument("--repository-owner",required=True);x.add_argument("--repository-name",required=True);x.add_argument("--merge-method",default="merge_commit");s.add_parser("verify-remote");s.add_parser("check-eligibility");x=s.add_parser("review");x.add_argument("artifact");x=s.add_parser("authorize");x.add_argument("artifact");s.add_parser("request-merge");s.add_parser("merge");s.add_parser("evidence");s.add_parser("verify-merged");s.add_parser("close");s.add_parser("show");return p
def j(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def main(argv=None):
 n=parser().parse_args(argv);b=load_session_store(n.store,n.session);a=Adapter(n.provider_state);c=n.command
 if c=="prepare":out=build_merge_preparation(b[PR_FILES["closure"]],repository_owner=n.repository_owner,repository_name=n.repository_name,merge_method=n.merge_method);key="preparation"
 elif c=="verify-remote":out=verify_merge_remote(b[STORE_FILES["preparation"]],a);key="remote"
 elif c=="check-eligibility":out=evaluate_merge_eligibility(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]]);key="eligibility"
 elif c=="review":out=review_merge(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["eligibility"]],j(n.artifact));key="review"
 elif c=="authorize":out=authorize_merge(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["eligibility"]],b[STORE_FILES["review"]],j(n.artifact));key="authorization"
 elif c=="request-merge":out=build_merge_request(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["eligibility"]],b[STORE_FILES["review"]],b[STORE_FILES["authorization"]]);key="request"
 elif c=="merge":used,out=execute_merge(b[PR_FILES["closure"]],b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["eligibility"]],b[STORE_FILES["review"]],b[STORE_FILES["authorization"]],b[STORE_FILES["request"]],a);write_session_artifact(n.store,n.session,STORE_FILES["authorization"],used);key="execution"
 elif c=="evidence":out=build_merge_evidence(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["eligibility"]],b[STORE_FILES["review"]],b[STORE_FILES["authorization"]],b[STORE_FILES["execution"]],a);key="evidence"
 elif c=="verify-merged":out=verify_merged(b[STORE_FILES["preparation"]],b[STORE_FILES["execution"]],b[STORE_FILES["evidence"]],a);key="post"
 elif c=="close":out=close_merge(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["eligibility"]],b[STORE_FILES["review"]],b[STORE_FILES["authorization"]],b[STORE_FILES["execution"]],b[STORE_FILES["evidence"]],b[STORE_FILES["post"]]);key="closure"
 else:out=inspect_merge_state(b);key=None
 if key:write_session_artifact(n.store,n.session,STORE_FILES[key],out)
 print(json.dumps(out,sort_keys=True,separators=(",",":")));return 0
if __name__=="__main__":raise SystemExit(main())
