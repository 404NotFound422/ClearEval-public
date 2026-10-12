"""Prepare source-linked pilot metadata and deterministic text controls."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cce_validation import ROOT,OUT,read,write,table,digest,filehash,segment,Encoder,score_steps

QIDS=[2,21,22,23,248]
MODELS=['gemini-3-flash','gemini-3-pro']

def prepare_refs():
    path=OUT/'reference_recovery/references.json'; doc=read(path)
    # Preserve the actually executed initial reference snapshot, including its typo.
    old=OUT/'reference_recovery/initial_q2_reference_snapshot.json'
    if not old.exists():write(old,doc)
    ref=doc['references'][0]
    for step in ref['steps']:step['text']=step['text'].replace('4 ?C','4 degrees C')
    ref['question_ids']=QIDS
    ref['question_applicability']={
        '2':{'task_family':'whole_brain_structure','scope':'Fixed mouse brain, post-fixation clearing only; labeling feasibility is not established by this reference.'},
        '21':{'task_family':'weak_reporter_brain_block_storage','scope':'Fixed 3 mm mouse brain block and storage; same source procedures, source-specific times unavailable.'},
        '22':{'task_family':'weak_reporter_brain_block_storage','scope':'Fixed 3 mm mouse brain block and storage; six-month outcome is NOT guaranteed by step coverage.'},
        '23':{'task_family':'weak_reporter_brain_block_storage','scope':'Fixed 3 mm mouse brain block and storage; repeat-imaging recovery is conditional and separately recorded.'},
        '248':{'task_family':'fixed_reporter_whole_brain','scope':'Already fixed reporter whole brain. No vector preparation, delivery, or labeling intervention is constructed.'}}
    ref['applicability']['remaining_review'] += ['Expanded question applicability and long-storage conditional recovery await review; no statement of complete target labeling coverage.'] if len(ref['question_ids'])>1 and not any('Expanded' in s for s in ref['applicability']['remaining_review']) else []
    ref['applicability']['scope']='Post-fixation tissue clearing, refractive-index matching, and storage only; requested target labeling judged separately. Long-storage rescue before repeated imaging is conditional, not an unconditional SR item.'
    ref['frozen']=True;ref['freeze_scope']='development baseline, no human confirmation'
    write(path,doc)
    hist={int(x['question_id']):x for x in read(ROOT/'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json')}
    links=[]
    for model in MODELS:
        p=ROOT/'dataset/Q+AR/model_response'/f'from_{model}_1-shot.json'
        for i,a in enumerate(read(p)):
            if a['question_id'] not in QIDS:continue
            h=hist[a['question_id']]
            assert a['specific_question']==h.get('specific_question',h.get('question'))
            links.append({'answer_id':f'{model}__q{a["question_id"]}','model':model,'question_id':a['question_id'],'array_index':i,'answer_path':str(p),'answer_sha256':digest(a['model_response']),'question_sha256':digest(a['specific_question']),'historical_question_exact_match':True,'source_family':ref['family_id'],'task_family':ref['question_applicability'][str(a['question_id'])]['task_family']})
    write(OUT/'reference_recovery/answer_source_links.json',links)
    write(OUT/'reference_recovery/reference_construction_ledger.json',{'scope':'first_source_historical_snapshot','current_summary':'reference_construction_current.json','reused_primary_sources':1,'source_extracted_routes':1,'human_confirmed_routes':0,'source_families':1,'task_families':3,'question_ids':QIDS,'natural_answer_links':len(links),'new_human_work':'One route plus its applicability conditions; separate from 5+15 answer review.','missing':'Second complete applicable routes and source-specific incubation table not recovered.'})
    print('Prepared 5 questions / 3 task families / 1 source family / 10 source-linked answers.')

def controlled_cases():
    """Edits are deterministic removals/format changes of existing natural answers.

    They are development candidates until necessity/applicability is confirmed.
    Every edited full text is then parsed and matched afresh.
    """
    refs=read(OUT/'reference_recovery/references.json')['references']
    cases=[];edits=[]
    # Select before inspecting responses: first 3 qids in fixed list, second archived model.
    answers={x['question_id']:x for x in read(ROOT/'dataset/Q+AR/model_response/from_gemini-3-pro_1-shot.json')}
    for qid in [2,21,22]:
        a=answers[qid];text=a['model_response'];base=f'gemini-3-pro__q{qid}'
        shared={'question_id':qid,'specific_question':a['specific_question'],'generator_model':'gemini-3-pro','base_id':base,'references':refs,
                'reference_status':'source_extracted','source_family':'FDISCO_QI2019_MOUSE_BRAIN','scope':'development_control_candidates_not_human_confirmed'}
        cases.append({**shared,'case_id':base+'__baseline','condition':'baseline','model_response':text})
        # Remove all processing statements naming the RI solvent. A joint RI/storage
        # module edit is explicitly recorded, not mislabeled as one atomic operation.
        spans=[s for s in segment(text) if re.search(r'\bDBE\b|dibenzyl ether',s['text'],re.I)]
        changed=text
        for s in reversed(spans):changed=changed[:s['start']]+changed[s['end']:]
        if spans and changed!=text:
            variant=base+'__ri_storage_module_deletion'
            cases.append({**shared,'case_id':variant,'condition':'necessary_step_deletion','model_response':changed})
            edits.append({'case_id':variant,'edit_type':'delete_all_RI_solvent_operation_spans','removed_spans':spans,'source_step_ids':['FDISCO-06','FDISCO-07'],'manipulation_scope':'RI plus storage module; not atomic single-step deletion','residual_in_justification':bool(re.search(r'\bDBE\b|dibenzyl ether',changed,re.I)),'necessity_status':'source_supported_development_pending_expert'})
        # Remove every time annotation from the answer, retaining the operation.
        # This is a parameter class deletion, not one concentration manipulation.
        changed,n=re.subn(r',?\s*Time:\s*[^)\n]+','',text,flags=re.I)
        changed,extra=re.subn(r'\b(?:for\s+)?\d+(?:\.\d+)?(?:\s*[-\u2013]\s*\d+(?:\.\d+)?)?\s*(?:hours?|hrs?|minutes?|mins?|days?)\b','',changed,flags=re.I)
        if n:
            variant=base+'__time_parameter_deletion'
            cases.append({**shared,'case_id':variant,'condition':'necessary_parameter_deletion','model_response':changed})
            edits.append({'case_id':variant,'edit_type':'delete_all_Time_annotations_and_numeric_durations','removed_occurrences':n,'other_duration_expressions_removed':extra,'parameter':'process_duration','stem_supplies_process_duration':False,'scope':'all explicit process durations; class deletion rather than one atomic parameter','remaining_numeric_durations':re.findall(r'\d+\s*(?:hours?|days?|min(?:utes)?)',changed,re.I),'necessity_status':'source_supported_development_pending_expert'})
        # Change only structural numbering. Parameters and operational text untouched.
        changed,n=re.subn(r'(?m)^(\s*)\d+(?:\.\d+)*\s+',r'\1- ',text)
        if n:
            variant=base+'__equivalent_numbering'
            cases.append({**shared,'case_id':variant,'condition':'deterministic_equivalent_representation','model_response':changed})
            edits.append({'case_id':variant,'edit_type':'numbering_to_bullets','changed_line_prefixes':n,'meaning_preserved':'deterministic structural numbering only'})
    out=OUT/'controls';write(out/'cases.json',{'cases':cases})
    write(out/'edits.json',edits)
    write(out/'planned_matrix.json',{'case_n':len(cases),'base_n':3,'variant_n':len(edits),'judge':'openai_qwen-max','repeats':1,'max_requests_before_retries':len(cases),'max_attempts_each':2,'baseline_and_variants_same_configuration':True,'alternative_route_pairs':0,'critical_conflicts':0,'pending_conditions':['complete_alternative_route: second full applicable source missing','evidence_supported_critical_conflict: no independently confirmed applicable manipulation yet'],'selection':'fixed qids 2,21,22 and generator gemini-3-pro, before fresh judge outputs'})
    print('Saved',len(cases),'full-text cases and',len(edits),'edits.')

def score_controls():
    cases=read(OUT/'controls/cases.json')['cases'];refs=read(OUT/'reference_recovery/references.json')['references'];enc=Encoder()
    step_config={'encoder':enc.identity,'threshold':.7,'adapter_sha256':filehash(Path(__file__).parent/'cce_validation.py'),'reference_sha256':digest(refs)}
    write(OUT/'controls/step_config.json',step_config)
    results=[]
    for c in cases:
        step=score_steps(c,refs,enc,.7)
        results.append({'case_id':c['case_id'],'base_id':c['base_id'],'condition':c['condition'],'question_id':c['question_id'],'input_sha256':digest(c['model_response']),'step_config_sha256':digest(step_config),'sr':step['sr'],'sp':step['sp'],'reference_id':step['reference_id'],'step_result':step,'scope':'step_only_full_text_reparse_pending_fresh_judge'})
    bases={r['base_id']:r for r in results if r['condition']=='baseline'}
    pairs=[]
    for r in results:
        if r['condition']=='baseline':continue
        b=bases[r['base_id']]
        pairs.append({k:r[k] for k in ['case_id','base_id','condition','question_id','scope']}|{'baseline_sr':b['sr'],'variant_sr':r['sr'],'delta_sr':r['sr']-b['sr'] if r['sr'] is not None and b['sr'] is not None else None,'baseline_sp':b['sp'],'variant_sp':r['sp'],'delta_sp':r['sp']-b['sp'] if r['sp'] is not None and b['sp'] is not None else None,'input_changed':r['input_sha256']!=b['input_sha256'],'full_pipeline_complete':False})
    write(OUT/'controls/step_results.json',results);table(OUT/'controls/step_pairs.csv',pairs)
    print(json.dumps(pairs,ensure_ascii=True),flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['references','controls','score-controls']);a=p.parse_args()
    {'references':prepare_refs,'controls':controlled_cases,'score-controls':score_controls}[a.command]()
