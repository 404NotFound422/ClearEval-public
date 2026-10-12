"""Source and identity verification after root AI review of the two author pages.

This is an AI source review, not a human expert review or task-applicability signoff.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'method_family_reference_v1'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def htext(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()

def main():
    candidate=OUT/'candidate_references.json'; refs=read(candidate)['references']
    manifest=read(OUT/'source_manifest.json'); passages=read(OUT/'source_passages.json')
    assert sha(candidate)=='dfb44da85f8d295331e3115f80b44098f8a6576cdf5f6744477e3d9d1f250881'
    assert len(refs)==2 and all(len(r['steps'])==9 for r in refs)
    assert len({r['true_multiversion_group'] for r in refs})==1
    spans=list(passages.values())+[s for r in refs for step in r['steps'] for s in step['source_spans']]
    paths={candidate,OUT/'source_manifest.json',OUT/'source_passages.json',OUT/'source_scope_gate.json'}
    for s in spans:
        text=Path(s['text_path']).read_text(encoding='utf-8')
        assert sha(s['pdf_path'])==s['pdf_sha256'] and sha(s['text_path'])==s['text_sha256']
        assert text[s['start']:s['end']]==s['quote'] and htext(s['quote'])==s['quote_sha256']
        paths.update([Path(s['pdf_path']),Path(s['text_path'])])
    old=read(BASE/'expanded_references_v7/references.json')['references']
    old_idisco=[r for r in old if r['route_id']=='iDISCO+']
    assert old_idisco and refs[0]['steps']==old_idisco[0]['steps']
    texts=[[s['text'] for s in r['steps']] for r in refs]
    assert texts[0]!=texts[1] and 'invert' in texts[1][-1]
    assert not any('room temperature' in t for t in texts[1][-3:])
    assert 'optionally' in passages['bench_gradient']['quote'] and 'explicitly optional' in texts[1][4]
    for r in refs:
        assert not r.get('formal_eligible',False)
        assert all(not x['source_task_applicability_confirmed'] for x in r['task_scope_bindings'])
        assert r['question_ids']==[1,2,21,22,23,248]
    figure_paths=[Path(p) for p in manifest['visually_checked_this_phase']]
    paths.update(figure_paths)
    verdict={
        'status':'pass_for_conditional_step_diagnostic','approved_for_development_pool':True,
        'reviewer':'root AI source review separate from constructing agent; not human/expert confirmation',
        'candidate_path':str(candidate),'candidate_sha256':sha(candidate),
        'allowed_diagnostic_question_ids':[1,2,21,22,23,248],
        'validated_source_spans':len(spans),'distinct_author_versions':2,'source_step_counts':[9,9],
        'both_original_rendered_pages_read':True,'source_pages_one_based':[27,38],
        'source_restatement':'Both author versions describe the post-immunolabel clearing/RI workflow. They differ in prescribed conditions and terminal handling. Each version is kept complete within that stated scope.',
        'same_scope_does_not_mean_same_parameters':True,'source_conflicts_kept_as_separate_versions':True,
        'no_cross_version_parameter_borrowing':True,'no_score_based_source_selection':True,
        'scope_limits':[
            'Upstream immunolabeling is a conditional prerequisite, not established by the task or silently reconstructed.',
            'q21-23: operation diagnostic only; exact 3mm parameters and outcomes remain unverified.',
            'q248: route-only operation diagnostic; native fluorescence compatibility is not established.',
            'Microscope-specific chamber construction and imaging are outside this clearing-branch scope.',
            'Optional waiting remains optional; terminal handling is not dropped to increase matching.',
            'No use as confirmed task-compatible CCE or proof of scientific suitability.'
        ],
        'human_expert_reviews':0,'formal_eligible':False,'new_judge_requests':0,
        'actual_command':[sys.executable,*sys.argv],
        'inputs':{str(p):sha(p) for p in sorted(paths)},'script_sha256':sha(__file__)}
    path=OUT/'independent_source_review.json'
    path.write_text(json.dumps(verdict,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:verdict[k] for k in ['status','validated_source_spans','distinct_author_versions','new_judge_requests']}))

if __name__=='__main__':main()
