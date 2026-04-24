from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MAIN_PATH = REPO_ROOT / "main.py"
PERSONA_RUNTIME_PATH = REPO_ROOT / "ui" / "persona_runtime_window.py"
PERSONA_ASSET_DIR = REPO_ROOT / "assets" / "persona" / "zero_v1"
PROFILE_PATH = PERSONA_ASSET_DIR / "profile.json"
CIRCUIT_BG_PATH = PERSONA_ASSET_DIR / "circuit_bg.png"
IDLE_OPEN_PATH = PERSONA_ASSET_DIR / "idle_open.png"
IDLE_HALF_PATH = PERSONA_ASSET_DIR / "idle_half.png"
IDLE_CLOSED_PATH = PERSONA_ASSET_DIR / "idle_closed.png"


def fail(message: str) -> int:
    print(f"[persona-runtime-entry-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[persona-runtime-entry-smoke] PASS: {message}")


def require_file(path: Path, label: str) -> bool:
    if not path.exists():
        print(f"[persona-runtime-entry-smoke] missing {label}: {path}")
        return False

    if not path.is_file():
        print(f"[persona-runtime-entry-smoke] not a file {label}: {path}")
        return False

    pass_step(f"{label} exists")
    return True


def require_text_contains(path: Path, needles: List[str], label: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[persona-runtime-entry-smoke] cannot read {label}: {path}")
        print(f"[persona-runtime-entry-smoke] error: {exc}")
        return False

    missing = [needle for needle in needles if needle not in text]
    if missing:
        print(f"[persona-runtime-entry-smoke] {label} missing required text:")
        for item in missing:
            print(f"  - {item}")
        return False

    pass_step(f"{label} contains required entry markers")
    return True


def import_module_from_path(module_name: str, path: Path) -> bool:
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            print(f"[persona-runtime-entry-smoke] cannot create import spec: {path}")
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as exc:
        print(f"[persona-runtime-entry-smoke] import failed: {path}")
        print(f"[persona-runtime-entry-smoke] error: {exc}")
        return False

    pass_step(f"module import ok: {path.relative_to(REPO_ROOT)}")
    return True


def validate_visual_profile_load() -> bool:
    try:
        from core.persona.visual_profile import load_default_visual_profile

        profile = load_default_visual_profile()
    except Exception as exc:
        print("[persona-runtime-entry-smoke] visual profile load failed")
        print(f"[persona-runtime-entry-smoke] error: {exc}")
        return False

    required_attrs = [
        "visual_id",
        "render_mode",
        "resolve_image_for_state",
        "resolve_blink_frame",
    ]

    missing_attrs = [name for name in required_attrs if not hasattr(profile, name)]
    if missing_attrs:
        print("[persona-runtime-entry-smoke] visual profile missing attributes:")
        for name in missing_attrs:
            print(f"  - {name}")
        return False

    pass_step(f"visual profile loaded: {profile.visual_id}")
    return True


def main() -> int:
    print("[persona-runtime-entry-smoke] START")
    print(f"[persona-runtime-entry-smoke] repo: {REPO_ROOT}")

    checks = [
        require_file(MAIN_PATH, "main.py"),
        require_file(PERSONA_RUNTIME_PATH, "persona runtime window"),
        require_file(PROFILE_PATH, "persona visual profile"),
        require_file(CIRCUIT_BG_PATH, "persona circuit background"),
        require_file(IDLE_OPEN_PATH, "persona idle open image"),
        require_file(IDLE_HALF_PATH, "persona idle half image"),
        require_file(IDLE_CLOSED_PATH, "persona idle closed image"),
        require_text_contains(
            MAIN_PATH,
            [
                "persona-runtime",
                "run_persona_runtime_window",
                "PERSONA_RUNTIME_WINDOW_PATH",
            ],
            "main.py",
        ),
        require_text_contains(
            PERSONA_RUNTIME_PATH,
            [
                "class PersonaRuntimeWindow",
                "ENABLE_BLINK = False",
                "run execution-demo",
                "circuit_bg.png",
            ],
            "persona runtime window",
        ),
        validate_visual_profile_load(),
        import_module_from_path("zero_persona_runtime_window_smoke", PERSONA_RUNTIME_PATH),
    ]

    if not all(checks):
        return fail("one or more persona runtime entry checks failed")

    print("[persona-runtime-entry-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())