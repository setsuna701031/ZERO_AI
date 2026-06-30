from __future__ import annotations

import sys
import unittest
from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeOwnershipContractTest(unittest.TestCase):
    def test_allowed_scheduler_queue_transition(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertTrue(
            can_access(
                RuntimeOwner.SCHEDULER,
                RuntimeResource.QUEUE_STATE,
                RuntimeAction.TRANSITION,
            )
        )

    def test_rejected_scheduler_execution_result_write(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertFalse(
            can_access(
                RuntimeOwner.SCHEDULER,
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )
        )

    def test_allowed_step_executor_execution_result_write(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertTrue(
            can_access(
                RuntimeOwner.STEP_EXECUTOR,
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )
        )

    def test_rejected_step_executor_queue_write(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertFalse(
            can_access(
                RuntimeOwner.STEP_EXECUTOR,
                RuntimeResource.QUEUE_STATE,
                RuntimeAction.WRITE,
            )
        )

    def test_allowed_orchestrator_dispatch(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertTrue(
            can_access(
                RuntimeOwner.ORCHESTRATOR,
                RuntimeResource.ORCHESTRATION_STATE,
                RuntimeAction.DISPATCH,
            )
        )

    def test_rejected_orchestrator_execution_result_write(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertFalse(
            can_access(
                RuntimeOwner.ORCHESTRATOR,
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )
        )

    def test_monitor_read_all_resources(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        for resource in RuntimeResource:
            with self.subTest(resource=resource):
                self.assertTrue(can_access(RuntimeOwner.MONITOR, resource, RuntimeAction.READ))

    def test_rejected_monitor_write_execution_result(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertFalse(
            can_access(
                RuntimeOwner.MONITOR,
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )
        )

    def test_repair_chain_can_write_repair_state(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertTrue(
            can_access(
                RuntimeOwner.REPAIR_CHAIN,
                RuntimeResource.REPAIR_STATE,
                RuntimeAction.WRITE,
            )
        )

    def test_rejected_repair_chain_queue_write(self) -> None:
        from core.runtime.runtime_ownership import RuntimeAction, RuntimeOwner, RuntimeResource, can_access

        self.assertFalse(
            can_access(
                RuntimeOwner.REPAIR_CHAIN,
                RuntimeResource.QUEUE_STATE,
                RuntimeAction.WRITE,
            )
        )

    def test_system_access_is_explicitly_scoped(self) -> None:
        from core.runtime.runtime_ownership import (
            RuntimeAction,
            RuntimeOwner,
            RuntimeResource,
            can_access,
            system_authority_rules,
        )

        allowed = {
            (resource, action)
            for resource in RuntimeResource
            for action in RuntimeAction
            if can_access(RuntimeOwner.SYSTEM, resource, action)
        }
        self.assertEqual(allowed, {(resource, action) for _, resource, action in system_authority_rules()})
        self.assertIn((RuntimeResource.RUNTIME_EVENT, RuntimeAction.EMIT), allowed)
        self.assertNotIn((RuntimeResource.QUEUE_STATE, RuntimeAction.WRITE), allowed)
        self.assertNotIn((RuntimeResource.ORCHESTRATION_STATE, RuntimeAction.DISPATCH), allowed)

    def test_assert_runtime_authority_raises_runtime_authority_error(self) -> None:
        from core.runtime.runtime_ownership import (
            RuntimeAction,
            RuntimeAuthorityError,
            RuntimeOwner,
            RuntimeResource,
            assert_runtime_authority,
        )

        with self.assertRaises(RuntimeAuthorityError):
            assert_runtime_authority(
                RuntimeOwner.SCHEDULER,
                RuntimeResource.EXECUTION_RESULT,
                RuntimeAction.WRITE,
            )


if __name__ == "__main__":
    unittest.main()
