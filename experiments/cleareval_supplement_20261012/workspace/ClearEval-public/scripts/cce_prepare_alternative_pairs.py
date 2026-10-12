"""Freeze six real-answer alternative-route candidate pairs pending source confirmation.

No generation, no scientific editing and no model requests. This is a waiting
matrix, not six completed or qualified alternative-route comparisons.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cce_validation import ROOT,OUT,read,write,table,digest,filehash

def main():
    references=read(OUT/'reference_recovery/references_two_source_development.json')['references']
    models=['gemini-3-pro','openai_deepseek-chat','openai_deepseek-reasoner']
    answers={}
    cases=[]
    for model in models:
        source=ROOT/'dataset/Q+AR/model_response'/f'from_{model}_1-shot.json'
        for answer in read(source):
            if answer['question_id'] not in [21,22,23]:continue
            cid=model+'__q'+str(answer['question_id'])+'__alternative_route_candidate'
            case={'case_id':cid,'question_id':answer['question_id'],'specific_question':answer['specific_question'],
                'model_response':answer['model_response'],'generator_model':model,'base_id':'alternative_q'+str(answer['question_id']),
                'condition':'alternative_route_natural_answer_candidate','references':references,
                'scope':'unrun_source_extracted_candidates_not_qualified_alternative_routes',
                'reference_status':'source_extracted_pending_supplement_and_expert',
                'source_family':['FDISCO_QI2019_MOUSE_BRAIN','PEGASOS_JING2018_MOUSE_BRAIN'],
                'answer_source':str(source),'answer_sha256':digest(answer['model_response']),
                'question_sha256':digest(answer['specific_question'])}
            answers[(model,answer['question_id'])]=case;cases.append(case)
    pairs=[]
    for qid in [21,22,23]:
        baseline=answers[('gemini-3-pro',qid)]
        for model in models[1:]:
            alternative=answers[(model,qid)]
            assert baseline['question_sha256']==alternative['question_sha256']
            pairs.append({'pair_id':f'q{qid}__gemini-pro_vs_{model}__candidate',
                'question_id':qid,'baseline_case_id':baseline['case_id'],'alternative_case_id':alternative['case_id'],
                'same_archived_question_sha256':baseline['question_sha256'],
                'routes':['FDISCO','PEGASOS'],'generator_models':['gemini-3-pro',model],
                'candidate':True,'eligible_confirmed':False,'full_pipeline_complete':False,
                'status':'needs_complete_reference_and_applicability_confirmation',
                'causal_scope':'Different archived answers and generators; not an isolated causal effect of route.'})
    write(OUT/'controls/alternative_route_candidate_cases.json',{'cases':cases})
    write(OUT/'controls/alternative_route_candidate_pairs.json',pairs)
    table(OUT/'controls/alternative_route_candidate_pairs.csv',pairs)
    write(OUT/'controls/alternative_route_waiting_matrix.json',{'candidate_pairs':6,'confirmed_eligible_pairs':0,
        'completed_pairs':0,'unique_actual_answers':9,'question_ids':[21,22,23],'task_families':1,
        'reference_source_families':2,'judge_models':['local_qwen3_8b'],'repeats':1,
        'prospective_new_pipeline_requests':9,'new_requests_this_preparation':0,'formal_eligible':False,
        'case_file_sha256':filehash(OUT/'controls/alternative_route_candidate_cases.json'),
        'pair_file_sha256':filehash(OUT/'controls/alternative_route_candidate_pairs.json'),
        'gate':'Confirm complete references and applicability first; freeze updated sources/settings before executing.',
        'reuse_note':'Existing single-reference judge trials do not match this two-reference evidence context and are not pre-counted as reusable.'})
    print('Frozen 6 candidate pairs / 9 actual answers; 0 confirmed eligible, 0 executed, future matrix 9 requests.')

if __name__=='__main__':main()
