"""Reuse the source-reviewed full CUBIC branch for conditional family diagnostics."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'method_family_reference_v1'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    path=OUT/'cubic_family_candidate_references.json';mapping_path=OUT/'cubic_family_scope_mapping.json'
    mapping=read(mapping_path);refs=read(path)['references']
    assert sha(path)==mapping['candidate_sha256']=='1fc4ddaaa5c61baba3515c2a00627b399666c1487df654339405f80704c11734'
    inputs={**mapping['source_bindings'],str(path):sha(path),str(mapping_path):sha(mapping_path)}
    for p,h in inputs.items():assert sha(p)==h,p
    old_path=BASE/'reference_recovery/cubic_hv_2020/candidate.json'
    old=read(old_path)['references'][0]
    review_path=BASE/'reference_recovery/cubic_hv_2020/review/source_scope_review.json'
    review=read(review_path)
    assert review['review_status']=='pass_for_unassigned_conditional_source_candidate'
    for r in review['input_artifacts']:
        assert sha(r['path'])==r['sha256'],r['path']
        inputs[r['path']]=r['sha256']
    assert len(refs)==1 and len(refs[0]['steps'])==20
    assert refs[0]['steps']==old['steps']
    assert refs[0]['route_id']==refs[0]['authored_method_id']=='CUBIC-HV'
    assert refs[0]['method_family_id']=='CUBIC' and not refs[0]['formal_eligible']
    assert mapping['source_scope']['intervening_condition']['already_labeled_at_initial_state'] is False
    assert all(not b['source_task_applicability_confirmed'] for b in mapping['task_scope_bindings'])
    result={'status':'pass_for_conditional_family_step_diagnostic','approved_for_development_pool':True,
        'candidate_path':str(path),'candidate_sha256':sha(path),
        'reviewer':'root AI mapping review, reusing unchanged prior AI source review; not human expert',
        'inherited_source_review':str(review_path),'inherited_source_review_sha256':sha(review_path),
        'new_full_pdf_read_claimed':False,'full_source_steps_byte_equal_to_reviewed_candidate':True,
        'full_step_count':20,'authored_version_count':1,'multiversion_comparison_claimed':False,
        'allowed_diagnostic_question_ids':[1,2,21,22,23,248],
        'version_conditions':['Explicit known legacy CUBIC versions must not be replaced with HV2020.',
            'A named CUBIC-1/CUBIC-2 legacy reagent pair is version evidence, not merely a wrong numeric parameter.',
            'Other unrecognized or erroneous parameter names alone do not exclude a method.',
            'Generic CUBIC means a conditional author-version candidate; it does not establish the answer actually selected HV2020.'],
        'scope_limits':['Intermediate labeling remains an unresolved intervening condition.',
            'All20 operations including the complete selected gel/storage branch retained.',
            'This gel branch is not claimed mandatory for every CUBIC task.',
            '3mm schedule, native signals and target storage effects remain unconfirmed.',
            'Output is conditional source-operation coverage, not confirmed task-compatible CCE.'],
        'human_expert_reviews':0,'formal_eligible':False,'new_judge_requests':0,
        'inputs':inputs,'actual_command':[sys.executable,*sys.argv],'script_sha256':sha(__file__)}
    (OUT/'cubic_independent_scope_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'protected_inputs':len(inputs),'full_steps':20,'new_judge_requests':0}))

if __name__=='__main__':main()
