from pathlib import Path

DOC = Path('docs/runtime_recovery_activation_simulation_readiness_review.md')


def test_readiness_review_exists():
    assert DOC.exists()


def test_readiness_review_pins_disabled_simulation_chain():
    text = DOC.read_text(encoding='utf-8')
    required = [
        'Activation Simulation consumes only the closed Activation Gate Report',
        'does not open the gate',
        'does not grant activation',
        'does not invoke the binding endpoint',
        'does not register runtime hooks',
        'does not apply runtime binding',
        'does not emit events',
        'does not mutate runtime state',
        'does not execute Recovery',
        'Final decision: GO',
        'Package 219',
    ]
    for item in required:
        assert item in text


def test_readiness_review_does_not_authorize_runtime_activation():
    text = DOC.read_text(encoding='utf-8')
    forbidden_phrases = [
        'authorizes runtime hook registration',
        'authorizes runtime binding application',
        'authorizes Recovery execution',
        'authorizes Runtime mainline activation',
    ]
    for phrase in forbidden_phrases:
        assert phrase not in text
