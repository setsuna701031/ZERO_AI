from core.system.llm_client import LocalLLMClient

c = LocalLLMClient()
print(c.get_runtime_info())
print(c.generate_general("請直接回答，不要顯示思考過程。1+1=?"))