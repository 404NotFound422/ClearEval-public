"""Replay explicitly authored, source-bound labels and operation-time scenarios.

This entry point performs arithmetic over an auditable semantic ledger. It does
not call a model, decide source semantics, or replace the archived judgments.
"""
import argparse
import copy
import csv
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_typed_label_scorer_v2 as typed
from cce_grounded_offline_scoring_v1 import derive,DIRECT,EGES
from cce_scales_source_key_alias_v1 import source_key_alias
b=typed.base
VERSION='source-assisted-semantic-ledger-replay-v1'


def calculate_time(annotation,scenario,doc):
    ops={o['operation_id']:o for o in annotation['operations']}
    assert len(ops)==len(annotation['operations'])
    for op in ops.values():
        for span in op['source_spans']:b.verify_span(doc['text'],span)
    selected=scenario['selected_operations'];ids=[x['operation_id'] for x in selected]
    assert len(ids)==len(set(ids)),'Duplicate execution must use an explicit repeat count'
    contributions=[];unknown=[]
    for choice in selected:
        op=ops[choice['operation_id']]
        assert op['role']=='core','An excluded or handling event cannot silently become timed core'
        duration=op['duration_options'][choice['duration_option']]
        bounds=duration['bounds_hours'];count=duration['count']
        assert type(count) is int and count>0
        record={'operation_id':op['operation_id'],'duration_option':choice['duration_option'],
            'reported_bounds_hours':bounds,'repeat_count':count,'duration_basis':duration['basis'],
            'source_spans':op['source_spans'],'interpretation':op['interpretation']}
        if bounds is None:
            record['contribution_hours']=None;unknown.append(op['operation_id'])
        else:
            assert len(bounds)==2 and all(b.finite(x) for x in bounds) and 0<=bounds[0]<=bounds[1]
            record['contribution_hours']=[x*count for x in bounds]
        contributions.append(record)
    assert ids,'A runtime cannot be estimated from an empty core ledger'
    totals=[sum(c['contribution_hours'][i] for c in contributions if c['contribution_hours'] is not None) for i in [0,1]]
    return {'hours':sum(totals)/2 if not unknown else None,
        'bounds_hours':totals if not unknown else None,'known_subtotal_bounds_hours':totals,
        'unknown_duration_operations':unknown,'contributions':contributions,
        'omitted_core_operations':scenario.get('omitted_core_operations',[]),
        'decision':'finite_range_midpoint' if not unknown else 'known_subtotal_with_unreported_durations',
        'complete_elapsed_laboratory_time':False,'scope':'reported core incubations only'}


def label_replay(row,post,quantitative,policy,config,runner,registry,annotation,doc,relations):
    one={**annotation,'relations':relations}
    return typed.replay_row({**row,'quantitative_data':quantitative},post,policy,config,runner,registry,one,doc)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',required=True,type=Path)
    p.add_argument('--metric-key',required=True)
    p.add_argument('--annotations',required=True,type=Path)
    p.add_argument('--config',required=True,type=Path)
    p.add_argument('--policy',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    args=p.parse_args()
    plan={'version':VERSION,'entrypoint':b.bind(__file__),'baseline':b.bind(args.baseline),
        'metric_key':args.metric_key,'annotations':b.bind(args.annotations),
        'config':b.bind(args.config),'label_policy':b.bind(args.policy),
        'label_scorer':b.bind(typed.__file__),'new_model_calls':0,
        'scientific_status':'source-assisted author analysis, not independent evaluator or expert',
        'score_functions':'original direct scores, raw SR/SP and EGES equations retained'}
    if (args.out/'plan.json').exists():assert b.read(args.out/'plan.json')==plan
    else:b.save(args.out/'plan.json',plan)
    (args.out/'code_snapshot').mkdir(parents=True,exist_ok=True)
    for script in [Path(__file__),Path(typed.__file__)]:
        (args.out/'code_snapshot'/script.name).write_bytes(script.read_bytes())
    annotations={r['cell_id']:r for r in b.read(args.annotations)['results']}
    rows=b.read(args.baseline);config=b.read(args.config);policy=b.read(args.policy)
    runner,registry=b.runtime();results=[];checks=[];source_files={}

    def check(name,passed):
        if not passed:raise AssertionError(name)
        checks.append({'name':name,'passed':True})

    def time_metrics(metric,quantitative,demand,hours):
        with source_key_alias():
            numeric=runner.calculate_effectiveness_score({**quantitative,'total_time_hours':hours},
                demand,runner.MODEL_SPACE_SIGNED,{},[])
        return derive({**{k:metric[k] for k in DIRECT+EGES},'s_time':numeric['s_time']},
            {k:metric[k] for k in ['sr','sp']},True),numeric['time_computation']

    for row in rows:
        metric=copy.deepcopy(row[args.metric_key]);annotation=annotations.get(row['cell_id'])
        result={**row,'source_assisted_metrics':metric,'source_assisted_complete_CCE':b.complete(metric),
            'author_annotation_applied':bool(annotation),'semantic_scenarios':[]}
        if annotation:
            doc=b.read(row['source_document']['path'])
            record=row.get('lexical_post') or row['source_record'];post=b.read(record['path'])
            check('annotation_identity:'+row['cell_id'],annotation['answer_sha256']==doc['answer_sha256']
                  and annotation['question_id']==row['question_id'])
            for binding in [row['source_document'],record,row['trial']]:
                check('binding:'+binding['path'],b.bind(binding['path'])==binding)
                source_files[binding['path']]=binding
            for unit in annotation['unit_review']:b.verify_span(doc['text'],unit['source'])
            check('whole_source_unit_review:'+row['cell_id'],
                [u['source']['unit_id'] for u in annotation['unit_review']]==[u['unit_id'] for u in doc['units']])
            quantitative=copy.deepcopy(row['method_candidate_quantitative_data'])
            if post.get('numeric'):
                demand=post['numeric']['user_preference_vector']
                quantitative_basis='saved quantitative inputs, including explicit method-header correction'
            else:
                # A partial full-object conversion still has a validated method
                # view and the same fixed question metadata. Do not fabricate a
                # complete model JSON or discard these valid dependencies.
                fixed_question=registry.questions[str(row['question_id'])]
                meta=runner.QUESTION_META_KB[fixed_question['question_id']]
                quantitative={'method_name':post['views']['method']['projected_extraction']['method_name'],
                    'tissue_ri_value':meta.get('tissue_ri_value'),'sample_tier':meta.get('tissue_tier_code'),
                    'total_time_hours':None}
                demand=registry.get(row['question_id'],fixed_question['question'])
                quantitative_basis='validated saved method view plus original fixed question metadata; original full conversion remains partial'
            result['semantic_quantitative_inputs']={'quantitative_data':quantitative,
                'user_preference_vector':demand,'basis':quantitative_basis}
            source_row={**row,'metrics':metric,'quantitative_data':quantitative}
            if annotation['relations'] is not None:
                labels=label_replay(source_row,post,quantitative,policy,config,runner,registry,annotation,doc,annotation['relations'])
                metric=labels['metrics'];result['source_assisted_label_derivation']=labels['label_derivation']
                result['source_assisted_lookup_trace']=labels['compatibility_lookup_trace']
            scenario_results=[]
            for scenario in annotation['scenarios']:
                one_metric=copy.deepcopy(metric)
                if scenario.get('label_relations') is not None:
                    label=label_replay({**source_row,'metrics':metric},post,quantitative,policy,config,runner,registry,
                        annotation,doc,scenario['label_relations'])
                    one_metric=label['metrics']
                else:label=None
                time=calculate_time(annotation,scenario,doc)
                middle,numeric=time_metrics(one_metric,quantitative,demand,time['hours'])
                endpoints=[]
                if time['bounds_hours'] is not None:
                    for h in sorted(set(time['bounds_hours'])):
                        m,calc=time_metrics(one_metric,quantitative,demand,h)
                        endpoints.append({'hours':h,'metrics':m,'original_time_computation':calc})
                scenario_results.append({'scenario_id':scenario['scenario_id'],'description':scenario['description'],
                    'time_derivation':time,'metrics':middle,'complete_CCE':b.complete(middle),
                    'original_time_computation':numeric,'endpoint_scores':endpoints,
                    'endpoint_interpretation':'evaluations at reported endpoints, not a confidence interval or proof of full interior bounds',
                    'label_derivation':label['label_derivation'] if label else result.get('source_assisted_label_derivation'),
                    'selection_uses_achieved_score':False})
                check('scenario_preserves_direct_and_SR_SP:'+row['cell_id']+':'+scenario['scenario_id'],
                    all(middle[k]==row[args.metric_key][k] for k in DIRECT+['sr','sp','Com','Cor']))
            primary=annotation['primary_scenario_id']
            if primary:
                metric=next(s['metrics'] for s in scenario_results if s['scenario_id']==primary)
            result.update(source_assisted_metrics=metric,source_assisted_complete_CCE=b.complete(metric),
                semantic_scenarios=scenario_results,primary_scenario_id=primary,
                author_annotation={k:annotation[k] for k in ['semantic_author','independent_evaluator','expert_validated','source_findings']})
        check('primary_preserves_direct_and_SR_SP:'+row['cell_id'],
            all(result['source_assisted_metrics'][k]==row[args.metric_key][k] for k in DIRECT+['sr','sp','Com','Cor']))
        if not annotation:
            check('unchanged_reuse:'+row['cell_id'],result['source_assisted_metrics']==row[args.metric_key])
        result['semantic_changes']={k:{'before':row[args.metric_key][k],'after':v}
            for k,v in result['source_assisted_metrics'].items() if v!=row[args.metric_key][k]}
        results.append(result)
        b.save(args.out/'records'/(row['cell_id']+'.json'),result)
    byid={r['cell_id']:r for r in results}
    def primary_time(ident):
        r=byid[ident+'__r0']
        return next(s['time_derivation']['hours'] for s in r['semantic_scenarios'] if s['scenario_id']==r['primary_scenario_id'])
    check('C01_explicit_12h_and_literal_repeats',primary_time('R3C01')==34.375)
    check('C04_fresh_exchange_and_preimaging_counted',primary_time('R3C04')==72)
    check('C07_consistent_explicit_setpoint',primary_time('R3C07')==8.5)
    check('C04_same_dye_two_distinct_targets_retained',len(byid['R3C04__r0']['source_assisted_label_derivation']['pair_results'])==3)
    check('C05_genuine_branch_not_forced_to_one',byid['R3C05__r0']['source_assisted_metrics']['s_time'] is None)
    check('C02_unknown_transition_not_invented',any(s['time_derivation']['unknown_duration_operations'] for s in byid['R3C02__r0']['semantic_scenarios']))
    check('C03_truncated_preserves_unknowns',byid['R3C03__r0']['source_assisted_metrics']['s_time'] is None
        and byid['R3C03__r0']['source_assisted_metrics']['Cor'] is None)
    summary=[]
    for cohort in sorted({r['cohort'] for r in results}):
        subset=[r for r in results if r['cohort']==cohort]
        summary.append({'cohort':cohort,'returns':len(subset),
            'complete_primary_CCE':sum(r['source_assisted_complete_CCE'] for r in subset),
            'additional_answers_with_complete_conditional_CCE':sum(not r['source_assisted_complete_CCE'] and any(s['complete_CCE'] for s in r['semantic_scenarios']) for r in subset),
            'label_available':sum(b.finite(r['source_assisted_metrics']['s_label']) for r in subset),
            'time_available':sum(b.finite(r['source_assisted_metrics']['s_time']) for r in subset),
            'author_annotations':sum(r['author_annotation_applied'] for r in subset),
            'independent_new_evaluator_calls':0})
    b.save(args.out/'results.json',results);b.save(args.out/'summary.json',summary)
    b.save(args.out/'verification.json',{'checks_passed':len(checks),'checks':checks,'source_bindings':list(source_files.values())})
    with (args.out/'per_answer.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['cohort','cell_id','question_id','author_annotation_applied','primary_scenario_id',*results[0]['metrics']]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in results:writer.writerow({**{k:r.get(k) for k in fields[:5]},**r['source_assisted_metrics']})
    with (args.out/'conditional_results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['cell_id','scenario_id','hours','lower_hours','upper_hours','complete_CCE',*results[0]['metrics']]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in results:
            for s in r['semantic_scenarios']:
                bounds=s['time_derivation']['bounds_hours'] or [None,None]
                writer.writerow({'cell_id':r['cell_id'],'scenario_id':s['scenario_id'],'hours':s['time_derivation']['hours'],
                    'lower_hours':bounds[0],'upper_hours':bounds[1],'complete_CCE':s['complete_CCE'],**s['metrics']})
    b.save(args.out/'execution.json',{'command':[sys.executable,*sys.argv],'new_model_calls':0,'plan':b.bind(args.out/'plan.json')})
    print(json.dumps({'summary':summary,'checks_passed':len(checks),
        'changes':[{k:r[k] for k in ['cell_id','semantic_changes']} for r in results if r['semantic_changes']]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
