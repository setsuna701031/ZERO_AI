from pathlib import Path

TARGETS = list(Path("core").rglob("*.py"))

PATCH = r'''
# ZERO_PATCH_OPERATOR_STATUS_RESUMABLE_V17

def _zero_patch_operator_get_session_status_v17(cls):
    if not hasattr(cls, "get_session"):
        return
    if getattr(cls.get_session, "_zero_v17_patched", False):
        return

    original = cls.get_session

    def wrapped(self, session_id, *args, **kwargs):
        session = original(self, session_id, *args, **kwargs)

        try:
            failed_step = None
            if isinstance(session, dict):
                failed_step = session.get("failed_step")
            else:
                failed_step = getattr(session, "failed_step", None)

            if failed_step:
                if isinstance(session, dict):
                    session["status"] = "resumable"
                else:
                    setattr(session, "status", "resumable")
        except Exception:
            pass

        return session

    wrapped._zero_v17_patched = True
    cls.get_session = wrapped

for _name, _obj in list(globals().items()):
    if isinstance(_obj, type):
        _zero_patch_operator_get_session_status_v17(_obj)
'''

patched = []
for path in TARGETS:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "def get_session" in text and "operator" in text.lower():
        marker = "ZERO_PATCH_OPERATOR_STATUS_RESUMABLE_V17"
        if marker not in text:
            path.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
            patched.append(str(path))

print("patched:", patched)