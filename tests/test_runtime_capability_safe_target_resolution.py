from core.runtime.runtime_capability_safe_target_resolution import build_capability_safe_target_resolution as build
from tests.test_runtime_capability_read_only_adapter_admission import admission
from tests.test_runtime_capability_bounded_observation_request import observation_request
def resolution(root,target="target.txt",kind="existence"):return build(admission(root),observation_request(kind,target,root))
def test_resolution_regular_missing_and_incompatible(tmp_path):
 p=tmp_path/"target.txt";p.touch();x=resolution(tmp_path);assert x["resolution_status"]=="resolved" and x["containment_verified"]
 assert resolution(tmp_path,"missing")["resolution_status"]=="missing"
 assert resolution(tmp_path,"target.txt","directory_listing")["resolution_status"]=="blocked"
 assert resolution(tmp_path/"missing")["resolution_status"]=="failed"
def test_symlink_blocked_when_available(tmp_path):
 target=tmp_path/"target";target.touch();link=tmp_path/"link"
 try:link.symlink_to(target)
 except OSError:return
 assert resolution(tmp_path,"link")["resolution_status"]=="blocked"
