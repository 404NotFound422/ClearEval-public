"""Audit the original five development answers against their actual rubric/context.

This exports saved judgments and author review notes. It never computes new
scientific scores, invokes a judge, or opens the Round 3 confirmation answers.
"""
import argparse
import collections
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_posthoc_source_backend_v3 as ground
from cce_grounded_extraction_fieldwise_base_v1 import _expand_ref

R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'
CASES = ROOT / 'artifacts/cce_validation/optimizer_20261010/grounded_development_v7/cases.json'
CELLS = R3 / 'uniform_v7/actual_01/cells.json'
EVIDENCE = ROOT / 'artifacts/cce_validation/reference_recovery/supplement_bound/evidence_manifest.json'
RUBRIC = ROOT / 'prompts/eval_oeq_teacher_rubric.txt'
DIRECT = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem']
SECTIONS = dict(zip(DIRECT, ['1.2', '2.1', '2.2', '2.3', '2.4']))
READ = {}


def text(path, expected=None):
    p = Path(path).resolve()
    data = p.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None:
        assert digest == expected, str(p)
    READ[str(p)] = digest
    return data.decode('utf-8-sig')


def read(path, expected=None):
    return json.loads(text(path, expected))


def binding(path):
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def save(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def rubric_part(prompt, section):
    start = re.search(r'^' + re.escape(section) + r'\s[^\n]+', prompt, re.M)
    assert start is not None, section
    tail = prompt[start.end():]
    stop = re.search(r'^(?:\d\.\d\s|\d\.\s|输出(?:格式|字段))', tail, re.M)
    assert stop is not None, section
    end = start.end() + stop.start()
    return {'start': start.start(), 'end': end, 'text': prompt[start.start():end].strip()}


def main(args):
    out = args.out.resolve()
    assert not out.exists(), 'Choose a fresh output directory.'
    notes = read(args.notes)
    cases = read(CASES)['cases']
    cells = read(CELLS)
    assert [c['anonymous_answer_id'] for c in cases] == ['A01','A02','A03','A04','A05']
    rubric = text(RUBRIC)
    manifest = read(EVIDENCE)['evidence']
    table_meta = manifest['FDISCO_TABLE_S1_P12']
    table = text(table_meta['text_path'], table_meta['text_sha256'])
    primary_meta = manifest['FDISCO_MAIN_CLEARING_P1']
    primary = text(primary_meta['extracted_text_path'], primary_meta['extracted_text_sha256'])
    # Numeric cells are read from the archived author-derived reference below;
    # the primary PDF page was also visually inspected by the author.
    for key in ['pdf', 'render_path']:
        p = Path(table_meta[key])
        expected = table_meta['pdf_sha256' if key == 'pdf' else 'render_sha256']
        assert binding(p)['sha256'] == expected
        READ[str(p.resolve())] = expected
    assert 'decreased by half' in re.sub(r'\s+', ' ', table)
    assert 'consisted of two steps: dehydration and refractive index matching' in primary
    packets, context, references = [], [], {}
    for case in cases:
        cid = case['anonymous_answer_id']
        cell = next(c for c in cells if c['cohort'] == 'development' and c['cell_id'] == cid)
        raw_binding, = [b for b in cell['source_bindings'] if b['sha256'] == cell['raw_sha256']]
        payload = read(raw_binding['path'], raw_binding['sha256'])
        prompt_path = Path(raw_binding['path']).with_name('prompt.txt')
        prompt_binding, = [b for b in cell['source_bindings'] if Path(b['path']) == prompt_path]
        prompt = text(prompt_path, prompt_binding['sha256'])
        doc = ground.document(case['model_response'], ground.source_id_for_case(case))
        assert doc['answer_sha256'] == case['answer_sha256']
        assert doc['source_id'] == payload['grounded_extraction']['source_id']
        refs = case['references']
        assert json.dumps(refs, ensure_ascii=False, sort_keys=True, separators=(',', ':')) in prompt
        for ref in refs:
            if ref['reference_id'] in references:
                assert references[ref['reference_id']] == ref
            references[ref['reference_id']] = ref
        context.append({'answer_id': cid, 'prompt': prompt_binding,
            'generic_shortening_note_present': 'Shortened timings in the table note are an author option' in prompt,
            'author_half_time_qualification_present': bool(re.search(r'\bhalf\b|减半|一半|50\s*%\s*(?:shorter|reduc)', prompt, re.I)),
            'unsupported_3mm_timing_disclosed': 'not_reported_for_3mm_no_interpolation' in prompt,
            'reference_ids': [r['reference_id'] for r in refs]})
        for metric in DIRECT:
            group = 'completeness' if metric == 'c_param' else 'correctness'
            score = payload['scores'][group][metric]
            evidence, = [e for e in payload['score_evidence'] if e['m'] == metric]
            spans = [ground.resolve(_expand_ref(ref), doc) for ref in evidence['u']]
            for span in spans:
                assert doc['text'][span['start']:span['end']] == span['quote']
            actual_rubric = rubric_part(prompt, SECTIONS[metric])
            original_rubric = rubric_part(rubric, SECTIONS[metric])
            normalize = lambda s: re.sub(r'\s+', ' ', s).lower()
            assert normalize(actual_rubric['text']) == normalize(original_rubric['text'])
            assert score['score'] == cell['posthoc_metrics'][metric]
            packets.append({'answer_id': cid, 'question_id': case['question_id'], 'metric': metric,
                'saved_score': score['score'], 'saved_reasoning': score['reasoning'],
                'saved_evidence_record': evidence, 'resolved_answer_spans': spans,
                'raw_source': raw_binding, 'raw_pointer': '/scores/' + group + '/' + metric,
                'actual_prompt_source': prompt_binding, 'actual_rubric': actual_rubric,
                'reference_ids': [r['reference_id'] for r in refs],
                'author_review_note': notes['metric_notes'].get(cid + '/' + metric),
                'expert_adjudicated': False, 'replacement_score': None})
    assert len(packets) == 25
    whole = references['FDISCO_SUPPLEMENT_V2_WHOLE_BRAIN']
    block = references['FDISCO_SUPPLEMENT_V2_BLOCK_3MM_UNTIMED']
    def hours(step):
        found = re.findall(r'for (\d+(?:\.\d+)?) hours', step['text'])
        assert len(found) == 1
        return float(found[0])
    thf_hours = hours(whole['steps'][0])
    dbe_hours = hours(whole['steps'][5])
    assert thf_hours == 12 and dbe_hours == 3
    assert block['applicability']['exact_3mm_schedule_supported'] is False
    assert all(s['timing_status'] == 'not_reported_for_3mm_no_interpolation' for s in block['steps'][:6])
    note_start = table.index('of each step could be decreased by half')
    note_quote = 'of each step could be decreased by half'
    qualification = {'evidence_id': 'FDISCO_TABLE_S1_P12', 'source': binding(table_meta['text_path']),
        'pdf': binding(table_meta['pdf']), 'page_one_based': 12,
        'source_span': {'start': note_start, 'end': note_start + len(note_quote), 'quote': note_quote},
        'meaning': 'The table permits halving step durations for fluorescence preservation; this is an option, not a required extra operation.',
        'exact_3mm_schedule_supplied': False, 'whole_route_validity_implied': False}
    candidate = [{'reference_id': key, 'original_reference_unchanged': ref,
        'additional_qualification_evidence': [qualification],
        'used_in_actual_judge_request': False,
        'source_steps_replaced': False, 'SR_SP_candidate_pool_changed': False}
        for key, ref in sorted(references.items())]
    findings = {
        'all_five_actual_prompts_contain_unmodified_registered_references': True,
        'generic_shortening_note_present': sum(x['generic_shortening_note_present'] for x in context),
        'quantitative_halving_note_present': sum(x['author_half_time_qualification_present'] for x in context),
        'block_answers_disclose_unavailable_exact_timing': [x['answer_id'] for x in context if x['unsupported_3mm_timing_disclosed']],
        'block_saved_parameter_scores': {x['answer_id']: x['saved_score'] for x in packets
            if x['metric'] == 'co_param' and x['answer_id'] in ['A02','A03','A04']},
        'whole_brain_table_THF_first_step_hours': thf_hours,
        'whole_brain_table_DBE_hours': dbe_hours,
        'author_option_half_THF_hours': thf_hours / 2,
        'quantitative_half_note_loss_is_observed': True,
        'causal_effect_of_note_restoration_on_judgments_measured': False,
        'saved_five_parameter_judgments_with_author_review_concern': 5,
        'numerical_parameter_scores_proven_wrong': None,
        'all_direct_proposals_have_bound_answer_evidence': len(packets),
        'bound_answer_evidence_does_not_prove_reference_or_rubric_entailment': True,
    }
    assert findings['generic_shortening_note_present'] == 5
    assert findings['quantitative_halving_note_present'] == 0
    assert findings['block_answers_disclose_unavailable_exact_timing'] == ['A02','A03','A04']
    out.mkdir(parents=True)
    save(out / 'metric_evidence_packets.json', packets)
    save(out / 'actual_prompt_context.json', context)
    save(out / 'findings.json', findings)
    save(out / 'reference_qualification_candidate.json', candidate)
    save(out / 'references_unchanged.json', references)
    summary = {'created_utc': datetime.now(timezone.utc).isoformat(),
        'actual_answers': 5, 'saved_direct_judgments': len(packets),
        'resolved_answer_citations': sum(len(x['resolved_answer_spans']) for x in packets),
        'author_flagged_metric_records': sum(x['author_review_note'] is not None for x in packets),
        'expert_judgments_added': 0, 'new_model_calls': 0, 'new_embeddings': 0,
        'new_scientific_score_computations': 0, 'confirmation_answer_bodies_read': 0,
        'scoring_rules_changed': False, 'original_scores_preserved': True,
        'candidate_context_tested_with_judge': False,
        'actual_command': [sys.executable, *sys.argv]}
    save(out / 'summary.json', summary)
    for path, digest in READ.items():
        assert binding(path)['sha256'] == digest
    save(out / 'verification.json', {'status': 'pass',
        'scope': 'Source identity, exact answer citations, rubric preservation, reference-context comparison and arithmetic only; not independent scientific adjudication.',
        'input_bindings': [{'path': p, 'sha256': h} for p,h in sorted(READ.items())],
        'code_bindings': [binding(__file__), binding(ground.__file__)],
        'output_bindings': [binding(p) for p in sorted(out.iterdir())]})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notes', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args())
