import json,sys
from pathlib import Path
from cli.zero_engineering_runtime_adapter_preparation import run, main
from tests.runtime_adapter_preparation_fixtures import pipeline2, request

def write(tmp_path,data): p=tmp_path/'in.json'; p.write_text(json.dumps(data),encoding='utf-8'); return str(p)
def test_all_supported_actions(tmp_path,capsys):
 req,pol,elig,desc,prep,clo,adm,h,s=pipeline2();
 actions=[('policy',{}),('request',{'admission':adm,'handoff':h,'session':s,'requested_adapter_id':'adapter.one','requested_adapter_version':'1.0.0','requested_operation':{'operation_type':'observe','target':'repo'},'requested_scope':{'files':['a']},'input_bindings':{'artifact_ref':'opaque-artifact'},'expected_output_contract':{'format':'json','schema_ref':'opaque-schema'},'resource_constraints':{'cpu_units':1,'memory_mb':128},'environment_constraints':{'network':'disabled','filesystem':'read_only'},'timeout_constraints':{'seconds':30,'finite':True,'perpetual':False},'authority_reference':'opaque-authority-ref','authority_constraints':req['authority_constraints']}),('eligibility',{'request':req,'policy':pol,'admission':adm,'handoff':h,'session':s}),('descriptor',{'request':req,'eligibility':elig,'admission':adm}),('prepare',{'request':req,'policy':pol,'eligibility':elig,'descriptor':desc}),('closure',{'request':req,'policy':pol,'eligibility':elig,'descriptor':desc,'preparation':prep})]
 for action,data in actions:
  out,code=run([action,write(tmp_path,data)] if action!='policy' else [action]); assert code==0; assert isinstance(out,dict)
 out,code=run(['validate','--kind','request',write(tmp_path,{'artifact':req})]); assert code==0 and out['valid']
 out,code=run(['inspect','--kind','closure',write(tmp_path,{'artifact':clo})]); assert code==0 and out['valid']
 assert run(['policy'])[0]==run(['policy'])[0]
def test_errors_no_traceback(tmp_path,capsys):
 bad=tmp_path/'bad.json'; bad.write_text('{',encoding='utf-8'); out,code=run(['request',str(bad)]); assert code!=0 and out=={'error':'input_error'}
 out,code=run(['unknown']); assert code!=0 and out=={'error':'argument_error'}
 code=main(['policy']); captured=capsys.readouterr(); assert code==0 and captured.err=='' and 'Traceback' not in captured.out
