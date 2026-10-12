"""Prepare five paired development inputs without using any model-call budget."""
import copy
import difflib
import json
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent/'qualitative_canonical_pending'
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
sys.path.insert(0,str(ROOT/'scripts'))
import cce_canonical_qualitative_candidate_v1 as candidate
import cce_scoped_midpoint_scorer_v1 as b
control=candidate.canonical
case_path=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/grounded_development_v11/cases.json'
payload=b.read(case_path);cases=payload['cases'] if isinstance(payload,dict) else payload
public=b.read(R3/'E2_canonical_qwen_01/plan.json')['public_model']
checks=[];observations=[]
def check(name,passed):
    if not passed:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
for case in cases:
    identifier=case['anonymous_answer_id'];folder=OUT/identifier
    original=control.ground.document(case['model_response'],control.ground.source_id_for_case(case))
    doc=control.evaluation_document(case,original)
    mapping=control.source_mapping(case,doc)
    schema=control.schema_for_document(doc)
    prompts={'C0':control.make_prompt(case,doc),'C1':candidate.make_prompt(case,doc)}
    payloads={k:control.payload_for(v,schema,public) for k,v in prompts.items()}
    b.save(folder/'original_source_document.json',original)
    b.save(folder/'evaluation_source_document.json',doc)
    b.save(folder/'source_mapping.json',mapping)
    b.save(folder/'schema.json',schema)
    evaluated=control.evaluation_case(case)
    check(identifier+':same_question_and_references',all(evaluated[k]==case[k] for k in ['specific_question','references']))
    check(identifier+':same_schema_and_transport',
        {k:v for k,v in payloads['C0'].items() if k!='prompt'}=={k:v for k,v in payloads['C1'].items() if k!='prompt'})
    check(identifier+':all_nonformat_characters_source_bound',all(
        index is not None and case['model_response'][index]==mapping['evaluation_text'][i]
        for i,index in enumerate(mapping['canonical_char_to_original_char']) if not mapping['evaluation_text'][i].isspace()))
    check(identifier+':uncertainty_and_percent_deviation_replaced',
        '[UNCERTAINTY CONTRACT]' not in prompts['C1'] and '时间/浓度偏差在 50%' not in prompts['C1']
        and '[PARAMETER COMPARISON SOURCE ALIGNMENT]' not in prompts['C1'])
    check(identifier+':retains_reading_aid','[SOURCE-PRESERVING READING AID v3]' in prompts['C1'])
    for condition in ['C0','C1']:
        (folder/(condition+'_prompt.txt')).write_text(prompts[condition],encoding='utf-8')
        b.save(folder/(condition+'_request_payload.json'),payloads[condition])
        observations.append({'case_id':case['case_id'],'anonymous_answer_id':identifier,'question_id':case['question_id'],
            'condition':condition,'status':'prepared_not_requested','development_exposed':True,
            'source':b.bind(folder/'evaluation_source_document.json'),'mapping':b.bind(folder/'source_mapping.json'),
            'payload':b.bind(folder/(condition+'_request_payload.json')),'schema':b.bind(folder/'schema.json'),
            'raw_SR_SP_source_unchanged':True,'old_successful_return_exactly_reusable':False})
    (folder/'prompt.diff').write_text(''.join(difflib.unified_diff(prompts['C0'].splitlines(True),prompts['C1'].splitlines(True),
        fromfile='C0_canonical_archived_scope',tofile='C1_canonical_qualitative_scope')),encoding='utf-8')

b.save(OUT/'manifest.json',{'version':candidate.CANDIDATE_VERSION,'candidate':b.bind(candidate.__file__),
    'control':b.bind(control.__file__),'scope_text':b.bind(candidate.qualitative.__file__),'cases':b.bind(case_path),
    'public_model':public,'observations':observations,'planned_development_requests':10,'new_model_requests':0,
    'existing_call_budget_remaining':0,'approval_for_new_requests_not_recorded':True,
    'paired_input_conditions_fixed':True,'prospective_confirmation':False,
    'main_endpoint':'source-grounded qualitative criterion application and complete-score availability',
    'no_predetermined_required_score':True,'Cor_scales':[3,2,2,1],'Cor_aggregation_unchanged':True,
    'co_param_definition_changed':True,'new_expert_budget':0,
    'known_limitation':'five exposed development answers; no new reliability or generalization estimate'})
b.save(OUT/'verification.json',{'checks':checks,'checks_passed':len(checks),'new_model_requests':0})
b.save(OUT/'execution.json',{'command':[sys.executable,*sys.argv],'new_model_requests':0})
print(json.dumps({'prepared':len(observations),'pairs':len(cases),'checks_passed':len(checks),'new_model_requests':0}))
