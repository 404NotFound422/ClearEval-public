"""Add conditional whole-brain uDISCO bindings to q2/q248, with zero judges.

Only existing six development questions are decoded. Original core and archived
components remain authoritative. Missing MPNet vectors use local installed assets.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_validation as core
import cce_expand_references_v5 as previous_driver

ART = ROOT / 'artifacts/cce_validation'
DEST = ART / 'expanded_references_v6'
OLD = ART / 'expanded_references_v5'
SOURCE = ART / 'reference_recovery/udisco_development_bindings_v2'
QIDS = [1, 2, 21, 22, 23, 248]
THRESHOLDS = [.6, .7, .8]
RAW = previous_driver.RAW
NUMERIC = previous_driver.NUMERIC
CACHES = [ART / 'embedding_cache', ART / 'judges/local_alternative_q1_v1/embedding_cache']
sha = previous_driver.sha
load = previous_driver.load
bind = previous_driver.bind
write = core.write

def no_network(*args, **kwargs):
    raise RuntimeError('v6 source expansion forbids network access and judge calls')

def verify_files(files):
    for path, expected in files.items():
        assert sha(path) == expected, 'Input/output changed: ' + str(path)

def prepare():
    DEST.mkdir(parents=True, exist_ok=True)
    if (DEST / 'plan.json').exists():
        verify_plan()
        print('Reused unchanged v6 pre-scoring freeze; no score computation.')
        return
    assert not (DEST / 'run.json').exists()
    old_run = load(OLD / 'run.json')
    verify_files(old_run['output_sha256'])
    old_plan = load(OLD / 'plan.json')
    verify_files(old_plan['input_sha256'])
    old_verification = load(OLD / 'verification.json')
    verify_files(old_verification['cached_vectors_read_only'])
    draft = load(SOURCE / 'next_batch_draft.json')
    review = load(SOURCE / 'verification.json')
    verify_files(review['input_sha256']); verify_files({str(SOURCE / k):v for k,v in review['output_sha256'].items()})
    previous = load(OLD / 'references.json')['references']
    added = load(SOURCE / 'candidate_references_draft.json')['references']
    parent = next(r for r in previous if r['route_id'] == 'uDISCO')
    assert len(previous) == 7 and len(added) == 2
    assert [r['question_ids'] for r in added] == [[2],[248]]
    for ref in added:
        assert ref['steps'] == parent['steps'] and ref['terminal_storage'] == parent['terminal_storage']
        assert not ref['formal_eligible'] and ref['human_confirmation'] is None and not ref['scientific_sufficiency_confirmed']
        assert all(not p['confirmed_by_question'] and not p['included_in_step_denominator'] for p in ref['scoring_start_prerequisites'])
    refs = previous + added
    assert len({r['reference_id'] for r in refs}) == 9
    write(DEST / 'references.json', {'schema_version':'conditional-reference-expansion-v6', 'references':refs,
          'scope':'Prior seven branches unchanged plus q2/q248 uDISCO conditional whole-brain clearing; no 3 mm task transfer or full-task scientific eligibility.', 'formal_eligible':False, 'human_confirmation':None})
    sources, anchors = previous_driver.collect_source_bindings(refs)
    files = [Path(__file__), ROOT/'scripts/cce_validation.py', ROOT/'scripts/cce_expand_references_v5.py', ROOT/'results/oeq_metrics.py',
             ART/'cohort_frozen.json', ART/'human_review/selection.json', DEST/'references.json',
             OLD/'references.json', OLD/'plan.json', OLD/'run.json', OLD/'verification.json', OLD/'review_final_scores.json',
             SOURCE/'task_bindings.json',SOURCE/'candidate_references_draft.json',SOURCE/'next_batch_draft.json',SOURCE/'source_evidence.json',SOURCE/'verification.json',SOURCE/'build_bindings.py',
             ART/'historical_reports/references_v5_at_104/request_ledger_at_104.jsonl']
    models = load(ART/'cohort_frozen.json')['models']; assert len(models) == 13
    protected = {int(x['question_id']) for x in load(ART/'human_review/selection.json')['selection'] if x['split'] == 'audit_holdout'}
    assert len(protected) == 15 and not protected.intersection(QIDS)
    for t in THRESHOLDS:
        tag=f't{round(t*100):03d}'
        files += [ART/f'expanded_references_v5_{tag}_per_answer.json',ART/f'expanded_references_v5_{tag}_resolved_config.json',OLD/f'{tag}_grid.json',OLD/f'{tag}_step_matches.json']
    for model in models:
        files += [ROOT/'dataset/Q+AR/model_response'/f'from_{model}_1-shot.json',ROOT/'dataset/Q+AR/result'/f'evaluation_results_{model}_1-shot.json']
    # Include model/tokenizer local assets, indirect metric module, and every
    # eligible existing cache file before computing new vectors.
    files += [p for p in (core.ASSETS/'assets/all-mpnet-base-v2').rglob('*') if p.is_file()]
    files += [p for cache in CACHES for p in cache.glob('*.npy')]
    for path in files: sources[str(path.resolve())] = sha(path)
    ledger = [json.loads(x) for x in files[17].read_text(encoding='utf-8').splitlines()] if False else None
    ledger_path = ART/'historical_reports/references_v5_at_104/request_ledger_at_104.jsonl'
    assert sum(json.loads(x).get('event') == 'request_started' for x in ledger_path.read_text(encoding='utf-8').splitlines()) == 104
    plan={'schema_version':'conditional-reference-expansion-v6','created_utc':datetime.now(timezone.utc).isoformat(),
          'input_sha256':sources,'models':models,'question_ids':QIDS,'thresholds':THRESHOLDS,'actual_answer_n':77,'grid_n':78,
          'target_answer_ids':[x['answer_id'] for x in draft['candidate_answers']], 'new_reference_ids':[x['reference_id'] for x in added],
          'reference_family_count_before':4,'reference_family_count_after':4,'candidate_new_numeric_answers':7,
          'source_scope':'q2/q248 whole adult brain only, exact author operations 03–11. Initial wash/meninge removal and target-label sufficiency remain conditional; q248 postfixation also unconfirmed. q21–23 remain without an applicable uDISCO branch.',
          'expected_changes_before_scoring':{'exact_row_reuse_if_core_equal':70,'new_reference_scored_answers':7},
          'score_policy':'Original unchanged core.score_steps/build_row and archived c_param/Correctness/EGES; no new judge scores.',
          'reuse_policy':'Reparse all 77 full answers and replay old/new pools at three thresholds; exact old row reuse only if core output, numerics, NA reasons and compatible pool agree.',
          'cache_policy':'Frozen existing MPNet caches read-only; only missing vectors are inferred locally into v6/embedding_cache. Save every vector hash actually read or written.',
          'protected_holdout_qids':sorted(protected),'holdout_answers_or_scores_decoded':0,'source_anchor_spans_verified_at_freeze':anchors,
          'new_judge_requests':0,'new_expert_labels':0,'formal_eligible':False,'package_ledger_snapshot':bind(ledger_path),'snapshot_request_count':104,
          'budget_accounting':'This zero-judge batch binds the immutable 104-request snapshot; other independent root batches may advance the live ledger.',
          'actual_prepare_command':subprocess.list2cmdline([sys.executable,*sys.argv])}
    assert len(plan['target_answer_ids']) == 7
    write(DEST/'plan.json',plan)
    print(json.dumps({'status':'frozen_before_scoring','reference_branches':9,'target_answers':7,'actual_answers':77,'new_judge_requests':0,'plan_sha256':sha(DEST/'plan.json')}))

def verify_plan():
    plan=load(DEST/'plan.json'); verify_files(plan['input_sha256']); return plan

class LocalEncoder(core.Encoder):
    def __init__(self):
        super().__init__()
        self.cache=DEST/'embedding_cache'; self.cache.mkdir(exist_ok=True)
        self.used={}; self.memo={}; self.new=[]; self.access=[]
    def encode(self,texts):
        result=[]
        for text in texts:
            key=core.digest([self.identity,text])+'.npy'
            if key not in self.memo:
                paths=[p/key for p in CACHES+[self.cache] if (p/key).exists()]
                if paths:
                    path=paths[0]
                    assert all(sha(p)==sha(path) for p in paths)
                    vec=self.np.load(path); origin='reused_existing_vector'
                else:
                    path=self.cache/key
                    vec=self.model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
                    self.np.save(path,vec); self.new.append(str(path)); origin='new_local_model_inference'
                assert vec.shape == (768,) and self.np.isfinite(vec).all()
                self.memo[key]=vec; self.used[str(path)]=sha(path)
                self.access.append({'path':str(path),'sha256':sha(path),'text_sha256':core.digest(text),'origin':origin})
            result.append(self.memo[key])
        return self.np.asarray(result)

def run():
    plan=verify_plan()
    if (DEST/'run.json').exists():
        old=load(DEST/'run.json'); assert old['plan_sha256']==sha(DEST/'plan.json')
        verify_files(old['output_sha256']); verify_files(load(DEST/'verification.json')['used_vectors'])
        print('Reused unchanged completed v6 results; zero new score/model/judge calculations.'); return
    socket.create_connection=no_network; socket.socket.connect=no_network
    old_refs=load(OLD/'references.json')['references']; refs=load(DEST/'references.json')['references']
    assert refs[:-2]==old_refs
    source_files,anchors=previous_driver.collect_source_bindings(refs)
    old_rows={r['answer_id']:r for r in load(ART/'expanded_references_v5_t070_per_answer.json')}
    originals={}; accesses=[]
    for model in plan['models']:
        ap=ROOT/'dataset/Q+AR/model_response'/f'from_{model}_1-shot.json'; sp=ROOT/'dataset/Q+AR/result'/f'evaluation_results_{model}_1-shot.json'
        answers,aa=previous_driver.authorized_records(ap); scores,ss=previous_driver.authorized_records(sp)
        accesses += [{'kind':'answer',**aa},{'kind':'score',**ss}]
        for qid,answer in answers.items():
            aid=model+'__q'+str(qid); saved=old_rows[aid]; score=scores[qid]
            assert core.digest(answer['model_response'])==saved['answer_sha256'] and core.digest(answer['specific_question'])==saved['question_sha256']
            assert answer['specific_question']==score['evaluation']['meta_data']['sample_info']
            assert Path(saved['answer_source']).resolve()==ap.resolve() and Path(saved['score_source']).resolve()==sp.resolve()
            originals[aid]=(answer,score,ap,sp)
    assert len(originals)==77 and set(originals)==set(old_rows)
    encoder=LocalEncoder(); targets=set(plan['target_answer_ids']); outputs={}; checks=[]; added=[]; batches=[]
    for threshold in THRESHOLDS:
        tag=f't{round(threshold*100):03d}'
        previous_rows=load(ART/f'expanded_references_v5_{tag}_per_answer.json')
        previous_steps={x['answer_id']:{k:v for k,v in x.items() if k!='answer_id'} for x in load(OLD/f'{tag}_step_matches.json')}
        previous_cfg=load(ART/f'expanded_references_v5_{tag}_resolved_config.json')
        assert previous_cfg['encoder']==encoder.identity
        cfg={'schema_version':'conditional-reference-expansion-v6','actual_threshold':threshold,'encoder':encoder.identity,
             'parser_version':core.VERSION,'adapter_sha256':sha(ROOT/'scripts/cce_validation.py'),'driver_sha256':sha(__file__),
             'reference_file':str(DEST/'references.json'),'reference_file_sha256':sha(DEST/'references.json'),'reference_digest':core.digest(refs),
             'plan_sha256':sha(DEST/'plan.json'),'source_per_answer_file':str(ART/f'expanded_references_v5_{tag}_per_answer.json'),
             'source_per_answer_sha256':sha(ART/f'expanded_references_v5_{tag}_per_answer.json'),
             'source_config_hashes_preserved_on_exact_reused_rows':sorted({x['config_hash'] for x in previous_rows}),
             'archive_component_policy':plan['score_policy'],'new_reference_scientific_status':plan['source_scope'],'formal_eligible':False}
        cfg_hash=core.digest(cfg); rows=[]; details=[]; categories={'exact_row_reuse':[],'new_reference_score':[]}
        for saved in previous_rows:
            aid=saved['answer_id']; answer,score,ap,sp=originals[aid]; qid=int(answer['question_id'])
            before=core.score_steps(answer,old_refs,encoder,threshold); after=core.score_steps(answer,refs,encoder,threshold)
            assert before==previous_steps[aid],('Old core changed',aid,threshold)
            old_replay=core.build_row(saved['model'],answer,score,before,ap,sp,threshold,saved['config_hash'])
            assert all(old_replay[k]==saved[k] for k in old_replay if k!='numeric_scope'),('Old row changed',aid)
            candidate=core.build_row(saved['model'],answer,score,after,ap,sp,threshold,cfg_hash)
            assert all(candidate[k]==saved[k] for k in RAW),('Archive component changed',aid)
            bp=previous_driver.pool(old_refs,qid,before['route_id']); apool=previous_driver.pool(refs,qid,after['route_id'])
            same_numeric=all(candidate[k]==saved[k] for k in NUMERIC)
            same_na=candidate['step_missing_reason']==saved['step_missing_reason'] and candidate['score_missing_reasons']==saved['score_missing_reasons']
            if aid in targets:
                assert not bp and len(apool)==1 and after['reference_id'] in plan['new_reference_ids']
                assert saved['sr'] is None and candidate['sr'] is not None
                category='new_reference_score'; row=candidate; row['numeric_scope']='v6_conditional_reference_expansion_provisional_archive_linked'
                added.append({'threshold':threshold,'row':row,'reference_hits':sum(m['matched'] for m in after['matches']),
                              'reference_n':after['reference_n'],'generated_hits':sum(x>=threshold for x in after['generated_max_similarity']),
                              'generated_n':after['generated_n'],'reference_truncated':after['reference_truncated'],
                              'generated_truncated':after['generated_truncated'],'generated_cjk_steps':after['generated_cjk_steps'],
                              'max_generated_similarity':max(after['generated_max_similarity']),
                              'new_Qwen_numeric_scores_used':False,'prior_reference_reason':saved['step_missing_reason'],
                              'new_reference_reason':row['step_missing_reason']})
            else:
                assert before==after and bp==apool and same_numeric and same_na,('Non-target changed',aid)
                category='exact_row_reuse'; row=copy.deepcopy(saved); assert row==saved
            if qid in [21,22,23] and after['route_id']=='uDISCO':
                assert after['sr'] is None and after['step_missing_reason']=='reference_insufficient'
            assert row['formal_eligible'] is False
            categories[category].append(aid); rows.append(row); details.append({'answer_id':aid,**after})
            checks.append({'answer_id':aid,'threshold':threshold,'category':category,'original_core_equal_to_saved':True,
                           'archive_components_unchanged':True,'numerics_unchanged':same_numeric,'NA_reasons_unchanged':same_na,
                           'old_candidate_pool':[x['reference_id'] for x in bp],'new_candidate_pool':[x['reference_id'] for x in apool],
                           'old_row_config_hash':saved['config_hash'],'new_row_config_hash':row['config_hash'],
                           'raw_answer_and_stem_bound':True})
        assert {k:len(v) for k,v in categories.items()}=={'exact_row_reuse':70,'new_reference_score':7}
        nsr=sum(x['sr'] is not None for x in rows); ncce=sum(x['HV'] is not None for x in rows)
        assert nsr==46 and ncce==46
        lookup={x['answer_id']:x for x in rows}; grid=[lookup.get(x['answer_id'],x) for x in load(OLD/f'{tag}_grid.json')]
        assert len(grid)==78 and sum(x['answer_sha256'] is None for x in grid)==1
        base=ART/f'expanded_references_v6_{tag}'
        outputs[Path(str(base)+'_per_answer.json')]=rows; outputs[Path(str(base)+'_resolved_config.json')]=cfg
        outputs[DEST/f'{tag}_step_matches.json']=details; outputs[DEST/f'{tag}_grid.json']=grid
        batches.append({'threshold':threshold,'per_answer_path':str(Path(str(base)+'_per_answer.json')),'config_path':str(Path(str(base)+'_resolved_config.json')),
                        'actual_answers':77,'numeric_SR':nsr,'numeric_candidate_CCE':ncce,'reference_insufficient':sum(x['step_missing_reason']=='reference_insufficient' for x in rows),
                        'missing_grid_slots':1,'categories':categories,'other_70_numeric_and_NA_unchanged':True})
    assert len(checks)==231 and len(added)==21
    verification={'status':'pass','actual_answers':77,'thresholds':3,'core_old_and_new_result_comparisons':231,'checks':checks,
                  'used_vectors':encoder.used,'vector_access':encoder.access,'new_embeddings':len(encoder.new),'new_embedding_paths':encoder.new,
                  'actual_archive_access':accesses,'source_files_rehashed':source_files,'source_spans_verified':anchors,
                  'network_disabled':True,'new_judge_requests':0,'holdout_records_decoded':0,'expert_labels_added':0,
                  'scope':'Conditional source coverage only; no confirmation of label compatibility or task success. Old archive grades preserved, not newly extracted.'}
    outputs[DEST/'verification.json']=verification; outputs[DEST/'added_answer_results.json']=added
    assert not any(p.exists() for p in outputs),'Successful output already exists; do not overwrite'
    for path,obj in outputs.items():
        write(path,obj)
        if path.name.endswith('_per_answer.json'): core.table(path.with_suffix('.csv'),obj)
    output_hashes={str(p):sha(p) for p in outputs}
    output_hashes.update({str(p.with_suffix('.csv')):sha(p.with_suffix('.csv')) for p in outputs if p.name.endswith('_per_answer.json')})
    verify_plan(); verify_files(encoder.used)
    record={'status':'complete_pass','completed_utc':datetime.now(timezone.utc).isoformat(),'plan_sha256':sha(DEST/'plan.json'),
            'actual_command':subprocess.list2cmdline([sys.executable,*sys.argv]),'cwd':str(Path.cwd()),'batches':batches,
            'reference_branches':9,'source_families':sorted({r['family_id'] for r in refs}),'actual_answers':77,'task_n':6,'model_n':13,
            'new_numeric_answer_count':7,'new_numeric_answer_threshold_observations':21,'other_70_numeric_NA_unchanged_each_threshold':True,
            'exact_row_reuse_each_threshold':70,'new_embeddings':len(encoder.new),'cached_unique_vectors':len(encoder.used),
            'new_judge_requests':0,'new_expert_labels':0,'formal_eligible_count':0,'budget_snapshot_request_count':104,
            'archive_score_used':'Original historical scores; no fresh Qwen proposals','output_sha256':output_hashes}
    write(DEST/'run.json',record)
    lines=['# v6 条件性参考覆盖扩展','','新增 q2/q248 的 uDISCO 全脑清除范围参考；3 mm 脑块 q21–23 不套用全脑分支。固定 6 题、13 模型、77 份实际答案及一格缺答。',
           '',f'实际逐阈值复验 77 份答案的旧/新参考池，共 231 次；每档 70 行原对象完全复用、7 行新增参考评分。原参数完整性、Correctness 和 EGES 全部不变。主暂定 CCE 从 39/77 增至 46/77；参考不足从 38 减为 31。新增 judge 0；本地新向量 {len(encoder.new)}。',
           '','| 答案 | SR | SP | Com | Cor | Eff | IA | HV |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for item in added:
        if item['threshold']!=.7: continue
        r=item['row']; lines.append('| '+r['answer_id']+' | '+' | '.join(format(r[k],'.9g') for k in ['sr','sp','Com','Cor','Eff','IA','HV'])+' |')
    lines += ['','q2 的标记完成和全神经元结构覆盖未确认；q248 仅确认已固定及 tdTomato 已存在，后固定、第二轴突标记和双信号兼容均未确认。原文通用 GFP/RFP 信号不能等同于 tdTomato 专项支持。初洗及去膜作为未确认起点前提，持续保存不人为增加操作。',
              '','七条新增评分均是限定清除范围的开发结果；专家为 0、正式结果为 0。不新增独立来源家族或不同任务数，也不证明完整合理替代路线。不同方法起点并不相同。',
              '','[来源适用性](../reference_recovery/udisco_development_bindings_v2/task_bindings.json)、[计划](plan.json)、[参考](references.json)、[核验](verification.json)、[新增逐答案三阈值结果](added_answer_results.json)、[执行记录](run.json)。',
              '','预算绑定历史 104 次快照；根代理其他批次可能推进 live ledger。本批无网络与 judge 入口。']
    (DEST/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (DEST/'EXECUTION.md').write_text('# 实际执行命令\n\n工作目录 C:/ClearEval/ClearEval-public。prepare 在评分前冻结；run 实际完成全部 231 项。\n\n```powershell\n& \''+sys.executable+"' scripts/cce_expand_references_v6.py prepare\n& '"+sys.executable+"' scripts/cce_expand_references_v6.py run\n```\n\n无新 judge/API；已安装 MPNet 本地推理与旧向量复用分开记录于 verification.json。\n",encoding='utf-8')
    print(json.dumps({'status':'complete_pass','actual_answers':77,'rows_checked':231,'numeric_SR_each_threshold':46,'numeric_CCE_each_threshold':46,
                      'exact_reuse_each_threshold':70,'new_answer_scored':7,'new_judge_requests':0,'new_embeddings':len(encoder.new)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=['prepare','run']); args=parser.parse_args()
    {'prepare':prepare,'run':run}[args.command]()
