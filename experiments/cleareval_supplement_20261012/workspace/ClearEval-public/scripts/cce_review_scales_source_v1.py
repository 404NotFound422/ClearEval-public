"""Record the coordinator's pre-scoring source-scope review, not expert approval."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
SOURCE = BASE / 'reference_recovery/development_binding_followup_v1'
DEST = BASE / 'expanded_references_v7'


def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    assert not (DEST / 'plan.json').exists() and not (DEST / 'run.json').exists(), 'review must precede scoring freeze'
    candidate = SOURCE / 'candidate_references.json'
    assert sha(candidate) == 'eb9d445427b3ff3907e6752720a189cd86add2397d29339ee53a3241d6fe9d37'
    ref = read(candidate)['references'][0]
    assert ref['question_ids'] == [21,22,23] and ref['route_id'] == 'ScaleS'
    assert len(ref['steps']) == 7 and ref['terminal_storage']['included_as_separate_operation'] is False
    assert ref['human_confirmation'] is None and ref['formal_eligible'] is False
    inputs = {str(candidate): sha(candidate), str(Path(__file__).resolve()): sha(__file__)}
    manifest = read(SOURCE / 'source_manifest.json')
    def check(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                assert sha(value['path']) == value['sha256'], value['path']
                inputs[value['path']] = value['sha256']
            for item in value.values(): check(item)
        elif isinstance(value, list):
            for item in value: check(item)
    check(manifest)
    passages = read(SOURCE / 'source_passages.json')['passages']
    for anchor in passages:
        check(anchor)
        text = Path(anchor['text_file']['path']).read_text(encoding='utf-8-sig')
        assert text[anchor['start']:anchor['end']] == anchor['quote']
        assert hashlib.sha256(anchor['quote'].encode()).hexdigest() == anchor['quote_sha256']
    assert len(passages) == 9
    assert all('(w/v)' in ref['steps'][i]['text'] and '(v/v)' in ref['steps'][i]['text'] for i in [0,2,3,5])
    assert '(w/v)' in ref['steps'][1]['text']
    assert all(s['timing_status'] == 'exact_3mm_incubation_duration_unknown_not_transferred_from_hemisphere' for s in ref['steps'])
    old = read(BASE / 'expanded_references_v6_t070_per_answer.json')
    targets = ref['target_answer_bindings']
    assert len(targets) == 4
    for binding in targets:
        row = next(r for r in old if r['answer_id'] == binding['answer_id'])
        assert row['answer_sha256'] == binding['answer_sha256'] and row['question_sha256'] == binding['question_sha256']
        assert row['sr'] is None
    for name in ['source_manifest.json','source_passages.json','source_review.json','build_scales_candidate.py','plan.json']:
        inputs[str(SOURCE / name)] = sha(SOURCE / name)
    result = {'status':'pass','approved_for_conditional_scoring':True,'candidate_sha256':sha(candidate),
        'target_answer_ids':[r['answer_id'] for r in targets], 'formal_eligible':False,
        'reviewer':'root coordinator source review; not human expert confirmation',
        'source_anchors_verified':9, 'source_pdf_sha256':manifest['supplement']['sha256'],
        'root_images_actually_viewed':['SI page1 Fig1b','SI page15 Table1'],
        'other_visual_source_evidence':'Four pages inspected by source author; root separately checked the two operation/formulation pages.',
        'confirmed_scope':['Seven post-fixed actions recovered from exact author figure and caption.',
            'Author explicitly allows slice duration shortening; no exact 3mm durations transferred.',
            'Concentration bases retained from Table1; tabulated pH/RI are not added adjustment actions.',
            'Storage maintained in terminal medium; 15-month observation is not an eighth action or mandatory incubation.',
            'Four route-declared answers all included; no filtering by parameter correctness.'],
        'remaining_unknowns':ref['task_outcome_unknowns'],
        'distinct_branches_not_merged':['AbScale','ChemScale','ScaleSQ'],
        'scientific_limit':'Conditional clearing-operation coverage only. Unknown prerequisite labeling, exact3mm outcomes and full-task adequacy remain NA/unconfirmed; not an expert-confirmed reasonable route.',
        'source_discrepancies_preserved':ref['source_discrepancies'],
        'input_sha256':inputs,'actual_command':[sys.executable,'scripts/cce_review_scales_source_v1.py'],
        'new_model_requests':0,'new_scores':0,'expert_confirmation':None}
    DEST.mkdir(exist_ok=True)
    (DEST / 'source_scope_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'pass','candidate_sha256':sha(candidate),'target_answers':4,'source_anchors':9,'new_scores':0}))


if __name__=='__main__': main()
