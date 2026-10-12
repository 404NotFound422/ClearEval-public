"""Local step-encoder intervention; no generative evaluator requests."""
import csv,json,os,socket,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(r'C:\ClearEval\ClearEval-public');OUT=Path(__file__).resolve().parent
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011';DEST=OUT/'run_01'
assert not DEST.exists()
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
for key in ['HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_HUB_DISABLE_TELEMETRY']:os.environ[key]='1'
for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[key]='2'
def no_network(*args,**kwargs):raise RuntimeError('Language probe uses local assets only')
socket.create_connection=no_network;socket.socket.connect=no_network;socket.socket.connect_ex=no_network
import cce_scoped_midpoint_scorer_v1 as b
import cce_validation as core
frozen=b.read(OUT/'frozen_inputs.json')
for item in frozen['inputs']:assert b.bind(item['path'])==item
assert b.bind(frozen['ledger']['path'])==frozen['ledger']
plan=b.read(OUT/'plan.json');translations=b.read(OUT/'translations.json')
details={r['anonymous_answer_id']:r for r in b.read(R3/'confirmation_inputs_01/selected_step_details.json')}
saved=b.read(R3/'confirmation_qwen_01/steps.json')
source_threshold={(r['cell_id'].replace('__r0',''),r['threshold']):r for r in b.read(OUT.parent/'automatic_time_scope/threshold_01/confirmation.json')}
allowed={r['english_body_original_metadata'] for r in translations}
amendment=b.read(OUT/'reference_cache_amendment.json')
assert b.bind(amendment['source']['path'])==amendment['source']
allowed_references=set(amendment['allowed_missing_reference_texts'])
used={};created={};created_translation={};created_reference={};checks=[];outputs=[];matrix_records=[];reference_rows=[]
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
class LocalEncoder(core.Encoder):
    def __init__(self):
        super().__init__();self.memo={}
        self.search=[self.cache,ROOT/'artifacts/cce_validation/expanded_references_v7/embedding_cache',core.ASSETS/'assets/embedding_cache',OUT/'new_embedding_cache']
        self.local=OUT/'new_embedding_cache';self.local.mkdir(exist_ok=True)
    def encode(self,texts):
        vectors=[]
        for text in texts:
            if text not in self.memo:
                key=core.digest([self.identity,text])+'.npy';paths=[p/key for p in self.search if (p/key).exists()]
                if paths:
                    path=paths[0];used[str(path)]=b.bind(path)
                    self.memo[text]=self.np.load(path)
                else:
                    if text not in allowed|allowed_references:raise FileNotFoundError('Frozen source vector not found: '+key+' '+text[:100])
                    vec=self.model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
                    path=self.local/key;self.np.save(path,vec);created[str(path)]=b.bind(path);self.memo[text]=vec
                    (created_translation if text in allowed else created_reference)[str(path)]=created[str(path)]
            vectors.append(self.memo[text])
        return self.np.asarray(vectors)
encoder=LocalEncoder()
print(json.dumps({'state':'local_encoder_loaded','identity':encoder.identity,'frozen_translated_steps':len(allowed)}),flush=True)
for aid in ['R3C04','R3C07','R3C03']:
    d=details[aid];check('encoder_identity:'+aid,encoder.identity==saved[d['case_id']]['encoder'])
    representations={'original':d['generated_steps']}
    if aid in plan['translated_answers']:
        translations_for_id=sorted([r for r in translations if r['answer_id']==aid],key=lambda r:r['step_index'])
        representations['english_body_original_metadata']=[{'text':r['english_body_original_metadata'],'source_step_index':r['step_index']} for r in translations_for_id]
    for name,steps in representations.items():
        pool={t:[] for t in plan['thresholds']}
        for candidate in d['all_candidates']:
            reftexts=[m['reference_text'] for m in candidate['score']['matches']]
            ref={'steps':reftexts};gtexts=[s['text'] for s in steps]
            mat=encoder.encode(reftexts)@encoder.encode(gtexts).T
            matrix_records.append({'answer_id':aid,'representation':name,'reference_id':candidate['reference_id'],
                'reference_texts':reftexts,'generated_texts':gtexts,'similarities':mat.tolist(),'dtype':str(mat.dtype)})
            for t in plan['thresholds']:
                score=encoder.score(ref,steps,t)
                score['reference_hits']=sum(m['matched'] for m in score['matches'])
                score['generated_hits']=sum(x>=t for x in score['generated_max_similarity'])
                if name=='original' and t==.7:
                    check('original_candidate_SR_SP:'+aid+':'+candidate['reference_id'],all(score[k]==candidate['score'][k] for k in ['sr','sp','reference_hits','generated_hits']))
                    maxerror=max(abs(a['similarity']-z['similarity']) for a,z in zip(score['matches'],candidate['score']['matches']))
                    check('original_maxima_float32_tolerance:'+aid+':'+candidate['reference_id'],maxerror<1e-6)
                item={'answer_id':aid,'representation':name,'threshold':t,'reference_id':candidate['reference_id'],
                    'version_id':candidate['version_id'],'fixed_order':candidate['fixed_order'],'score':score}
                pool[t].append(item)
                for m in score['matches']:
                    reference_rows.append({'answer_id':aid,'representation':name,'threshold':t,'reference_id':candidate['reference_id'],**m})
        generated_tokens=[encoder.model.tokenizer.encode(s['text'],truncation=False) for s in steps]
        for t in plan['thresholds']:
            selected=dict(max(pool[t],key=lambda r:(r['score']['sr'],r['score']['sp'],-r['fixed_order'])))
            selected['all_candidate_scores']=pool[t]
            if name=='original':
                baseline=source_threshold[aid,t];check('original_threshold_reproduction:'+aid+':'+str(t),
                    selected['reference_id']==baseline['selected_reference'] and all(selected['score'][k]==baseline['metrics'][k] for k in ['sr','sp']))
            outputs.append({**selected,'generated_step_count':len(steps),
                'tokenizer_unknown_tokens':sum(ts.count(encoder.model.tokenizer.unk_token_id) for ts in generated_tokens),
                'tokenizer_total_tokens':sum(map(len,generated_tokens)),'max_generated_tokens':max(map(len,generated_tokens)),
                'truncated_generated_steps':sum(len(ts)>encoder.identity['max_seq_length'] for ts in generated_tokens),
                'is_full_pipeline_fresh_evaluation':False,'source_translation_expert_verified':False})
        print(json.dumps({'state':'representation_scored','answer':aid,'representation':name,'new_vectors_so_far':len(created)}),flush=True)
check('at_most_frozen_translation_vectors',len(created_translation)<=55)
check('references_only_with_pre_outcome_amendment',len(created_reference)<=len(allowed_references))
check('no_evaluator_request',b.bind(frozen['ledger']['path'])==frozen['ledger'])
for r in frozen['inputs']:check('frozen_input_unchanged:'+r['path'],b.bind(r['path'])==r)
summary={'actual_source_answers':3,'translated_answers':2,'translated_steps':55,'derived_settings':len(outputs),
    'new_local_embedding_vectors':len(created),'new_translation_vectors':len(created_translation),'new_reference_vectors':len(created_reference),
    'cached_vector_files_reused':len(used),'new_evaluator_requests':0,
    'primary_SR_SP_overwritten':False,'independent_accuracy_claimed':False,
    'rows':[{k:r[k] for k in ['answer_id','representation','threshold','reference_id','tokenizer_unknown_tokens','max_generated_tokens','truncated_generated_steps']}|
        {k:r['score'][k] for k in ['sr','sp','reference_hits','generated_hits']} for r in outputs]}
b.save(DEST/'results.json',outputs);b.save(DEST/'matrices.json',matrix_records);b.save(DEST/'summary.json',summary)
b.save(DEST/'verification.json',{'checks_passed':len(checks),'checks':checks})
for name,data in [('per_answer',summary['rows']),('per_reference',reference_rows)]:
    with (DEST/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
b.save(DEST/'execution.json',{'command':[sys.executable,*sys.argv],'completed_utc':datetime.now(timezone.utc).isoformat(),
    'inputs':[b.bind(__file__),b.bind(OUT/'frozen_inputs.json'),b.bind(OUT/'reference_cache_amendment.json'),*frozen['inputs'],b.bind(OUT.parent/'automatic_time_scope/threshold_01/confirmation.json')],
    'encoder_identity':encoder.identity,'used_vectors':list(used.values()),'created_vectors':list(created.values()),
    'ledger':frozen['ledger'],'network_disabled':True,'new_evaluator_requests':0})
print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
