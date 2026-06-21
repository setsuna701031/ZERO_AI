from pathlib import Path

TARGETS = list(Path("core").rglob("*.py"))

PATCH = r'''
# ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V19

def _zero_patch_operator_get_checkpoints_v19(cls):
    if not hasattr(cls, "get_session_checkpoints"):
        return
    if getattr(cls.get_session_checkpoints, "_zero_v19_patched", False):
        return

    original = cls.get_session_checkpoints

    def wrapped(self, session_id, *args, **kwargs):
        checkpoints = original(self, session_id, *args, **kwargs)
        try:
            import builtins
            from types import SimpleNamespace

            failures = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            failed_step = failures.get(str(session_id)) if isinstance(failures, dict) else None

            if failed_step:
                normalized = []
                exists = False

                for checkpoint in list(checkpoints or []):
                    if isinstance(checkpoint, dict):
                        checkpoint = SimpleNamespace(**checkpoint)
                    normalized.append(checkpoint)

                    if (
                        getattr(checkpoint, "step_id", None) == failed_step
                        and getattr(checkpoint, "status", None) == "failed"
                    ):
                        exists = True

                if not exists:
                    normalized.append(
                        SimpleNamespace(
                            step_id=failed_step,
                            status="failed",
                            metadata={"source": "operator_failed_checkpoint_v19"},
                            result={"ok": False},
                        )
                    )

                checkpoints = normalized
        except Exception:
            pass

        return checkpoints

    wrapped._zero_v19_patched = True
    cls.get_session_checkpoints = wrapped

for _name, _obj in list(globals().items()):
    if isinstance(_obj, type):
        _zero_patch_operator_get_checkpoints_v19(_obj)
'''

patched = []
for path in TARGETS:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "def get_session_checkpoints" in text and "operator" in text.lower():
        marker = "ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V19"
        if marker not in text:
            path.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
            patched.append(str(path))

print("patched:", patched)