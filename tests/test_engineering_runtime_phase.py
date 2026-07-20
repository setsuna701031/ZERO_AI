from core.engineering.engineering_runtime_phase import *
def test_monotonic_phase():
 p=build_engineering_runtime_phase("s"); assert transition_phase(p,"session_admitted")["status"]=="valid"; assert transition_phase(p,"analysis_coordinated")["status"]=="invalid"
