from __future__ import annotations
import re
from typing import Any
from core.engineering.engineering_intake_common import identified,normalize_request,passive_boundary
SCHEMA="zero.engineering.developer_intent.v1";STATUSES=frozenset({"accepted","needs_clarification","rejected","invalid"})
_RULES=(("add_feature",r"\b(add|implement|create)\b|新增|加入|實作"),("diagnose_failure",r"\b(diagnos|root cause|failure|failing|stuck|hang)\b|診斷|原因|卡住|失敗"),("explain_code",r"\b(explain|understand)\b|解釋|說明"),("inspect_repository",r"\b(inspect|analy[sz]e|repository|repo)\b|分析|檢查|儲存庫|程式庫"),("refactor_bounded",r"\brefactor\b|重構"),("repair_defect",r"\b(fix|repair|bug|defect)\b|修正|修復|錯誤"),("update_tests",r"\b(update|add|write).{0,12}\btests?\b|更新測試|新增測試"),("validate_change",r"\b(validate|verify|test|pytest)\b|驗證|測試"))
def parse_developer_intent(request:Any)->dict[str,Any]:
    try:text=normalize_request(request)
    except (TypeError,ValueError):
        text="";status="invalid";types=[];reasons=["invalid_developer_request"]
    else:
        types=sorted({name for name,pattern in _RULES if re.search(pattern,text,re.I)})
        status="accepted" if types else "needs_clarification";reasons=["developer_intent_accepted" if types else "engineering_action_unclear"]
    validation=["requested_validation"] if any(x in types for x in ("update_tests","validate_change","diagnose_failure")) else []
    constraints=["bounded_scope","no_unapproved_mutation","controlled_execution_required"]
    base={"schema":SCHEMA,"normalized_request":text,"intent_types":types,"requested_outcomes":types.copy(),"explicit_constraints":constraints,"requested_validation":validation,"scope_hints":["current_repository"],"risk_flags":["mutation_intent"] if any(x in types for x in ("add_feature","repair_defect","refactor_bounded","update_tests")) else [],"status":status,"reasons":reasons,"boundary":passive_boundary("natural_language_intake")}
    return identified(base,"developer_intent_id","engineering-developer-intent-")
build_developer_intent=parse_developer_intent
__all__=["SCHEMA","STATUSES","build_developer_intent","parse_developer_intent"]
