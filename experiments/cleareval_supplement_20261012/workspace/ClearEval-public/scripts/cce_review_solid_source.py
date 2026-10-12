"""Record the root assistant's narrow source review and verify SOLID evidence anchors."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'artifacts/cce_validation/reference_recovery/solid_2024'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value,list):
        for child in value:
            yield from walk(child)

def main():
    paths=[DEST/name for name in ['candidate.json','source_passages.json','source_manifest.json',
                                 'supplement_review.json','task_applicability.json','validation.json']]
    inputs={str(p):sha(p) for p in paths}
    objects=[read(p) for p in paths]
    candidate=objects[0]
    assert inputs[str(paths[0])]=='edba891fec27eecb587299cdc1a9cd0a4bc6ca80ad6c4efc03c49d31d2e6ca3f'
    original=read(DEST/'main_text_v1_snapshot/candidate.json')
    assert candidate['continuous_conditions']==original['continuous_conditions']
    for before, after in zip(original['steps'], candidate['steps']):
        assert all(after[k]==v for k,v in before.items())
        assert set(after)-set(before)=={'supplemental_corroboration'}
    assert len(candidate['steps'])==6 and candidate['score_input'] is False
    assert not candidate.get('question_ids') and candidate['human_confirmation'] is None
    assert candidate['completeness']['clearing_RI_terminal_storage_complete'] is False
    assert candidate['stage_boundary']['terminal_storage'] is None
    assert candidate['initial_state']['SOLID_DL_required_for_every_sample'] is False
    spans=[]
    for obj in objects:
        for node in walk(obj):
            if 'path' in node and 'sha256' in node and isinstance(node['path'],str):
                path=Path(node['path'])
                assert path.exists() and sha(path)==node['sha256'], str(path)
                inputs[str(path)]=sha(path)
            if all(k in node for k in ('text_path','start','end','quote')):
                path=Path(node['text_path'])
                text=path.read_text(encoding='utf-8')
                assert text[node['start']:node['end']]==node['quote']
                assert hashlib.sha256(node['quote'].encode()).hexdigest()==node['quote_sha256']
                assert sha(path)==node['text_sha256']
                inputs[str(path)]=sha(path)
                spans.append((str(path),node['start'],node['end']))
    # These four source-page images were actually viewed by /root, separately from their author's review.
    viewed=[DEST/'source_pages/main_p03.png', DEST/'source_pages/main_p13.png',
            DEST/'supplement_pages/supplement_p01.png', DEST/'supplement_pages/supplement_p16.png']
    inputs.update({str(p):sha(p) for p in viewed})
    findings=[
        {'id':'S1','verdict':'pass','finding':'Four ordered gradient stages, a dehydration stage and endpoint-based RI matching are supported by main Methods p13. The whole-brain five-stage durations are reported examples, not specimen-specific confirmations.'},
        {'id':'S2','verdict':'pass','finding':'Gentle shaking and 30 C apply continuously to the reported clearing operation, including RI; these conditions are preserved separately rather than counted as extra operations.'},
        {'id':'S3','verdict':'pass_with_source_limit','finding':'The original HxD-TBN wording leaves the added water amount and percentage basis unresolved. Supplementary Fig1 compares formulations and does not justify silently normalizing a final recipe.'},
        {'id':'S4','verdict':'pass_with_source_limit','finding':'Pre-clearing PBS storage is not terminal post-RI storage. The candidate correctly stops at transparency and explicitly lacks a complete clearing-RI-storage scope.'},
        {'id':'S5','verdict':'pass','finding':'Main Fig1E labels deep labeling optional. Do not make SOLID-DL mandatory for every already labeled specimen or infer labeling completed in a fixed task specimen.'},
        {'id':'S6','verdict':'pass_with_source_limit','finding':'Supplementary Fig15A has neuronal/vascular/plaque channels; Fig15C antibody/probe overlap, read with Methods Par33, is a slice validation. This does not establish two whole-brain amyloid channels.'},
        {'id':'S7','verdict':'pass_with_source_conflict','finding':'The reported 3M/8M result groups remain distinct from the Animals 12/56-week statement; the supplement does not resolve the discrepancy.'},
        {'id':'S8','verdict':'pass','finding':'q13 asks self-selected dual targets; q14/q15 explicitly require mutual pathological-label verification. Recommended marker metadata is not silently made a verbatim task requirement.'},
    ]
    result={'status':'pass_for_inactive_source_record_with_explicit_unresolved_scope',
            'reviewer':'/root assistant, separate from SOLID candidate author /root/human_wetlab; not a human expert',
            'reviewed_utc':datetime.now(timezone.utc).isoformat(),'candidate_sha256':sha(paths[0]),
            'source_span_occurrences_checked':len(spans),'unique_source_spans_checked':len(set(spans)),
            'visually_viewed_pages':[str(p) for p in viewed], 'findings':findings,
            'blocking_for_source_record':[],
            'remaining_limits_for_scoring_or_route_confirmation':['No task binding','Terminal post-RI storage not established',
                'Formulation ambiguity remains','Whole-brain second pathological channel not established',
                'Reported age conflict unresolved','Human/reference confirmation absent'],
            'original_candidate_unchanged':True,'new_scores':0,'new_model_requests':0,'new_expert_labels':0,
            'input_sha256':inputs,'actual_command':subprocess.list2cmdline([sys.executable,*sys.argv]),
            'script_sha256':sha(__file__)}
    output=DEST/'review'
    output.mkdir(exist_ok=True)
    (output/'source_scope_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'source_scope_review.md').write_text(
        '# SOLID source-scope review\n\n'
        'The inactive six-operation source record passes this narrow source/representation review. '
        'This is an assistant review separate from the candidate author, not expert confirmation.\n\n'+
        '\n\n'.join(f"- {f['id']}: {f['finding']}" for f in findings)+
        f"\n\nVerified {len(spans)} source-span occurrences ({len(set(spans))} unique spans) and viewed four identified source-page images. "
        'No task assignments, score rows, candidate changes or expert labels were added. '
        'The candidate is not a confirmed complete clearing/RI/storage route. '
        'See [machine review](source_scope_review.json) for input hashes and actual command.\n',encoding='utf-8')
    print({k:v for k,v in result.items() if k not in ('input_sha256','findings','visually_viewed_pages','remaining_limits_for_scoring_or_route_confirmation')})

if __name__=='__main__':
    main()
