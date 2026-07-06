from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

BRIDGE_SOURCE = Path(__file__).with_name("runtime_operator_scheduler_bridge.py").read_text(
    encoding="utf-8"
)
TEST_SOURCE = Path(__file__).with_name("test_runtime_operator_scheduler_bridge_seal.py").read_text(
    encoding="utf-8"
)

bridge_path = ROOT / "core" / "runtime" / "runtime_operator_scheduler_bridge.py"
test_path = ROOT / "tests" / "test_runtime_operator_scheduler_bridge_seal.py"
bridge_path.parent.mkdir(parents=True, exist_ok=True)
test_path.parent.mkdir(parents=True, exist_ok=True)
bridge_path.write_text(BRIDGE_SOURCE, encoding="utf-8")
test_path.write_text(TEST_SOURCE, encoding="utf-8")

print("runtime operator scheduler bridge applied")
