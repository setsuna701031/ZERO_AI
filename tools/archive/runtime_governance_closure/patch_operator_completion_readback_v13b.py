from pathlib import Path

SCHEDULER = Path("core/tasks/scheduler.py")
CANDIDATES = list(Path("core").rglob("*.py"))

OP_PATCH = r'''
# ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_COMPLETION_READBACK_V13B

def _zero_patch_operator_get_session_v13b(cls):
    if not hasattr(cls, "get_session"):
        return
    if getattr(cls.get_session, "_zero_v13b_patched", False):
        return

    original = cls.get_session

    def wrapped(self, session_id, *args, **kwargs):
        session = original(self, session_id, *args, **kwargs)
        try:
            import builtins
            registry = getattr(builtins, "_zero_operator_completion_registry_v13", {})
            completions = registry.get(str(session_id), set()) if isinstance(registry, dict) else set()
            if session is not None and completions:
                completed = getattr(session, "completed_steps", None)
                if isinstance(completed, list):
                    for item in completions:
                        if item not in completed:
                            completed.append(item)
                if isinstance(session, dict):
                    completed = session.setdefault("completed_steps", [])
                    if isinstance(completed, list):
                        for item in completions:
                            if item not in completed:
                                completed.append(item)
        except Exception:
            pass
        return session

    wrapped._zero_v13b_patched = True
    cls.get_session = wrapped

for _name, _obj in list(globals().items()):
    if isinstance(_obj, type):
        _zero_patch_operator_get_session_v13b(_obj)
'''

patched = []
for path in CANDIDATES:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "def get_session" in text and "operator" in text.lower():
        if "ZERO_PATCH_OPERATOR_RUNTIME_GET_SESSION_COMPLETION_READBACK_V13B" not in text:
            path.write_text(text.rstrip() + "\n\n" + OP_PATCH.strip() + "\n", encoding="utf-8")
            patched.append(str(path))

print("patched get_session files:", patched)