"""Offline regression checks and paired descriptive analysis of saved returns."""
import copy
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

ROOT = Path(r'C:\ClearEval\ClearEval-public')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_typed_label_scorer_v2 as s
b = s.base
runner, registry = b.runtime()
policy = b.read(OUT/'policy_with_sources.json')
rows = b.read(OUT/'with_author_labels/results.json')
actual = {r['cell_id']: r for r in rows if r.get('source_record')}
checks = []


def check(name, condition, detail=None):
    if not condition:
        raise AssertionError(name)
    checks.append({'name': name, 'passed': True, 'detail': detail})


def close(a, z):
    return a is None and z is None or b.finite(a) and b.finite(z) and math.isclose(a, z, abs_tol=1e-12)


def csv_write(path, values):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


unchanged = s.DIRECT + ['s_method', 's_trans', 's_time', 'sr', 'sp', 'Com', 'Cor']
check('all_67_unaffected_component_vectors_preserved', all(
    r['metrics'][k] == r['comparison_metrics'][k] for r in actual.values() for k in unchanged),
    {'records': len(actual), 'values': len(actual) * len(unchanged)})
check('all_previously_complete_cases_remain_complete', all(
    r['complete_numeric_CCE'] for r in actual.values() if b.complete(r['comparison_metrics'])))
check('actual_native_GFP_needs_no_antibody_target', close(
    actual['E2_01__local_qwen27b_q8_development__r0']['metrics']['s_label'], 5.4))
check('actual_direct_DAPI_not_false_target_mismatch', close(actual['A01']['metrics']['s_label'], 4.2))
check('secondary_carrier_no_duplicate_missing_target', close(actual['FPC13']['metrics']['s_label'], 4.8))
check('genuine_unknown_target_and_unknown_method_value_remain',
      actual['FPC09']['metrics']['s_label'] is None and actual['FPC11']['metrics']['s_label'] is None)
check('actual_DiI_partial_record_recovered_without_overwriting_Cor', close(actual['FPC16']['metrics']['s_label'], 1.2))
check('known_zero_is_retained_when_original_target_match_is_zero', actual['FPC08']['metrics']['s_label'] == 0)
check('both_A04_assignments_yield_same_value',
      actual['A04']['label_derivation']['score_invariant_across_declared_scenarios'] and
      all(close(x['result']['s_label'], 4.5) for x in actual['A04']['label_derivation']['relation_scenarios']))
check('FPC04_alternatives_are_not_averaged_or_maximized', actual['FPC04']['metrics']['s_label'] is None and
      all(close(a,z) for a,z in zip(actual['FPC04']['label_derivation']['conditional_s_label_bounds'], [4.8, 5.1])))

q = actual['A01']['quantitative_data']
demand = registry.get(2, registry.questions['2']['question'])
check('empty_label_list_still_unknown', s.score_labels({'pairs': [], 'explicit_label_uncertainties': []},
      runner, q, demand, [], policy)['s_label'] is None)
try:
    s.project_annotation({'answer_sha256': 'correct', 'relations': [{'fluorophore':'GFP','marker':'',
        'source_spans': [{'start':0,'end':3,'quote':'XYZ'}], 'basis':'synthetic'}]},
        {'answer_sha256': 'correct', 'text':'GFP'})
except ValueError:
    check('mislocated_source_quote_rejected', True)
else:
    raise AssertionError('mislocated quote accepted')

# Contradictory donor evidence must not be converted to its maximum.
class LookupFixture:
    _normalize_name = staticmethod(lambda value: str(value).casefold())
    TISSUE_KB = [{'AlexaFluor 488':1, 'AlexaFluor 568/Cy3':0}]


stub = {'value':None, 'status':'unmapped_authored_fluor_column', 'selected_row_indices':[0],
        'per_scope_evidence':[]}
without_sources = {**policy, 'sourced_target_fluor_pairs': []}
with patch.object(s.catalog, 'marker_scope_lookup', return_value=copy.deepcopy(stub)):
    check('AF_disagreeing_donors_remain_unknown', s.compatibility(
        LookupFixture(), 'MAP2', 'Alexa Fluor 594', [], {}, without_sources)['value'] is None)
with patch.object(s.catalog, 'marker_scope_lookup', return_value={**copy.deepcopy(stub), 'value':False}):
    check('specific_negative_not_overridden_by_positive_product_source', s.compatibility(
        LookupFixture(), 'MAP2', 'Alexa Fluor 594', [], {}, policy)['value'] is False)
source_trace = actual['A03']['compatibility_lookup_trace']
check('actual_GFP488_has_identified_primary_source', any(t.get('pair_sources') and t['marker']=='GFP'
      and t['value'] is True for t in source_trace))
check('time_deleted_controls_not_filled_from_baseline', all(
    actual[f'E2_{i:02d}__local_qwen27b_q8_development__r0']['metrics']['s_time'] is None for i in [3,7,11]))

source_index = b.read(OUT.parent/'missing_score_diagnosis/evidence.json')['records']
input_bindings = {v['path']:v for r in source_index for k in ['source_document','posthoc_record','raw_response']
                  if isinstance((v:=r.get(k)),dict) and 'path' in v}
check('source_answer_posthoc_and_raw_files_unchanged', all(b.bind(p)==v for p,v in input_bindings.items()),
      {'unique_files': len(input_bindings)})

controls = ROOT/'artifacts/cce_validation/optimizer_round2_20261010/grounded_controls_v11'
with (controls/'observations.csv').open(encoding='utf-8-sig',newline='') as f:
    case_to_anon = {r['case_id']:r['anonymous_answer_id'] for r in csv.DictReader(f)}
with (controls/'per_pair.csv').open(encoding='utf-8-sig',newline='') as f:
    source_pairs = list(csv.DictReader(f))
pair_rows = []
for pair in source_pairs:
    left = actual[case_to_anon[pair['baseline_case_id']]+'__local_qwen27b_q8_development__r0']
    right = actual[case_to_anon[pair['variant_case_id']]+'__local_qwen27b_q8_development__r0']
    result = {'pair_id':pair['pair_id'], 'question_id':pair['question_id'], 'condition':pair['condition'],
        'baseline_cell':left['cell_id'], 'variant_cell':right['cell_id'],
        'distinct_fulltext_hashes':left['answer_sha256'] != right['answer_sha256'],
        'complete_pair_before':b.complete(left['comparison_metrics']) and b.complete(right['comparison_metrics']),
        'complete_pair_after':b.complete(left['metrics']) and b.complete(right['metrics']),
        'new_full_pipeline_requests':0}
    for metric in left['metrics']:
        a,z = left['metrics'][metric],right['metrics'][metric]
        result['baseline_'+metric],result['variant_'+metric] = a,z
        result['delta_'+metric] = z-a if b.finite(a) and b.finite(z) else None
    pair_rows.append(result)
check('15_control_pairs_bind_distinct_edited_fulltexts', len(pair_rows)==15 and all(r['distinct_fulltext_hashes'] for r in pair_rows))
csv_write(OUT/'controlled_pairs.csv', pair_rows)
conditions = []
for condition in sorted({r['condition'] for r in pair_rows}):
    subset = [r for r in pair_rows if r['condition']==condition]
    conditions.append({'condition':condition, 'pairs':len(subset),
        'complete_before':sum(r['complete_pair_before'] for r in subset),
        'complete_after':sum(r['complete_pair_after'] for r in subset),
        'details':[{'q':r['question_id'], **{k:r[k] for k in ['delta_sr','delta_sp','delta_c_param','delta_Cor','delta_Eff','delta_HV']}} for r in subset]})

# Reuse real repetitions; author annotations are a deterministic repair condition,
# not additional trials and not an estimate of future extraction reliability.
metrics = s.DIRECT + s.EGES + ['Com','Cor','Eff','IA','HV']
stability = []
for phase in ['comparison_metrics', 'rules_only', 'with_pair_sources', 'with_author_labels']:
    phase_rows = list(actual.values()) if phase=='comparison_metrics' else [r for r in b.read(OUT/phase/'results.json') if r.get('source_record')]
    groups = defaultdict(list)
    for row in phase_rows:
        if row['cohort'] in ['Qwen_repeats','Codex']:
            groups[(row['cohort'],row['cell_id'].split('__')[0])].append(row)
    for (cohort,answer), group in groups.items():
        if len(group)<2:
            continue
        for metric in metrics:
            vals = [r['comparison_metrics' if phase=='comparison_metrics' else 'metrics'][metric] for r in group]
            known = [v for v in vals if b.finite(v)]
            state = 'all_numeric' if len(known)==len(vals) else 'all_missing' if not known else 'mixed_missing'
            stability.append({'phase':phase,'judge_family':cohort,'answer':answer,'metric':metric,
                'actual_returns':len(vals),'numeric_returns':len(known),'state':state,
                'range':max(known)-min(known) if state=='all_numeric' else None,
                'values':json.dumps(vals), 'new_repeat_calls':0})
csv_write(OUT/'archived_repeat_sensitivity.csv', stability)
repeat_summary = []
for phase in ['comparison_metrics','rules_only','with_pair_sources','with_author_labels']:
    for family in ['Qwen_repeats','Codex']:
        group = [r for r in stability if r['phase']==phase and r['judge_family']==family]
        repeat_summary.append({'phase':phase, 'family':family, 'metric_groups':len(group),
            'all_numeric_groups':sum(r['state']=='all_numeric' for r in group),
            'all_numeric_zero_range':sum(r['state']=='all_numeric' and abs(r['range'])<1e-12 for r in group),
            'all_numeric_nonzero_range':sum(r['state']=='all_numeric' and abs(r['range'])>=1e-12 for r in group),
            'missingness_groups':sum(r['state']!='all_numeric' for r in group)})

summary = {'saved_returns':len(actual), 'unique_answer_texts':len({r['answer_sha256'] for r in actual.values()}),
    'checks_passed':len(checks), 'paired_controls':conditions, 'archived_repeat_sensitivity':repeat_summary,
    'new_model_requests':0, 'new_independent_repetitions':0, 'expert_records':0,
    'claim_scope':'post-hoc scoring coverage and sensitivity on already exposed answers',
    'old_complete_score_changes':[{'cell_id':r['cell_id'],'changes':r['typed_changes']} for r in actual.values()
        if b.complete(r['comparison_metrics']) and r['typed_changes']],
    'remaining':[{'cell_id':r['cell_id'],'missing':[k for k in ['Cor','s_label','s_time'] if r['metrics'][k] is None]}
        for r in actual.values() if not r['complete_numeric_CCE']]}
b.save(OUT/'verification.json', {'checks':checks, 'entrypoint':b.bind(__file__)})
b.save(OUT/'readout.json', summary)
print(json.dumps(summary,ensure_ascii=False,indent=2))
