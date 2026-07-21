from __future__ import annotations
import argparse,json,os,tempfile
from pathlib import Path
from core.engineering.engineering_governed_explicit_pull_request import *
from core.engineering.engineering_governed_explicit_push import STORE_FILES as PUSH_FILES
from core.engineering.engineering_runtime_session_store import load_session_store,write_session_artifact

class JsonProviderAdapter:
 def __init__(self,path:str):self.path=Path(path);self.state=json.loads(self.path.read_text(encoding="utf-8"));self.provider_name=str(self.state["provider_name"])
 def inspect_repository(self,o,n):return self.state["repository"]
 def inspect_branches(self,o,n,s,t,c):
  branches=self.state.get("branches",{});sh=branches.get(s);th=branches.get(t);return {"source_exists":sh is not None,"target_exists":th is not None,"source_head":sh,"target_head":th,"source_commit_ancestor":sh==c,"has_changes":sh!=th}
 def find_equivalent_open_pull_request(self,o,n,s,t):return next((x for x in self.state.get("pull_requests",[]) if x.get("source_branch")==s and x.get("target_branch")==t and x.get("state")=="open"),None)
 def create_pull_request(self,r):
  prs=self.state.setdefault("pull_requests",[]);number=len(prs)+1;row={**r,"provider_pr_id":f"pr-{number}","pr_number":number,"pr_url":f"{self.state['repository']['web_url']}/pull/{number}","state":"open","merged":False,"closed":False,"source_head":self.state["branches"][r["source_branch"]],"target_head":self.state["branches"][r["target_branch"]]};prs.append(row)
  fd,tmp=tempfile.mkstemp(prefix=".provider-",suffix=".json",dir=self.path.parent)
  try:
   with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:json.dump(self.state,f,ensure_ascii=False,sort_keys=True,separators=(",",":"));f.write("\n");f.flush();os.fsync(f.fileno())
   os.replace(tmp,self.path)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
  return {"created":True,"status":"open","provider_pr_id":row["provider_pr_id"],"pr_number":number,"pr_url":row["pr_url"]}
 def inspect_pull_request(self,o,n,p):
  row=next((x for x in self.state.get("pull_requests",[]) if x.get("provider_pr_id")==p),{});return {**row,"repository_id":self.state["repository"]["repository_id"]}

def parser():
 p=argparse.ArgumentParser(prog="zero_engineering_runtime_pull_request",description="Explicit governed PR orchestration; create never runs by default.");p.add_argument("--store",required=True);p.add_argument("--session",required=True);p.add_argument("--provider-state",required=True);s=p.add_subparsers(dest="command",required=True)
 x=s.add_parser("prepare");
 for n in ("repository-provider","repository-id","repository-owner","repository-name","remote-name","remote-url","source-branch","target-branch","target-commit-sha","title","body"):x.add_argument("--"+n,required=n!="body",default="")
 s.add_parser("admit-provider");s.add_parser("verify-remote");x=s.add_parser("review");x.add_argument("artifact");x=s.add_parser("authorize");x.add_argument("artifact");s.add_parser("request-create");s.add_parser("create");s.add_parser("evidence");s.add_parser("verify-created");s.add_parser("close");s.add_parser("show")
 return p
def load_json(path):return json.loads(Path(path).read_text(encoding="utf-8"))
def main(argv=None):
 n=parser().parse_args(argv);b=load_session_store(n.store,n.session);a=JsonProviderAdapter(n.provider_state);c=n.command
 if c=="prepare":out=build_pr_preparation(b[PUSH_FILES["closure"]],repository_provider=n.repository_provider,repository_id=n.repository_id,repository_owner=n.repository_owner,repository_name=n.repository_name,remote_name=n.remote_name,remote_url=n.remote_url,source_branch=n.source_branch,target_branch=n.target_branch,target_commit_sha=n.target_commit_sha,title=n.title,body=n.body);key="preparation"
 elif c=="admit-provider":out=admit_repository_provider(b[STORE_FILES["preparation"]],a);key="admission"
 elif c=="verify-remote":out=verify_pr_remote(b[STORE_FILES["preparation"]],b[STORE_FILES["admission"]],a);key="remote"
 elif c=="review":out=review_pull_request(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],load_json(n.artifact));key="review"
 elif c=="authorize":out=authorize_pull_request(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["review"]],load_json(n.artifact));key="authorization"
 elif c=="request-create":out=build_pr_creation_request(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["review"]],b[STORE_FILES["authorization"]]);key="request"
 elif c=="create":
  used,out=execute_pull_request(b[PUSH_FILES["closure"]],b[STORE_FILES["preparation"]],b[STORE_FILES["admission"]],b[STORE_FILES["remote"]],b[STORE_FILES["review"]],b[STORE_FILES["authorization"]],b[STORE_FILES["request"]],a);write_session_artifact(n.store,n.session,STORE_FILES["authorization"],used);key="execution"
 elif c=="evidence":out=build_pr_evidence(b[STORE_FILES["preparation"]],b[STORE_FILES["review"]],b[STORE_FILES["authorization"]],b[STORE_FILES["execution"]],a);key="evidence"
 elif c=="verify-created":out=verify_created_pull_request(b[STORE_FILES["preparation"]],b[STORE_FILES["execution"]],b[STORE_FILES["evidence"]],a);key="post"
 elif c=="close":out=close_pull_request(b[STORE_FILES["preparation"]],b[STORE_FILES["remote"]],b[STORE_FILES["review"]],b[STORE_FILES["authorization"]],b[STORE_FILES["execution"]],b[STORE_FILES["evidence"]],b[STORE_FILES["post"]]);key="closure"
 else:out=inspect_pr_state(b);key=None
 if key:write_session_artifact(n.store,n.session,STORE_FILES[key],out)
 print(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(",",":")));return 0
if __name__=="__main__":raise SystemExit(main())
