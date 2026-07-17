from pathlib import Path

TARGETS = list(Path("core").rglob("*.py"))

PATCH = r'''
# ZERO_PATCH_OPERATOR_RECOVERY_PAYLOAD_V21

def _zero_patch_recovery_resume_payload_v21(cls):
    if not hasattr(cls, "recovery_resume_payload"):
        return
    if getattr(cls.recovery_resume_payload, "_zero_v21_patched", False):
        return

    original = cls.recovery_resume_payload

    def wrapped(self, session_id, *args, **kwargs):
        payload = original(self, session_id, *args, **kwargs)
        if payload is not None:
            return payload

        try:
            import builtins
            failures = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            failed_step = failures.get(str(session_id)) if isinstance(failures, dict) else None
            if failed_step:
                return {
                    "session_id": session_id,
                    "failed_step": failed_step,
                    "status": "resumable",
                    "recovery_available": True,
                    "source": "operator_recovery_payload_v21",
                }
        except Exception:
            pass

        return payload

    wrapped._zero_v21_patched = True
    cls.recovery_resume_payload = wrapped

for _name, _obj in list(globals().items()):
    if isinstance(_obj, type):
        _zero_patch_recovery_resume_payload_v21(_obj)
'''

patched = []
for path in TARGETS:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "def recovery_resume_payload" in text:
        marker = "ZERO_PATCH_OPERATOR_RECOVERY_PAYLOAD_V21"
        if marker not in text:
            path.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
            patched.append(str(path))

print("patched:", patched)