from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

from .overlay_v7332 import _zero_v7332_constitutional_boundary_payload, _zero_v7332_constitutional_metadata, _zero_v7332_is_constitutional_block, _zero_v7332_mark_constitutional_boundary, _zero_v7332_repairable_decision
from .overlay_v7333 import _zero_v7333_attach_governed_continuation, _zero_v7333_governed_continuation_summary, _zero_v7333_repairable_decision
from .overlay_v7334 import _zero_v7334_attach_self_repair_summary, _zero_v7334_governed_self_repair_summary, _zero_v7334_repairable_decision
from .overlay_v7335 import _zero_v7335_attach_controlled_mutation_bridge, _zero_v7335_controlled_mutation_bridge_summary, _zero_v7335_has_approved_execution_authority, _zero_v7335_is_repair_work, _zero_v7335_repairable_decision
from .overlay_v7336 import _zero_v7336_attach_verified_mutation_continuation, _zero_v7336_repairable_decision, _zero_v7336_verified_mutation_continuation_summary


def _zero_v7332_repairable_decision(task: Dict[str, Any], original: Any, scheduler: Any) -> Tuple[bool, str]:
    if _zero_v7332_is_constitutional_block(task):
        return False, "constitutional block requires governed review"
    return original(scheduler, task)


