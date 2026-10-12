"""Development-only lexical normalization of existing clearing-answer segments.

No semantic repairs, new protocols, judge calls, threshold fitting or holdout reads.
The original segmenter and all archived scientific results stay unchanged.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import socket
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import cce_validation as core

BASE = ROOT/'artifacts/cce_validation'
OLD = BASE/'judges/local_controls_supplement_v2'
OUT = BASE/'representation_normalization_v1'
VERBS = r'(?:Incubat(?:e|ion)|Wash|Rinse|Transfer|Immerse|Place|Store|Dehydrate|Clear|Mount|Equilibrate|Stain|Permeabilize|Block|Replace|Repeat|Add|Keep|Prepare|Image|Soak)\b'
# A deliberately narrow English surface-form candidate, not a semantic step extractor.
# Parenthesis boundary covers a closed parameter block; modifiers stay with the action.
BOUNDARY = re.compile(r'(?<=[.!?;。；)])\s+(?=(?:(?:Then|Next|Finally)[, ]+)?'+VERBS+r'|Before\b)', re.ASCII)

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def demand(ok, msg):
    if not ok: raise ValueError(msg)
def whitespace(s): return ' '.join(s.split())

def normalize(steps):
    stream = whitespace(' '.join(s['text'] if isinstance(s,dict) else s for s in steps))
    cuts = [0] + [m.end() for m in BOUNDARY.finditer(stream)] + [len(stream)]
    result = []
    for a,b in zip(cuts,cuts[1:]):
        text = stream[a:b].strip()
        if text:
            start = a + len(stream[a:b])-len(stream[a:b].lstrip())
            result.append({'text':text,'normalized_stream_start':start,'normalized_stream_end':start+len(text)})
    demand(whitespace(' '.join(s['text'] for s in result)) == stream,'Operation stream changed')
    return result, stream

def sources():
    return [ROOT/'scripts/cce_validation.py',Path(__file__),
            *[OLD/n for n in ('cases.json','pairs.json','paired_results.json','step_results.json','references.json','step_config.json')]]

def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT/'plan.json'
    inputs = {str(x):sha(x) for x in sources()}
    plan = {'version':'english_surface_operation_boundary_v1','inputs':inputs,
        'boundary_regex':BOUNDARY.pattern,'thresholds':[.6,.7,.8],'primary_threshold':.7,
        'normalize_both_reference_and_answer':True,'preserve_nonwhitespace_text_and_order':True,
        'scope':'Existing exposed Gemini-Pro q2/q21/q22 controls; not identical to all five expert-development answers.',
        'not_a_new_independent_sample':True,'not_semantic_accuracy_validation':True,
        'no_new_judge_requests':True,'old_BioProBench_baseline_unchanged':True,
        'candidate_status':'development_surface_form_probe_not_primary_replacement',
        'promotion_requires':'Evidence-span/parameter attachment review and wider language/representation validation; no automatic promotion.'}
    if p.exists(): demand(read(p)==plan,'Frozen plan differs; use a new version')
    else: save(p,plan)
    print(json.dumps({'status':'prepared','input_files':len(inputs),'new_judge_requests':0}))

class Encoder(core.Encoder):
    def __init__(self):
        super().__init__()
        self.cache=OUT/'embedding_cache'; self.cache.mkdir(parents=True,exist_ok=True)
        self.caches=[p for p in BASE.rglob('embedding_cache') if p.is_dir() and 'sealed' not in p.parts]
        self.reused={}; self.created={}
    def encode(self,texts):
        rows=[]
        for text in texts:
            name=core.digest([self.identity,text])+'.npy'
            found=[p/name for p in self.caches if (p/name).exists()]
            if found:
                path=found[0]
                demand(all(sha(p)==sha(path) for p in found),'Conflicting saved vectors')
                vec=self.np.load(path,allow_pickle=False)
                if str(path) not in self.created:self.reused[str(path)]=sha(path)
            else:
                vec=self.model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
                path=self.cache/name; self.np.save(path,vec); self.created[str(path)]=sha(path)
            demand(vec.shape==(768,) and self.np.isfinite(vec).all(),'Invalid vector')
            rows.append(vec)
        return self.np.asarray(rows)

def run():
    plan=read(OUT/'plan.json')
    demand(all(sha(p)==h for p,h in plan['inputs'].items()),'Frozen source changed')
    ledger=BASE/'judges/request_ledger.jsonl'; ledger_hash=sha(ledger)
    encoder=Encoder()
    demand(encoder.identity==read(OLD/'step_config.json')['encoder'],'Encoder changed')
    cases=read(OLD/'cases.json')['cases']; references=read(OLD/'references.json')['references']
    old_steps={r['case_id']:r['step_result'] for r in read(OLD/'step_results.json')}
    old_pairs=read(OLD/'paired_results.json')
    refs=[]; reference_audit=[]
    for ref in references:
        norm,stream=normalize(ref['steps'])
        refs.append({**ref,'steps':norm})
        reference_audit.append({'reference_id':ref['reference_id'],'before_n':len(ref['steps']),
            'after_n':len(norm),'normalized_stream_sha256':core.digest(stream),'text_preserved':True})
    rows=[]; units=[]
    for case in cases:
        cid=case['case_id']; original=core.segment(case['model_response'])
        demand(core.digest(case['model_response'])==case['answer_sha256'],'Full answer changed')
        demand(original==old_steps[cid]['generated_steps'],'Original segmenter drift')
        steps,stream=normalize(original)
        units.append({'case_id':cid,'full_answer_sha256':case['answer_sha256'],
            'original_segments':original,'normalized_units':steps,'stream_sha256':core.digest(stream),
            'nonwhitespace_text_order_preserved':True,'scientific_parameter_attachment_checked':False})
        route,declared=core.selected_route(case['model_response'],refs)
        applicable=[r for r in refs if int(case['question_id']) in r['question_ids'] and r['route_id']==route]
        demand(applicable,'Missing source for existing development case')
        for threshold in plan['thresholds']:
            scores=[(encoder.score(r,steps,threshold),r,i) for i,r in enumerate(applicable)]
            score,ref,_=max(scores,key=lambda x:(x[0]['sr'],x[0]['sp'],-x[2]))
            rows.append({'case_id':cid,'question_id':case['question_id'],'threshold':threshold,
                'original_entry_n':len(original),'normalized_entry_n':len(steps),
                'reference_id':ref['reference_id'],'declared_route':declared,**score,
                'old_primary_sr':old_steps[cid]['sr'],'old_primary_sp':old_steps[cid]['sp'],
                'formal_eligible':False})
    index={(r['case_id'],r['threshold']):r for r in rows}
    unit_index={r['case_id']:r for r in units}
    pairs=[]
    for pair in old_pairs:
        for threshold in plan['thresholds']:
            b=index[pair['baseline_case_id'],threshold]; v=index[pair['variant_case_id'],threshold]
            ub=unit_index[b['case_id']]; uv=unit_index[v['case_id']]
            pairs.append({'pair_id':pair['pair_id'],'question_id':pair['question_id'],'condition':pair['condition'],
                'threshold':threshold,'baseline_case_id':b['case_id'],'variant_case_id':v['case_id'],
                'baseline_sr':b['sr'],'variant_sr':v['sr'],'delta_sr':v['sr']-b['sr'],
                'baseline_sp':b['sp'],'variant_sp':v['sp'],'delta_sp':v['sp']-b['sp'],
                'baseline_n':b['generated_n'],'variant_n':v['generated_n'],
                'same_reference':b['reference_id']==v['reference_id'],
                'same_full_normalized_stream':ub['stream_sha256']==uv['stream_sha256'],
                'same_normalized_unit_texts':[s['text'] for s in ub['normalized_units']]==[s['text'] for s in uv['normalized_units']],
                'old_primary_delta_sr':pair['delta_sr'],'old_primary_delta_sp':pair['delta_sp'],
                'old_judge_outputs_not_rescored_or_relabelled':True})
    primary=[r for r in pairs if r['threshold']==.7]
    summary={'status':'completed_development_diagnostic','case_n':len(cases),'unique_pairs':len(old_pairs),
        'per_threshold_counts':dict(Counter(str(r['threshold']) for r in rows)),
        'primary_by_condition':{condition:{'pairs':len(group),'sr_changes':sum(abs(r['delta_sr'])>1e-12 for r in group),
            'sp_changes':sum(abs(r['delta_sp'])>1e-12 for r in group)}
            for condition in sorted({r['condition'] for r in primary})
            for group in [[r for r in primary if r['condition']==condition]]},
        'primary_granularity_pairs':[r for r in primary if r['condition']=='adjacent_entry_merge'],
        'reference_unit_counts':reference_audit,'new_local_vectors':len(encoder.created),'cached_vectors_reused':len(encoder.reused),
        'new_judge_requests':0,'full_pipeline_new_judge_run':False,'new_expert_labels':0,
        'formal_eligible':False,'primary_configuration_changed':False,
        'limitation':'Observed representation invariance may follow from identical normalized streams by construction; it is not semantic extraction accuracy or general robustness.'}
    for name,data in [('per_case.json',rows),('units.json',units),('paired_results.json',pairs),('summary.json',summary)]:save(OUT/name,data)
    with (OUT/'paired_results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(pairs[0]));w.writeheader();w.writerows(pairs)
    demand(sha(ledger)==ledger_hash,'Unexpected model ledger mutation during offline run')
    demand(all(sha(p)==h for p,h in plan['inputs'].items()),'Input mutated')
    save(OUT/'execution.json',{'status':'pass','actual_command':[sys.executable,*sys.argv],
        'plan_sha256':sha(OUT/'plan.json'),'ledger_sha256_before_after':ledger_hash,
        'cached_vectors':encoder.reused,'new_vectors':encoder.created,'new_judge_requests':0,
        'outputs':{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='execution.json'}})
    print(json.dumps({k:summary[k] for k in ('status','case_n','unique_pairs','primary_by_condition','new_local_vectors','cached_vectors_reused','new_judge_requests')},ensure_ascii=True),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','run']);args=parser.parse_args()
    if args.command=='prepare':prepare()
    else:run()
