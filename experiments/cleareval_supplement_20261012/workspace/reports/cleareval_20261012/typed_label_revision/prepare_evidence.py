"""Materialize this turn's author label interpretation with exact source offsets.

No new evaluator/expert observations. The selected answers are development-
exposed by this inspection. Interpretations below are author inputs, not a
general-purpose parser inferred from output scores.
"""
import json
import sys
from pathlib import Path

ROOT = Path(r'C:\ClearEval\ClearEval-public')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_scoped_midpoint_scorer_v1 as b

policy = b.read(OUT / 'policy.json')
policy['version'] = 'typed-label-applicability-AF-and-sourced-pairs-v2.1'
policy['af_family_approximation']['allow_sourced_pair_donors'] = True
policy['sourced_target_fluor_pairs'] = [
    {'marker': 'GFP', 'fluorophore': 'Alexa Fluor 488', 'compatible': True,
     'source_url': 'https://www.thermofisher.com/antibody/product/A-21311.html?CID=AFLBC-A-21311',
     'corroborating_url': 'https://www.abcam.com/en-us/products/primary-antibodies/alexa-fluor-488-gfp-antibody-epr14104-gfp-booster-ab225314',
     'catalogue_ids': ['A-21311', 'ab225314'], 'accessed': '2026-10-12',
     'supported_claim': 'A GFP-targeting antibody conjugated to AF488 exists and has reported IF use.',
     'scope_limit': 'General target-fluor pairing only; does not validate this answer, clone, sample depth or clearing method.'},
    {'marker': 'MAP2', 'fluorophore': 'Alexa Fluor 594', 'compatible': True,
     'source_url': 'https://www.abcam.com/en-us/products/primary-antibodies/alexa-fluor-594-map2-antibody-epr19691-neuronal-marker-ab302832',
     'catalogue_ids': ['ab302832'], 'accessed': '2026-10-12',
     'supported_claim': 'MAP2 antibody EPR19691 conjugated to AF594 has reported mouse/rat neuron IF use.',
     'scope_limit': 'General target-fluor pairing only; not tissue-clearing retention or penetration validation.'}
]
b.save(OUT / 'policy_with_sources.json', policy)
index_path = OUT.parent / 'missing_score_diagnosis/evidence.json'
records = b.read(index_path)['records']
annotations = {}


def start(cell):
    record = next(r for r in records if r['cell_id'] == cell)
    binding = record['source_document']
    assert b.bind(binding['path']) == binding
    doc = b.read(binding['path'])
    annotation = {'cell_id_at_annotation': cell, 'answer_sha256': doc['answer_sha256'],
        'question_id': record['question_id'], 'source_document': binding,
        'semantic_author': 'current_Codex_assistant_author_annotation',
        'qualification': 'source-bound post-hoc label interpretation; not expert truth, independent judge repeat or prospective confirmation',
        'review_scope': 'label identities, selected versus alternative usage and target-fluor relationships',
        'remaining_uncertainties': []}
    annotations[doc['answer_sha256']] = annotation
    return annotation, doc


def relation(doc, fluor, marker, quotes, basis):
    spans = []
    for quote in quotes:
        assert doc['text'].count(quote) == 1, ('quote must locate one source span', quote)
        offset = doc['text'].index(quote)
        spans.append({'start': offset, 'end': offset + len(quote), 'quote': quote,
                      'answer_sha256': doc['answer_sha256']})
    return {'fluorophore': fluor, 'marker': marker, 'source_spans': spans, 'basis': basis}


a, d = start('A01')
a['relations'] = [
    relation(d, 'GFP', '', ['**Chosen Labeling:** [GFP (内源), DAPI / Hoechst / PI]'],
             '原文指定内源 GFP，自身是荧光信号。'),
    relation(d, 'DAPI', '', ['1.1 Incubation with DAPI (10 μg/ml) in 0.01M PBS for nuclear labeling of cell bodies.(Temperature: 4 ℃, Time: 72 hours)'],
             '标题给出核染料备选，实际操作明确执行 DAPI；Hoechst/PI 不作为另行使用的染料。')]
a['selection_basis'] = 'Actual DAPI operation resolves the slash-separated heading alternatives; no choice by compatibility score.'

a, d = start('A04')
header = '**Chosen Labeling:** [GFP (内源) + Alexa Fluor, MAP2 + Alexa Fluor]'
primary = next(line for line in d['text'].splitlines() if line.startswith('2.1 Incubation'))
secondary = next(line for line in d['text'].splitlines() if line.startswith('2.3 Incubation'))
a['scenario_basis'] = 'Two targets and two different AF dyes are stated, but the assignment is unspecified. Enumerate both bijections; publish a scalar only when both scores coincide. Generic AF is refined by the named dyes, not counted as a third channel.'
a['relation_scenarios'] = []
for identifier, gfp_fluor, map2_fluor in [('GFP488_MAP2647', 'Alexa Fluor 488', 'Alexa Fluor 647'),
                                       ('GFP647_MAP2488', 'Alexa Fluor 647', 'Alexa Fluor 488')]:
    a['relation_scenarios'].append({'scenario_id': identifier, 'relations': [
        relation(d, 'GFP', '', [header], 'Explicit native GFP remains a signal.'),
        relation(d, gfp_fluor, 'GFP', [header, primary, secondary], 'One admissible pairing, not a uniquely extracted source fact.'),
        relation(d, map2_fluor, 'MAP2', [header, primary, secondary], 'Complementary pairing in the same admissible scenario.')]})

# All edited control texts receive their own source-bound label annotation.
# Changes in time/order remain in their own saved extraction and scores.
for record in records:
    if not record['cell_id'].startswith('E2_') or record['question_id'] != 22:
        continue
    a, d = start(record['cell_id'])
    header = '**Chosen Labeling:** [GFP (内源), MAP2 + Alexa Fluor]'
    assert header in d['text']
    a['relations'] = [
        relation(d, 'GFP', '', [header], 'Explicit native GFP, no external marker required.'),
        relation(d, 'Alexa Fluor', 'MAP2', [header], 'Header explicitly states the target-fluor relation; repeated AF mentions describe the same channel.')]

a, d = start('FPC05')
header = d['text'].splitlines()[0]
a['relations'] = [relation(d, 'GFP', '', [header], '明确内源 GFP。'),
    relation(d, 'Alexa Fluor 647', 'MAP2', [header], '标题明确 MAP2+AF647；正文一抗和二抗步骤一致。')]

a, d = start('FPC08')
header = '**Chosen Labeling:** [GFP (内源) + Alexa Fluor 488, Phalloidin + Alexa Fluor 568]'
primary = next(line for line in d['text'].splitlines() if line.startswith('4.1 Incubation'))
staining = next(line for line in d['text'].splitlines() if line.startswith('6.1 Incubation'))
a['relations'] = [relation(d, 'GFP', '', [header], 'Native signal explicitly stated.'),
    relation(d, 'Alexa Fluor 488', 'GFP', [header, primary, staining], 'Anti-GFP plus matching fluorescent secondary is explicit.'),
    relation(d, 'Alexa Fluor 568', 'Phalloidin', [header, staining], 'Explicit conjugated phalloidin probe; marker key follows the existing authored dictionary convention.')]

a, d = start('FPC16')
header = '**Chosen Labeling:** [tdTomato (endogenous), DiI]'
a['relations'] = [relation(d, 'tdTomato', '', [header], 'Native reporter is explicit.'),
    relation(d, 'DiI', '', [header], 'Direct lipophilic stain; do not turn the word axonal into an antibody-target entity ID.')]

a, d = start('FPC04')
header = next(line for line in d['text'].splitlines() if line.startswith('**Chosen Labeling:'))
assert '546' in header and '647' in header
a['scenario_basis'] = 'The submitted answer explicitly offers AF546 or AF647. Keep both, without substituting their average or choosing the higher score.'
a['relation_scenarios'] = [{'scenario_id': 'MAP2_AF' + dye, 'relations': [
    relation(d, 'EGFP', '', [header], 'Source-declared native protein.'),
    relation(d, 'Alexa Fluor ' + dye, 'MAP2', [header], 'One explicitly offered alternative in the source.')]} for dye in ['546', '647']]

b.save(OUT / 'author_label_annotations.json', {'version': 'source-bound-label-author-annotations-20261012',
    'new_model_requests': 0, 'expert_records': 0, 'source_index': b.bind(index_path),
    'development_exposed': True, 'results': list(annotations.values())})
print(json.dumps({'unique_annotated_answers': len(annotations), 'new_model_requests': 0}))
