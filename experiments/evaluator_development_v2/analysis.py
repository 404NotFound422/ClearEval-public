"""Analyze actual records without changing their planned denominator."""
from collections import defaultdict
from pathlib import Path
import uuid

from .execution import attempt_records, proposal_vector, vectors
from .io import digest, file_hash, now, read, save
from .metrics import group_metrics
from .prepare import verify


def analyze(folder):
    folder = Path(folder).resolve()
    manifest = verify(folder)
    _, records = attempt_records(folder)
    cases = {row['id']: row for row in read(folder / 'cases.json')}
    judges = {row['id']: row for row in read(folder / 'judges.json')}
    processors = read(folder / 'processors.json')
    trials = read(folder / 'trials.json')
    by_trial = {row['id']: row for row in trials}
    invocations = set()
    for record in records:
        expected = by_trial[record['id']]
        for key in expected:
            if record[key] != expected[key]:
                raise ValueError('Recorded trial differs from frozen plan')
        if record['manifest_sha256'] != manifest['manifest_sha256']:
            raise ValueError('Attempt manifest mismatch')
        target = folder / 'attempts' / record['id'] / record['attempt_id']
        for name in ('request', 'receipt', 'parsed', 'tags_before', 'tags_after'):
            if record.get(name + '_sha256') and file_hash(target / (name + '.json')) != record[name + '_sha256']:
                raise ValueError('Bound attempt artifact changed')
        if record.get('response_sha256') and file_hash(target / 'response.json') != record['response_sha256']:
            raise ValueError('Raw response changed')
        retained_proposal = record.get('parsed_judge_vector_status') == 'COMPLETE'
        if record['technical_status'] == 'COMPLETE' or retained_proposal:
            if record['invocation_id'] in invocations:
                raise ValueError('An invocation was copied into multiple repeats')
            invocations.add(record['invocation_id'])
            judge = judges[record['judge_id']]
            if record['origin'] != 'EXTERNAL_ACTUAL':
                request = read(target / 'request.json')
                prompt = (folder / 'prompts' / (record['candidate_id'] + '.txt')).read_bytes().decode('utf-8')
                reconstructed = {'model': judge['model'], 'prompt': prompt, 'stream': False,
                    'think': False, 'format': 'json', 'options': judge['params']}
                if request['payload'] != reconstructed or request['payload_sha256'] != digest(reconstructed):
                    raise ValueError('Request differs from reconstructed actual information')
            parsed = read(target / 'parsed.json')
            from evaluator_integrity import parse_judge_object
            response = read(target / 'response.json')
            content = response.get('content') if record['origin'] == 'EXTERNAL_ACTUAL' else response.get('response')
            if parsed != parse_judge_object(content):
                raise ValueError('Parsed response differs from retained raw content')
            public = cases[record['candidate_id']]['input']
            if record['proposed_vector'] != proposal_vector(public, parsed):
                raise ValueError('Retained model proposal differs from actual raw teacher content')
            fields = public.get('requested_fields', [key for key in parsed if key != 'requirements'])
            structure = {field: {'present': field in parsed, 'value': parsed.get(field)} for field in fields}
            if record['structure_vector'] != structure:
                raise ValueError('Retained structure differs from actual raw teacher content')
            if record['technical_status'] == 'COMPLETE':
                fresh = vectors(public, parsed, processors)
                if (record['proposed_vector'], record['effective_vector'], record['mechanisms']) != fresh:
                    raise ValueError('Stored states differ from actual frozen processor recomputation')
            elif retained_proposal:
                try:
                    vectors(public, parsed, processors)
                except Exception as exc:
                    failure = record.get('failure') or {}
                    if (record.get('technical_stage') != 'GROUNDING_VALIDATION' or
                            failure.get('type') != type(exc).__name__ or failure.get('message') != str(exc)):
                        raise ValueError('Grounding failure differs from frozen processor recomputation') from exc
                else:
                    raise ValueError('Stored grounding failure cannot be reproduced')
    groups = defaultdict(list)
    for record in records:
        groups[record['candidate_id'], record['judge_id']].append(record)
    summaries = []
    for case in cases.values():
        requirements = [req['id'] for req in case['input'].get('requirements', [])]
        for judge in judges.values():
            observed = groups[case['id'], judge['id']]
            metrics = group_metrics(observed, requirements, manifest['repeats'])
            comparisons = []
            for processor in processors:
                method_records = []
                for record in observed:
                    if record['technical_status'] == 'COMPLETE':
                        row = {**record, 'effective_vector': record['mechanisms'][processor['id']]['effective_vector']}
                        method_records.append(row)
                    else:
                        method_records.append(record)
                comparisons.append({'processor': processor['id'],
                    'same_public_input_sha256': case['input_sha256'],
                    'metrics': group_metrics(method_records, requirements, manifest['repeats'])})
            summaries.append({'candidate_id': case['id'], 'judge_id': judge['id'],
                'teacher_family': judge['family'], 'teacher_model': judge['model'],
                'declared_revision': judge['revision'], 'declared_params': judge['params'],
                'prompt_sha256': next(t['prompt_sha256'] for t in trials if t['candidate_id'] == case['id']),
                **metrics, 'processor_comparison': comparisons})
    cross_family = []
    for case in cases.values():
        identities = list(judges.values())
        for index, a in enumerate(identities):
            for b in identities[index + 1:]:
                if a['family'] == b['family'] or 'UNKNOWN' in (a['family'], b['family']):
                    continue
                left = [r for r in groups[case['id'], a['id']] if r['origin'] in ('OLLAMA_ACTUAL', 'EXTERNAL_ACTUAL') and r['technical_status'] == 'COMPLETE']
                right = [r for r in groups[case['id'], b['id']] if r['origin'] in ('OLLAMA_ACTUAL', 'EXTERNAL_ACTUAL') and r['technical_status'] == 'COMPLETE']
                pairs = [(x, y) for x in left for y in right]
                cross_family.append({'candidate_id': case['id'], 'judge_a': a['id'], 'judge_b': b['id'],
                    'family_a': a['family'], 'family_b': b['family'], 'same_public_input_sha256': case['input_sha256'],
                    'three_per_teacher': len(left) >= 3 and len(right) >= 3, 'paired_comparisons': len(pairs),
                    'proposed_vector_disagreement_rate': sum(x['proposed_vector'] != y['proposed_vector'] for x, y in pairs) / len(pairs) if pairs else None,
                    'effective_vector_disagreement_rate': sum(x['effective_vector'] != y['effective_vector'] for x, y in pairs) / len(pairs) if pairs else None,
                    'scientific_accuracy': None})
    result = {'schema': 'evaluator-experiment-analysis-v2', 'at': now(),
        'round_id': manifest['round_id'], 'manifest_sha256': manifest['manifest_sha256'],
        'planned_trials': len(trials), 'recorded_attempts': len(records),
        'independent_families_observed': sorted({r['teacher_family'] for r in summaries if r['independent_complete']}),
        'scientific_accuracy': None, 'groups': summaries, 'cross_family': cross_family,
        'interpretation': ('Entropy/flip and same-information processing describe these actual inputs only. '
            'All unknown states have zero decisive coverage; risk requires separate reference labels. '
            'Fixed replay, fake transport and cache are not independent judge repetitions. '
            'Unknown revisions/parameters limit model-version comparisons.')}
    save(folder / 'analysis' / (uuid.uuid4().hex + '.json'), result)
    return result