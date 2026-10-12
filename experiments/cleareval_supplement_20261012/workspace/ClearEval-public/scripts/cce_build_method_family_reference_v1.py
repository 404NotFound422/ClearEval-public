"""Recover a real pair of authored, same-family protocols without scoring answers."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'method_family_reference_v1'
SRC = BASE / 'reference_recovery/idisco_plus_2016'
PDF = SRC / 'publisher_attachments/1-s2.0-S0092867416305554-mmc8.pdf'
EXPECTED_PDF = '8176ba46b6eb4bda5dfb3531c1fc108ea2271d6c382f8b5498ec33b78685b244'
QIDS = [1, 2, 21, 22, 23, 248]
GROUP = 'IDISCO_PLUS_2016_POST_IMMUNOLABEL_CLEARING'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def digest(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def save(name, x):
    (OUT / name).write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def span(page, start_text, end_text=None):
    p = SRC / f'publisher_pages/publisher_p{page:03d}.txt'
    text = p.read_text(encoding='utf-8')
    start = text.index(start_text)
    end = start + len(start_text) if end_text is None else text.index(end_text, start) + len(end_text)
    return {'pdf_path': str(PDF), 'pdf_sha256': sha(PDF), 'pdf_page_one_based': page,
            'text_path': str(p), 'text_sha256': sha(p), 'offset_unit': 'Unicode code points; end exclusive',
            'start': start, 'end': end, 'quote': text[start:end],
            'quote_sha256': hashlib.sha256(text[start:end].encode('utf-8')).hexdigest()}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = [PDF, SRC / 'candidate.json', SRC / 'source_version_differences.json',
              SRC / 'publisher_pages/extraction_manifest.json', SRC / 'publisher_attachments/retrieval_manifest.json']
    for page in [27, 36, 37, 38]:
        inputs += [SRC / f'publisher_pages/publisher_p{page:03d}.txt', SRC / f'publisher_pages/publisher_p{page:03d}.png']
    protected = {str(p): sha(p) for p in inputs}
    assert sha(PDF) == EXPECTED_PDF
    old = read(SRC / 'candidate.json')['references'][0]
    old_steps = copy.deepcopy(old['steps'])
    pages = {p: (SRC / f'publisher_pages/publisher_p{p:03d}.txt').read_text(encoding='utf-8') for p in [27, 36, 37, 38]}
    passages = {
        'supplement_prerequisite': span(27, 'Immunolabeled brains were cleared', 'Ertürk et al., 2012).'),
        'bench_title': span(36, "iDISCO'protocol' April'2016'", 'iDISCO+(protocol('),
        'bench_sample_wholebrain': span(36, "'''Whole'brain' 7d' 4.5mL'"),
        'bench_trim_scope': span(37, "4. Dissect'the'brain/organ'and'trim'to'the'appropriate'size.'"),
        'bench_gradient': span(38, "1. Dehydrate'in'methanol/H2O'series:", "overnight'at'RT'at'this'point.'"),
        'bench_mixture': span(38, "2. 3H'incubation,", "Methanol'at'RT'"),
        'bench_pure_dcm': span(38, "3. Incubate'in'100%'DCM", "to'wash'the'MeOH.'"),
        'bench_dbe': span(38, "4. Incubate'in'DiBenzyl'Ether", "oxidizing'the'sample.'"),
        'bench_inversion': span(38, "Before'imaging,", "mixing'the'solution.'"),
        'bench_container': span(38, "Incubations'and'", "tubes.''"),
    }
    # Text extraction preserves unusual PDF glyphs. Source quote identities remain exact.
    assert 'Clearing' in pages[38] and 'Immunolabeling' in pages[37]
    scope = {
        'scope_id': GROUP,
        'start': 'Fixed brain after an appropriate immunolabeling branch; no assertion that this prerequisite is already satisfied in the benchmark answer.',
        'end': 'Complete author clearing and RI sequence, including reported terminal storage or pre-imaging handling; excludes microscope-specific chamber construction and image acquisition.',
        'included_modules': ['post-immunolabel dehydration', 'clearing', 'RI matching', 'reported terminal handling'],
        'excluded_modules': ['initial fixation already supplied by the task', 'pretreatment and immunolabeling upstream of clearing', 'microscope-specific chamber construction', 'image acquisition', 'any vector engineering or delivery'],
        'scope_completeness': 'Every action in the selected author clearing section is retained; repeated treatments are retained as count-bearing operations, not truncated to a favorable shared prefix.',
        'upstream_condition_is_not_established': True,
        'upstream_workflow_not_reconstructed_in_this_package': True,
        'action_granularity': 'Same as existing supplement: individual concentration levels; repeated identical treatment is one operation retaining its repeat count; independently prescribed terminal handling is retained.',
    }
    tasks = []
    for q in QIDS:
        status = ('conditional_whole_brain_operation_coverage' if q in [1, 2]
                  else 'route_only_native_reporter_task_applicability_unconfirmed' if q == 248
                  else 'conditional_brain_block_operation_diagnostic_size_schedule_unverified')
        tasks.append({'question_id': q, 'allowed_for_new_conditional_step_diagnostic': True,
                      'scope_status': status, 'source_task_applicability_confirmed': False,
                      'formal_eligible': False, 'main_v7_scores_unchanged': True,
                      'task_specific_parameters_validated': False,
                      'prerequisite': 'Appropriate immunolabeling before this clearing branch is conditional, not asserted completed.',
                      'reason': ('Adult whole brains are explicitly represented in both source workflows; target labels/outcomes remain unconfirmed.' if q in [1, 2]
                                 else 'Original task requires native reporter fluorescence; immunolabel amplification is not equivalent. This is route-operation coverage only, not task-compatible CCE evidence.' if q == 248
                                 else 'The bench source allows trimming brain/organ to an appropriate size and uses a common clearing section. Neither author source reports a distinct 3 mm clearing action list or a validated 3 mm schedule; transfer is limited to a conditional operation diagnostic, not a claim of exact parameter or outcome support.')})
    shared = {
        'route_id': 'iDISCO+', 'route_aliases': ['iDISCO+', 'iDISCO +', 'iDISCO Plus', 'iDISCO-plus'],
        'method_family_id': 'iDISCO_plus_2016', 'method_family_name': 'iDISCO+ (2016)',
        'family_id': old['family_id'], 'true_multiversion_group': GROUP,
        'question_ids': QIDS, 'task_scope_bindings': tasks,
        'full_action_scope': scope, 'source_path': str(PDF), 'source_sha256': sha(PDF),
        'source_url': old['source_url'], 'doi': old['doi'], 'status': 'source_extracted',
        'human_confirmation': None, 'formal_eligible': False,
        'source_scope': 'Complete selected author clearing procedure within the stated conditional start/end boundary; no biological necessity or task efficacy confirmation.',
        'excluded_aliases': ['iDISCO', 'iDISCO 2014', '3DISCO'],
        'explicit_version_priority': True,
        'version_selection_rule': 'An explicitly named author/date/version must restrict selection to that version; an unspecified iDISCO+ version may compare the two complete candidates. Do not infer version from a wrong parameter alone.',
        'prerequisites': [scope['start']], 'exclusions': scope['excluded_modules'],
        'new_model_requests': 0,
    }
    supplement = {**copy.deepcopy(shared),
        'reference_id': 'IDISCO_PLUS_2016_SUPPLEMENT_METHOD_FAMILY_V1',
        'protocol_version': 'Cell 2016 Supplemental Experimental Procedures, sample clearing',
        'version_id': 'IDISCO_PLUS_2016_ARTICLE_SUPPLEMENT',
        'version_aliases': ['2016 Supplemental Experimental Procedures', 'Renier 2016 supplement', 'Cell 2016 supplement'],
        'source_pages': [27], 'steps': old_steps,
        'continuous_conditions': copy.deepcopy(old['continuous_conditions']),
        'unknown_parameters': copy.deepcopy(old['unknown_parameters']),
        'completeness_status': 'complete_author_reported_clearing_section_with_explicit_unknown_conditions',
        'reuse': {'parent_reference_id': old['reference_id'], 'parent_path': str(SRC / 'candidate.json'),
                 'parent_sha256': sha(SRC / 'candidate.json'), 'steps_copied_without_change': True,
                 'original_steps_digest': digest(old_steps),
                 'not_counted_as_a_new_authored_protocol': True}}
    definitions = []
    for concentration in [20, 40, 60, 80]:
        definitions.append((f'After immunolabeling, dehydrate the brain in {concentration}% methanol in water for 1 hour at room temperature.', 'clearing', 'bench_gradient'))
    definitions += [
        ('After the methanol gradient, treat with 100% methanol for 1 hour twice at room temperature. Leaving the sample overnight at room temperature at this point is explicitly optional.', 'clearing', 'bench_gradient'),
        ('Incubate in 66% dichloromethane (DCM) and 33% methanol for 3 hours at room temperature with shaking.', 'clearing', 'bench_mixture'),
        ('Wash twice in 100% dichloromethane (DCM), 15 minutes each, with shaking to remove methanol.', 'clearing', 'bench_pure_dcm'),
        ('Incubate in dibenzyl ether (DBE) without shaking. Fill the tube almost completely with DBE to prevent air from oxidizing the sample.', 'RI_matching', 'bench_dbe'),
        ('Before imaging, invert the tube a couple of times to finish mixing the solution.', 'terminal_handling', 'bench_inversion'),
    ]
    bench_steps = []
    for i, (text, module, key) in enumerate(definitions, 1):
        s = passages[key]
        bench_steps.append({'step_id': f'IDP16-BENCH-CLEAR-{i:02d}', 'text': text, 'module': module,
                            'source_anchor': f"publisher mmc8 physical p38; April2016 Bench, Clearing; page text [{s['start']}:{s['end']})",
                            'source_spans': [s], 'required': True,
                            'required_scope': 'coverage of the complete selected author procedure, not independently demonstrated biological necessity',
                            'optional_subcondition': 'Overnight pause is optional, not an additional required operation.' if i == 5 else None})
    bench = {**copy.deepcopy(shared),
        'reference_id': 'IDISCO_PLUS_2016_APRIL_BENCH_METHOD_FAMILY_V1',
        'protocol_version': 'iDISCO+ April 2016 Bench Protocol, Clearing section',
        'version_id': 'IDISCO_PLUS_2016_APRIL_BENCH',
        'version_aliases': ['April 2016 Bench Protocol', 'iDISCO+ April 2016', 'April 2016 iDISCO protocol'],
        'source_pages': [36, 37, 38], 'steps': bench_steps,
        'continuous_conditions': [{'condition': 'Incubations and storage can be done in plastic Eppendorf tubes.',
                                   'mandatory': False, 'source_spans': [passages['bench_container']]}],
        'unknown_parameters': ['DBE incubation duration and numerical endpoint are not specified in this branch.',
                               'Pure DCM and DBE incubation temperatures are not explicitly stated in their local instructions; do not import the supplement values.',
                               'Storage duration and storage temperature are not specified by the Bench clearing section.',
                               'Exact 3 mm block schedule and task-specific marker/outcome compatibility have not been established.'],
        'completeness_status': 'complete_author_clearing_section_through_preimaging_handling; storage-specific parameters unreported',
        'reuse': {'new_authored_version_recovery': True, 'same_document_different_author_protocol_section': True,
                 'not_a_renamed_copy': True}}
    refs = [supplement, bench]
    assert supplement['steps'] == old['steps']
    assert len(refs) == 2 and all(len(r['steps']) == 9 for r in refs)
    assert digest(supplement['steps']) != digest(bench['steps'])
    all_spans = list(passages.values()) + [s for r in refs for step in r['steps'] for s in step['source_spans']]
    for s in all_spans:
        text = Path(s['text_path']).read_text(encoding='utf-8')
        assert text[s['start']:s['end']] == s['quote']
        assert sha(s['text_path']) == s['text_sha256']
        assert hashlib.sha256(s['quote'].encode('utf-8')).hexdigest() == s['quote_sha256']
    differences = [x for x in read(SRC / 'source_version_differences.json')['differences'] if x['id'] in ['IDP16-C05', 'IDP16-C06', 'IDP16-C07', 'IDP16-C08']]
    save('candidate_references.json', {'schema': 'method-family-multi-protocol-source-v1', 'references': refs})
    save('source_passages.json', passages)
    save('source_manifest.json', {'doi': old['doi'], 'paper_title': 'Mapping of Brain Activity by Automated Volume Analysis of Immediate Early Genes',
        'official_source': {'path': str(PDF), 'sha256': sha(PDF), 'url': old['source_url'], 'pages': 133},
        'source_version_group': GROUP, 'distinct_authored_versions': 2,
        'newly_recovered_version_count': 1, 'reused_existing_version_count': 1,
        'substantive_differences': differences,
        'scope_comparability': scope, 'task_scope_bindings': tasks,
        'source_glyph_note': 'The page38 text extractor uses apostrophes and H for some spaces/hyphens. Exact extracted spans and hashes are retained; English step prose was checked against the rendered official PDF page.',
        'visually_checked_this_phase': [str(SRC / 'publisher_pages/publisher_p027.png'), str(SRC / 'publisher_pages/publisher_p038.png')],
        'source_input_sha256': protected, 'new_downloads': 0, 'new_model_requests': 0})
    save('source_scope_gate.json', {'status': 'ready_for_independent_source_review', 'approved_for_development_pool': False,
        'candidate_path': str(OUT / 'candidate_references.json'), 'candidate_sha256': sha(OUT / 'candidate_references.json'),
        'allowed_diagnostic_question_ids_proposed': QIDS, 'task_scope_bindings': tasks,
        'complete_versions_same_family_same_scope': 2, 'cross_method_pooling_allowed': False,
        'reference_union_or_best_substeps_allowed': False, 'human_confirmation': None, 'formal_eligible': False,
        'independent_source_review_required_before_new_score': True})
    save('construction_record.json', {'status': 'source_extracted_pending_independent_scope_review',
        'agent_source_recovery': True, 'human_expert_reviews': 0, 'local_5_plus_15_review_budget_consumed': 0,
        'source_family_count': 1, 'authored_protocol_versions': 2, 'new_author_version_recovered': 1,
        'old_sources_modified': False, 'answer_texts_read': 0, 'heldout_scientific_outputs_read': 0,
        'new_model_requests': 0, 'new_scores': 0, 'unknowns_not_imputed': True,
        'other_leads_read': ['udisco_2016/source_version_differences.json: selected whole-organ column agrees; half-brain difference is not a same-scope whole-brain candidate.',
                             'cubic_hv_2020/source_version_differences.json: real main/supplement differences exist, but no second complete comparable version constructed in this first delivery.'],
        'next_independent_work': 'Map existing complete CUBIC author sources to a separately tagged conditional method-family scope; no need to manufacture a second version.',
        'task_package': 'Execution revision r2; candidates provisional, SR/SP from one whole selected reference.',
        'skills_read': ['toc-paper-evidence SKILL.md and REVIEW.md', 'toc-evidence-review SKILL.md and REVIEW.md', 'pdf SKILL.md']})
    for p, h in protected.items():
        assert sha(p) == h, p
    save('build_run.json', {'status': 'success', 'utc': datetime.now(timezone.utc).isoformat(),
        'actual_command': [sys.executable, 'scripts/cce_build_method_family_reference_v1.py'],
        'script_sha256': sha(__file__), 'candidate_sha256': sha(OUT / 'candidate_references.json'),
        'all_source_inputs_unchanged': True, 'source_spans_verified': len(all_spans),
        'source_family_count': 1, 'protocol_versions': 2, 'step_counts': [len(r['steps']) for r in refs],
        'new_model_requests': 0, 'new_scores': 0})
    print(json.dumps({'status': 'success', 'candidate_path': str(OUT / 'candidate_references.json'),
                      'candidate_sha256': sha(OUT / 'candidate_references.json'), 'protocol_versions': 2,
                      'step_counts': [9, 9], 'new_model_requests': 0, 'new_scores': 0}))


if __name__ == '__main__':
    main()
