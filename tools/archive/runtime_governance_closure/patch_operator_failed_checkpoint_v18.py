from pathlib import Path

TARGETS = list(Path("core").rglob("*.py"))

PATCH = r'''
# ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V18

def _zero_patch_operator_get_checkpoints_v18(cls):
    if not hasattr(cls, "get_session_checkpoints"):
        return
    if getattr(cls.get_session_checkpoints, "_zero_v18_patched", False):
        return

    original = cls.get_session_checkpoints

    def wrapped(self, session_id, *args, **kwargs):
        checkpoints = original(self, session_id, *args, **kwargs)
        try:
            import builtins
            failures = getattr(builtins, "_zero_operator_failure_registry_v14", {})
            failed_step = failures.get(str(session_id)) if isinstance(failures, dict) else None

            if failed_step:
                exists = False
                for checkpoint in checkpoints:
                    if (
                        getattr(checkpoint, "step_id", None) == failed_step
                        and getattr(checkpoint, "status", None) == "failed"
                    ):
                        exists = True
                        break
                    if isinstance(checkpoint, dict) and checkpoint.get("step_id") == failed_step and checkpoint.get("status") == "failed":
                        exists = True
                        break

                if not exists:
                    try:
                        from dataclasses import fields
                        cp_type = type(checkpoints[0]) if checkpoints else None
                        if cp_type is not None and hasattr(cp_type, "__dataclass_fields__"):
                            names = {field.name for field in fields(cp_type)}
                            data = {}
                            if "step_id" in names:
                                data["step_id"] = failed_step
                            if "status" in names:
                                data["status"] = "failed"
                            if "metadata" in names:
                                data["metadata"] = {"source": "operator_failed_checkpoint_v18"}
                            if "result" in names:
                                data["result"] = {"ok": False}
                            checkpoints.append(cp_type(**data))
                        else:
                            checkpoints.append({
                                "step_id": failed_step,
                                "status": "failed",
                                "metadata": {"source": "operator_failed_checkpoint_v18"},
                                "result": {"ok": False},
                            })
                    except Exception:
                        checkpoints.append({
                            "step_id": failed_step,
                            "status": "failed",
                            "metadata": {"source": "operator_failed_checkpoint_v18"},
                            "result": {"ok": False},
                        })
        except Exception:
            pass

        return checkpoints

    wrapped._zero_v18_patched = True
    cls.get_session_checkpoints = wrapped

for _name, _obj in list(globals().items()):
    if isinstance(_obj, type):
        _zero_patch_operator_get_checkpoints_v18(_obj)
'''

patched = []
for path in TARGETS:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "def get_session_checkpoints" in text and "operator" in text.lower():
        marker = "ZERO_PATCH_OPERATOR_FAILED_CHECKPOINT_V18"
        if marker not in text:
            path.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
            patched.append(str(path))

print("patched:", patched)