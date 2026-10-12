"""Offline CCE replay with explicit label-channel applicability and AF family evidence.

Uses saved judge relations and original per-channel EGES arithmetic. Native
proteins/direct stains do not require an antibody marker. No model requests,
direct-score imputation, answer-ID conditions, or selection by achieved score.
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import csv
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_scoped_midpoint_scorer_v1 as base
import cce_target_catalog_role_fix_v2 as catalog
from cce_grounded_offline_scoring_v1 import DIRECT, EGES, derive
from cce_scales_source_key_alias_v1 import source_key_alias

VERSION = 'cce-typed-label-scorer-v2'
CHANNELS = ['s_target_match', 's_marker_fluor_compat', 's_method_fluor_compat']


def key(value):
    return re.sub(r'[\s_\-]+', '', str(value)).casefold()


def af_identity(value):
    match = re.fullmatch(r'\s*(?:Alexa\s*Fluor|AF)\s*(\d{3})?\s*', str(value), re.I)
    return ('Alexa Fluor' + (' ' + match[1] if match[1] else '')) if match else None


def label_type(fluor, policy):
    for group in ('native_fluorescent_protein', 'direct_stain'):
        if key(fluor) in {key(n) for n in policy['standalone_types'][group]}:
            return group
    return 'targeted_or_unclassified_reagent'


def nullable_min(values):
    if not values:
        return None
    if any(v == 0 for v in values):
        return 0.0
    return None if any(v is None for v in values) else min(values)


def compatibility(runner, marker, fluor, targets, preferences, policy):
    requested = preferences.get(runner._normalize_name(marker))
    selected = targets
    if requested:
        selected = [t for t in targets if all(t.get(a) == requested['scope'][b]
                    for a, b in catalog.SCOPE_KEYS.items())]
        if not selected:
            raise ValueError('Declared task marker scope absent from question')
    result = catalog.marker_scope_lookup(runner, marker, fluor, selected)
    result['declared_task_scope'] = requested
    result['exact_lookup_value'] = result['value']
    # Specific positive/negative facts always take precedence over approximation.
    if result['value'] is not None:
        result['evidence_level'] = 'existing_specific_table_value'
        return result
    if not af_identity(fluor) or not policy.get('af_family_approximation'):
        result['evidence_level'] = 'unresolved'
        return result
    if result['status'] in ('conflicting_authored_values_unresolved', 'applicable_scopes_disagree'):
        result['evidence_level'] = 'conflicting_specific_values'
        return result
    donor_cells = []
    for index in result['selected_row_indices']:
        row = runner.TISSUE_KB[index]
        for column in policy['af_family_approximation']['donor_columns']:
            value = row.get(column)
            if type(value) in (int, float) and value in (0, 1):
                donor_cells.append({'row_index': index, 'column': column, 'value': value,
                                    'scope': {k: row.get(k) for k in catalog.SCOPE_KEYS.values()}})
    known = {r['value'] for r in donor_cells}
    result['family_donor_cells'] = donor_cells
    result['family_rule'] = policy['af_family_approximation']['version']
    if len(known) == 1:
        result.update(value=bool(next(iter(known))), status='AF_family_consensus_approximation',
                      evidence_level='user_authorized_family_approximation')
    else:
        result.update(evidence_level='unresolved_family_evidence',
                      family_issue='donors_disagree' if known else 'no_known_donor_cells')
    return result


@contextlib.contextmanager
def using_lookup(runner, targets, preferences, policy):
    oldmatch, oldcompat = runner._match_marker_to_targets, runner._get_marker_fluor_compat
    trace = []

    def match(marker, query_targets, fluor_name=None):
        return oldmatch(marker, catalog.expanded_targets(query_targets), fluor_name=fluor_name)

    def compat(marker, fluor):
        result = compatibility(runner, marker, fluor, targets, preferences, policy)
        trace.append(result)
        return result['value']

    runner._match_marker_to_targets, runner._get_marker_fluor_compat = match, compat
    try:
        yield trace
    finally:
        runner._match_marker_to_targets, runner._get_marker_fluor_compat = oldmatch, oldcompat


def validate_evidence(doc, span):
    if span.get('answer_sha256') not in (None, doc['answer_sha256']):
        raise ValueError('Label evidence belongs to another answer')
    base.verify_span(doc['text'], span)


def score_labels(projection, runner, quantitative, demand, targets, policy, entities=None, doc=None):
    entities = entities or {}
    rows, resolved, pending = [], [], []
    for pair in projection['pairs']:
        if doc and pair.get('evidence'):
            spans = pair['evidence'] if isinstance(pair['evidence'], list) else [pair['evidence']]
            for span in spans:
                validate_evidence(doc, span)
        fluor = pair['fluor_literal']
        original_marker = pair.get('marker_literal')
        kind = label_type(fluor, policy)
        standalone = kind != 'targeted_or_unclassified_reagent'
        marker = '' if standalone else (original_marker or '')
        original = runner.calculate_effectiveness_score(quantitative, demand,
                    runner.MODEL_SPACE_SIGNED, {fluor: marker}, targets)
        channels = {k: original[k] for k in CHANNELS}
        applicable = {k: bool(marker) for k in CHANNELS[:2]}
        applicable['s_method_fluor_compat'] = True
        # An unbound targeted relation is a real missing relation, unlike native GFP.
        if not standalone and not marker and pair['kind'] == 'unresolved_relation':
            applicable.update(s_target_match=True, s_marker_fluor_compat=True)
        if standalone:
            channels['s_target_match'] = channels['s_marker_fluor_compat'] = None
        rows.append({'pair_id': pair['pair_id'], 'entity_id': pair.get('entity_id'),
                     'fluorophore': fluor, 'reported_marker': original_marker,
                     'reported_target_literal': pair.get('reported_target_literal'),
                     'label_type': kind, 'original_function_input': {fluor: marker},
                     'applicable': applicable, 'channels': channels,
                     'not_applicable_reason': 'standalone fluorescence has no antibody target-pair channel' if standalone else None,
                     'source_evidence': pair.get('evidence'),
                     'compatibility_audit': original['compatibility_audit']})
    # Only an actual dependency of this metric may withhold its value.
    for uncertainty in projection.get('explicit_label_uncertainties', []):
        item = copy.deepcopy(uncertainty)
        entity = entities.get(item.get('entity_id'), {})
        relevant = [r for r in rows if r.get('entity_id') == item.get('entity_id')]
        literal = entity.get('literal_name', item.get('literal_name', ''))
        if relevant and all(r['label_type'] != 'targeted_or_unclassified_reagent' for r in relevant):
            item['resolution'] = 'antibody relation is not applicable to this standalone signal'
            resolved.append(item)
            continue
        if literal and label_type(literal, policy) != 'targeted_or_unclassified_reagent' and relevant:
            item['resolution'] = 'standalone signal identity already retained'
            resolved.append(item)
            continue
        # A secondary antibody's carrier details do not invalidate an explicit fluor-target pair.
        support = entity.get('supporting_evidence') or entity.get('name') or {}
        context = support.get('quote', '')
        dyes = re.findall(r'Alexa\s*Fluor\s*\d{3}', literal, flags=re.I)
        matching = [r for r in rows if r['reported_marker'] and
                    af_identity(r['fluorophore']) in {af_identity(d) for d in dyes}]
        if (item['kind'] == 'reported_unknown_label_entity' and matching
                and re.search(r'secondary\s+antibody|二抗', context, re.I)):
            if doc:
                validate_evidence(doc, support)
            item.update(resolution='explicit target-fluor relation already covers this secondary carrier',
                        supported_pair_ids=[r['pair_id'] for r in matching], source_evidence=support)
            resolved.append(item)
            continue
        pending.append(item)
    channel_results = {}
    for channel in CHANNELS:
        values = [r['channels'][channel] for r in rows if r['applicable'][channel]]
        channel_results[channel] = {'applicable': bool(values), 'value': nullable_min(values),
                                   'contributing_pairs': [r['pair_id'] for r in rows if r['applicable'][channel]]}
    active = [v['value'] for v in channel_results.values() if v['applicable']]
    known_min = nullable_min(active)
    # Pending required relationships remain explicit inputs to the minimum.
    label = nullable_min(active + ([None] if pending else []))
    return {'version': VERSION, 's_label': label, 'channels': {k: v['value'] for k, v in channel_results.items()},
            'channel_applicability': channel_results, 'pair_results': rows,
            'resolved_uncertainties': resolved, 'remaining_uncertainties': pending,
            'minimum_of_available_applicable_channels': known_min,
            'task_target_coverage': 'native/direct task coverage remains separate from antibody-pair applicability',
            'new_model_calls': 0, 'expert_validated': False}


def project_annotation(annotation, doc):
    if annotation['answer_sha256'] != doc['answer_sha256']:
        raise ValueError('Annotation answer mismatch')
    pairs = []
    for index, relation in enumerate(annotation['relations']):
        spans = relation['source_spans']
        if not spans:
            raise ValueError('Annotation relation requires source evidence')
        for span in spans:
            validate_evidence(doc, span)
        pairs.append({'pair_id': 'semantic:' + str(index), 'fluor_literal': relation['fluorophore'],
                      'marker_literal': relation['marker'] or None, 'kind': 'supported_relation' if relation['marker'] else 'source_key_only',
                      'evidence': spans, 'semantic_basis': relation['basis']})
    return {'pairs': pairs, 'explicit_label_uncertainties': annotation.get('remaining_uncertainties', [])}


@source_key_alias()
def replay_row(row, post, policy, config, runner, registry, annotation=None, doc=None):
    old = row['metrics']
    conversion = post.get('conversion')
    if conversion:
        projection = conversion['label_occurrence_projection']
        entities = {e['id']: e for e in conversion['source_audit']['resolved']['entities']}
        quantitative = row['quantitative_data']
        demand = post['numeric']['user_preference_vector']
    elif annotation:
        meta = runner.QUESTION_META_KB[registry.questions[str(row['question_id'])]['question_id']]
        extraction = post['views']['method']['projected_extraction']
        quantitative = {'method_name': extraction['method_name'], 'tissue_ri_value': meta.get('tissue_ri_value'),
                        'sample_tier': meta.get('tissue_tier_code'), 'total_time_hours': None}
        demand = registry.questions[str(row['question_id'])]['demand_vector']
        entities = {}
    else:
        return {**copy.deepcopy(row), 'version': VERSION, 'typed_replay_status': 'partial_label_source_needed',
                'comparison_metrics': old, 'typed_changes': {}}
    if annotation:
        projection = project_annotation(annotation, doc)
    meta = runner.QUESTION_META_KB[registry.questions[str(row['question_id'])]['question_id']]
    targets = meta['marker_query_targets']
    preferences = config.get('task_marker_scopes', {}).get(str(row['question_id']), {})
    with using_lookup(runner, targets, preferences, policy) as trace:
        label = score_labels(projection, runner, quantitative, demand, targets, policy, entities, doc)
    components = {k: old[k] for k in DIRECT + EGES}
    components['s_label'] = label['s_label']
    metrics = derive(components, {k: old[k] for k in ('sr', 'sp')}, True)
    for k in DIRECT + ['s_method', 's_trans', 's_time', 'sr', 'sp', 'Com', 'Cor']:
        assert metrics[k] == old[k], ('unaffected metric changed', k)
    result = copy.deepcopy(row)
    result.update(version=VERSION, comparison_metrics=old, metrics=metrics,
                  complete_numeric_CCE=base.complete(metrics), typed_replay_status='replayed',
                  label_derivation=label, compatibility_lookup_trace=trace,
                  typed_semantic_annotation=bool(annotation),
                  remaining_dependencies={'time': row.get('time_derivation', {}).get('issues', []),
                                          'label_relations': label['remaining_uncertainties'],
                                          'compatibility': [r for r in trace if r['value'] is None]},
                  typed_changes={k: {'before': old[k], 'after': v} for k, v in metrics.items() if old[k] != v})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--source-index', required=True, type=Path)
    parser.add_argument('--decompositions', type=Path)
    parser.add_argument('--additional-label-annotations', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    rows, config, policy = base.read(args.baseline), base.read(args.config), base.read(args.policy)
    sources = {r['cell_id']: r for r in base.read(args.source_index)['records']}
    annotations = {}
    for path in (args.decompositions, args.additional_label_annotations):
        if path:
            annotations.update({r['answer_sha256']: r for r in base.read(path)['results']})
    manifest = {name: base.bind(path) for name, path in (
        ('baseline', args.baseline), ('config', args.config), ('policy', args.policy),
        ('source_index', args.source_index), ('entrypoint', __file__),
        ('original_scorer', ROOT / 'OEQ_run_grading_new.py'),
        ('tissue_table', ROOT / 'KnowledgeBase/tissue.json'),
        ('method_fluor_table', ROOT / 'KnowledgeBase/method_fluro_compati.json'))}
    manifest.update(version=VERSION, new_model_calls=0, expert_records=0,
                    decompositions=base.bind(args.decompositions) if args.decompositions else None,
                    additional_label_annotations=base.bind(args.additional_label_annotations) if args.additional_label_annotations else None)
    runner, registry = base.runtime()
    output = []
    for row in rows:
        if not row.get('source_record'):
            output.append({**row, 'typed_replay_status': 'no_saved_return'})
            continue
        source = sources[row['cell_id']]
        assert base.bind(source['posthoc_record']['path']) == source['posthoc_record']
        assert base.bind(source['source_document']['path']) == source['source_document']
        post, doc = base.read(source['posthoc_record']['path']), base.read(source['source_document']['path'])
        annotation = annotations.get(doc['answer_sha256'])
        result = replay_row(row, post, policy, config, runner, registry, annotation, doc)
        result['source_document'] = source['source_document']
        result['answer_sha256'] = doc['answer_sha256']
        base.save(args.out / 'records' / row['cohort'] / (row['cell_id'] + '.json'), result)
        output.append(result)
    actual = [r for r in output if r.get('source_record')]
    summary = {'version': VERSION, 'saved_returns': len(actual),
               'complete_before': sum(base.complete(r['metrics']) for r in rows),
               'complete_after': sum(r['complete_numeric_CCE'] for r in actual),
               'labels_available_before': sum(r['metrics']['s_label'] is not None for r in rows),
               'labels_available_after': sum(r['metrics']['s_label'] is not None for r in actual),
               'missing_after': {k: sum(r['metrics'][k] is None for r in actual) for k in ('Cor', 's_label', 's_time', 'Eff')},
               'changed_cells': [r['cell_id'] for r in actual if r.get('typed_changes')],
               'complete_lost': [r['cell_id'] for r in actual if base.complete(r['comparison_metrics']) and not r['complete_numeric_CCE']],
               'new_model_calls': 0, 'direct_scores_rejudged': False,
               'claim_scope': 'paired archived-return scoring replay, not new evaluator stability or prospective validation'}
    base.save(args.out / 'execution_manifest.json', manifest)
    base.save(args.out / 'results.json', output)
    base.save(args.out / 'summary.json', summary)
    fields = ['cohort', 'cell_id', 'question_id', 'complete_numeric_CCE'] + DIRECT + EGES + ['sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV']
    with (args.out / 'per_answer.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in output:
            writer.writerow({**{k: row.get(k) for k in fields if k not in row['metrics']}, **row['metrics']})
    for name in ('baseline', 'config', 'source_index', 'original_scorer', 'tissue_table', 'method_fluor_table'):
        assert base.bind(manifest[name]['path']) == manifest[name]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
