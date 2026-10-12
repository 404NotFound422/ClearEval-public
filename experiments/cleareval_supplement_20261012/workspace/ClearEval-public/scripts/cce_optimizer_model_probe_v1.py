"""Five actual development calls isolating a local model change from prompt changes."""
import argparse
import asyncio
import contextlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_judges as j
import cce_output_identity_v2 as original
import cce_output_contract_v1 as parent
import cce_analyze_output_contract_v1 as audit

OUT=ROOT/'artifacts/cce_validation/optimizer_20261010/model_probe_v1'
RUN=OUT/'run'
MODEL='local_qwen27b_q8_development'


def require(ok,why):
    if not ok:raise ValueError(why)


def args(allow=False):
    return SimpleNamespace(out=RUN,cases=OUT/'cases.json',model_config=OUT/'model_config.json',
        models=[MODEL],question_file=j.HIST,demand_file=ROOT/'dataset/Q+AR/src/demand_vectors_all.json',
        demand_manifest=None,ledger=parent.LEDGER,total_budget=300,external_request_count=0,
        max_calls=5,max_attempts=1,repeats=1,temperature=0.,max_output_tokens=8192,timeout_seconds=600,allow_api=allow)


def validate():
    original.validate();original.require_probes();plan=j.read(OUT/'plan.json')
    for r in plan['frozen_inputs']:require(j.filehash(r['path'])==r['sha256'],'frozen_probe_input_changed:'+r['path'])
    return plan


def record(action,**details):
    p=OUT/'actual_commands.json';rows=j.read(p) if p.exists() else []
    rows.append({'utc':j.now(),'actual_command':[sys.executable,*sys.argv],'action':action,
                 'script_sha256':j.filehash(__file__),'requests_snapshot':parent.request_count(),**details})
    j.save(p,rows)


@contextlib.contextmanager
def runtime():
    with original.wrapper():
        old=j.contract
        def contract(*a,**kw):
            actual=old(*a,**kw)
            require(actual==j.read(OUT/'expected_contract.json'),'runtime_contract_drift_before_request')
            return actual
        j.contract=contract
        try:yield
        finally:j.contract=old


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'plan.json').exists():validate();return
    original.validate();original.require_probes();before=parent.request_count()
    require(before==192,'prespecified_model_only_probe_must_start_at_192')
    (OUT/'cases.json').write_bytes((original.OUT/'cases.json').read_bytes())
    config={'models':[{'name':MODEL,'type':'Ollama','model_name':'qwen3.8:27b-q8_0-local',
        'host':'http://127.0.0.1:11434','model_digest':'ea6892d079c639acf4812dee100eca284199c3ae3fb4ffd9e5a5ae8641ae73ba',
        'temperature':0.,'max_tokens':8192,'num_ctx':40960,'enable_thinking':False,'format':'json','transport':'http'}]}
    j.save(OUT/'model_config.json',config)
    with original.wrapper(),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        _,_,_,models,cases,contract=j.preflight(args())
    old=j.read(original.RUN/'preflight.json')['contract']
    require({**contract,'models':[]}=={**old,'models':[]},'non_model_science_contract_changed')
    require([c['anonymous_answer_id'] for c in cases]==['A01','A02','A03','A04','A05'],'development_population_changed')
    require(len(models)==1 and models[0]['name']==MODEL,'model_selection_changed')
    j.save(OUT/'expected_contract.json',contract)
    ledger_ids={r['trial_id'] for r in j.ledger_rows(parent.LEDGER)}
    matrix=[]
    for c in cases:
        identity={'case_id':c['case_id'],'input_sha256':c['input_sha256'],'judge':MODEL,'repeat_index':0,'contract_sha256':j.digest(contract)}
        require(j.digest(identity) not in ledger_ids,'probe_trial_already_recorded')
        matrix.append({'anonymous_answer_id':c['anonymous_answer_id'],'identity':identity,'planned_trial_id':j.digest(identity),'attempt':1,
                       'expected_prompt_sha256':j.filehash(original.OUT/'prompts'/f"{c['anonymous_answer_id']}_prompt.txt")})
    j.save(OUT/'matrix.json',matrix)
    paths=[Path(__file__),OUT/'cases.json',OUT/'model_config.json',OUT/'expected_contract.json',OUT/'matrix.json',
        original.OUT/'plan.json',original.OUT/'software_probes.json',original.RUN/'preflight.json',Path(original.__file__),Path(parent.__file__)]
    paths += [original.OUT/'prompts'/f'{aid}_prompt.txt' for aid in ['A01','A02','A03','A04','A05']]
    plan={'status':'frozen_before_generation','kind':'model_only_exposed_development_probe','planned_new_requests':5,
        'max_attempts':1,'starting_requests':before,'development_budget_charge':5,'generation_model_identity':models[0]['public'],
        'old_prompt_version':'output_identity_v2','non_model_science_contract_exactly_unchanged':True,
        'predefined_outcomes':['strict structural pass count','complete original numeric component count','raw full-name retention','extracted-time and direct-score differences'],
        'success_interpretation':'Structural and numeric completeness alone do not prove faithful entities, target relations or times. No best-model or best-output claim without later grounded controls and confirmation.',
        'formal_eligible':False,'human_expert_returns':0,'old_observations_replaced':False,
        'frozen_inputs':[parent.bind(p) for p in paths]}
    j.save(OUT/'plan.json',plan);validate()
    require(parent.request_count()==before,'metadata_prepare_made_generation')
    record('prepare',new_requests=0,planned_new_requests=5)
    print(j.canonical({'status':'prepared_zero_generation','model':MODEL,'new_calls_planned':5,'scientific_contract_same_except_model':True}))


async def run():
    validate();before=parent.request_count()
    with runtime():await j.run(args(True))
    validate();record('run',new_requests=parent.request_count()-before)


def analyze():
    validate();before=parent.request_count()
    matrix=j.read(OUT/'matrix.json');cases={c['case_id']:c for c in j.read(OUT/'cases.json')['cases']}
    ledger={r['request_id']:r for r in j.ledger_rows(parent.LEDGER)}
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):runner,_,registry=j.runtime(args())
    rows=[];bound=[]
    for cell in matrix:
        p=RUN/'trials'/f"{cell['planned_trial_id']}.json";require(p.exists(),'probe_not_complete')
        t=j.read(p);c=cases[t['case_id']];e=t.get('evaluation') or {};attempt=RUN/'attempts'/f"{t['trial_id']}_1"
        require(t['identity']==cell['identity'] and t['attempt']==1 and t['actual_api_request_made'],'actual_trial_identity')
        receipt=j.read(attempt/'request_receipt.json');require(receipt==ledger[receipt['request_id']],'actual_receipt_identity')
        require(j.filehash(attempt/'prompt.txt')==cell['expected_prompt_sha256']==t['prompt_sha256'],'prompt_changed')
        values=j.proposals(e);extraction=e.get('extraction');replay=False
        if t['status']=='success':
            demand=registry.get(c['question_id'],c['specific_question']);meta=runner.QUESTION_META_KB[registry.questions[str(c['question_id'])]['question_id']]
            quant={'method_name':extraction['method_name'],'tissue_ri_value':meta.get('tissue_ri_value'),
                   'total_time_hours':extraction['clearing_total_time_hours'],'sample_tier':meta.get('tissue_tier_code')}
            for k in ['reagent_ri_value','protocol_time_hours','method_stages']:
                if k in extraction:quant[k]=extraction[k]
            require(quant==e['quantitative_data'] and demand==e['user_preference_vector'],'original_EGES_inputs')
            score=runner.calculate_effectiveness_score(quant,demand,runner.MODEL_SPACE_SIGNED,extraction['marker_dict'],meta.get('marker_query_targets') or [])
            require(all(audit.same(score[k],values[k]) for k in audit.EGES),'original_EGES_replay')
            replay=True
        rows.append({'anonymous_answer_id':cell['anonymous_answer_id'],'trial_id':t['trial_id'],'request_index':receipt['package_request_index'],
            'status':t['status'],'original_numeric_proposals':values,'complete_numeric':all(audit.finite(values[k]) for k in audit.METRICS),
            'extraction':extraction,'eges_replayed':replay,'failure_stage':e.get('failure_stage'),'extraction_truth_expert_verified':False})
        bound += [parent.bind(x) for x in [p,*sorted(x for x in attempt.glob('*') if x.is_file())]]
    j.save(OUT/'per_answer.json',rows)
    result={'status':'complete','observations':5,'new_requests':5,'successes':sum(r['status']=='success' for r in rows),
            'complete_numeric':sum(r['complete_numeric'] for r in rows),'original_EGES_replays':sum(r['eges_replayed'] for r in rows),
            'requests_snapshot':before,'same_prompt_and_scientific_contract_except_model':True,'human_expert_returns':0,
            'formal_eligible':False,'new_analysis_requests':0,'bound_observations':bound}
    j.save(OUT/'completion_summary.json',result)
    require(parent.request_count()==before,'analysis_made_generation');record('analyze',new_requests=0)
    print(j.canonical({k:v for k,v in result.items() if k!='bound_observations'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','analyze']);p.add_argument('--allow-local-calls',action='store_true');options=p.parse_args()
    if options.action=='run':
        require(options.allow_local_calls,'explicit_local_execution_flag_required');asyncio.run(run())
    else:{'prepare':prepare,'analyze':analyze}[options.action]()
