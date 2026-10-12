"""Offline verification on the original five exposed development answers.

No confirmation answers, score recomputation, provider, or embeddings are used.
"""
import argparse
import collections
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_record_diagnostics_v2 as candidate
import cce_partial_components_v1 as original
import cce_posthoc_source_backend_v3 as ground
import cce_grounded_extraction_fieldwise_base_v1 as wire

R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'
CASES = ROOT / 'artifacts/cce_validation/optimizer_20261010/grounded_development_v7/cases.json'
CELLS = R3 / 'uniform_v7/actual_01/cells.json'
READ = {}


def read(path):
    path = Path(path)
    data = path.read_bytes()
    READ[str(path.resolve())] = hashlib.sha256(data).hexdigest()
    return json.loads(data.decode('utf-8-sig'))


def bind(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf8')).hexdigest()


def main(args):
    out = Path(args.out).resolve()
    assert not out.exists(), 'NEW_OUTPUT_REQUIRED'
    cases, cells = read(CASES)['cases'], read(CELLS)
    assert {c['anonymous_answer_id'] for c in cases} == {'A01','A02','A03','A04','A05'}
    # This comparator executes the unchanged original audit with exactly its
    # missing dependency supplied locally. It does not mutate any module.
    explicit_original = SimpleNamespace(**vars(ground), _expand_ref=wire._expand_ref)
    summaries, actual, controls, inputs = [], [], [], []
    for case in cases:
        cid = case['anonymous_answer_id']
        row = next(r for r in cells if r['cohort'] == 'development' and r['cell_id'] == cid)
        raw_binding, = [b for b in row['source_bindings'] if b['sha256'] == row['raw_sha256']]
        payload = read(raw_binding['path'])
        assert READ[str(Path(raw_binding['path']).resolve())] == row['raw_sha256']
        doc = ground.document(case['model_response'], ground.source_id_for_case(case))
        assert doc['source_id'] == payload['grounded_extraction']['source_id']
        assert doc['answer_sha256'] == case['answer_sha256']
        posthoc = read(row['posthoc_record']['path'])
        assert READ[str(Path(row['posthoc_record']['path']).resolve())] == row['posthoc_record']['sha256']
        before_digest = digest([payload, doc])
        before = original.records_audit(payload, doc, ground)
        after = candidate.records_audit(payload, doc, ground)
        reference = original.records_audit(payload, doc, explicit_original)
        assert after == reference, 'DIAGNOSTIC_BEHAVIOR_DIFFERS_BEYOND_MISSING_INTERFACE'
        assert digest([payload, doc]) == before_digest
        stored = posthoc['conversion']['source_audit']['resolved']
        compared_fields = 0
        for record in after[0]:
            source_row = next(x for x in stored[record['group']] if x['id'] == record['id'])
            for key, value in record['resolved_fields'].items():
                assert value == source_row[wire.WIRE_MAPS[record['group']][key]]
                assert doc['text'][value['start']:value['end']] == value['quote']
                compared_fields += 1
            if 'name' in record:
                assert record['name'] == source_row['name']
        summary = {'answer_id': cid, 'question_id': case['question_id'], 'records': len(after[0]),
            'original_local_valid': sum(x['valid_shape_and_local_source'] for x in before[0]),
            'candidate_local_valid': sum(x['valid_shape_and_local_source'] for x in after[0]),
            'old_errors': dict(collections.Counter(x['code'] for x in before[1])),
            'new_errors': dict(collections.Counter(x['code'] for x in after[1])),
            'stored_full_conversion_source_fields_matched': compared_fields,
            'original_with_explicit_dependency_equal': True, 'source_and_raw_unchanged': True,
            'saved_scores_not_recomputed': True, 'raw_source': raw_binding,
            'saved_posthoc_source': row['posthoc_record']}
        summaries.append(summary)
        actual.append({'answer_id': cid, 'before': before, 'after': after})
        inputs.append((payload, doc))
    payload, doc = inputs[0]
    mutations = []
    bad = copy.deepcopy(payload); bad['grounded_extraction']['method_mentions'][0]['u'] = 'L999999'
    mutations.append(('unknown_source_unit', bad, 'method_mentions', 0, 'schema'))
    bad = copy.deepcopy(payload); bad['grounded_extraction']['method_mentions'][0]['n'] = 'ABSENT_LITERAL_X987654'
    mutations.append(('absent_literal', bad, 'method_mentions', 0, 'name'))
    bad = copy.deepcopy(payload); bad['grounded_extraction']['method_mentions'][0]['a'] = 999999
    mutations.append(('nonexistent_occurrence', bad, 'method_mentions', 0, 'name'))
    bad = copy.deepcopy(payload); bad['grounded_extraction']['operations'][0]['d'] = 'D999999'
    mutations.append(('unknown_duration_candidate', bad, 'operations', 0, 'schema'))
    bad = copy.deepcopy(payload); bad['grounded_extraction']['entities'][0] = 17
    mutations.append(('malformed_entity_record', bad, 'entities', 0, 'schema'))
    bad = copy.deepcopy(payload); bad['grounded_extraction']['method_mentions'].append(copy.deepcopy(bad['grounded_extraction']['method_mentions'][0]))
    mutations.append(('duplicate_record_id', bad, 'method_mentions', 0, 'duplicate'))
    for name, bad, group, index, kind in mutations:
        before_digest = digest(bad)
        result = candidate.records_audit(bad, doc, ground)
        assert result == original.records_audit(bad, doc, explicit_original)
        target = next(r for r in result[0] if r['pointer'] == '/grounded_extraction/' + group + '/' + str(index))
        assert not target['valid_shape_and_local_source'] and target['errors']
        assert not any("has no attribute '_expand_ref'" in x['code'] for x in result[1])
        if kind == 'name':
            assert any('NAME_' in x['code'] for x in target['errors'])
        if kind == 'duplicate':
            assert target['id'] in result[2] and any(x['code'] == 'DUPLICATE_GLOBAL_RECORD_ID' for x in target['errors'])
        assert digest(bad) == before_digest
        controls.append({'name': name, 'software_fixture_only': True, 'target': target,
                         'original_with_explicit_dependency_equal': True, 'raw_unchanged': True})
    # A missing array is reported; it is not silently presented as an empty,
    # valid group. The remaining record-local diagnostics remain available.
    bad = copy.deepcopy(payload); bad['grounded_extraction']['entities'] = None
    missing = candidate.records_audit(bad, doc, ground)
    assert any(x['code'] == 'RECORD_ARRAY_REQUIRED' for x in missing[1])
    assert missing == original.records_audit(bad, doc, explicit_original)
    controls.append({'name': 'missing_entity_array', 'software_fixture_only': True, 'errors': missing[1]})
    for path, sha in READ.items():
        assert bind(path)['sha256'] == sha
    # Verify the scientific configuration remains exactly the registered one.
    freeze = read(R3 / 'confirmation_configuration_freeze.json')
    for item in freeze['bindings']:
        assert bind(item['path'])['sha256'] == item['sha256']
    totals = {'actual_development_answers': len(summaries),
        'actual_records': sum(r['records'] for r in summaries),
        'original_local_valid': sum(r['original_local_valid'] for r in summaries),
        'candidate_local_valid': sum(r['candidate_local_valid'] for r in summaries),
        'source_fields_matched_to_existing_conversion': sum(r['stored_full_conversion_source_fields_matched'] for r in summaries),
        'negative_software_controls': len(controls), 'negative_controls_rejected': len(controls),
        'new_model_calls': 0, 'new_embeddings': 0, 'new_score_computations': 0,
        'confirmation_answer_bodies_read': 0, 'frozen_scientific_configuration_unchanged': True,
        'scientific_accuracy_estimated': False, 'diagnostic_only_not_primary_adoption': True,
        'created_utc': datetime.now(timezone.utc).isoformat(), 'actual_command': [sys.executable, *sys.argv]}
    save(out / 'actual_records.json', actual)
    save(out / 'negative_controls.json', controls)
    save(out / 'per_answer.json', summaries)
    save(out / 'summary.json', totals)
    save(out / 'verification.json', {'status': 'pass', 'input_bindings': [{'path': p,'sha256':h} for p,h in sorted(READ.items())],
        'code_bindings': [bind(p) for p in [__file__, candidate.__file__, original.__file__, ground.__file__, wire.__file__]],
        'outputs': [bind(p) for p in sorted(out.iterdir())], 'new_model_calls': 0})
    print(json.dumps(totals, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args())
