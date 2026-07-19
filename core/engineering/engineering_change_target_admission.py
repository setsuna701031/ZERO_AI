from __future__ import annotations
from typing import Any
from core.engineering.engineering_change_proposal_common import *
def admit_change_target(path:Any, policy:dict[str,Any])->dict[str,Any]:
 rs=[]; norm,prs=normalize_relative_path(path,policy.get('maximum_path_length',240),policy.get('maximum_segment_count',32)); rs+=prs
 prefixes=policy.get('allowed_relative_path_prefixes',[])
 if norm and prefixes and not prefix_allowed(norm,prefixes): rs.append('path_prefix_not_allowed')
 body={'requested_path':path if isinstance(path,str) and not path.startswith('/') and not path.startswith('\\') else '<redacted-invalid-path>','target_relative_path':norm,'status':'admitted' if not rs else ('invalid' if any(x.startswith('path_') for x in rs) else 'not_admitted'),'reason_codes':reasons(rs)}
 return artifact('ctgt',SCHEMAS['target_admission'],body,'target_admission_id')
