"""Independently replay archived inputs and arithmetic for all nine score batches.

Read-only for every source batch. Does not instantiate an encoder or a judge.
Stored similarities are thresholded again; embeddings are not regenerated.
"""
import argparse, collections, copy, functools, hashlib, json, math, pathlib, re, sys
from urllib.parse import urlparse, parse_qs

sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import cce_validation as scorer
OUT=ROOT/'artifacts/cce_validation'
SETTINGS=[('pilot',.7),('pilot_t060',.6),('pilot_t080',.8),
          ('two_source_t070',.7),('two_source_t060',.6),('two_source_t080',.8),
          ('supplement_v2_t070',.7),('supplement_v2_t060',.6),('supplement_v2_t080',.8)]
NUMERIC=['sr','sp','c_step','c_param','co_order','co_method','co_param','co_chem',
         's_method','s_label','s_trans','s_time','Cor','Eff','historical_Com','Com','IA','HV']

def require(ok,message):
    if not ok:raise ValueError(message)
def rawsha(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
@functools.lru_cache(None)
def file_hash(path,algorithm='sha256'):
    h=hashlib.new(algorithm)
    with pathlib.Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def bind(path):return {'path':str(pathlib.Path(path).resolve()),'sha256':file_hash(str(path))}
@functools.lru_cache(None)
def load(path):return scorer.read(path)
def eq(left,right):
    if isinstance(left,bool) or isinstance(right,bool):return left is right
    if isinstance(left,(float,int)) and isinstance(right,(float,int)):
        return math.isclose(left,right,rel_tol=1e-12,abs_tol=1e-12)
    if isinstance(left,dict) and isinstance(right,dict):return set(left)==set(right) and all(eq(left[k],right[k]) for k in left)
    if isinstance(left,list) and isinstance(right,list):return len(left)==len(right) and all(eq(a,b) for a,b in zip(left,right))
    return left==right
def unique(records,key):
    out={str(r[key]):r for r in records}
    require(len(out)==len(records),'Duplicate '+key)
    return out

def verify_reference_sources(refs):
    results=[]
    for ref in refs:
        actual=file_hash(ref['source_path'])
        require(actual==ref['source_sha256'],'Reference source hash differs: '+ref['reference_id'])
        results.append({'reference_id':ref['reference_id'],'source_path':ref['source_path'],'actual_sha256':actual,
                        'matches_frozen_reference':True})
    return results

def recount_steps(answer,step,refs,threshold):
    parsed=scorer.segment(answer['model_response'])
    require(parsed==step['generated_steps'],'Current parser output/offsets differ')
    route,declared=scorer.selected_route(answer['model_response'],refs)
    require(route==step['route_id'] and declared==step['declared_route'],'Declared route parsing differs')
    compatible=[r for r in refs if int(answer['question_id']) in r['question_ids'] and r['route_id']==route]
    result=copy.deepcopy(step)
    if step['reference_id'] is None:
        require(step['sr'] is None and step['sp'] is None,'Reference-free score is not NA')
        parser_failure=not parsed and bool(re.search(r'\d+\.\d+\s|Temperature:|Time:|孵育|洗涤|转移|置于',answer['model_response']))
        expected_reason='evaluator_failure' if parser_failure else 'reference_insufficient'
        require(parser_failure or not compatible,'Eligible reference exists for unscored answer')
        require(step['step_missing_reason']==expected_reason,'NA reason disagrees with actual route/parser state')
        result.update(sr=None,sp=None,step_missing_reason=expected_reason)
        return result,{'generated_n_actual':len(parsed),'reference_n':None,'sr_recount':None,'sp_recount':None,'missing_reason':expected_reason}
    require(len(compatible)==1,'Multiple eligible candidates need independent candidate-score reconstruction')
    ref=compatible[0]
    require(ref['reference_id']==step['reference_id'],'Selected reference is not the compatible branch')
    require(step['candidate_reference_ids']==[r['reference_id'] for r in compatible],'Eligible reference IDs differ')
    require(step['reference_n']==len(ref['steps']) and step['generated_n']==len(parsed),'Reference/generated count differs')
    require(step['step_missing_reason'] is None,'Scored answer contains step missing reason')
    if not parsed:
        sr=sp=0.;reference_hits=generated_hits=0
        require(step['matches']==[],'Empty answer has nonempty matching')
    else:
        matches=step['matches'];gmax=step['generated_max_similarity']
        require(len(matches)==len(ref['steps']) and len(gmax)==len(parsed),'Stored maxima dimensions differ')
        require({m['reference_index'] for m in matches}==set(range(len(ref['steps']))),'Reference index coverage differs')
        for m in matches:
            ri,gi=m['reference_index'],m['generated_index']
            require(0<=gi<len(parsed),'Generated match index out of bounds')
            require(m['reference_text']==ref['steps'][ri]['text'] and m['generated_text']==parsed[gi]['text'],'Matching text not bound to source steps')
            require(math.isfinite(m['similarity']) and -1.000001<=m['similarity']<=1.000001,'Invalid similarity')
            require(m['matched'] is (m['similarity']>=threshold),'Stored threshold boolean differs')
            require(m['similarity']<=gmax[gi]+1e-6,'Chosen match exceeds corresponding generated maximum')
        require(all(math.isfinite(x) and -1.000001<=x<=1.000001 for x in gmax),'Invalid generated maximum')
        reference_hits=sum(m['similarity']>=threshold for m in matches)
        generated_hits=sum(x>=threshold for x in gmax)
        sr=reference_hits/len(ref['steps']);sp=generated_hits/len(parsed)
    require(eq(sr,step['sr']) and eq(sp,step['sp']),'SR/SP threshold recount differs')
    for key in ['reference_status','source_path','source_url','family_id']:
        expected=ref['status'] if key=='reference_status' else ref.get(key)
        require(step.get(key)==expected,'Selected reference metadata differs: '+key)
    result.update(sr=sr,sp=sp)
    return result,{'generated_n_actual':len(parsed),'reference_n':len(ref['steps']),
        'reference_hits':reference_hits,'generated_hits':generated_hits,'sr_recount':sr,'sp_recount':sp,'missing_reason':None}

def verify_batch(tag,threshold):
    paths={key:OUT/(tag+suffix) for key,suffix in [('config','_resolved_config.json'),('references','_references.json'),
           ('rows','_per_answer.json'),('steps','_step_matches.json'),('run','_run.json')]}
    cfg,run=load(str(paths['config'])),load(str(paths['run']))
    refs=load(str(paths['references']))['references'];rows=load(str(paths['rows']))
    steps=unique(load(str(paths['steps'])),'answer_id')
    require(len(rows)==len(steps)==65,'Batch must contain 65 unique rows/step records')
    require(len(unique(rows,'answer_id'))==65,'Duplicate row identity')
    cfg_hash=scorer.digest(cfg)
    require(run['config_hash']==cfg_hash,'Run configuration digest mismatch')
    require(cfg['run_setting']['actual_threshold']==threshold,'Actual threshold differs from batch tag')
    require(cfg['resolved']['adapter_sha256']==file_hash(str(ROOT/'scripts/cce_validation.py')),'Current adapter differs from frozen adapter')
    require(cfg['resolved']['adapter_version']==scorer.VERSION==cfg['run_setting']['segmentation_version'],'Adapter version mismatch')
    require(cfg['resolved']['reference_digest']==scorer.digest(refs),'Reference collection digest mismatch')
    live_reference=pathlib.Path(cfg['inputs']['complete_reference_manifest'])
    require(load(str(live_reference))['references']==refs,'Actual configured reference file differs from saved batch references')
    if tag.startswith('two_source'):
        driver=ROOT/'scripts/cce_score_reference_expansion.py';scope='two_source_development_provisional_archive_linked'
    elif tag.startswith('supplement_v2'):
        driver=ROOT/'scripts/cce_score_supplement_references.py';scope='supplement_bound_development_provisional_archive_linked'
    else:driver=ROOT/'scripts/cce_validation.py';scope='development_provisional_archive_linked'
    if driver.name!='cce_validation.py':require(file_hash(str(driver))==cfg['run_setting']['batch_driver_sha256'],'Batch driver hash differs')
    frozen_input_count=0
    for path,expected in cfg['run_setting'].get('batch_input_sha256',{}).items():
        require(file_hash(path)==expected,'Frozen batch input bytes changed: '+path);frozen_input_count+=1
    if 'reference_file_sha256' in cfg['run_setting']:
        require(file_hash(str(live_reference))==cfg['run_setting']['reference_file_sha256'],'Reference file SHA mismatch')
    cohort=load(str(OUT/'cohort_frozen.json'));models=cohort['models'];qids=[2,21,22,23,248]
    require(set(run['models'])==set(models)==set(cfg['cohort']['resolved_generator_models']),'Model cohort differs')
    require(set(run['tasks'])==set(qids),'Task cohort differs')
    require({(r['model'],int(r['question_id'])) for r in rows}=={(m,q) for m in models for q in qids},'Actual model/question cross-product differs')
    snapshot=ROOT/cfg['resolved']['generation_question_snapshot']
    historical=unique(load(str(snapshot)),'question_id')
    model_sources={}
    for model in models:
        ap=ROOT/'dataset/Q+AR/model_response'/f'from_{model}_1-shot.json'
        sp=ROOT/'dataset/Q+AR/result'/f'evaluation_results_{model}_1-shot.json'
        require(file_hash(str(ap))==cohort['input_files'][str(ap.relative_to(ROOT))],'Original answer file changed from frozen cohort')
        model_sources[model]=(ap,sp,unique(load(str(ap)),'question_id'),unique(load(str(sp)),'question_id'))
    source_checks=verify_reference_sources(refs)
    encoder_asset=scorer.ASSETS/'assets/all-mpnet-base-v2'
    weights=encoder_asset/('model.safetensors' if (encoder_asset/'model.safetensors').exists() else 'pytorch_model.bin')
    require(file_hash(str(weights))==run['encoder']['weights_sha256'],'Encoder weights differ')
    encoder_config=load(str(encoder_asset/'sentence_bert_config.json'))
    require(encoder_config['max_seq_length']==run['encoder']['max_seq_length'],'Encoder sequence limit differs')
    results=[]
    for row in rows:
        aid=row['answer_id'];qid=str(row['question_id']);ap,sp,answers,scores=model_sources[row['model']]
        answer,score=answers[qid],scores[qid]
        require(pathlib.Path(row['answer_source']).resolve()==ap.resolve() and pathlib.Path(row['score_source']).resolve()==sp.resolve(),'Recorded source paths do not match model filenames')
        require(str(score['question_id'])==qid==str(answer['question_id']),'Original score/answer question IDs differ')
        require(score['evaluation']['meta_data']['sample_info']==answer['specific_question'],'Score stem not bound to actual answer stem')
        require(historical[qid]['question']==answer['specific_question'],'Original answer stem differs from historical generation snapshot')
        require(rawsha(answer['model_response'])==row['answer_sha256'],'Raw original answer hash differs')
        require(rawsha(answer['specific_question'])==row['question_sha256'],'Raw original question hash differs')
        step,recount=recount_steps(answer,steps[aid],refs,threshold)
        replay=scorer.build_row(row['model'],answer,score,step,ap,sp,threshold,cfg_hash)
        replay['numeric_scope']=scope
        require(set(row)==set(replay),'Rebuilt row schema differs')
        for key in replay:require(eq(row[key],replay[key]),'Recomputed row differs: '+aid+' / '+key)
        require(row['formal_eligible'] is False,'Development score became formal eligible')
        results.append({'answer_id':aid,'question_id':int(qid),'status':'pass',
            'answer_raw_sha256':row['answer_sha256'],'question_raw_sha256':row['question_sha256'],
            'answer_file_sha256':file_hash(str(ap)),'score_file_sha256':file_hash(str(sp)),
            'historical_stem_and_filename_model_qid_binding':'pass',
            'generated_steps_and_offsets_current_parser_exact':'pass','stored_similarity_threshold_recount':recount,
            'numeric_fields_recomputed_and_equal':NUMERIC,'all_rebuilt_row_fields_equal':True,
            'missing_reasons_equal':True,'config_hash':cfg_hash})
    require(run['answer_n']==65 and run['step_scored']==sum(r['sr'] is not None for r in rows),'Run row summary mismatch')
    return {'tag':tag,'status':'pass','threshold':threshold,'row_n':len(results),
        'scored_step_rows':sum(r['sr'] is not None for r in rows),'config_hash':cfg_hash,
        'inputs':{k:bind(v) for k,v in paths.items()},'actual_driver':bind(driver),
        'driver_bound_by':'batch_driver_sha256' if driver.name!='cce_validation.py' else 'adapter_sha256 (same source executes batch)',
        'configured_reference_file':bind(live_reference),'reference_source_checks':source_checks,
        'encoder_weights':bind(weights),'encoder_max_seq_length':encoder_config['max_seq_length'],
        'historical_question_snapshot':bind(snapshot),'explicit_batch_input_hashes_checked':frozen_input_count,'rows':results}

def verify_supplement_bytes():
    path=OUT/'reference_recovery/supplement_bound/evidence_manifest.json';manifest=load(str(path))
    originals=[];evidence=[]
    for obj in manifest['original_objects']:
        pdf=pathlib.Path(obj['output_path']);actual_md5=file_hash(str(pdf),'md5');actual_sha=file_hash(str(pdf))
        require(file_hash(obj['local_index_path'])==obj['local_index_sha256'],'Official local index changed')
        index=load(obj['local_index_path']);uri=obj['indexed_source_uri']
        require(uri in index['media_urls'],'Object URI not found in actual official index media_urls')
        indexed_md5=parse_qs(urlparse(uri).query)['md5'][0]
        require(actual_md5==indexed_md5==obj['expected_md5']==obj['md5'],'Actual PDF MD5 differs from official indexed MD5')
        require(actual_sha==obj['sha256'] and pdf.stat().st_size==obj['bytes'],'Actual PDF SHA/size differs')
        with pdf.open('rb') as f:require(f.read(4)==b'%PDF','Original object does not have PDF header')
        originals.append({'label':obj['label'],'pdf':str(pdf),'actual_md5':actual_md5,'actual_sha256':actual_sha,
            'bytes':pdf.stat().st_size,'official_index':bind(obj['local_index_path']),'indexed_uri':uri,'status':'pass'})
    for key,item in manifest['evidence'].items():
        checked=[]
        for filekey,hashkey in [('pdf','pdf_sha256'),('text_path','text_sha256'),('render_path','render_sha256'),
                                ('source_path','source_sha256'),('extracted_text_path','extracted_text_sha256')]:
            if filekey in item:
                require(file_hash(item[filekey])==item[hashkey],'Evidence bytes differ: '+key+' / '+filekey)
                checked.append(bind(item[filekey]))
        text_path=item.get('text_path',item.get('extracted_text_path'))
        if text_path:
            text=pathlib.Path(text_path).read_text(encoding='utf-8-sig')
            require(0<=item['extracted_text_start']<item['extracted_text_end']<=len(text),'Evidence offsets outside actual extracted text')
        evidence.append({'evidence_id':key,'files':checked,'offsets_in_bounds':True})
    return {'status':'pass','manifest':bind(path),'original_objects':originals,'evidence':evidence,
            'note':'Local official-index MD5 and actual local bytes rechecked; no download or claim of new server verification.'}

def audit_v2_branches():
    path=OUT/'reference_recovery/supplement_bound/references_supplement_v2.json';refs=load(str(path))['references']
    require(len(refs)==4 and len({r['reference_id'] for r in refs})==4,'Expected four independent route/sample branches')
    report=[]
    duration=re.compile(r'\b\d+(?:\.\d+)?\s*(?:hours?|hrs?|days?|minutes?|mins?|seconds?|weeks?|months?)\b',re.I)
    for route in ['FDISCO','PEGASOS']:
        pair=[r for r in refs if r['route_id']==route]
        require(len(pair)==2,'Route does not have two sample branches')
        whole=next(r for r in pair if 'WHOLE_BRAIN' in r['reference_id'])
        block=next(r for r in pair if 'BLOCK_3MM_UNTIMED' in r['reference_id'])
        require(set(whole['question_ids'])=={2,248} and set(block['question_ids'])=={21,22,23},'Sample-class question assignment differs')
        require(not(set(whole['question_ids'])&set(block['question_ids'])),'Whole and block applicability overlap')
        require(whole['steps']!=block['steps'],'Untimed branch copied whole-brain timed steps')
        require([s['module'] for s in whole['steps']]==[s['module'] for s in block['steps']],'Route operation module order diverged between sample branches')
        require(block['applicability']['exact_3mm_schedule_supported'] is False and
                block['applicability']['timing_policy']=='not_reported_for_3mm_no_interpolation','Unknown 3 mm schedule not explicit')
        require('3mm-specific dwell times' in block['unknown_parameters'],'3 mm unknown durations not recorded')
        timed=[s['step_id'] for s in block['steps'] if duration.search(s['text'])]
        require(not timed,'Numeric dwell duration filled into untimed branch')
        require(all(s['timing_status'] in {'not_reported_for_3mm_no_interpolation','qualitative_duration_only','no_fixed_storage_duration'} for s in block['steps']),'Untimed branch has whole-brain timing status')
        if route=='FDISCO':
            require('3mm-specific repeat count' in block['unknown_parameters'],'FDISCO unknown repeat count missing')
            require(not any(re.search(r'\b(twice|thrice|three incubations|in total|\d+ times)\b',s['text'],re.I) for s in block['steps']),'Unknown block repeat count was filled')
        for ref in pair:require(ref['human_confirmation'] is None and ref['status']=='source_extracted' and ref['formal_eligible'] is False,'Unconfirmed branch became formally validated')
        report.append({'route_id':route,'whole_reference_id':whole['reference_id'],'block_reference_id':block['reference_id'],
            'whole_question_ids':whole['question_ids'],'block_question_ids':block['question_ids'],
            'disjoint_applicability':True,'separate_reference_and_step_ids':not({s['step_id'] for s in whole['steps']}&{s['step_id'] for s in block['steps']}),
            'numeric_3mm_dwell_durations_present':timed,'unknown_parameters':block['unknown_parameters'],
            'conditional_refresh_cadence_is_not_assigned_dwell_time':any('daily during multi-day treatment' in s['text'] for s in block['steps']),
            'expert_confirmation':None,'status':'pass_structural_source_scope_check'})
    construction=load(str(OUT/'reference_recovery/supplement_bound/construction_run.json'))
    preserved=[]
    for source,expected in construction['protected_v1_inputs_before'].items():
        require(file_hash(source)==expected,'Protected v1 input changed since v2 construction')
        preserved.append(bind(source))
    require(file_hash(str(path))==construction['output_manifest_sha256'],'v2 reference file changed since construction')
    return {'status':'pass','source':bind(path),'branches':report,'preserved_v1_inputs':preserved,
        'scope':'Read-only metadata/text timing-boundary check. Does not confirm biological applicability, completeness, or wet-lab outcomes.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=pathlib.Path,default=OUT/'score_batch_verification.json')
    args=p.parse_args();batches=[];failures=[]
    for tag,threshold in SETTINGS:
        try:
            result=verify_batch(tag,threshold);batches.append(result)
            print(tag+': 65 raw-input/parser/threshold/arithmetic rows verified',flush=True)
        except Exception as exc:
            failures.append({'batch':tag,'error_type':type(exc).__name__,'error':str(exc)})
            print(tag+': FAILED '+str(exc),flush=True)
    extras={}
    for name,fn in [('supplement_bytes',verify_supplement_bytes),('v2_branch_audit',audit_v2_branches)]:
        try:extras[name]=fn()
        except Exception as exc:failures.append({'section':name,'error_type':type(exc).__name__,'error':str(exc)})
    report={'status':'pass' if not failures and len(batches)==9 else 'failed',
        'scope':'Actual current archived inputs, parser output, stored-similarity threshold recount, original build_row numerical replay and original source bytes. Not fresh embeddings, judge validation, expert confirmation, or wet-lab validation.',
        'batches_expected':9,'rows_expected':585,'batches_verified':len(batches),'rows_verified':sum(b['row_n'] for b in batches),
        'numeric_field_comparisons':sum(b['row_n'] for b in batches)*len(NUMERIC),
        'unique_archived_answers':65,'new_model_requests':0,'expert_labels_added':0,
        'historical_score_binding_limit':'Filename model + question ID + exact archived stem; historical score records still lack an original answer hash/evaluator provenance.',
        'verifier_source':bind(__file__),'actual_command':{'executable':sys.executable,'argv':sys.argv,'cwd':str(pathlib.Path.cwd())},
        'batches':batches,**extras,'failures':failures}
    scorer.write(args.out,report)
    commands=args.out.with_name('score_batch_verification_commands.md')
    commands.write_text('# 实际核验命令\n\n工作目录 `'+str(ROOT)+'`。\n\n```powershell\n& \''+sys.executable+'\' scripts/cce_verify_score_batches.py\n```\n\n'+
        f"实际结果：{report['rows_verified']}/585 行，{report['batches_verified']}/9 批；状态 {report['status']}。新增模型请求 0。旧评分批次不覆盖。\n\n"+
        '逐行从当前原答案/题干和原 scores 重新绑定，调用原 build_row 重算；SR/SP 从实际存储的匹配最大值按各批阈值重新计数。未重新生成 embedding，不把哈希一致当成科学验证。\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['status','batches_verified','rows_verified','numeric_field_comparisons','new_model_requests']}))
    if failures:sys.exit(1)
if __name__=='__main__':main()
