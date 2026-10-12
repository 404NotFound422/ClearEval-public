"""Versioned, conditional method-family procedure coverage; preserve all old results.

Uses unchanged core segmentation, MPNet, SR/SP and CCE arithmetic. No judge/network.
New source packages require an independent hash-bound conditional-scope review.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
import re
import socket
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import cce_validation as core
import cce_expand_references_v5 as helpers

ART=ROOT/'artifacts/cce_validation'
DEST=ART/'method_family_steps_v1'
SOURCE=ART/'method_family_reference_v1'
OLD=ART/'expanded_references_v7'
CONTROL=ART/'judges/local_controls_supplement_v2'
QIDS=[1,2,21,22,23,248]
THRESHOLDS=[.6,.7,.8]
RAW=helpers.RAW
load,write,sha=helpers.load,core.write,core.filehash
CACHES=[ART/'embedding_cache',ART/'judges/local_alternative_q1_v1/embedding_cache',
 ART/'expanded_references_v6/embedding_cache',OLD/'embedding_cache',
 ART/'reference_recovery/idisco_plus_2016/review/q248_route_only_diagnostic/embedding_cache']
REGISTRY=[
 {'route_id':'FDISCO','route_aliases':['FDISCO']},
 {'route_id':'PEGASOS','route_aliases':['PEGASOS']},
 {'route_id':'iDISCO+','route_aliases':['iDISCO+','iDISCO +','iDISCO Plus','iDISCO-plus']},
 {'route_id':'uDISCO','route_aliases':['uDISCO']},
 {'route_id':'ScaleS','route_aliases':['ScaleS','Scale S','Scale-S']},
 {'route_id':'CUBIC','route_aliases':['CUBIC','CUBIC-HV','CUBIC HistoVIsion','CUBIC-HistoVIsion']},
 {'route_id':'SeeDB2','route_aliases':['SeeDB2','SeeDB 2']},
]
METHOD_MAP={'CUBIC-HV':'CUBIC',**{r['route_id']:r['route_id'] for r in REGISTRY}}
OLD_VERSION={'FDISCO':'FDISCO_2019_AUTHOR_SUPPLEMENT','PEGASOS':'PEGASOS_2018_AUTHOR_SUPPLEMENT',
 'iDISCO+':'IDISCO_PLUS_2016_ARTICLE_SUPPLEMENT','uDISCO':'UDISCO_2016_AUTHOR_PROTOCOL',
 'ScaleS':'SCALES_2015_ORIGINAL'}

def check(x,reason):
    if not x:raise AssertionError(reason)
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def equal(a,b):return a==b if a is None or b is None else math.isclose(a,b,rel_tol=0,abs_tol=1e-12)
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def verify_files(values):
    for p,h in values.items():check(sha(p)==h,'Frozen input changed: '+str(p))
def no_network(*args,**kwargs):raise RuntimeError('Offline method-family scoring forbids network and judge requests')
def record(action,**kwargs):
    p=DEST/'execution_commands.json';items=load(p) if p.exists() else []
    items.append({'action':action,'utc':datetime.now(timezone.utc).isoformat(),
     'actual_command':subprocess.list2cmdline([sys.executable,*sys.argv]),'cwd':str(Path.cwd()),
     'script_sha256':sha(__file__),'new_judge_requests':0,**kwargs});write(p,items)

def policy():
    return {'schema':'method-family-procedure-coverage-policy-v1','method_registry':REGISTRY,
     'method_identity_map':METHOD_MAP,'population':{'qids':QIDS,'models':13,'present_answers':77,'answer_slots':78},
     'scope':'Separate conditional procedure-coverage and legacy-component CCE sensitivity; not a replacement for original main or formal scientific results.',
     'method_rule':'Use unchanged core selected_route grammar with a frozen method registry independent of candidate availability. No cross-method fallback.',
     'version_rule':'An explicitly recognized author-version alias or explicit year/version declaration constrains the pool. A named CUBIC-1 AND CUBIC-2 pair is a legacy branch identity. Unknown explicit versions stay NA. Generic names use the reviewed same-method scope pool.',
     'version_evidence_scope':'Chosen Method declaration, or first nonempty line for fallback; explicit version fields and known author-version aliases may also appear elsewhere. Named legacy CUBIC pair is checked across the full answer, not inferred from numerical parameters.',
     'parameter_policy':'Wrong/missing/invented numerical parameters and arbitrary reagent labels never remove a candidate. Only explicit version identities select versions.',
     'candidate_rule':'Complete authored operation range, same declared method, independently approved qid scope; no prefix truncation or stepwise mixing. Retain every candidate and denominator.',
     'selection':['maximum_whole_reference_SR','maximum_same_reference_SP','earliest_frozen_candidate_order'],
     'paired_rule':'Reparse both complete unchanged texts. Adaptive rule uses the same pool/config; fixed diagnostic locks the baseline-selected reference separately at each threshold. Report switching and both deltas.',
     'thresholds':THRESHOLDS,'primary_threshold':.7,'parser':'unchanged core.segment',
     'encoder':'unchanged all-mpnet-base-v2 local assets','CCE':'Com=.4*SR+.6*c_param/3; Cor/Eff inherited unchanged; IA=min dimensions; HV=product; no NA imputation.',
     'eligibility':'Procedure number and scientific applicability are separate fields; all new results conditional, formal_eligible=false, expert_returns=0.',
     'legacy_limits':'Archived/main and existing-control direct judgments/EGES are retained, not rejudged for the new reference version. Derived CCE is a sensitivity calculation, not a new full-pipeline judge run.',
     'control_scope':'All 3 existing step-deletion pairs /6 full texts. If they have one same-method version, no-switch is not evidence of multi-version robustness.',
     'reuse':'Keep old files unchanged; only current output directory receives new vectors/results. Hash-bind used vectors and count actual new local inference.'}

def design():
    DEST.mkdir(parents=True,exist_ok=True);p=DEST/'policy.json';obj=policy()
    if p.exists():check(load(p)==obj,'Frozen policy differs')
    else:write(p,obj)
    record('design',policy_sha256=sha(p),status='policy_frozen_before_scoring')
    print(json.dumps({'status':'policy_frozen','policy_sha256':sha(p),'new_judge_requests':0}))

def controls():
    cases={r['case_id']:r for r in load(CONTROL/'cases.json')['cases']}
    pairs=[p for p in load(CONTROL/'paired_results.json') if p['condition']=='necessary_step_deletion']
    check(len(pairs)==3 and sorted(p['question_id'] for p in pairs)==[2,21,22],'Control selection changed')
    selected={}
    for pair in pairs:
      for side in ['baseline','variant']:
        c=cases[pair[side+'_case_id']]
        check(core.digest(c['model_response'])==c['answer_sha256'],'Control text hash')
        check(core.digest(c['specific_question'])==c['question_sha256'],'Control stem hash')
        selected[c['case_id']]=c
    check(len(selected)==6,'Expected six distinct control texts')
    return pairs,selected

def normalize_ref(ref,inherited=False):
    r=copy.deepcopy(ref);method=METHOD_MAP[r['route_id']]
    r['comparison_method_id']=method
    r.setdefault('version_id',OLD_VERSION[method] if inherited else r.get('protocol_version'))
    check(r.get('version_id'),'Version identity missing')
    r.setdefault('version_aliases',[])
    r.setdefault('protocol_version',r['version_id'])
    r.setdefault('method_family_id',method)
    if inherited:
        r['task_scope_bindings']=[{'question_id':q,'allowed_for_new_conditional_step_diagnostic':True,
          'scope_status':'inherited_v7_conditional_operation_coverage','source_task_applicability_confirmed':False,
          'formal_eligible':False,'original_reference_id':r['reference_id']} for q in r['question_ids']]
    check(r['steps'] and r.get('formal_eligible') is False,'Incomplete/formal reference')
    for q in r['question_ids']:
        b=next((x for x in r['task_scope_bindings'] if int(x['question_id'])==q),None)
        check(b and b['allowed_for_new_conditional_step_diagnostic'] is True,'Missing approved task comparison scope')
        check(b.get('formal_eligible',False) is False,'Unexpected formal scope')
    return r

def declared_version(text,declared,method,refs):
    chosen=re.search(r'^\s*(?:\*\*)?Chosen\s+Method:\s*(?:\*\*)?\s*([^\r\n]+)',text,re.M|re.I)
    context=chosen.group(1) if chosen else next((x for x in text.splitlines() if x.strip()),'')
    evidence=[];matches=set()
    for r in refs:
        for alias in r.get('version_aliases',[]):
            # Full exact authored labels are evidence; arbitrary parameter text is not.
            hit=re.search(re.escape(alias),text,re.I)
            if hit:matches.add(r['version_id']);evidence.append({'kind':'known_author_version_alias','quote':hit.group(),'start':hit.start(),'end':hit.end(),'version_id':r['version_id']})
    if method=='CUBIC':
        a=re.search(r'(?<![A-Za-z])(?:CUBIC\s*[- ]\s*1|Reagent\s*[- ]?\s*1)(?![A-Za-z0-9])',text,re.I)
        b=re.search(r'(?<![A-Za-z])(?:CUBIC\s*[- ]\s*2|Reagent\s*[- ]?\s*2)(?![A-Za-z0-9])',text,re.I)
        if a and b:
            return {'status':'explicit_unsupported_version','version_ids':['CUBIC_LEGACY_NAMED_1_2_PAIR'],
                    'evidence':[{'kind':'named_legacy_pair','quote':h.group(),'start':h.start(),'end':h.end()} for h in [a,b]]}
    if len(matches)>1:return {'status':'explicit_version_ambiguous','version_ids':sorted(matches),'evidence':evidence}
    if matches:return {'status':'explicit_supported_version','version_ids':sorted(matches),'evidence':evidence}
    # Version/year tokens attached to the declaration constrain rather than silently disappear.
    years=sorted(set(re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)',context)))
    explicit_field=re.search(r'(?:protocol\s*version|version|版本)\s*[:=：]\s*([^\r\n;；]+)',text,re.I)
    if explicit_field:return {'status':'explicit_unsupported_version','version_ids':[], 'evidence':[{'kind':'unmapped_explicit_version_field','quote':explicit_field.group(),'start':explicit_field.start(),'end':explicit_field.end()}]}
    if years:
        supported=[r['version_id'] for r in refs if all(y in r['protocol_version'] or y in r['version_id'] for y in years)]
        return {'status':'explicit_supported_year' if supported else 'explicit_unsupported_version','version_ids':sorted(set(supported)),
                'evidence':[{'kind':'declaration_year','quote':y} for y in years]}
    return {'status':'version_unspecified','version_ids':[],'evidence':[]}

def resolve(answer,refs):
    text=answer['model_response'];qid=int(answer['question_id'])
    method,declared=core.selected_route(text,REGISTRY)
    method_refs=[r for r in refs if r['comparison_method_id']==method]
    version=declared_version(text,declared,method,method_refs) if method else {'status':'route_unresolved','version_ids':[],'evidence':[]}
    pool=[r for r in method_refs if qid in r['question_ids']]
    if version['status'] in ['explicit_supported_version','explicit_supported_year']:pool=[r for r in pool if r['version_id'] in version['version_ids']]
    elif version['status'] in ['explicit_unsupported_version','explicit_version_ambiguous','route_unresolved']:pool=[]
    return method,declared,version,pool

def prepare(args):
    check((DEST/'policy.json').exists(),'Run design first');check(load(DEST/'policy.json')==policy(),'Policy changed')
    if (DEST/'plan.json').exists():verify_files(load(DEST/'plan.json')['input_sha256']);print('Reused unchanged frozen plan');return
    check(len(args.candidate)==len(args.source_review)>0,'Pair each candidate with its independent review')
    original=load(OLD/'references.json')['references'];added=[];packages=[];source_files={}
    for cp,gp in zip(args.candidate,args.source_review):
        cp,gp=Path(cp).resolve(),Path(gp).resolve();g=load(gp)
        check(g.get('approved_for_development_pool') is True or g.get('approved_for_conditional_scoring') is True,'Source gate not approved')
        check(str(g.get('status','')).startswith('pass'),'Source review did not pass')
        check(g['candidate_sha256']==sha(cp),'Candidate hash differs from review')
        if g.get('input_sha256'):verify_files(g['input_sha256']);source_files.update(g['input_sha256'])
        new=load(cp)['references'];added += [normalize_ref(r) for r in new]
        packages.append({'candidate':bind(cp),'review':bind(gp),'reference_ids':[r['reference_id'] for r in new]})
        source_files.update({str(cp):sha(cp),str(gp):sha(gp)})
    replaced={r['comparison_method_id'] for r in added}
    retained=[normalize_ref(r,True) for r in original if METHOD_MAP[r['route_id']] not in replaced]
    refs=retained+added
    check(len({r['reference_id'] for r in refs})==len(refs),'Duplicate reference ID')
    # Do not create artificial versions by cloning a source or mutually exclusive specimens.
    for method in sorted({r['comparison_method_id'] for r in refs}):
      for q in QIDS:
        pool=[r for r in refs if r['comparison_method_id']==method and q in r['question_ids']]
        check(len({r['version_id'] for r in pool})==len(pool),'Duplicate version within one task/method pool')
        check(len({core.digest([s['text'] for s in r['steps']]) for r in pool})==len(pool),'Identical step text falsely counted as another version')
    refpath=DEST/'references.json';write(refpath,{'schema':'method-family-conditional-comparison-v1','references':refs,'source_packages':packages,'formal_eligible':False})
    bindings,anchors=helpers.collect_source_bindings(refs);source_files.update(bindings)
    models=load(ART/'cohort_frozen.json')['models'];check(len(models)==13,'Cohort changed')
    saved=load(ART/'expanded_references_v7_t070_per_answer.json');check(len(saved)==77,'Saved answers changed')
    lookup={r['answer_id']:r for r in saved};answer_metadata=[];access=[]
    files=[Path(__file__),Path(core.__file__),ROOT/'scripts/cce_expand_references_v5.py',DEST/'policy.json',refpath,
      ART/'cohort_frozen.json',OLD/'references.json',OLD/'run.json',CONTROL/'cases.json',CONTROL/'paired_results.json']
    for t in THRESHOLDS:
        tag=f't{round(t*100):03d}';files.extend([ART/f'expanded_references_v7_{tag}_per_answer.json',OLD/f'{tag}_step_matches.json',ART/f'expanded_references_v7_{tag}_resolved_config.json'])
    for model in models:
        p=ROOT/f'dataset/Q+AR/model_response/from_{model}_1-shot.json';files.append(p);answers,meta=helpers.authorized_records(p);access.append(meta)
        for q,a in answers.items():
            aid=f'{model}__q{q}';s=lookup[aid];check(core.digest(a['model_response'])==s['answer_sha256'],'Answer hash changed')
            check(core.digest(a['specific_question'])==s['question_sha256'],'Question hash changed')
            method,declared,v,pool=resolve(a,refs)
            answer_metadata.append({'answer_id':aid,'question_id':q,'model':model,'answer_sha256':s['answer_sha256'],'question_sha256':s['question_sha256'],
                'comparison_method_id':method,'version_selection':v,'candidate_reference_ids':[r['reference_id'] for r in pool],
                'candidate_version_ids':[r['version_id'] for r in pool],'candidate_count':len(pool),
                'old_numeric':finite(s['sr']),'expected_new_numeric_if_parser_nonempty':bool(pool)})
    check(len(answer_metadata)==77,'Original fixed population mismatch')
    pairs,cases=controls();controlmeta=[]
    for pid,c in cases.items():
        method,declared,v,pool=resolve(c,refs)
        controlmeta.append({'case_id':pid,'question_id':c['question_id'],'answer_sha256':c['answer_sha256'],
          'full_input_sha256':core.digest(c),'segmented_text_sha256':core.digest(core.segment(c['model_response'])),
          'comparison_method_id':method,'candidate_reference_ids':[r['reference_id'] for r in pool],'candidate_count':len(pool)})
    files += [p for p in (core.ASSETS/'assets/all-mpnet-base-v2').rglob('*') if p.is_file()]
    source_files.update({str(p.resolve()):sha(p) for p in files})
    caches={str(p.resolve()):sha(p) for cache in CACHES for p in cache.glob('*.npy')};source_files.update(caches)
    ledger=ART/'judges/request_ledger.jsonl';snapshot=DEST/'request_ledger_at_preparation.jsonl';snapshot.write_bytes(ledger.read_bytes())
    source_files[str(snapshot.resolve())]=sha(snapshot)
    obj={'schema':'method-family-steps-frozen-plan-v1','status':'frozen_before_scoring','created_utc':datetime.now(timezone.utc).isoformat(),
      'policy_sha256':sha(DEST/'policy.json'),'source_packages':packages,'input_sha256':source_files,
      'reference_sha256':sha(refpath),'source_anchor_count_verified':anchors,'models':models,'qids':QIDS,'thresholds':THRESHOLDS,
      'answer_metadata':answer_metadata,'control_metadata':controlmeta,'original_pair_ids':[p['pair_id'] for p in pairs],
      'source_methods_replaced_without_duplicate_branches':sorted(replaced),'old_reference_ids_replaced':[r['reference_id'] for r in original if METHOD_MAP[r['route_id']] in replaced],
      'reference_branch_count':len(refs),'author_version_count':len({r['version_id'] for r in refs}),
      'candidate_count_distribution':dict(Counter(str(x['candidate_count']) for x in answer_metadata)),
      'expected_numeric_if_parser_success':sum(x['expected_new_numeric_if_parser_nonempty'] for x in answer_metadata),
      'control_multiversion_cases':sum(x['candidate_count']>1 for x in controlmeta),
      'read_only_cache_sha256':caches,'archive_access':access,'package_requests_at_preparation':sum(json.loads(s).get('event')=='request_started' for s in snapshot.read_text(encoding='utf-8-sig').splitlines() if s.strip()),
      'new_judge_requests':0,'expert_returns':0,'formal_eligible':False}
    write(DEST/'plan.json',obj);record('prepare',plan_sha256=sha(DEST/'plan.json'),expected_numeric=obj['expected_numeric_if_parser_success'])
    print(json.dumps({'status':'frozen','expected_numeric':obj['expected_numeric_if_parser_success'],'candidate_counts':obj['candidate_count_distribution'],'control_multiversion_cases':obj['control_multiversion_cases'],'plan_sha256':sha(DEST/'plan.json')}))

class LocalEncoder(core.Encoder):
    def __init__(self):
        super().__init__();self.cache=DEST/'embedding_cache';self.cache.mkdir(exist_ok=True)
        self.memo={};self.used={};self.access=[];self.new=[]
    def encode(self,texts):
        out=[]
        for text in texts:
            key=core.digest([self.identity,text])+'.npy'
            if key not in self.memo:
                paths=[p/key for p in CACHES+[self.cache] if (p/key).exists()]
                if paths:
                    path=paths[0];check(all(sha(p)==sha(path) for p in paths),'Conflicting existing embedding');v=self.np.load(path,allow_pickle=False);origin='reused'
                else:
                    path=self.cache/key;v=self.model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
                    self.np.save(path,v);self.new.append(str(path));origin='new_local_vector'
                check(v.shape==(768,) and self.np.isfinite(v).all(),'Invalid local embedding')
                self.memo[key]=v;self.used[str(path)]=sha(path);self.access.append({'path':str(path),'sha256':sha(path),'text_sha256':core.digest(text),'origin':origin})
            out.append(self.memo[key])
        return self.np.asarray(out)

def score(answer,refs,encoder,threshold):
    method,declared,version,pool=resolve(answer,refs);steps=core.segment(answer['model_response'])
    out={'comparison_method_id':method,'declared_route_text':declared,'version_selection':version,'generated_steps':steps,
      'candidate_reference_ids':[r['reference_id'] for r in pool],'candidate_count':len(pool),'all_candidates':[],
      'sr':None,'sp':None,'reference_id':None,'missing_reason':None}
    if not steps and re.search(r'\d+\.\d+\s|Temperature:|Time:|孵育|洗涤|转移|置于',answer['model_response']):
        out['missing_reason']='evaluator_failure:operation_text_present_but_unparsed';return out
    if not pool:
        out['missing_reason']='route_unresolved' if method is None else version['status'] if version['status'].startswith('explicit_') else 'complete_compatible_reference_missing'
        return out
    for order,r in enumerate(pool):
        scored=encoder.score(r,steps,threshold)
        scored['reference_hits']=sum(x['matched'] for x in scored['matches'])
        scored['generated_hits']=sum(x>=threshold for x in scored.get('generated_max_similarity',[]))
        check(equal(scored['sr'],scored['reference_hits']/scored['reference_n']),'SR count arithmetic')
        check(equal(scored['sp'],scored['generated_hits']/scored['generated_n'] if scored['generated_n'] else 0),'SP count arithmetic')
        out['all_candidates'].append({'reference_id':r['reference_id'],'version_id':r['version_id'],'fixed_order':order,
          'source_path':r['source_path'],'source_url':r.get('source_url'),'source_family_id':r['family_id'],
          'task_scope_binding':next(b for b in r['task_scope_bindings'] if int(b['question_id'])==int(answer['question_id'])),
          'score':scored})
    chosen=max(out['all_candidates'],key=lambda r:(r['score']['sr'],r['score']['sp'],-r['fixed_order']))
    out.update(chosen['score']);out.update({k:chosen[k] for k in ['reference_id','version_id','source_path','source_url','source_family_id','task_scope_binding']})
    return out

def derived(sr,cparam,cor,eff):
    com=.4*sr+.6*cparam/3 if finite(sr) and finite(cparam) else None
    full=all(finite(x) for x in [com,cor,eff])
    return {'Com':com,'Cor':cor,'Eff':eff,'IA':min(com,cor,eff) if full else None,'HV':com*cor*eff if full else None}

def joint(rows,models):
    index={m:{int(r['question_id']):r for r in rows if r['model']==m and all(finite(r[k]) for k in ['Com','Cor','Eff','IA','HV'])} for m in models}
    qs=set.intersection(*(set(v) for v in index.values()))
    qs=sorted(q for q in qs if len({index[m][q]['question_sha256'] for m in models})==1)
    means={m:{k:math.fsum(index[m][q][k] for q in qs)/len(qs) for k in ['Com','Cor','Eff','IA','HV']} for m in models} if qs else {}
    front=[m for m in means if not any(n!=m and all(means[n][k]>=means[m][k]-1e-12 for k in ['Com','Cor','Eff']) and any(means[n][k]>means[m][k]+1e-12 for k in ['Com','Cor','Eff']) for n in means)]
    return {'fixed_model_count':len(models),'common_question_ids':qs,'common_n':len(qs),'means':means,'empirical_nondominated':front,
      'aggregation':'Mean of taskwise dimensions, IA and HV; not IA/HV of mean CCE.','scope':'Conditional procedure/legacy-component point estimate; no formal scientific claim.','new_bootstrap_draws':0}

def run():
    plan=load(DEST/'plan.json');verify_files(plan['input_sha256'])
    if (DEST/'run.json').exists():
        old=load(DEST/'run.json');check(old['plan_sha256']==sha(DEST/'plan.json'),'Plan changed');verify_files(old['output_sha256']);print('Reused unchanged completed run');return
    socket.create_connection=no_network;socket.socket.connect=no_network
    refs=load(DEST/'references.json')['references'];oldrefs=load(OLD/'references.json')['references']
    originals={};archive_access=[]
    for m in plan['models']:
        a,meta=helpers.authorized_records(ROOT/f'dataset/Q+AR/model_response/from_{m}_1-shot.json');archive_access.append(meta)
        for q,z in a.items():originals[f'{m}__q{q}']=z
    check(len(originals)==77,'Population changed')
    encoder=LocalEncoder();pairs,cases=controls();outputs={};summaries=[];allchecks=[];joint_by_t=[]
    for threshold in THRESHOLDS:
        tag=f't{round(threshold*100):03d}';previous=load(ART/f'expanded_references_v7_{tag}_per_answer.json')
        expected_steps={r['answer_id']:{k:v for k,v in r.items() if k!='answer_id'} for r in load(OLD/f'{tag}_step_matches.json')}
        check(load(ART/f'expanded_references_v7_{tag}_resolved_config.json')['encoder']==encoder.identity,'Encoder changed')
        cfg={'schema':'method-family-step-diagnostic-v1','threshold':threshold,'encoder':encoder.identity,'segment_version':core.VERSION,
          'core_sha256':sha(core.__file__),'driver_sha256':sha(__file__),'policy_sha256':sha(DEST/'policy.json'),
          'references_sha256':sha(DEST/'references.json'),'plan_sha256':sha(DEST/'plan.json'),
          'full_pipeline_judge_rerun':False,'legacy_components_unchanged':True,'formal_eligible':False}
        cfg_hash=core.digest(cfg);rows=[];details=[];candidate_rows=[]
        for old in previous:
            aid=old['answer_id'];answer=originals[aid]
            check(core.digest(answer['model_response'])==old['answer_sha256'],'Answer changed during run')
            before=core.score_steps(answer,oldrefs,encoder,threshold)
            check(before==expected_steps[aid],f'Original core replay differs: {aid} {threshold}')
            after=score(answer,refs,encoder,threshold)
            row={k:copy.deepcopy(old[k]) for k in old if k not in ['sr','sp','Com','IA','HV','reference_id','reference_status','source_path','source_url','family_id','route_id','threshold','config_hash','step_missing_reason','numeric_scope','limitation']}
            row.update({k:after.get(k) for k in ['sr','sp','reference_id','version_id','source_path','source_url','reference_hits','reference_n','generated_hits','generated_n','candidate_count','comparison_method_id']})
            row.update(derived(after['sr'],old['c_param'],old['Cor'],old['Eff']))
            row.update({'threshold':threshold,'config_hash':cfg_hash,'step_missing_reason':after['missing_reason'],
              'version_selection_status':after['version_selection']['status'],'candidate_reference_ids':after['candidate_reference_ids'],
              'source_family_id':after.get('source_family_id'),'task_scope_status':after.get('task_scope_binding',{}).get('scope_status'),
              'task_applicability_confirmed':False,'formal_eligible':False,'expert_returns':0,
              'numeric_scope':'conditional_procedure_coverage_with_unchanged_legacy_components',
              'legacy_component_version_basis':'Inherited v7 archived judgments; not reassessed against the newly selected author version.',
              'new_judge_requests':0,'old_main_reference_id':old['reference_id'],'old_main_sr':old['sr'],'old_main_sp':old['sp'],
              'old_main_Com':old['Com'],'old_main_IA':old['IA'],'old_main_HV':old['HV'],
              'delta_sr_from_v7':after['sr']-old['sr'] if finite(after['sr']) and finite(old['sr']) else None,
              'new_numeric_from_v7_NA':not finite(old['sr']) and finite(after['sr']),
              'full_pipeline_judge_rerun':False,'main_result_replaced':False})
            check(all(row[k]==old[k] for k in RAW),'Original archived component changed')
            rows.append(row);details.append({'answer_id':aid,**after})
            for c in after['all_candidates']:
                candidate_rows.append({'answer_id':aid,'question_id':old['question_id'],'model':old['model'],'threshold':threshold,
                  **{k:c[k] for k in ['reference_id','version_id','fixed_order','source_path','source_url','source_family_id']},
                  **{k:c['score'][k] for k in ['sr','sp','reference_hits','reference_n','generated_hits','generated_n']},
                  'selected':c['reference_id']==after['reference_id'],'scope_status':c['task_scope_binding']['scope_status'],'formal_eligible':False})
            allchecks.append({'answer_id':aid,'threshold':threshold,'original_core_exact_replay':True,'archived_components_unchanged':True,
              'new_candidate_count':after['candidate_count'],'new_numeric':row['new_numeric_from_v7_NA']})
        control_details=[];control_rows=[];pair_rows=[]
        for p in pairs:
            scored={side:score(cases[p[side+'_case_id']],refs,encoder,threshold) for side in ['baseline','variant']}
            a,b=scored['baseline'],scored['variant'];locked=a['reference_id']
            check(a['candidate_reference_ids']==b['candidate_reference_ids'],'Control arms do not share frozen pool')
            fixed_b=next((c['score'] for c in b['all_candidates'] if c['reference_id']==locked),None)
            for side,s in scored.items():
                case=cases[p[side+'_case_id']]
                dims=derived(s['sr'],p[side+'_c_param'],p[side+'_Cor'],p[side+'_Eff'])
                control_rows.append({'pair_id':p['pair_id'],'case_id':case['case_id'],'side':side,'question_id':p['question_id'],
                  'threshold':threshold,'config_hash':cfg_hash,'answer_sha256':case['answer_sha256'],'question_sha256':case['question_sha256'],
                  'reference_id':s['reference_id'],'sr':s['sr'],'sp':s['sp'],'candidate_count':s['candidate_count'],
                  'reference_hits':s.get('reference_hits'),'reference_n':s.get('reference_n'),'generated_hits':s.get('generated_hits'),'generated_n':s.get('generated_n'),
                  'legacy_c_param':p[side+'_c_param'],**dims,'legacy_judge_config_sha256':p['judge_config_sha256'],
                  'legacy_reference_pool_sha256':p['references_sha256'],'new_judge_requests':0,'full_pipeline_judge_rerun':False,'formal_eligible':False})
                control_details.append({'pair_id':p['pair_id'],'case_id':case['case_id'],'side':side,'threshold':threshold,**s})
            fixed_sr=fixed_b['sr'] if fixed_b else None;fixed_sp=fixed_b['sp'] if fixed_b else None
            pr={'pair_id':p['pair_id'],'question_id':p['question_id'],'threshold':threshold,'config_hash':cfg_hash,
              'candidate_count':a['candidate_count'],'adaptive_baseline_reference_id':a['reference_id'],'adaptive_variant_reference_id':b['reference_id'],
              'reference_switch':a['reference_id']!=b['reference_id'],'fixed_reference_id':locked,
              'adaptive_baseline_sr':a['sr'],'adaptive_variant_sr':b['sr'],'fixed_baseline_sr':a['sr'],'fixed_variant_sr':fixed_sr,
              'adaptive_baseline_sp':a['sp'],'adaptive_variant_sp':b['sp'],'fixed_baseline_sp':a['sp'],'fixed_variant_sp':fixed_sp,
              'adaptive_delta_sr':b['sr']-a['sr'] if finite(a['sr']) and finite(b['sr']) else None,
              'fixed_delta_sr':fixed_sr-a['sr'] if finite(a['sr']) and finite(fixed_sr) else None,
              'adaptive_delta_sp':b['sp']-a['sp'] if finite(a['sp']) and finite(b['sp']) else None,
              'fixed_delta_sp':fixed_sp-a['sp'] if finite(a['sp']) and finite(fixed_sp) else None,
              'control_exercises_multiple_versions':a['candidate_count']>1,'new_judge_requests':0,'formal_eligible':False}
            if finite(pr['adaptive_delta_sr']) and finite(pr['fixed_delta_sr']):check(pr['adaptive_delta_sr']>=pr['fixed_delta_sr']-1e-12,'Max-selection identity violated')
            pair_rows.append(pr)
        grid=[];lookup={r['answer_id']:r for r in rows}
        for m in plan['models']:
            for q in QIDS:grid.append(lookup.get(f'{m}__q{q}',{'answer_id':f'{m}__q{q}','model':m,'question_id':q,'sr':None,'sp':None,'Com':None,'Cor':None,'Eff':None,'IA':None,'HV':None,'step_missing_reason':'answer_missing','formal_eligible':False}))
        outputs.update({DEST/f'{tag}_per_answer.json':rows,DEST/f'{tag}_step_details.json':details,
          DEST/f'{tag}_all_candidate_scores.json':candidate_rows,DEST/f'{tag}_resolved_config.json':cfg,
          DEST/f'{tag}_grid.json':grid,DEST/f'{tag}_control_per_case.json':control_rows,
          DEST/f'{tag}_control_step_details.json':control_details,DEST/f'{tag}_control_pairs.json':pair_rows})
        j=joint(rows,plan['models']);joint_by_t.append({'threshold':threshold,**j})
        summaries.append({'threshold':threshold,'answers':len(rows),'numeric_SR_SP':sum(finite(r['sr']) for r in rows),
          'numeric_conditional_CCE':sum(finite(r['HV']) for r in rows),'remaining_NA':sum(not finite(r['sr']) for r in rows),
          'new_numeric_from_v7_NA':sum(r['new_numeric_from_v7_NA'] for r in rows),'multiple_candidate_answers':sum(r['candidate_count']>1 for r in rows),
          'selected_versions':dict(Counter(r['version_id'] for r in rows if r['version_id'])),
          'NA_reasons':dict(Counter(r['step_missing_reason'] for r in rows if r['step_missing_reason'])),
          'control_pairs':len(pair_rows),'control_multiversion_pairs':sum(r['control_exercises_multiple_versions'] for r in pair_rows),
          'control_switch_pairs':sum(r['reference_switch'] for r in pair_rows),'Q_star':j['common_question_ids']})
    common_across=sorted(set.intersection(*(set(j['common_question_ids']) for j in joint_by_t)))
    outputs[DEST/'joint_point_estimates.json']={'scope':'Conditional numeric sensitivity only; original main fixed cohort preserved; no bootstrap rerun.',
       'threshold_results':joint_by_t,'common_qids_across_thresholds':common_across,'new_bootstrap_draws':0,'formal_eligible':False}
    check(len(allchecks)==231,'Expected 77x3 original-core checks')
    verify_files(plan['input_sha256']);verify_files(encoder.used)
    outputs[DEST/'verification.json']={'status':'pass','old_core_replays':231,'checks':allchecks,
      'used_vectors':encoder.used,'vector_access':encoder.access,'new_embeddings':len(encoder.new),'reused_unique_embeddings':sum(x['origin']=='reused' for x in encoder.access),
      'new_embedding_paths':encoder.new,'archive_reads':archive_access,'heldout_records_decoded':0,'new_judge_requests':0,
      'original_inputs_unchanged':True,'scope':'Software/source identity and arithmetic verification, not scientific accuracy.'}
    for p,obj in outputs.items():check(not p.exists(),'Refuse output overwrite: '+str(p));write(p,obj)
    for p,obj in list(outputs.items()):
        if any(p.name.endswith(s) for s in ['_per_answer.json','_all_candidate_scores.json','_grid.json','_control_per_case.json','_control_pairs.json']):core.table(p.with_suffix('.csv'),obj)
    output_paths=list(outputs)+[p.with_suffix('.csv') for p in outputs if p.with_suffix('.csv').exists()]
    run_record={'status':'complete_pass','completed_utc':datetime.now(timezone.utc).isoformat(),'plan_sha256':sha(DEST/'plan.json'),
      'batches':summaries,'actual_answers':77,'fixed_models':13,'qids':QIDS,'new_judge_requests':0,'new_embeddings':len(encoder.new),
      'reused_unique_embeddings':sum(x['origin']=='reused' for x in encoder.access),'formal_eligible':0,'expert_returns':0,
      'old_main_result_replaced':False,'full_pipeline_judge_rerun':False,'controlled_full_texts':6,'controlled_pairs':3,
      'new_bootstrap_draws':0,'actual_command':subprocess.list2cmdline([sys.executable,*sys.argv]),'cwd':str(ROOT),
      'output_sha256':{str(p):sha(p) for p in output_paths}}
    write(DEST/'run.json',run_record);record('run',status='complete_pass',new_embeddings=len(encoder.new))
    md=['# 同方法版本步骤覆盖：新条件性诊断','',
      '本批固定77份真实答案、13模型、6题，沿用原core分割、MPNet、SR/SP阈值和CCE公式。新结果单独保留，原主结果没有替换。参数完整性、Correctness、EGES均直接继承原存档；没有为新参考版本重新judge，因此联合数值是条件性敏感性结果。','',
      '| 阈值 | 数值SR/SP及条件CCE | 新增数值 | 仍NA | 多候选答案 | 共同qid |','|---|---:|---:|---:|---:|---|']
    md += [f"| {s['threshold']} | {s['numeric_SR_SP']}/77 | {s['new_numeric_from_v7_NA']} | {s['remaining_NA']} | {s['multiple_candidate_answers']} | {s['Q_star']} |" for s in summaries]
    md += ['', '主阈值逐答案先看[SR/SP与命中分母CSV](t070_per_answer.csv)，再看[全部候选](t070_all_candidate_scores.csv)及[完整匹配](t070_step_details.json)。候选按整份SR、同份SP、固定次序择优；没有逐步骤跨版本拼接。明确版本优先；泛称只表示对相容作者候选的最好覆盖，不识别实际采用版本。来源适用未知、初始/中间标记前提与正式资格单独保留。','',
      '受控3对、6份旧真实全文均重新解析并按本次同配置评分。[自适应与固定基线参考对照](t070_control_pairs.csv)同时保留。它们仍全部为FDISCO单候选，不构成同方法多版本切换的有效性验证。控制的旧judge/EGES分项仅用于重算联合列，不是本轮新full-pipeline判分。','',
      '其他入口：[冻结规则](policy.json)、[来源与输入计划](plan.json)、[新参考集合](references.json)、[三阈值共同集与点估计](joint_point_estimates.json)、[核验](verification.json)、[实际运行及计数](run.json)、[实际命令](execution_commands.json)。新增API0、专家回传0；仅缺少缓存的向量在新目录离线计算，实际数量见run.json。所有旧输入哈希在运行前后校验一致。','']
    (DEST/'README.md').write_text('\n'.join(md),encoding='utf-8')
    print(json.dumps({'status':'complete_pass','batches':summaries,'new_embeddings':len(encoder.new),'new_judge_requests':0},ensure_ascii=False))

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['design','prepare','run'])
    p.add_argument('--candidate',action='append',default=[]);p.add_argument('--source-review',action='append',default=[])
    args=p.parse_args()
    if args.action=='design':design()
    elif args.action=='prepare':prepare(args)
    else:run()
if __name__=='__main__':main()
