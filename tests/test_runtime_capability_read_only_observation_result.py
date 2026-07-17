from hashlib import sha256
import io
from core.runtime.runtime_capability_read_only_observation_result import build_capability_read_only_observation_result as build
from tests.test_runtime_capability_read_only_adapter_admission import admission
from tests.test_runtime_capability_bounded_observation_request import observation_request
from tests.test_runtime_capability_safe_target_resolution import resolution
def result(root,target="target.txt",kind="existence"):return build(admission(root),observation_request(kind,target,root),resolution(root,target,kind))
def test_observations_bounded_and_read_only(tmp_path):
 p=tmp_path/"target.txt"
 with io.open(p,"wb") as h:h.write("你好".encode())
 with io.open(p,"rb") as h:before=h.read()
 assert result(tmp_path,kind="text_preview")["observation"]["preview"]=="你好"
 assert result(tmp_path,kind="sha256")["observation"]["digest"]==sha256(before).hexdigest()
 with io.open(p,"rb") as h:after=h.read()
 assert after==before and result(tmp_path)["side_effects_performed"]==[]
def test_invalid_utf8_and_directory_listing(tmp_path):
 with io.open(tmp_path/"target.txt","wb") as h:h.write(b"\xff")
 assert result(tmp_path,kind="text_preview")["result_status"]=="not_observed"
 (tmp_path/"b").touch();(tmp_path/"a").touch();x=result(tmp_path,".","directory_listing");assert [e["name"] for e in x["observation"]["entries"]]==["a","b","target.txt"]
