"""Prepare the remaining two development observations; never issue a model call."""
import copy,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_source_alignment_prompt_candidate_v1 as candidate
import cce_round3_runner_v1 as runner

def main():
    r3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
    source=r3/'development_inputs_01'
    out=r3/'source_alignment_inputs_01'
    cases=runner.j.read(source/'cases.json')['cases'][:2]
    steps=runner.j.read(source/'steps.json')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
        'stage':'adaptive_development_before_two_new_returns',
        'trigger':'actual v3 q2 numbering pair co_param 2 vs 1; both provider and conversion complete',
        'question_ids':[2], 'case_ids':[c['case_id'] for c in cases],
        'intervention':'append only generic reference alignment instruction',
        'held_fixed':['same full answers','same reference evidence','same rubric','same schema and property order',
            'same representation aid','same Qwen settings','same v7 component processor','same original SR/SP'],
        'no_ground_truth_score_prescribed':True,
        'primary_observations':['co_param reasoning numerical claims and source anchors','all five direct metric pair differences','missingness'],
        'failure_criteria':['supplied reference values still invented or transferred across phases',
            'a numeric format-pair difference remains in any direct metric'],
        'null_pair_interpretation':'may support source discipline if correctly justified, never numeric invariance or recovered scientific correctness',
        'success_limits':'one exposed task, one return per answer; no generalized accuracy claim',
        'source_alignment_and_score_order_are_not_combined':True,
        'expected_new_calls':2,'new_model_calls_by_prepare':0,
        'source_bindings':[runner.bind(source/'cases.json'),runner.bind(source/'steps.json'),
            runner.bind(candidate.__file__),runner.bind(candidate.base.__file__)],
        'literature_cycle':'problem_cycles/parameter_drift_cycle01'}
    checks=[]
    for c in cases:
        d=runner.base.grounded.document(c['model_response'],runner.base.grounded.source_id_for_case(c))
        before=copy.deepcopy(c)
        old=candidate.base.make_prompt(c,d);new=candidate.make_prompt(c,d)
        assert new==old+'\n'+candidate.NOTE
        a=candidate.schema_for_document(d);b=candidate.base.schema_for_document(d)
        assert runner.ordered(a)==runner.ordered(b)
        assert c==before
        checks.append({'case_id':c['case_id'],'single_append_only':True,'ordered_schema_identical':True,
            'answer_sha256':hashlib.sha256(c['model_response'].encode()).hexdigest(),
            'prompt_sha256':hashlib.sha256(new.encode()).hexdigest()})
    out.mkdir(parents=True,exist_ok=False)
    for name,value in [('cases.json',{'cases':cases}),('steps.json',{c['case_id']:steps[c['case_id']] for c in cases}),
                       ('development_plan.json',plan),('software_checks.json',checks)]:
        runner.save_once(out/name,value)
    print(json.dumps({'status':'prepared_inputs','cases':len(cases),'checks':checks,'new_model_calls':0},ensure_ascii=True))

if __name__=='__main__':main()
