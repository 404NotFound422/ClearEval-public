"""Synthetic-only check: no heldout texts, judge outputs or encoder weights loaded."""
from pathlib import Path
import ast,json,math,sys,types
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cce_holdout_source_steps_v1 as driver
core=driver.core
SCRIPT=Path(driver.__file__)
ast.parse(SCRIPT.read_text(encoding='utf-8'))
raw=[]
for i in range(15):
    text='Chosen Method: TEST\nChosen Labeling: synthetic\nProtocol Steps:\n1. Incubate prepared material in buffer.\nTemperature: 25 °C; Time: 1 h\n2. Wash sample gently with water.\n'
    if i==13:text='Chosen Method: OTHER\nProtocol Steps:\n1. Wash sample gently with water.\n'
    if i==14:text='Chosen Method: TEST\nProtocol Steps:\nA heading\n'
    q='Synthetic question '+str(i)
    raw.append({'anonymous_answer_id':f'A{i+6:02d}','case_id':f'A{i+6:02d}__synthetic','question_id':901+i,
      'split':'audit_holdout','condition':'baseline','specific_question':q,'model_response':text,
      'answer_sha256':core.digest(text),'question_sha256':core.digest(q),
      'model_name':'SYNTHETIC_PROVIDER_METADATA_SHOULD_DROP','unrelated_score':'SYNTHETIC_SCORE_SHOULD_DROP'})
cases=driver.validate_cases({'cases':raw})
refs=[{'reference_id':'synthetic_ref','route_id':'TEST','question_ids':[c['question_id'] for c in cases],
  'steps':['Incubate reference material in buffer.','Wash sample gently with water.'],'status':'synthetic_only',
  'source_path':str(Path(__file__)),'family_id':'synthetic_family','scope_conditions':'Synthetic check, no biological evidence.'}]
assert driver.validate_references({'references':refs},cases)==refs
class FakeEncoder(core.Encoder):
    def __init__(self):
        self.model=types.SimpleNamespace(max_seq_length=384,tokenizer=types.SimpleNamespace(encode=lambda t:list(range(len(t.split())))))
    def encode(self,texts):
        return np.asarray([[1.,0.,0.] if 'reference material' in t else [0.75,math.sqrt(1-0.75**2),0.] if 'Incubate' in t else [0.,0.,1.] for t in texts])
enc=FakeEncoder();calls=[];original=core.score_steps
def capture(a,r,e,t):
    calls.append((a['question_id'],a['model_response'],t))
    return original(a,r,e,t)
core.score_steps=capture
try: rows,details,review=driver.score_all(cases,refs,enc,'synthetic_plan_only')
finally:core.score_steps=original
assert len(calls)==45 and len(rows)==45 and len(review)==15
for q,text,t in calls:assert text==next(c['model_response'] for c in cases if c['question_id']==q)
for row in rows:
    if row['anonymous_answer_id']=='A19':assert row['sr'] is None and row['step_missing_reason']=='reference_insufficient'
    elif row['anonymous_answer_id']=='A20':assert row['sr']==0 and row['sp']==0 and row['step_missing_reason'] is None
    else:assert row['sr']==row['sp']==(0.5 if row['threshold']==0.8 else 1.0)
assert all('Temperature: 25 °C; Time: 1 h' in d['step_result']['generated_steps'][0]['text'] for d in details if d['anonymous_answer_id'] not in ['A19','A20'])
payload=json.dumps([rows,details,review],ensure_ascii=False)
assert 'SYNTHETIC_PROVIDER_METADATA_SHOULD_DROP' not in payload and 'SYNTHETIC_SCORE_SHOULD_DROP' not in payload
for attachment in review:
    assert not any(k in attachment for k in ['sr','sp','model','model_name','Cor','Eff','IA','HV','Com','similarity','matched'])
    for pair in attachment['automatic_candidate_pairs']:
        assert not any(k in pair for k in ['similarity','matched','sr','sp'])
        assert pair['expert_match_decision']==pair['expert_note']==''
errors=0
for bad in [dict(raw[0],answer_sha256='bad'),dict(raw[0],question_sha256='bad'),dict(raw[0],anonymous_answer_id='model__q1')]:
    try:driver.validate_cases({'cases':[bad,*raw[1:]]})
    except ValueError:errors+=1
assert errors==3
try:driver.source_path(driver.CASES)
except ValueError:pass
else:raise AssertionError('Judge directory must be excluded from source inputs.')
assert not (driver.DEST/'plan.json').exists(),'Unexpected real preparation already exists; this check must remain separate.'
out=driver.ART/'tool_checks/holdout_source_steps_v1';out.mkdir(parents=True,exist_ok=True)
report={'status':'PASS_synthetic_only','driver_sha256':core.filehash(SCRIPT),'selftest_sha256':core.filehash(__file__),
 'checks':{'unchanged_core_calls_on_full_synthetic_texts':45,'synthetic_cases':15,'thresholds':[0.6,0.7,0.8],
 'full_text_continuations_preserved':True,'reference_NA_distinct_from_true_zero':True,
 'threshold_changes_use_inherited_encoder_score':True,'anonymous_metadata_boundary':True,
 'reviewer_metrics_hidden_and_expert_fields_blank':True,'bad_identity_checks':3,'judge_source_path_rejected':True},
 'real_prepare_or_run_executed':False,'real_holdout_answers_read':0,'judge_outputs_read':0,'real_encoder_or_weights_loaded':False,
 'new_model_requests':0,'new_embeddings':0,'limitations':'Static + pure synthetic calculation check; not a real-data end-to-end run or independent expert review.',
 'actual_command':[sys.executable,*sys.argv]}
core.write(out/'selftest.json',report)
print(json.dumps({'status':report['status'],'actual_core_calls':45,'real_holdout_answers_read':0,'selftest_result_sha256':core.filehash(out/'selftest.json')}))
