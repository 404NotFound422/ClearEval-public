"""Build a source-extracted development reference; no wet-lab execution or optimization."""
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cce_validation import ROOT, OUT, read, write, filehash, digest


def main():
    folder = OUT / 'reference_recovery'
    source = ROOT.parent / 'literature/tissue_optical_clearing/fulltext_txt/009_TOC_6c8871f5003c_2018_Tissue_clearing_of_both_hard_and_soft_tissue_organs_with_the_PEGASOS_method.txt'
    text = source.read_text(encoding='utf-8')
    start = text.index('MATERIALS AND METHODS')
    recipe_start = text.index('Preparation of PEGASOS solutions', start)
    recipe_end = text.index('Perfusion and tissue preparation', recipe_start)
    branch_start = text.index('For soft tissue or tissue slices, decalcification procedure was', start)
    branch_end = text.index('Measurement of the organ size change', branch_start)
    for token in ['30% v/v', '50% v/v', '70% v/v', 'PEGMMA500']:
        assert token in text[recipe_start:recipe_end]
    passages = [
        {'source_id': 'PEGASOS2018-METHODS-RECIPES', 'start': recipe_start, 'end': recipe_end,
         'text': text[recipe_start:recipe_end], 'section': 'Materials and methods / Preparation of PEGASOS solutions'},
        {'source_id': 'PEGASOS2018-METHODS-SOFT', 'start': branch_start, 'end': branch_end,
         'text': text[branch_start:branch_end], 'section': 'Materials and methods / PEGASOS passive immersion procedure / soft-tissue paragraph'}]
    write(folder / 'pegasos_primary_passages.json', {'source_path': str(source), 'source_sha256': filehash(source),
         'offset_convention': 'Unicode character offsets in Path.read_text UTF-8 with universal newline handling', 'passages': passages})
    reference_id = 'PEGASOS_JING2018_FIXED_BRAIN_SOFT_IMMERSION_V1'
    texts = [
        ('decolorization', 'Incubate fixed soft tissue in the Quadrol decolorization solution at 37 degrees C for 2 days.'),
        ('delipidation', 'Immerse the tissue in 30% (vol/vol) tert-butanol delipidation solution with Quadrol at 37 degrees C with shaking.'),
        ('delipidation', 'Immerse the tissue in 50% (vol/vol) tert-butanol delipidation solution with Quadrol at 37 degrees C with shaking.'),
        ('delipidation', 'Immerse the tissue in 70% (vol/vol) tert-butanol delipidation solution with Quadrol at 37 degrees C with shaking.'),
        ('dehydration', 'Transfer the tissue to tB-PEG dehydration solution for 1 to 2 days.'),
        ('ri_matching', 'Transfer the tissue to BB-PEG clearing medium for at least 1 day, until transparent.'),
        ('storage', 'Preserve the cleared tissue in the clearing medium at room temperature.')]
    reference = {'reference_id': reference_id, 'route_id': 'PEGASOS', 'route_aliases': ['PEGASOS'],
        'question_ids': [2, 21, 22, 23, 248],
        'steps': [{'step_id': f'PEGASOS-{i:02d}', 'text': statement, 'module': module,
                   'source_anchor': 'PEGASOS2018-METHODS-SOFT; gradient identities from PEGASOS2018-METHODS-RECIPES',
                   'required': True, 'required_scope': 'author-reported branch coverage, not proof that omission causes experimental failure'}
                  for i, (module, statement) in enumerate(texts, 1)],
        'source_path': str(source), 'source_sha256': filehash(source),
        'source_url': 'https://doi.org/10.1038/s41422-018-0049-z',
        'source_title': 'Tissue clearing of both hard and soft tissue organs with the PEGASOS method',
        'status': 'source_extracted', 'family_id': 'PEGASOS_JING2018_MOUSE_BRAIN',
        'human_confirmation': None, 'steps_language': 'en',
        'construction': 'Source-based paraphrase of reported fixed-soft-tissue branch, not derived from model answers.',
        'completeness_status': 'main_text_operation_sequence_recovered; supplement and expert confirmation pending',
        'applicability': {'species': 'mouse', 'tissue': 'fixed brain / soft tissue',
            'scope': 'Post-fixation passive immersion clearing, RI matching and storage; labeling choices remain separately evaluated.',
            'initial_conditions': ['Fixation and postfixation already complete'],
            'excluded_steps': ['Already completed fixation', 'Hard-tissue decalcification', 'Whole-body recirculation',
                               'New labeling interventions; not requested as part of the step-reference scope'],
            'remaining_review': ['Table S1 tissue schedules and Data S1 were identified but downloads failed; no per-gradient time inferred.',
                'Reported 1-2 days for the gradient stage is not assigned separately to each concentration.',
                'Specific 3 mm weak sparse-reporting brain blocks and each chosen dual label combination are not directly validated.',
                'Month-long quantitative preservation evidence is from intestine, not six-month brain storage; no expiry limit inferred.',
                'Native fluorescence, distortion and long-term outcomes are not established by step coverage.',
                'One expert has not confirmed completeness, applicability or step granularity.']},
        'conditions': {'delipidation_stage_duration_reported': '1 to 2 days; per-gradient allocation unresolved',
                       'reagent_identity': 'PEGMMA500 catalog number corrected in 2019; do not use the old 409529 entry',
                       'reagent_preparation_counted_as_tissue_operation': False},
        'correction': {'doi': '10.1038/s41422-019-0180-5', 'url': 'https://www.nature.com/articles/s41422-019-0180-5',
                       'verified_change': 'PEGMMA500 catalog identifier corrected from 409529 to 447943; Data S1 already had the correct identifier.',
                       'scope': 'Catalog correction, not a new tissue-processing operation'},
        'question_applicability': {str(q): {'task_family': 'whole_brain_structure' if q == 2 else 'fixed_reporter_whole_brain' if q == 248 else 'weak_reporter_brain_block_storage',
            'scope': 'Candidate for fixed-brain operation coverage only; no guarantee of target-label compatibility or storage outcome.'} for q in [2,21,22,23,248]},
        'frozen': True, 'freeze_scope': 'development candidate, unconfirmed supplemental completeness and applicability'}
    write(folder / 'pegasos_candidate_reference.json', {'schema_version': 'cce_reference_recovery_v1', 'references': [reference]})
    # Preserve the successful first-source run; do not overwrite any pilot result.
    original = read(folder / 'references.json')
    assert [r['route_id'] for r in original['references']] == ['FDISCO']
    combined = {'schema_version': 'cce_reference_recovery_v1', 'references': original['references'] + [reference]}
    write(folder / 'references_two_source_development.json', combined)
    links = []
    for model in ['openai_deepseek-chat', 'openai_deepseek-reasoner']:
        path = ROOT / 'dataset/Q+AR/model_response' / f'from_{model}_1-shot.json'
        for answer in read(path):
            if answer['question_id'] in [21,22,23]:
                assert 'PEGASOS' in answer['model_response'][:600]
                links.append({'answer_id': model + '__q' + str(answer['question_id']), 'question_id': answer['question_id'],
                    'answer_source': str(path), 'answer_sha256': digest(answer['model_response']),
                    'question_sha256': digest(answer['specific_question']), 'reference_id': reference_id,
                    'binding': 'declared route plus fixed-brain task; expert applicability pending'})
    write(folder / 'pegasos_answer_links.json', links)
    write(folder / 'second_reference_status.json', {'source_extracted_route_candidates': 2, 'expert_confirmed_routes': 0,
        'new_reference_id': reference_id, 'linked_actual_answers': len(links), 'supplement_completeness': 'not_verified',
        'formal_eligible': False, 'new_model_requests': 0,
        'commands': ['scripts/cce_recover_pegasos.py'],
        'source_review': 'Main-text procedure and exact source offsets read; independent scope review; published correction checked.',
        'reference_collection': str(folder / 'references_two_source_development.json')})
    print('Saved second source-extracted development candidate and six actual-answer links; no expert confirmation or model calls.')

if __name__ == '__main__':
    main()
