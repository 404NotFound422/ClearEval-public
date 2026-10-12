"""Explain missing common questions without equating unrun cases with absent evidence."""
import argparse
import collections
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cce_validation import ROOT, OUT, read, write, table, filehash


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis', type=Path, default=OUT / 'analysis_two_source')
    p.add_argument('--out', type=Path, default=OUT / 'common_set_gaps')
    args = p.parse_args()
    inputs = {
        'numeric_rows': args.analysis / 'revised_full_numeric_rows.json',
        'cohort': OUT / 'cohort_frozen.json',
        'historical_questions': ROOT / 'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json',
        'bindings': OUT / 'inventory/answer_score_bindings.json',
        'joint_summary': args.analysis / 'joint_summary.json',
    }
    rows = read(inputs['numeric_rows'])
    models = read(inputs['cohort'])['models']
    questions = read(inputs['historical_questions'])
    if isinstance(questions, dict):
        raise ValueError('Expected the frozen question list; do not infer another question universe')
    qids = sorted({str(q['question_id']) for q in questions}, key=int)
    indexed = {(r['model'], str(r['question_id'])): r for r in rows}
    bindings = {(r['model'], str(r['question_id'])): r for r in read(inputs['bindings'])}
    assert len(indexed) == len(rows) and set(m for m, q in indexed) == set(models)
    assert all(q in qids for m, q in indexed)
    details, wide, per_question = [], [], []
    for qid in qids:
        current = []
        for model in models:
            r = indexed.get((model, qid))
            binding = bindings.get((model, qid), {})
            if r is None:
                state = 'answer_missing'
            elif finite(r.get('Com')) and finite(r.get('Cor')) and finite(r.get('Eff')):
                state = 'provisional_CCE_numeric'
            elif r.get('step_missing_reason') == 'revised_step_score_not_run':
                state = 'revised_steps_not_run'
            elif r.get('step_missing_reason') == 'reference_insufficient':
                state = 'screened_reference_insufficient'
            else:
                state = 'evaluated_other_incomplete'
            missing = [k for k in ['sr', 'sp', 'c_param', 'Com', 'Cor', 'Eff', 'IA', 'HV'] if not r or not finite(r.get(k))]
            cell = {
                'question_id': qid, 'model': model,
                'answer_present': r is not None,
                'question_sha256': (r or {}).get('question_sha256'),
                'answer_sha256': (r or {}).get('answer_sha256') or binding.get('answer_sha256'),
                'state': state, 'missing_components': missing,
                'original_step_missing_reason': (r or {}).get('step_missing_reason'),
                'historical_score_complete': binding.get('legacy_score_row_complete') if r else None,
                'historical_identity_eligible': (r or {}).get('identity_eligible') if r else None,
                'historical_score_error_coexists_with_step_not_run': bool(r and not binding.get('legacy_score_row_complete') and state == 'revised_steps_not_run'),
                'numeric_CCE_complete': state == 'provisional_CCE_numeric',
                'formal_eligible': bool(r and r.get('formal_eligible')),
                'reference_status': (r or {}).get('reference_status'),
                'numeric_scope': (r or {}).get('numeric_scope'),
                'reference_gap_verified_for_this_case': state == 'screened_reference_insufficient',
                'next_action': {
                    'answer_missing': 'Recover the missing archived answer, or keep this model/question absent.',
                    'provisional_CCE_numeric': 'Confirm source applicability and inherited-score provenance; retain provisional numbers.',
                    'revised_steps_not_run': 'Audit task/route and reference applicability before scoring; an unrun case does not prove a source is absent.',
                    'screened_reference_insufficient': 'Recover and confirm a compatible complete reference for this declared route.',
                    'evaluated_other_incomplete': 'Inspect the recorded per-component reason; do not impute a score.',
                }[state],
            }
            details.append(cell); current.append(cell)
        numeric = [c['model'] for c in current if c['numeric_CCE_complete']]
        question_hashes = {c['question_sha256'] for c in current if c['answer_present']}
        hashes_agree = len(question_hashes) == 1 and None not in question_hashes
        counts = collections.Counter(c['state'] for c in current)
        per_question.append({
            'question_id': qid, 'fixed_models': len(models),
            'answers_present': sum(c['answer_present'] for c in current),
            'provisional_CCE_numeric_models': len(numeric),
            'models_with_provisional_CCE': numeric,
            'blocking_models': [c['model'] for c in current if not c['numeric_CCE_complete']],
            'state_counts': dict(counts), 'cross_model_question_hash_agreement': hashes_agree,
            'in_numeric_common_set': len(numeric) == len(models) and hashes_agree,
            'in_formal_common_set': all(c['formal_eligible'] for c in current) and hashes_agree,
        })
        wide.append({'question_id': qid, **{c['model']: c['state'] for c in current}})
    per_model = []
    for model in models:
        cells = [c for c in details if c['model'] == model]
        counts = collections.Counter(c['state'] for c in cells)
        per_model.append({'model': model, 'questions_expected': len(qids),
                          **{state: counts[state] for state in sorted({c['state'] for c in details})},
                          'formal_eligible': sum(c['formal_eligible'] for c in cells),
                          'historical_score_error_with_unrun_steps': sum(c['historical_score_error_coexists_with_step_not_run'] for c in cells)})
    numeric_common = [r['question_id'] for r in per_question if r['in_numeric_common_set']]
    formal_common = [r['question_id'] for r in per_question if r['in_formal_common_set']]
    expected = read(inputs['joint_summary'])['revised_full_fixed_cohort']['common_question_ids']
    assert numeric_common == expected, (numeric_common, expected)
    assert len(details) == len(models) * len(qids)
    counts = dict(collections.Counter(c['state'] for c in details))
    assert sum(counts.values()) == len(details)
    summary = {
        'scope': 'fixed_cohort_question_by_model_gap_audit_no_new_scores',
        'fixed_models': models, 'question_count': len(qids), 'expected_cells': len(details),
        'existing_answers': len(rows), 'state_counts': counts,
        'numeric_common_question_ids': numeric_common, 'formal_common_question_ids': formal_common,
        'historical_score_errors_coexisting_with_unrun_steps': sum(c['historical_score_error_coexists_with_step_not_run'] for c in details),
        'identity_rule': 'Exact historical question identity; missing answers are explicit grid cells.',
        'unrun_rule': 'Not run is a computational status, not proof that no applicable reference exists.',
        'model_requests': 0, 'scores_changed': 0,
        'command': ' '.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]),
        'input_sha256': {k: filehash(v) for k, v in inputs.items()},
        'script_sha256': filehash(__file__),
    }
    write(args.out / 'summary.json', summary)
    write(args.out / 'cell_status.json', details)
    table(args.out / 'cell_status.csv', details)
    table(args.out / 'question_model_matrix.csv', wide)
    table(args.out / 'per_question_gaps.csv', per_question)
    table(args.out / 'per_model_gaps.csv', per_model)
    evaluated_q = [r for r in per_question if any(k != 'revised_steps_not_run' and k != 'answer_missing' for k in r['state_counts'])]
    text = [
        '# Fixed-cohort common-set gaps', '',
        f"The fixed {len(models)}-model × {len(qids)}-question grid contains {len(details):,} cells and {len(rows):,} archived answers. Numeric common questions: {len(numeric_common)}; formal common questions: {len(formal_common)}.", '',
        '| Cell state | Count |', '|---|---:|',
        *[f'| {state} | {count} |' for state, count in counts.items()], '',
        'The unrun cases are not reclassified as scientifically missing references. One historical score failure may coexist with the unrun-step state; these causes are recorded separately.', '',
        '| Evaluated question | Models with provisional CCE | Models still blocking the fixed cohort |', '|---|---:|---|',
        *[f"| {r['question_id']} | {r['provisional_CCE_numeric_models']} | {', '.join(r['blocking_models'])} |" for r in evaluated_q], '',
        'No generator was dropped to create a common set, and no historical c_step was substituted for SR. These tables add missingness detail, not scores or confirmed references.', '',
        '[Full cell status](cell_status.csv) · [Question × model matrix](question_model_matrix.csv) · [Per-model counts](per_model_gaps.csv) · [Per-question gaps](per_question_gaps.csv)', '',
        'Actual command:', '', '```powershell', summary['command'], '```', '',
    ]
    (args.out / 'README.md').write_text('\n'.join(text), encoding='utf-8')
    print({'existing_answers': len(rows), 'expected_cells': len(details), 'state_counts': counts, 'numeric_Qstar': len(numeric_common), 'formal_Qstar': len(formal_common)})


if __name__ == '__main__':
    main()
