from core.engineering.engineering_runtime_operator_pause import *
def test_operator_is_not_inferred(): assert build_engineering_runtime_operator_pause({})["status"]=="awaiting_input"
def test_automated_approval_rejected(): assert build_engineering_runtime_operator_pause({},[{"decision":"approved","operator_id":"x","automated_decision":True}])["status"]=="invalid"
