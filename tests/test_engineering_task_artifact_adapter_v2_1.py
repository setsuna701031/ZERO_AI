from __future__ import annotations
import pytest
from core.engineering.engineering_task_artifact_adapter import ArtifactAdapterDescriptor, ArtifactAdapterError
from core.engineering.engineering_task_artifact_adapter_registry import ArtifactAdapterRegistry, ArtifactAdapterRegistryError, default_registry
from core.engineering.engineering_task_artifact_compatibility import build_compatibility_report
from core.engineering.engineering_mutation_transaction_common import finish


def test_descriptor_deterministic_and_material_changes():
    a=ArtifactAdapterDescriptor(phase='p',supported_schema='s',production_module='m',validator_entry_point='v',identity_field='id',accepted_statuses=('b','a'),linkage_fields=('z','a'))
    b=ArtifactAdapterDescriptor(phase='p',supported_schema='s',production_module='m',validator_entry_point='v',identity_field='id',accepted_statuses=('a','b'),linkage_fields=('a','z'))
    c=ArtifactAdapterDescriptor(phase='p2',supported_schema='s',production_module='m',validator_entry_point='v',identity_field='id',accepted_statuses=('a','b'),linkage_fields=('a','z'))
    assert a.adapter_id == b.adapter_id
    assert a.adapter_fingerprint == b.adapter_fingerprint
    assert a.adapter_fingerprint != c.adapter_fingerprint


def test_registry_lookup_unknown_and_duplicates():
    adapters=default_registry().list()
    reg=ArtifactAdapterRegistry([adapters[0]])
    assert reg.lookup(adapters[0].descriptor.phase, adapters[0].descriptor.supported_schema) is adapters[0]
    with pytest.raises(ArtifactAdapterRegistryError): reg.register(adapters[0])
    with pytest.raises(ArtifactAdapterRegistryError): reg.lookup('missing','schema')


def test_canonical_builder_result_rejects_lookalike_handoff():
    reg=default_registry()
    fake={'schema':'zero.engineering.mutation_executor_handoff.v1','status':'handed_off','handoff_id':'mutx-handoff-look','fingerprint':'0'*64}
    with pytest.raises(ArtifactAdapterError):
        reg.validate_artifact('executor_handoff', fake)


def test_builder_result_artifact_reference_is_bounded_and_exact():
    art=finish('mutx-handoff','mutation_executor_handoff','handoff_id',{'status':'handed_off'})
    ref=dict(default_registry().validate_artifact('executor_handoff', art))
    assert ref['schema']=='zero.engineering.task_artifact_reference.v1'
    assert ref['artifact_identity']==art['handoff_id']
    assert ref['artifact_fingerprint']==art['fingerprint']
    assert 'status' in ref['bounded_summary']
    assert 'ordered_transaction_steps' not in ref


def test_compatibility_report_labels_unsupported_and_structural_limitations():
    report=build_compatibility_report()
    assert report == build_compatibility_report()
    phases={r['phase']:r for r in report['adapters'] if r['health_status']=='unsupported'}
    assert 'closure' in phases
    structural={r['phase']:r for r in report['adapters'] if r['validation_level']=='structural_reference_only'}
    assert structural['candidate_selection']['orchestration_readiness']=='limited'
    levels={r['validation_level'] for r in report['adapters']}
    assert 'canonical_builder_result' in levels
