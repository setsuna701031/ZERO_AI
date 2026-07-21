import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engineering_natural_language_intake import INTENT_TERMS, MATCH_KINDS, classify_engineering_intent


def performance_evidence(text):
    result=classify_engineering_intent(text)
    return result,next((entry for entry in result['classification_evidence'] if entry['intent']=='performance_improvement'),None)


@pytest.mark.parametrize('text',['Perform repository analysis','Perform the analysis','The worker performs validation','Performed repository inspection','Performing bounded checks','imperf','perfect','perforce'])
def test_short_perf_alias_does_not_match_inside_words(text):
    result,evidence=performance_evidence(text)
    assert evidence is None
    assert result['primary_intent']!='performance_improvement'


def test_performance_independent_uses_full_word_not_short_alias():
    result,evidence=performance_evidence('performance-independent contract')
    assert result['primary_intent']=='performance_improvement'
    assert evidence['matched_terms']==['performance']
    assert evidence['matches'][0]['match_kind']=='full_ascii_word'


@pytest.mark.parametrize('text',['perf','run perf checks','perf-test','perf/check'])
def test_explicit_short_alias_boundaries(text):
    result,evidence=performance_evidence(text)
    assert result['primary_intent']=='performance_improvement'
    assert 'perf' in evidence['matched_terms']
    assert next(match for match in evidence['matches'] if match['matched_term']=='perf')['match_kind']=='short_ascii_alias'


@pytest.mark.parametrize('text',['performance','performance improvement','improve performance','optimize performance','performance_improvement'])
def test_explicit_ascii_performance_terms(text):
    result,evidence=performance_evidence(text)
    assert result['primary_intent']=='performance_improvement'
    assert evidence and all(match['matched_span'][0]>=0 for match in evidence['matches'])


@pytest.mark.parametrize('text',['效能改善','性能優化','改善效能'])
def test_non_ascii_performance_phrases(text):
    result,evidence=performance_evidence(text)
    assert result['primary_intent']=='performance_improvement'
    assert any(match['match_kind']=='non_ascii_phrase' for match in evidence['matches'])


def test_repository_analysis_not_mixed_by_perform_and_has_no_false_evidence():
    result=classify_engineering_intent('Perform repository analysis on the intake component')
    assert result['primary_intent']=='repository_analysis'
    assert result['secondary_intents']==[]
    assert all(entry['intent']!='performance_improvement' for entry in result['classification_evidence'])


@pytest.mark.parametrize('text',['perform repository analysis and improve performance','run repository analysis with explicit perf checks'])
def test_explicit_repository_and_performance_is_mixed(text):
    result=classify_engineering_intent(text)
    assert result['primary_intent']=='mixed'
    assert {entry['intent'] for entry in result['classification_evidence']}=={'repository_analysis','performance_improvement'}


@pytest.mark.parametrize(('text','intent'),[('repository analysis','repository_analysis'),('bug fix','bug_fix'),('test request','test_addition'),('documentation update','documentation_change'),('configuration change','configuration_change')])
def test_existing_non_performance_intents(text,intent):
    assert classify_engineering_intent(text)['primary_intent']==intent


def test_normalization_identifier_path_and_punctuation_boundaries():
    assert classify_engineering_intent('ｐｅｒｆ')['primary_intent']=='performance_improvement'
    for text in ('performance_improvement','perf-check','perf/check','“perf”'):
        assert classify_engineering_intent(text)['primary_intent']=='performance_improvement'


def test_cli_intake_uses_boundary_policy(tmp_path):
    root=Path(__file__).parents[1]; store=tmp_path/'sessions'
    command=[sys.executable,'cli/zero_engineering_work.py','--format','json','--store-root',str(store),'intake','Perform repository analysis on the intake component','--repository',str(root)]
    completed=subprocess.run(command,cwd=root,text=True,capture_output=True)
    assert completed.returncode==0
    classification=json.loads(completed.stdout)['natural_language_intake']['intent_classification']
    assert classification['primary_intent']=='repository_analysis'
    assert all(entry['intent']!='performance_improvement' for entry in classification['classification_evidence'])


def test_no_governance_authority_added():
    result=classify_engineering_intent('perf')
    assert set(result)=={'primary_intent','secondary_intents','confidence_band','classification_evidence','unsupported_elements'}


def test_every_alias_has_an_explicit_supported_match_kind():
    assert INTENT_TERMS
    for terms in INTENT_TERMS.values():
        assert terms and all(isinstance(term,str) and kind in MATCH_KINDS for term,kind in terms)
