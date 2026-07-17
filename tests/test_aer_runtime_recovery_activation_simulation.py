import inspect

from core.runtime.aer_runtime_recovery_activation_gate_report import (
    RECOVERY_ACTIVATION_GATE_DECISION_REPORT_CONTRACT,
)
from core.runtime.aer_runtime_recovery_activation_simulation import (
    RECOVERY_ACTIVATION_SIMULATION_DENIED_CAPABILITIES,
    RECOVERY_ACTIVATION_SIMULATION_REPORT_CONTRACT,
    __all__,
    prepare_recovery_activation_simulation,
)


def _gate_report():
    return {
        'contract': RECOVERY_ACTIVATION_GATE_DECISION_REPORT_CONTRACT,
        'prepared': True,
        'blocked': False,
        'denied': False,
        'status': 'prepared',
        'gate_report_prepared': True,
        'activation_state': 'disabled',
        'gate_state': 'closed',
        'gate_open': False,
        'gate_enabled': False,
        'activation_granted': False,
        'activation_allowed': False,
        'recovery_enabled': False,
        'binding_disabled': True,
        'binding_applied': False,
        'runtime_hook_registered': False,
        'runtime_mainline_wiring_enabled': False,
        'endpoint_invoked': False,
        'event_emitted': False,
        'kill_switch_required': True,
        'admission_required': True,
        'single_entry_only': True,
        'activation_report_only': True,
        'executes_recovery': False,
        'side_effects_performed': False,
        'plain_dict_only': True,
    }


def test_public_surface_is_strict():
    assert __all__ == [
        'RECOVERY_ACTIVATION_SIMULATION_REPORT_CONTRACT',
        'RECOVERY_ACTIVATION_SIMULATION_ALLOWED_STATUSES',
        'RECOVERY_ACTIVATION_SIMULATION_DENIED_CAPABILITIES',
        'prepare_recovery_activation_simulation',
    ]


def test_prepare_activation_simulation_is_disabled_and_plain_dict():
    report = prepare_recovery_activation_simulation(_gate_report(), simulation_id='sim-1')
    assert report['contract'] == RECOVERY_ACTIVATION_SIMULATION_REPORT_CONTRACT
    assert report['simulation_id'] == 'sim-1'
    assert report['prepared'] is True
    assert report['blocked'] is False
    assert report['denied'] is False
    assert report['status'] == 'prepared'
    assert report['simulation_declared'] is True
    assert report['simulation_only'] is True
    assert report['simulation_applied'] is False
    assert report['simulation_result'] == 'not_applied'
    assert report['activation_state'] == 'disabled'
    assert report['gate_state'] == 'closed'
    assert report['gate_open'] is False
    assert report['activation_granted'] is False
    assert report['activation_allowed'] is False
    assert report['recovery_enabled'] is False
    assert report['binding_disabled'] is True
    assert report['binding_applied'] is False
    assert report['runtime_hook_registered'] is False
    assert report['runtime_mainline_wiring_enabled'] is False
    assert report['endpoint_invoked'] is False
    assert report['event_emitted'] is False
    assert report['activation_gate_report_reference'] == _gate_report()
    assert report['executes_recovery'] is False
    assert report['side_effects_performed'] is False
    assert report['plain_dict_only'] is True


def test_invalid_gate_report_blocks_simulation():
    report = prepare_recovery_activation_simulation({'contract': 'wrong'})
    assert report['prepared'] is False
    assert report['blocked'] is True
    assert report['denied'] is False
    assert report['status'] == 'blocked'
    assert report['activation_gate_report_reference'] == {}
    assert 'missing or incompatible' in report['reason']


def test_simulation_apply_request_is_denied():
    report = prepare_recovery_activation_simulation(_gate_report(), request_simulation_apply=True)
    assert report['prepared'] is False
    assert report['blocked'] is False
    assert report['denied'] is True
    assert report['status'] == 'denied'
    assert 'prohibited' in report['reason']


def test_denied_capabilities_include_runtime_surfaces():
    for capability in [
        'recovery_execution',
        'recovery_enablement',
        'runtime_hook_registration',
        'runtime_binding_application',
        'endpoint_invocation',
        'activation_gate_opening',
        'activation_grant',
        'event_emission',
        'scheduler_call',
        'operator_call',
        'dispatcher_call',
        'supervisor_call',
        'native_runtime_call',
        'runtime_mutation',
        'file_io',
    ]:
        assert capability in RECOVERY_ACTIVATION_SIMULATION_DENIED_CAPABILITIES


def test_module_does_not_import_runtime_surfaces_or_io():
    source = inspect.getsource(__import__('core.runtime.aer_runtime_recovery_activation_simulation', fromlist=['x']))
    forbidden = ['import core.tasks', 'import core.runtime.scheduler', 'import subprocess', 'open(', 'Path(', 'write_text']
    for token in forbidden:
        assert token not in source
