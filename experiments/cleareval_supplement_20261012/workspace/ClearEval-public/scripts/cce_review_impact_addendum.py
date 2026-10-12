"""Read-only E1/E3 scope-denominator and actual EGES-evidence audit.

Existing frozen bridges, trials, review tables and scores remain untouched.
Only this addendum's output directory is written. No model transport is called.
"""
import argparse
import collections
import copy
import json
import pathlib
import re
import sys
import types

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_rescore_extractions as bridge
import cce_local_step_audit as local

BASE = ROOT / 'artifacts/cce_validation'
HUMAN = BASE / 'human_review'
METRICS = bridge.EGES + ['Eff', 'Com', 'Cor', 'IA', 'HV', 'sr', 'sp']


def bind(p):
    p = pathlib.Path(p)
    return {'path': str(p.resolve()), 'sha256': bridge.judges.filehash(p)}


def fraction(n, d):
    return {'numerator': n, 'denominator': d, 'fraction': n / d if d else None}


def completed_step_scope(answers, accepted):
    """Coverage mismatches, not candidate-span mismatches, can alter SR."""
    result = []
    for answer in answers:
        rows = [r for r in accepted if r['answer_id'] == answer['answer_id']
                and r['expert_reference_covered_in_full_answer'] in {'yes', 'no'}
                and r['expert_candidate_covers_reference'] in {'yes', 'no'}]
        complete = answer['selected_rows'] > 0 and len(rows) == answer['selected_rows']
        deltas = [int(r['expert_reference_covered_in_full_answer'] == 'yes')
                  - int(r['auto_matched'] == 'true') for r in rows]
        result.append({'answer_id': answer['answer_id'], 'split': answer['split'],
                       'prespecified_reference_rows': answer['selected_rows'],
                       'definitive_reviewed_reference_rows': len(rows),
                       'completed_prespecified_local_scope': complete,
                       'at_least_one_coverage_error_can_change_SR': any(deltas) if complete else None,
                       'net_reviewed_matched_count_delta': sum(deltas) if complete else None,
                       'manual_SR': None})
    splits = {}
    for split in ['audit_dev', 'audit_holdout']:
        group = [r for r in result if r['split'] == split]
        complete = [r for r in group if r['completed_prespecified_local_scope']]
        splits[split] = {'planned_answers': len(group),
                        'answers_with_prespecified_local_candidates': sum(r['prespecified_reference_rows'] > 0 for r in group),
                        'completed_prespecified_local_scope_answers': len(complete),
                        'answers_with_reviewed_SR_relevant_coverage_error': fraction(
                            sum(r['at_least_one_coverage_error_can_change_SR'] for r in complete), len(complete)),
                        'answers_with_nonzero_net_reviewed_coverage_delta': fraction(
                            sum(r['net_reviewed_matched_count_delta'] != 0 for r in complete), len(complete))}
    return {'answers': result, 'splits': splits,
            'interpretation': 'Local prespecified review only. Opposite coverage errors may cancel in the net SR contribution; both counts are retained. A wrong automatic span with a valid alternative span need not change SR.'}


def audit_steps(folder):
    manifest = local.read(folder / 'manifest.json')
    local.verify_binding(manifest['script'])
    for key, binding in manifest['sources'].items():
        if key != 'original_review':
            local.verify_binding(binding)
    rows = local.csvread(folder / 'review_rows.csv')
    local.verify_rows(manifest, rows)
    packets = {}
    for answer in manifest['answers']:
        local.verify_binding(answer['packet'])
        packets[answer['answer_id']] = local.read(answer['packet']['path'])
    accepted = [r for r in rows if local.validate_review(r, packets[r['answer_id']]['answer_text'])]
    return completed_step_scope(manifest['answers'], accepted)


def reviewed_extraction_scope(labels, packets):
    lookup = collections.defaultdict(dict)
    for row in labels:
        if row['item'] not in bridge.ITEM_ROOTS:
            continue
        bridge.require(row['item'] not in lookup[row['answer_id']], 'Duplicate extraction review item')
        lookup[row['answer_id']][row['item']] = row
    result = []
    for aid, rows in sorted(lookup.items()):
        definitive = []
        for row in rows.values():
            if row['review_status'] != 'reviewed' or row['expert_decision'] not in {'成立', '不成立'}:
                continue
            bridge.require(bool(row['reviewer_id'].strip()) and bool(row['review_date'].strip()), 'Missing reviewer identity/date')
            m = re.fullmatch(r'(answer_text|task_text):(\d+):(\d+)', row['source_location'].strip())
            bridge.require(m is not None, 'Extraction review needs verifiable original-text offsets')
            bridge.require(0 <= int(m[2]) < int(m[3]) <= len(packets[aid][m[1]]), 'Review offsets outside packet')
            definitive.append(row)
        complete = set(rows) == set(bridge.ITEM_ROOTS) and len(definitive) == len(bridge.ITEM_ROOTS)
        if complete:
            provenance = {(r['reviewer_id'], r['review_date']) for r in definitive}
            bridge.require(len(provenance) == 1, 'Completed four-item review needs consistent reviewer/date')
        result.append({'answer_id': aid, 'split': next(iter(rows.values()))['split'],
                       'prespecified_field_items': len(bridge.ITEM_ROOTS), 'definitive_reviewed_items': len(definitive),
                       'completed_prespecified_extraction_scope': complete,
                       'confirmed_extraction_error': any(r['expert_decision'] == '不成立' for r in definitive) if complete else None,
                       'confirmed_error_types': dict(collections.Counter(r.get('error_type') or 'unspecified_by_reviewer'
                            for r in definitive if r['expert_decision'] == '不成立'))})
    return result


def actual_effects(record, extraction, runner, registry, case):
    runner.validate_teacher_extraction(extraction)
    fixed = registry.get(record['question_id'], case['specific_question'])
    meta = runner.QUESTION_META_KB[registry.questions[str(record['question_id'])]['question_id']]
    quantitative = {'method_name': extraction['method_name'], 'tissue_ri_value': meta.get('tissue_ri_value'),
                    'total_time_hours': extraction['clearing_total_time_hours'], 'sample_tier': meta.get('tissue_tier_code')}
    for key in ['reagent_ri_value', 'protocol_time_hours', 'method_stages']:
        if key in extraction:
            quantitative[key] = extraction[key]
    effects = runner.calculate_effectiveness_score(quantitative, fixed, runner.MODEL_SPACE_SIGNED,
                extraction['marker_dict'], meta.get('marker_query_targets') or [])
    identity = effects['method_identity']
    is_single = identity['status'] == 'RESOLVED_SINGLE'
    ri_key = runner.resolve_method(extraction['method_name'], runner.METHOD_RI_REF_KB) if is_single else None
    sigma_key = runner.resolve_method(extraction['method_name'], runner.SIGMA_RI_KB) if is_single else None
    time = effects['time_computation']
    evidence = {
        's_method': {'source': 'dataset/Q+AR/src/model_space_signed.json', 'resolved_key': identity.get('resolved_key'),
                     'resolution_status': identity['status'], 'demand_question_id': record['question_id']},
        's_label': {'compatibility_lookups': sorted(effects['compatibility_audit'], key=bridge.judges.canonical),
                    'fixed_marker_query_targets': meta.get('marker_query_targets') or []},
        's_trans': {'method_ri_source': 'KnowledgeBase/method_ri_ref.json', 'method_ri_key': ri_key,
                    'sigma_source': 'KnowledgeBase/method_sigma_ri.json', 'sigma_method_key': sigma_key,
                    'sigma_tier': quantitative['sample_tier'], 'fixed_tissue_ri': quantitative['tissue_ri_value'],
                    'time_KB_gate_method_key': time.get('method_key'), 'time_KB_gate_resolved_tier': time.get('resolved_tier'),
                    'status': effects['_s_trans_status'], 'reference_ri': effects['_s_trans_ri_method_ref'],
                    'reference_sigma': effects['_s_trans_sigma']},
        's_time': {'source': time.get('source'), 'method_key': time.get('method_key'),
                   'resolved_tier': time.get('resolved_tier'), 'requested_tier': quantitative['sample_tier'],
                   'reference_min_hours': time.get('min_hours'), 'reference_max_hours': time.get('max_hours'),
                   'reference_tau_hours': time.get('tau_hours')},
    }
    # Actual proposed time is deliberately excluded from selection fingerprints:
    # changing a score input without changing the chosen KB row is not reference reselection.
    return {'component_values': {k: effects[k] for k in bridge.EGES},
            'evidence_selection': evidence,
            'evidence_selection_sha256': {k: bridge.judges.digest(v) for k, v in evidence.items()},
            'actual_audit': {'method_identity': identity, 'compatibility_audit': effects['compatibility_audit'],
                            'marker_coverage_audit': effects['marker_coverage_audit'], 'time_computation': time,
                            'trans_status': effects['_s_trans_status']}}


def pair_values(a, b, before, after):
    return {'component_deltas': {k: b[k] - a[k] if a[k] is not None and b[k] is not None else None for k in METRICS},
            'na_created': [k for k in METRICS if a[k] is not None and b[k] is None],
            'na_resolved': [k for k in METRICS if a[k] is None and b[k] is not None],
            'evidence_selection_changed_components': [k for k in bridge.EGES
                if before['evidence_selection_sha256'][k] != after['evidence_selection_sha256'][k]],
            'step_reference_changed': a['reference_id'] != b['reference_id'],
            'na_reasons_before': a['na_reasons'], 'na_reasons_after': b['na_reasons']}


def software_checks():
    answers = [{'answer_id': 'fixture', 'split': 'audit_dev', 'selected_rows': 2}]
    def row(auto, truth):
        return {'answer_id': 'fixture', 'auto_matched': auto, 'expert_reference_covered_in_full_answer': truth,
                'expert_candidate_covers_reference': 'no'}
    partial = completed_step_scope(answers, [row('true', 'no')])
    canceled = completed_step_scope(answers, [row('true', 'no'), row('false', 'yes')])
    alternate = completed_step_scope(answers, [row('true', 'yes'), row('true', 'yes')])
    bridge.require(partial['splits']['audit_dev']['completed_prespecified_local_scope_answers'] == 0, 'Partial review entered answer denominator')
    bridge.require(canceled['answers'][0]['at_least_one_coverage_error_can_change_SR'] is True and canceled['answers'][0]['net_reviewed_matched_count_delta'] == 0, 'Opposite errors silently canceled')
    bridge.require(alternate['answers'][0]['at_least_one_coverage_error_can_change_SR'] is False, 'Alternative valid span falsely counted as SR change')
    bridge.require(fraction(0, 0)['fraction'] is None, 'Unreviewed cases converted to zero error')
    return {'scope': 'isolated in-memory software fixtures; not expert labels or scientific observations',
            'partial_review_excluded': True, 'opposite_errors_and_net_delta_distinguished': True,
            'alternative_span_preserves_coverage': True, 'empty_denominator_remains_NA': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auto-inputs', type=pathlib.Path, default=HUMAN/'rescoring/v4_dev_v2/auto_inputs.json')
    parser.add_argument('--review', type=pathlib.Path, default=HUMAN/'reviewer/review_items.csv')
    parser.add_argument('--corrections', type=pathlib.Path, default=HUMAN/'expert_extraction_corrections.json')
    parser.add_argument('--packets', type=pathlib.Path, default=HUMAN/'reviewer')
    parser.add_argument('--local-step-audit', type=pathlib.Path, default=HUMAN/'local_step_audit')
    parser.add_argument('--out', type=pathlib.Path, default=HUMAN/'review_impact_addendum')
    args = parser.parse_args()
    # Frozen implementation and all direct trial/step/task dependencies are verified here.
    auto, runner, registry, cases = bridge.load_auto(args)
    labels = bridge.human.read_csv(args.review)
    packets = {p.stem: bridge.read(p) for p in args.packets.glob('A*.json')}
    originals = {r['answer_id']: r for r in auto['records']}
    bridge.validate_packet_bindings(packets, originals)
    # Bind every packet, including unanswered holdout, before counting returned rows.
    identities = {r['answer_id']: r for r in bridge.human.read_csv(auto['scoring_config']['identity_file'])}
    for aid, packet in packets.items():
        bridge.require(aid == packet['answer_id'] and aid in identities, 'Packet identity mismatch')
        for field, hk in [('answer_text', 'answer_sha256'), ('task_text', 'question_sha256')]:
            bridge.require(bridge.rawsha(packet[field]) == packet[hk] == identities[aid][hk], 'Packet source mismatch')
    bridge.require({(r['answer_id'], r['item']) for r in labels if r['item'] in bridge.ITEM_ROOTS}
        == {(aid, item) for aid in identities for item in bridge.ITEM_ROOTS}, 'Prespecified review answer/item set changed')
    for r in labels:
        bridge.require(r['split'] == identities[r['answer_id']]['split'], 'Review split changed')
    corrections = bridge.human.get_records(args.corrections)
    bridge.validate_correction_gate(corrections, labels, packets)
    args.out.mkdir(parents=True, exist_ok=True)
    faithful_path = args.out/'validated_faithful_inputs.json'
    bridge.human.faithful_inputs(types.SimpleNamespace(review=args.review, corrections=args.corrections,
        auto_extractions=args.auto_inputs, packets=args.packets, out=faithful_path))
    corrected = {r['answer_id']: r for r in bridge.read(faithful_path)['records']}
    no_change = set(bridge.reviewed_no_change_ids(labels, packets, set(originals)))
    scope = reviewed_extraction_scope(labels, packets)
    scope_by_id = {r['answer_id']: r for r in scope}
    traces, pairs = [], []
    for aid, record in originals.items():
        case = cases[record['case_id']]
        before = actual_effects(record, record['extraction'], runner, registry, case)
        a = bridge.recompute(record, record['extraction'], runner, registry, case, 'identity_replay')
        for metric in bridge.EGES + ['Eff']:
            bridge.require(bridge.equal(a[metric], record['original_numeric_proposals'][metric]), 'Original real trial identity differs')
        traces.append({'answer_id': aid, 'source_trial_id': record['trial_id'], 'split': record['split'],
                       'auto': before, 'identity_equal_actual_trial': True, 'expert_pair': False})
        if aid not in corrected and aid not in no_change:
            continue
        extraction = corrected[aid]['extraction'] if aid in corrected else record['extraction']
        b = bridge.recompute(record, extraction, runner, registry, case, 'faithful_reviewed_fields_only')
        after = actual_effects(record, extraction, runner, registry, case)
        pairs.append({'answer_id': aid, 'split': record['split'],
                      'completed_prespecified_extraction_scope': scope_by_id[aid]['completed_prespecified_extraction_scope'],
                      'pair_kind': 'reviewed_correction' if aid in corrected else 'reviewed_no_change',
                      'changed_extraction_fields': b['changed_extraction_fields'],
                      'potentially_affected_original_EGES_components': b['affected_eges_components'],
                      'auto': before, 'faithful': after, **pair_values(a, b, before, after)})
    split_results = {}
    for split in ['audit_dev', 'audit_holdout']:
        group = [r for r in scope if r['split'] == split]
        complete = [r for r in group if r['completed_prespecified_extraction_scope']]
        paired = [r for r in pairs if r['split'] == split and r['completed_prespecified_extraction_scope']]
        split_results[split] = {'planned_answers': len(group), 'completed_prespecified_field_audit_answers': len(complete),
            'confirmed_extraction_error': fraction(sum(r['confirmed_extraction_error'] for r in complete), len(complete)),
            'confirmed_error_with_actual_original_scorer_dependency': {
                'numerator': sum(bool(r['potentially_affected_original_EGES_components']) for r in paired),
                'completed_prespecified_field_audit_denominator': len(complete),
                'dependency_classification_pending_answers': len(complete) - len(paired),
                'fraction': (sum(bool(r['potentially_affected_original_EGES_components']) for r in paired) / len(complete))
                    if complete and len(paired) == len(complete) else None,
                'meaning': 'A corrected field actually consumed by an original EGES component; not merely a review-item label or a claim of changed numerical score.'},
            'complete_review_with_verified_auto_faithful_pair': len(paired),
            'completed_review_awaiting_auto_or_correction': len(complete) - len(paired),
            'answers_with_changed_EGES_evidence_selection': fraction(sum(bool(r['evidence_selection_changed_components']) for r in paired), len(paired)),
            'answers_with_changed_step_reference': fraction(sum(r['step_reference_changed'] for r in paired), len(paired)),
            'na_transition_counts': {k: {'created': sum(k in r['na_created'] for r in paired),
                                       'resolved': sum(k in r['na_resolved'] for r in paired),
                                       'paired_answer_denominator': len(paired)} for k in METRICS}}
    result = {'status': 'scoped_review_statistics_available' if pairs else 'needs_human_labels',
        'new_model_requests': 0, 'expert_labels_added': 0, 'formal_eligible': False,
        'step_audit': audit_steps(args.local_step_audit),
        'extraction_audit': {'answers': scope, 'splits': split_results, 'paired_effects': pairs,
                            'partial_review_pair_count_excluded_from_complete_denominator': sum(not r['completed_prespecified_extraction_scope'] for r in pairs)},
        'actual_auto_evidence_traces': len(traces), 'actual_identity_replays': len(traces),
        'step_reference_boundary': 'score_steps reads the unchanged original full answer and question ID, independently of teacher extraction. Faithful teacher-field corrections cannot change that deterministic input; SR/SP/reference remain fixed. EGES knowledge-base selections are traced separately.',
        'evidence_selection_scope': 'Actual scorer lookups/rows/status, not expert-confirmed applicability. Score-input-only changes are separate from reference-selection changes.',
        'absence_note': 'Zero reviewed denominators imply NA rates and no expert effect. Numeric zero NA-transition event counts are bookkeeping over zero pairs, not demonstrated stability.',
        'inputs': {k: bind(p) for k, p in {'auto_inputs': args.auto_inputs, 'review': args.review,
            'corrections': args.corrections, 'local_manifest': args.local_step_audit/'manifest.json',
            'local_review': args.local_step_audit/'review_rows.csv', 'script': __file__,
            'bridge': bridge.__file__, 'step_adapter': ROOT/'scripts/cce_validation.py'}.items()}}
    bridge.save(args.out/'actual_evidence_traces.json', {'records': traces, 'new_model_requests': 0, 'expert_pairs': 0})
    bridge.save(args.out/'summary.json', result)
    bridge.save(args.out/'software_checks.json', software_checks())
    bridge.save(args.out/'execution.json', {'executable': sys.executable, 'argv': sys.argv, 'new_model_requests': 0,
        'input_and_script_sha256': result['inputs']})
    print(json.dumps({'status': result['status'], 'actual_identity_replays': len(traces),
                      'expert_pairs': len(pairs), 'new_model_requests': 0}))


if __name__ == '__main__':
    main()
