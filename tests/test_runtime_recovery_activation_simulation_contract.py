from pathlib import Path

DOC = Path('docs/contracts/runtime/recovery_activation_simulation_v1.md')


def test_activation_simulation_contract_doc_exists():
    assert DOC.exists()


def test_activation_simulation_contract_pins_disabled_terms():
    text = DOC.read_text(encoding='utf-8')
    required = [
        'aer.runtime.recovery.activation_simulation.v1',
        'activation_state: disabled',
        'gate_state: closed',
        'simulation_applied: false',
        'simulation_result: not_applied',
        'executes_recovery: false',
        'side_effects_performed: false',
        'plain_dict_only: true',
    ]
    for item in required:
        assert item in text


def test_activation_simulation_contract_forbids_runtime_behavior():
    text = DOC.read_text(encoding='utf-8')
    forbidden_rules = [
        'execute Recovery',
        'enable Recovery',
        'open an activation gate',
        'grant activation',
        'register runtime hooks',
        'apply runtime binding',
        'invoke runtime endpoints',
        'emit events',
        'mutate runtime state',
    ]
    for rule in forbidden_rules:
        assert rule in text
