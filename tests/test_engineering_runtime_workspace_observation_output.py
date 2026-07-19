import json, os, sys, subprocess, pytest
from pathlib import Path
from core.engineering.engineering_runtime_workspace_adapter_protocol import *
from core.engineering.engineering_runtime_workspace_adapter_registry import *
from core.engineering.engineering_runtime_workspace_root_admission import admit_workspace_root
from core.engineering.engineering_runtime_workspace_read_scope import create_read_scope, validate_scope_request
from core.engineering.engineering_runtime_workspace_path_resolution import resolve_workspace_path
from tests.runtime_workspace_adapter_fixtures import make_workspace, run_pipeline

def test_descriptor_registry_deterministic_duplicate_lookup():
 assert build_workspace_adapter_descriptor()==build_workspace_adapter_descriptor()
 r=default_workspace_adapter_registry(); assert r.snapshot()==default_workspace_adapter_registry().snapshot(); assert r.lookup(ADAPTER_ID,'1') is not None; assert r.lookup(ADAPTER_ID,'2') is None
 with pytest.raises(ValueError): WorkspaceAdapterRegistry((r.lookup(ADAPTER_ID,'1'),r.lookup(ADAPTER_ID,'1')))

def test_admission_rejects(tmp_path):
 root=make_workspace(tmp_path); assert admit_workspace_root(root,'ws')['admitted']
 assert not admit_workspace_root(root/'missing','ws')['admitted']; assert not admit_workspace_root(root/'a.txt','ws')['admitted']; assert not admit_workspace_root(Path('/'),'ws')['admitted']

def test_paths_scope_and_resolution(tmp_path):
 root=make_workspace(tmp_path); adm=admit_workspace_root(root,'ws'); scope=create_read_scope(allowed_relative_path_prefixes=('dir',),allowed_operations=('path_exists',))
 for bad in ('/x','../x','//srv/x','C:/x','a\x00b','a//b'):
  art,_=resolve_workspace_path(adm,bad); assert not art['resolved']
 assert validate_scope_request(scope,'read_text','dir/z.txt')[1]==['operation_not_allowed']
 assert 'path_outside_workspace' in validate_scope_request(scope,'path_exists','a.txt')[1]
 assert 'scope_expansion' in validate_scope_request(create_read_scope(max_read_bytes=3),'read_text','a.txt',{'max_read_bytes':4})[1]
 if hasattr(os,'symlink'):
  os.symlink('/tmp', root/'link'); art,_=resolve_workspace_path(adm,'link/x'); assert 'symlink_disallowed' in art['reason_codes']

def test_operations_and_boundaries(tmp_path):
 root=make_workspace(tmp_path)
 assert run_pipeline(root,'workspace_exists')[7]['result_status']=='succeeded'
 assert run_pipeline(root,'path_exists','a.txt')[7]['output']['payload']['exists'] is True
 assert run_pipeline(root,'path_exists','missing')[7]['output']['payload']['exists'] is False
 assert run_pipeline(root,'path_kind','dir')[7]['output']['payload']['path_kind']=='directory'
 (root/'c.txt').write_text('c',encoding='utf-8')
 out=run_pipeline(root,'list_directory')[7]['output']['payload']; assert [e['name'] for e in out['entries']]==sorted(e['name'] for e in out['entries']); assert all('/' not in e['name'] for e in out['entries'])
 assert run_pipeline(root,'list_directory',params={'max_directory_entries':1})[7]['result_status']=='failed'
 assert run_pipeline(root,'read_text','a.txt')[7]['output']['payload']['content']=='hello'
 assert run_pipeline(root,'read_text','b.bin')[7]['failure']['failure_code']=='invalid_utf8'
 assert run_pipeline(root,'read_text','a.txt',scope=create_read_scope(max_read_bytes=2))[7]['failure']['failure_code']=='file_too_large'
 assert run_pipeline(root,'file_sha256','a.txt')[7]['output']['payload']['sha256']
 assert run_pipeline(root,'file_sha256','a.txt',scope=create_read_scope(max_hash_bytes=2))[7]['failure']['failure_code']=='file_too_large'
 meta=run_pipeline(root,'file_metadata','a.txt')[7]['output']['payload']; assert set(meta)=={'relative_path','path_kind','size_bytes','readable','symlink'}
 dumped=json.dumps(run_pipeline(root,'file_metadata','a.txt')[7]); assert str(root) not in dumped and 'traceback' not in dumped.lower()

def test_cancel_failure_verification_evidence_closure_flags(tmp_path):
 root=make_workspace(tmp_path); p=run_pipeline(root,'read_text','a.txt',cancel=True); assert p[6]['controlled_execution_status']=='cancelled' and not p[6]['adapter_invoked']; assert p[7]['result_status']=='cancelled'; assert p[10]['closure_status']=='closed'
 p=run_pipeline(root,'read_text','b.bin'); assert p[7]['result_status']=='failed'; assert p[10]['closure_status']=='closed'; assert 'hello' not in json.dumps(p[9]); assert str(root) not in json.dumps(p[9])
 p=run_pipeline(root,'read_text','a.txt'); assert p[8]['verification_status']=='verified'; assert p[10]['closure_status']=='closed'
 for k,v in p[6].items():
  if k.endswith('_performed') or k.endswith('_created') or k.endswith('_invoked'):
   if k not in ('filesystem_read_performed','adapter_invoked'): assert v is False
 bad=dict(p[7]); bad['submission_id']='x'; from core.engineering.engineering_runtime_workspace_execution_verification import verify_workspace_execution; assert verify_workspace_execution(p[3],p[4],p[6],bad)['verification_status']=='invalid'

def test_cli(tmp_path):
 root=make_workspace(tmp_path); cmd=[sys.executable,'cli/zero_engineering_runtime_workspace_adapter.py','pipeline','--workspace-root',str(root),'--json',json.dumps({'operation':'read_text','relative_path':'a.txt'})]
 a=subprocess.check_output(cmd,text=True); b=subprocess.check_output(cmd,text=True); assert a==b; obj=json.loads(a); assert obj['result']['result_status']=='succeeded'; assert str(root) not in a
 fail=subprocess.check_output([sys.executable,'cli/zero_engineering_runtime_workspace_adapter.py','pipeline','--workspace-root',str(root),'--json',json.dumps({'operation':'read_text','relative_path':'../x'})],text=True); assert json.loads(fail)['result']['result_status']=='rejected'
