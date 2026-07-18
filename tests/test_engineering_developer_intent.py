import pytest
from core.engineering.developer_intent import parse_developer_intent
def test_bilingual_deterministic_normalization_and_intents():
 a=parse_developer_intent("  分析 repository，找出 pytest 卡住原因並修正  ");b=parse_developer_intent("分析 repository,找出 pytest 卡住原因並修正")
 assert a==b and a["status"]=="accepted" and a["intent_types"]==sorted(set(a["intent_types"])) and {"inspect_repository","diagnose_failure","repair_defect","validate_change"}<=set(a["intent_types"])
 assert parse_developer_intent("Explain code and add tests")["status"]=="accepted"
def test_empty_oversized_nul_and_clarification():
 assert parse_developer_intent("")["status"]=="invalid" and parse_developer_intent("x"*8001)["status"]=="invalid" and parse_developer_intent("fix\0bug")["status"]=="invalid"
 assert parse_developer_intent("請幫我看看")["status"]=="needs_clarification"
