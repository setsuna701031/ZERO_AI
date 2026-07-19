from __future__ import annotations
from .engineering_workspace_mutation_executor_common import *
def normalize_failure(code,artifact=None):
    c=code if code in FAILURE_CODES else 'internal_execution_failure'
    return finish('wsmut-failure','failure','failure_id',{'status':'failed','failure_code':c,'artifact_fingerprint':(artifact or {}).get('fingerprint'),'reason_codes':[c]})
