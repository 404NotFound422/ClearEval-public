"""Independent cached arithmetic audit; no generation or biological source editing."""
from __future__ import annotations
import collections, contextlib, hashlib, io, json, math, os, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[k]='2'
import cce_method_family_steps_v1 as driver
import cce_validation as core
import cce_expand_references_v5 as helpers
BASE=ROOT/'artifacts/cce_validation';SRC=BASE/'method_family_steps_v1';OUT=SRC/'independent_review'
INPUTS={}
def require(ok,why):
    if not ok:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):
    p=Path(p).resolve();INPUTS[str(p)]=sha(p);return p
def read(p):return json.loads(bind(p).read_text(encoding='utf-8-sig'))
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def dims(sr,cp,cor,eff):
    com=.4*sr+.6*cp/3 if finite(sr) and finite(cp) else None
    ready=all(finite(v) for v in [com,cor,eff])
    return {'Com':com,'Cor':cor,'Eff':eff,'IA':min(com,cor,eff) if ready else None,'HV':com*cor*eff if ready else None}
def close(a,b):return a==b if a is None or b is None else abs(a-b)<=1e-12

def main():
    plan=read(SRC/'plan.json');run=read(SRC/'run.json');verified=read(SRC/'verification.json')
    for p,h in plan['input_sha256'].items():require(sha(bind(p))==h,'frozen_input_changed:'+p)
    for p,h in run['output_sha256'].items():require(sha(bind(p))==h,'executed_output_changed:'+p)
    require(sha(SRC/'plan.json')==run['plan_sha256'],'run_plan_binding')
    refs=read(SRC/'references.json')['references'];refmap={r['reference_id']:r for r in refs}
    oldrefs=read(BASE/'expanded_references_v7/references.json')['references']
    lookup={}
    for model in plan['models']:
        path=bind(ROOT/f'dataset/Q+AR/model_response/from_{model}_1-shot.json')
        records,meta=helpers.authorized_records(path)
        require(set(records)<=set([1,2,21,22,23,248]),'unauthorized_question_decoded')
        for q,r in records.items():lookup[f'{model}__q{q}']=r
    require(len(lookup)==77 and len(plan['models'])==13,'frozen_cohort_changed')
    cache={}
    for p,h in verified['used_vectors'].items():
        require(sha(bind(p))==h,'cached_vector_changed')
        name=Path(p).name
        if name in cache:require(sha(p)==sha(cache[name]),'cache_name_collision')
        cache[name]=Path(p)
    class ReadOnlyEncoder(core.Encoder):
        def __init__(self):
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):super().__init__()
            self.used=set();self.memo={}
            def forbid(*a,**kw):raise AssertionError('new_embedding_forbidden')
            self.model.encode=forbid
        def encode(self,texts):
            result=[]
            for text in texts:
                name=core.digest([self.identity,text])+'.npy';require(name in cache,'vector_not_executed:'+name)
                if name not in self.memo:
                    v=self.np.load(cache[name],allow_pickle=False);require(v.shape==(768,) and self.np.isfinite(v).all(),'vector_shape')
                    self.memo[name]=v
                self.used.add(name);result.append(self.memo[name])
            return self.np.asarray(result)
    encoder=ReadOnlyEncoder();counts=collections.Counter();decisions=[];batches=[];explicit=[];pairchecks=[]
    def review_detail(answer,detail,threshold):
        generated=core.segment(answer['model_response']);require(generated==detail['generated_steps'],'fulltext_resegmentation')
        method,declared=core.selected_route(answer['model_response'],driver.REGISTRY)
        method=driver.METHOD_MAP.get(method,method)
        require(method==detail['comparison_method_id'] and declared==detail['declared_route_text'],'declared_method_binding')
        method_refs=[r for r in refs if r['comparison_method_id']==method]
        all_pool=[r for r in method_refs if int(answer['question_id']) in r['question_ids']]
        version=driver.declared_version(answer['model_response'],declared,method,method_refs) if method else {'status':'route_unresolved','version_ids':[],'evidence':[]}
        require(version==detail['version_selection'],'version_evidence_binding')
        for ev in version['evidence']:
            if 'start' in ev:require(answer['model_response'][ev['start']:ev['end']]==ev['quote'],'version_quote_offset')
        pool=all_pool
        if version['status'] in ['explicit_unsupported_version','explicit_version_ambiguous']:pool=[]
        elif version['status'].startswith('explicit_supported'):pool=[r for r in pool if r['version_id'] in version['version_ids']]
        ids=[r['reference_id'] for r in pool]
        require(ids==detail['candidate_reference_ids'] and len(pool)==detail['candidate_count'],'same_method_version_pool')
        candidates=[]
        for i,ref in enumerate(pool):
            require(ref['formal_eligible'] is False and ref['steps'],'source_conditional_boundary')
            source_binding=next(r for r in ref['task_scope_bindings'] if r['question_id']==answer['question_id'])
            require(source_binding['allowed_for_new_conditional_step_diagnostic'] is True,'source_scope_not_allowed')
            s=encoder.score(ref,generated,threshold);stored=detail['all_candidates'][i]
            expected={**s,'reference_hits':sum(m['matched'] for m in s['matches']),
                      'generated_hits':sum(v>=threshold for v in s['generated_max_similarity'])}
            require(stored['score']==expected,'whole_candidate_original_core_replay')
            require(stored['reference_id']==ref['reference_id'] and stored['version_id']==ref['version_id'] and stored['fixed_order']==i,'candidate_identity_order')
            require(s['sr']==expected['reference_hits']/len(ref['steps']) and s['sp']==expected['generated_hits']/len(generated),'actual_nN_denominators')
            candidates.append((expected,ref,i));counts['whole_candidate_core_replays']+=1
        if candidates:
            selected,ref,_=max(candidates,key=lambda x:(x[0]['sr'],x[0]['sp'],-x[2]))
            require(detail['reference_id']==ref['reference_id'] and all(detail[k]==v for k,v in selected.items()),'same_reference_SR_SP_max_rule')
        else:
            require(detail['sr'] is None and detail['sp'] is None and detail['reference_id'] is None,'empty_pool_NA')
        if version['status']!='version_unspecified':explicit.append({'answer_id':detail.get('answer_id'), 'threshold':threshold,'method':method,'version_status':version['status'],'candidate_count':len(pool)})
        return candidates
    controlpairs,controlcases=driver.controls()
    joint_saved=read(SRC/'joint_point_estimates.json')['threshold_results']
    for threshold in [.6,.7,.8]:
        tag=f't{round(threshold*100):03d}';rows=read(SRC/f'{tag}_per_answer.json');details=read(SRC/f'{tag}_step_details.json')
        cfg=read(SRC/f'{tag}_resolved_config.json');oldrows=read(BASE/f'expanded_references_v7_{tag}_per_answer.json')
        oldstep={x['answer_id']:{k:v for k,v in x.items() if k!='answer_id'} for x in read(BASE/f'expanded_references_v7/{tag}_step_matches.json')}
        oldmap={r['answer_id']:r for r in oldrows};detailmap={r['answer_id']:r for r in details}
        require(cfg['threshold']==threshold and cfg['encoder']==encoder.identity and cfg['core_sha256']==sha(core.__file__) and cfg['driver_sha256']==sha(driver.__file__),'actual_configuration')
        require(cfg['references_sha256']==sha(SRC/'references.json') and cfg['policy_sha256']==sha(SRC/'policy.json'),'actual_source_policy_hash')
        candrows=[]
        for row in rows:
            aid=row['answer_id'];a=lookup[aid];old=oldmap[aid];d=detailmap[aid]
            require(core.digest(a['model_response'])==row['answer_sha256']==old['answer_sha256'] and core.digest(a['specific_question'])==row['question_sha256']==old['question_sha256'],'original_question_answer_binding')
            require(core.score_steps(a,oldrefs,encoder,threshold)==oldstep[aid],'old_core_exact_replay');counts['old_core_replays']+=1
            require(all(row[k]==old[k] for k in helpers.RAW),'archived_science_component_changed')
            require(row['config_hash']==core.digest(cfg),'row_config_hash')
            cs=review_detail(a,d,threshold)
            require(all(row[k]==d.get(k) for k in ['sr','sp','reference_id','version_id','reference_hits','reference_n','generated_hits','generated_n','candidate_count','comparison_method_id']),'row_detail_binding')
            require(row['step_missing_reason']==d['missing_reason'],'NA_reason_binding')
            require(all(close(row[k],v) for k,v in dims(d['sr'],old['c_param'],old['Cor'],old['Eff']).items()),'conditional_CCE_formula')
            require(row['formal_eligible'] is False and row['task_applicability_confirmed'] is False and row['full_pipeline_judge_rerun'] is False,'scope_overclaim')
            decisions.append({'answer_id':aid,'threshold':threshold,'candidate_count':len(cs),'reference_id':d['reference_id'],'SR':d['sr'],'SP':d['sp'],'reference_n':d.get('reference_n'),'generated_n':d.get('generated_n')})
            for s,ref,i in cs:candrows.append((aid,ref['reference_id'],s['sr'],s['sp'],s['reference_hits'],s['reference_n'],s['generated_hits'],s['generated_n'],ref['reference_id']==d['reference_id']))
        savedc=read(SRC/f'{tag}_all_candidate_scores.json')
        require(candrows==[(r['answer_id'],r['reference_id'],r['sr'],r['sp'],r['reference_hits'],r['reference_n'],r['generated_hits'],r['generated_n'],r['selected']) for r in savedc],'candidate_flat_table')
        pc=read(SRC/f'{tag}_control_per_case.json');pd=read(SRC/f'{tag}_control_step_details.json');pp=read(SRC/f'{tag}_control_pairs.json')
        pmap={(x['pair_id'],x['side']):x for x in pc};dmap={(x['pair_id'],x['side']):x for x in pd}
        for p,saved in zip(controlpairs,pp):
            reconstructed={}
            for side in ['baseline','variant']:
                a=controlcases[p[side+'_case_id']];d=dmap[p['pair_id'],side];r=pmap[p['pair_id'],side]
                reconstructed[side]=review_detail(a,d,threshold)
                require(r['answer_sha256']==core.digest(a['model_response']) and r['question_sha256']==core.digest(a['specific_question']),'control_fulltext_binding')
                require(all(close(r[k],v) for k,v in dims(d['sr'],p[side+'_c_param'],p[side+'_Cor'],p[side+'_Eff']).items()),'control_conditional_formula')
            b=dmap[p['pair_id'],'baseline'];v=dmap[p['pair_id'],'variant']
            lock=next(s for s,r,i in reconstructed['variant'] if r['reference_id']==b['reference_id'])
            require(saved['fixed_reference_id']==b['reference_id'] and saved['reference_switch']==(b['reference_id']!=v['reference_id']),'pair_reference_selection')
            for metric in ['sr','sp']:
                require(saved['adaptive_delta_'+metric]==v[metric]-b[metric] and saved['fixed_delta_'+metric]==lock[metric]-b[metric],'paired_delta_arithmetic')
            require(b['candidate_reference_ids']==v['candidate_reference_ids'] and b['candidate_count']==1,'control_single_candidate_scope')
            pairchecks.append({'pair_id':p['pair_id'],'question_id':p['question_id'],'threshold':threshold,'candidate_count':1,'reference_switch':saved['reference_switch'],'adaptive_delta_sr':saved['adaptive_delta_sr'],'fixed_delta_sr':saved['fixed_delta_sr']})
        bymodel={m:{r['question_id']:r for r in rows if r['model']==m and all(finite(r[k]) for k in ['Com','Cor','Eff','IA','HV'])} for m in plan['models']}
        qstar=sorted(set.intersection(*(set(g) for g in bymodel.values())))
        qstar=[q for q in qstar if len({bymodel[m][q]['question_sha256'] for m in bymodel})==1]
        means={m:{k:math.fsum(bymodel[m][q][k] for q in qstar)/len(qstar) for k in ['Com','Cor','Eff','IA','HV']} for m in bymodel} if qstar else {}
        front=[m for m in means if not any(n!=m and all(means[n][k]>=means[m][k]-1e-12 for k in ['Com','Cor','Eff']) and any(means[n][k]>means[m][k]+1e-12 for k in ['Com','Cor','Eff']) for n in means)]
        js=next(j for j in joint_saved if j['threshold']==threshold)
        require(js['common_question_ids']==qstar and js['means']==means and js['empirical_nondominated']==front,'Qstar_point_estimates')
        batch={'threshold':threshold,'numeric':sum(finite(r['sr']) for r in rows),'NA':sum(not finite(r['sr']) for r in rows),'new_numeric':sum(not finite(oldmap[r['answer_id']]['sr']) and finite(r['sr']) for r in rows),'candidate_distribution':dict(collections.Counter(r['candidate_count'] for r in rows)),'Q_star':qstar,'pareto_count':len(front)}
        require(batch['numeric']==66 and batch['NA']==11 and batch['new_numeric']==16,'batch_counts');batches.append(batch)
    require(all(sha(p)==h for p,h in INPUTS.items()),'review_input_changed')
    OUT.mkdir(parents=True,exist_ok=True)
    report={'status':'pass','scope':'Independent cached software/numeric and version-policy review; not scientific or expert validation.',
        'batches':batches,'counts':dict(counts),'cached_vectors_read':len(encoder.used),'new_embeddings':0,'new_judge_requests':0,
        'all_77_archived_components_preserved_at_3_thresholds':True,'SR_SP_selected_from_same_whole_reference':True,
        'controlled_pairs':3,'controlled_fulltexts':6,'controls_multiversion_pairs':0,'controls_reference_switches':0,
        'explicit_version_checks':explicit,'pair_checks':pairchecks,'decisions':decisions,'input_sha256':INPUTS,
        'limitations':['50 old numeric and all 77 archived components retained; new conditional CCE combines new step references with unrejudged archived components.',
        'Best same-method coverage does not identify the actual protocol used or confirm task applicability.',
        'All 3 deletion pairs are single-candidate FDISCO: no-switch cannot validate multiversion robustness.',
        'Q* is one question (q2), not six tasks; no new bootstrap draws or expert confirmation.'],
        'actual_command':[sys.executable,'scripts/cce_review_method_family_steps_v1.py'],'reviewer_script_sha256':sha(__file__)}
    (OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (OUT/'review.md').write_text('# 同方法多参考独立数值审阅\n\n软件核验通过。用已执行缓存重新调用原 Encoder.score，核对每个候选整份 SR/SP、实际命中分母、同一参考择优、显式版本限制、三阈值 NA 和 CCE。77 份原答案/原题哈希及存档科学分项保持；旧 core 231 行复算精确相等。没有新 judge 或向量推理。\n\n三阈值均 66/77 数值、11 NA，较旧 50 新增 16；候选数为 39 份单版本、27 份双版本、11 份无候选。Q* 仅 q2，Pareto 数 6/5/4。显式旧 CUBIC-1/2 不受支持时保留 NA。\n\n受控 3 对、6 全文均重分割和重算，但仍是 FDISCO 单候选，未发生参考切换；这不能验证多版本选择的稳健性。新 CCE 只是新步骤覆盖与未重新评价的存档分项结合的条件性敏感性结果；不是正式 gold 或完整新判分。\n\n[实际输入哈希、逐候选与配对核验](review.json)。执行：`python scripts/cce_review_method_family_steps_v1.py`。\n',encoding='utf8')
    print(json.dumps({'status':'pass','batches':batches,'counts':dict(counts),'cached_vectors':len(encoder.used),'review_sha256':sha(OUT/'review.json')},ensure_ascii=True))
if __name__=='__main__':main()
