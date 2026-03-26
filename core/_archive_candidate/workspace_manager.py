from pathlib import Path

WORKSPACE_ROOT = Path("E:/zero_workspace").resolve()


def ensure_workspace():
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


def get_workspace_root():
    ensure_workspace()
    return WORKSPACE_ROOT


def safe_path(relative_path: str):
    root = get_workspace_root()
    target = (root / relative_path).resolve()

    if not str(target).startswith(str(root)):
        raise Exception("Access outside workspace is not allowed")

    return target