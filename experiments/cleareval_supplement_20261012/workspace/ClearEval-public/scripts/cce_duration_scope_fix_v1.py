"""Derived-only correction of spatial ND map nouns misclassified as durations.

The v11 source document, raw response, registry, candidate IDs, operations and
all time policies remain unchanged. This corrects the omitted map/maps endpoint
in the existing duration_role lexical classification, without re-enumeration.
"""
from __future__ import annotations
import argparse, copy, contextlib, io, re, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_operation_coverage_scope_diagnostic_v1 as scope
g, j, base, scoring = scope.g, scope.j, scope.base, scope.scoring
OUT = base.BASE / 'duration_scope_fix_v1'
VERSION = 'derived-spatial-map-duration-classification-v1'
SPATIAL = r'(?:morphological|anatomical|spatial|volumetric|structural|cellular|high[- ]resolution|light[- ]sheet|confocal|fluorescen(?:ce|t)|whole[- ](?:organ|brain))'
MAP_ENDPOINT = re.compile(r'^\s*(?:' + SPATIAL + r'\s+(?:or\s+)?){0,4}(?:maps?|mapping)\b', re.I)
require, bind, save_once = scope.require, scope.bind, scope.save_once


def derive_audit(original, doc):
    """Keep raw source and IDs; reclassify only source-exact spatial map leads."""
    require(original['source_binding']['source_id'] == doc['source_id']
        and original['source_binding']['answer_sha256'] == doc['answer_sha256']
        and g.rawsha(doc['text']) == doc['answer_sha256'], 'SOURCE_IDENTITY_MISMATCH')
    audit = copy.deepcopy(original); changes = []
    units = {u['unit_id']: u for u in doc['units']}
    for row in audit['inventory']:
        if row['kind'] != 'duration': continue
        s = row['span']; u = units[s['unit_id']]
        require(s['answer_sha256'] == doc['answer_sha256'] and doc['text'][s['start']:s['end']] == s['quote']
            and u['start'] <= s['start'] <= s['end'] <= u['end'], 'DURATION_SOURCE_SPAN_MISMATCH')
        # Case-sensitive uppercase D is necessary. Lowercase d stays a time unit.
        if not re.fullmatch(r'\d+\s*D', s['quote']): continue
        right = doc['text'][s['end']:u['end']]; match = MAP_ENDPOINT.match(right)
        if not match: continue
        old_kind, old_state = row['kind'], row['coverage_state']
        row['kind'] = 'dimensional_expression_lead'
        row['coverage_state'] = 'classified_non_duration_dimensional_expression'
        row['original_candidate_kind'] = old_kind
        row['original_coverage_state'] = old_state
        row['non_additive_classification'] = 'source-exact uppercase ND with bounded spatial map/maps/mapping noun; missing v11 map endpoint corrected'
        row['source_text_unchanged'] = True
        changes.append({'candidate_id': row['candidate_id'], 'span': copy.deepcopy(s),
            'original_kind': old_kind, 'derived_kind': row['kind'], 'original_coverage_state': old_state,
            'derived_coverage_state': row['coverage_state'], 'matched_right_context': match.group(),
            'candidate_id_unchanged': True, 'source_registry_reenumerated': False})
    require(audit['source_binding'] == original['source_binding'] and audit['resolved'] == original['resolved']
        and audit.get('score_evidence') == original.get('score_evidence'), 'NON_INVENTORY_STATE_CHANGED')
    require([r['candidate_id'] for r in audit['inventory']] == [r['candidate_id'] for r in original['inventory']], 'CANDIDATE_ID_CHANGED')
    audit['derived_duration_scope_classification'] = {'version': VERSION, 'changes': changes,
        'original_registry_hash_retained': True, 'original_raw_and_candidate_ids_retained': True,
        'source_registry_reenumerated': False, 'original_time_formula_unchanged': True,
        'not_a_model_return': True, 'not_a_scientific_time_confirmation': True}
    return audit, changes


def self_check(out):
    require(not out.exists(), 'NEW_OUTPUT_ONLY'); out.mkdir(parents=True)
    checks = []
    for text, expected in [('A 3D morphological map.', True), ('A 3D spatial maps representation.', True),
        ('A 3D map.', True), ('A 3D mapping.', False), ('Incubate for 3 d.', False),
        ('Incubate for 3 days.', False), ('Duration: 3D.', False), ('A 3D uncertain term.', False)]:
        doc = g.document(text, 'SYNTHETIC_ONLY'); registry = g.candidate_registry(doc)
        audit = {'source_binding': {'source_id': doc['source_id'], 'answer_sha256': doc['answer_sha256'],
            'candidate_registry_sha256': registry['registry_sha256']}, 'inventory': copy.deepcopy(registry['records']),
            'resolved': {'operations': [], 'coverage': {'unresolved': []}}, 'score_evidence': []}
        for r in audit['inventory']: r['coverage_state'] = 'uncovered_candidate'
        new, changes = derive_audit(audit, doc)
        ok = bool(changes) is expected and new['resolved'] == audit['resolved'] and new['source_binding'] == audit['source_binding']
        checks.append({'text': text, 'expected_change': expected, 'changed': bool(changes), 'pass': ok})
        require(ok, 'LEXICAL_BOUNDARY_PROBE_FAILED:' + text)
    save_once(out / 'verification.json', {'status': 'pass', 'software_only': True, 'checks': checks,
        'note': 'mapping already had the correct original classification; only missing map/maps changes',
        'script': bind(__file__), 'new_model_requests': 0, 'actual_command': [sys.executable, *sys.argv]})
    print(j.canonical({'status': 'pass', 'checks': len(checks), 'new_model_requests': 0}))


def public_five(out):
    """Authorized exact five stored E2 conversions; no whole-source re-execution."""
    require(not out.exists(), 'NEW_OUTPUT_ONLY'); out.mkdir(parents=True)
    source = base.BASE / 'operation_coverage_scope_batch_v1/actual_execution_01'
    cases_path = base.BASE / 'grounded_controls_v11/cases.json'; matrix_path = base.BASE / 'grounded_controls_v11/matrix.json'
    cases = {c['anonymous_answer_id']: c for c in j.read(cases_path)['cases']}
    matrix = {r['anonymous_answer_id']: r for r in j.read(matrix_path)}
    all_cells = {r['anonymous_answer_id']: r for r in j.read(source / 'cells.json') if r['cohort'] == 'E2'}
    results = []; inputs = [bind(cases_path), bind(matrix_path), bind(source / 'summary.json'), bind(source / 'cells.json')]
    for aid in ['E2_01', 'E2_04', 'E2_13', 'E2_14', 'E2_19']:
        case = cases[aid]; row = matrix[aid]; saved = all_cells[aid]
        require(saved['status'] == 'success', 'ORIGINAL_SUCCESS_REQUIRED')
        folder = source / 'cells/E2' / row['cell_id']; cvpath = folder / 'derived_conversion.json'; numpath = folder / 'posthoc_numeric.json'
        cv = j.read(cvpath); numeric = j.read(numpath); docpath = Path(row['assets']['source_document']['path']); doc = j.read(docpath)
        require(g.rawsha(case['model_response']) == doc['answer_sha256'], 'CASE_SOURCE_MISMATCH')
        audit, changes = derive_audit(cv['source_audit'], doc)
        require(len(changes) == 1, 'ACTUAL_ONE_FALSE_DURATION_EXPECTED')
        derived = copy.deepcopy(cv); derived['source_audit'] = audit; derived['legacy_projection'] = g.project_legacy(audit)
        derived['legacy_runner_payload'] = {'scores': copy.deepcopy(cv['legacy_runner_payload']['scores']),
            'extraction': copy.deepcopy(derived['legacy_projection']['extraction'])}
        derived['legacy_runner_content'] = g.canonical(derived['legacy_runner_payload'])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            before = scoring.score_conversion(case, cv, base.BACKEND, row['step'])
            after = scoring.score_conversion(case, derived, base.BACKEND, row['step'])
        require(before == numeric and all(scoring.same(before['metrics'][m], saved['posthoc_metrics'][m]) for m in scoring.METRICS), 'STORED_ORIGINAL_NUMERIC_MISMATCH')
        require(all(scoring.same(before['metrics'][m], after['metrics'][m]) for m in scoring.DIRECT + ['s_method', 's_label', 's_trans', 'sr', 'sp', 'Com', 'Cor']), 'NON_TIME_METRIC_CHANGED')
        result = {'anonymous_answer_id': aid, 'original_time_hours': cv['legacy_projection']['time_calculation']['total_hours'],
            'derived_time_hours': derived['legacy_projection']['time_calculation']['total_hours'],
            'original_s_time': before['metrics']['s_time'], 'derived_s_time': after['metrics']['s_time'],
            'original_issues': cv['legacy_projection']['time_calculation']['issues'],
            'derived_issues': derived['legacy_projection']['time_calculation']['issues'], 'changes': changes,
            'original_metrics': before['metrics'], 'derived_metrics': after['metrics'],
            'original_success_retained': True, 'original_results_overwritten': False, 'new_model_requests': 0}
        require(result['original_time_hours'] is None and result['derived_time_hours'] == 84, 'ACTUAL_EXPECTED_TIME_REPAIR')
        save_once(out / (aid + '.json'), result); results.append(result)
        inputs.extend([bind(cvpath), bind(numpath), bind(docpath)])
    base.verify_bindings(inputs)
    summary = {'status': 'five_actual_posthoc_checks_passed', 'actual_cases': 5, 'new_model_requests': 0,
        'script': bind(__file__), 'original_converter': bind(g.__file__), 'inputs': inputs,
        'results': [{k: r[k] for k in ['anonymous_answer_id', 'original_time_hours', 'derived_time_hours', 'original_s_time', 'derived_s_time']} for r in results],
        'original_scientific_formulas_unchanged': True, 'raw_and_original_results_unchanged': True,
        'actual_command': [sys.executable, *sys.argv]}
    save_once(out / 'summary.json', summary); print(j.canonical({'status': summary['status'], 'results': summary['results']}))


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['self-check', 'public-five']); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); out = a.out.resolve(); require(out.is_relative_to(OUT.resolve()), 'NEW_DURATION_NAMESPACE_ONLY')
    if a.action == 'self-check': self_check(out)
    else: public_five(out)


if __name__ == '__main__': main()
