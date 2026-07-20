from core.engineering.engineering_runtime_resume import determine_resume
def test_resume_rejects_ambiguous_store(): assert determine_resume({}, {})["status"]=="invalid"
