"""Public E2 representation candidate; original rubric, scores and SR/SP retained.

Only structural prefixes and whitespace change. Every non-format character maps
back to the original full answer. Local cached embeddings evaluate the unchanged
BioProBench formula at the original thresholds; this is a separate candidate.
No evaluator/model requests, no downloads, no holdout input, no score overrides.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,re,sys
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_validation as core
import cce_representation_normalization_v1 as oldnorm
VERSION='fulltext-structural-display-and-source-map-v1'
OUT=ROOT/'artifacts/cce_validation/optimizer_round3_20261011/representation_repair'
OLD=ROOT/'artifacts/cce_validation/judges/local_controls_supplement_v2'
PUBLIC=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/grounded_controls_v11'
NORMAL=ROOT/'artifacts/cce_validation/representation_normalization_v1'
PREFIX=re.compile(r'^(?P<prefix>(?P<num>\d+(?:\.\d+)*)(?P<punct>[.)]?)|[-*\u2022])\s+')
QUANTITY=re.compile(r'^(?:%|degrees?\b|hours?\b|hrs?\b|minutes?\b|min\b|days?\b|[munp]?m\b|[munp]?g\b|[munp]?l\b|mm\b|cm\b|mice\b|times?\b|\u00b0|\u2103)',re.I)
CROSSREF=re.compile(r'\b(?:step|steps|section|sections)\s+\d+(?:\.\d+)*\b',re.I)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def textsha(t):return hashlib.sha256(t.encode()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def binding(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}

def canonicalize_full_text(text):
 """Create a display view; preserve source text/order and explicit cross-references.

 Bare integers count as hierarchy only when corresponding child labels occur.
 Numeric units and referenced step labels are not silently discarded. Uncertain
 typography is retained. This is deliberately narrower than semantic rewriting.
 """
 pieces=[];removed=[];source_offset=0;crossref=bool(CROSSREF.search(text))
 for raw in text.splitlines(keepends=True):
  left=len(raw)-len(raw.lstrip());right=len(raw.rstrip());body=raw[left:right];base=source_offset+left
  m=PREFIX.match(body)
  if m and not crossref:
   tail=body[m.end():];num=m.group('num');punct=m.group('punct')
   # A bullet before a number could be a minus sign; keep it unchanged.
   safe_bullet=num is None and not re.match(r'\d',tail)
   child=bool(num and re.search(r'(?m)^\s*'+re.escape(num)+r'\.\d+(?:\.\d+)*[.)]?\s+',text))
   safe_number=bool(num and (punct or '.' in num or child) and not QUANTITY.match(tail))
   if safe_bullet or safe_number:
    removed.append({'start':base,'end':base+m.end(),'text':body[:m.end()],
      'reason':'structural_bullet' if safe_bullet else 'punctuated_or_child_supported_ordinal'})
    base+=m.end();body=tail
  if body:
   chars=[];positions=[];pending_space=None
   for i,c in enumerate(body):
    if c.isspace():
     if chars and pending_space is None:pending_space=base+i
    else:
     if pending_space is not None:chars.append(' ');positions.append(pending_space)
     chars.append(c);positions.append(base+i);pending_space=None
   stream=''.join(chars);bounds=[0]+[m.end() for m in oldnorm.BOUNDARY.finditer(stream)]+[len(stream)]
   for a,b in zip(bounds,bounds[1:]):
    while a<b and stream[a].isspace():a+=1
    while b>a and stream[b-1].isspace():b-=1
    if a<b:pieces.append((stream[a:b],positions[a:b]))
  source_offset+=len(raw)
 output='\n'.join(x[0] for x in pieces)+ ('\n' if pieces else '')
 positions=[]
 for part,indices in pieces:positions.extend(indices);positions.append(None)
 assert len(positions)==len(output)
 excluded={i for r in removed for i in range(r['start'],r['end'])}
 old_nonwhite=''.join(c for i,c in enumerate(text) if not c.isspace() and i not in excluded)
 assert old_nonwhite==''.join(output.split()),'NONFORMAT_CONTENT_CHANGED'
 assert all(i is None or (output[j].isspace() and text[i].isspace()) or output[j]==text[i] for j,i in enumerate(positions))
 assert [i for i in positions if i is not None]==sorted(i for i in positions if i is not None)
 return {'version':VERSION,'original_answer_sha256':textsha(text),'evaluation_view_sha256':textsha(output),
   'evaluation_text':output,'canonical_char_to_original_char':positions,'removed_structural_prefixes':removed,
   'cross_reference_labels_retained':crossref,'nonformat_content_and_order_exact':True,
   'not_proof_of_scientific_equivalence':True,'headings_and_rationale_retained':True}

def original_ranges(view,start,end):
 """Map a returned display span to exact original ranges; never fabricate a span."""
 if not (0<=start<=end<=len(view['evaluation_text'])):raise ValueError('VIEW_OFFSET_RANGE')
 pp=[p for p in view['canonical_char_to_original_char'][start:end] if p is not None]
 ranges=[]
 for p in pp:
  if ranges and ranges[-1][1]==p:ranges[-1][1]=p+1
  else:ranges.append([p,p+1])
 return ranges

def software_checks():
 checks=[]
 fixtures=[('1 Heading\n1.1 Wash item.\n','- Heading\n- Wash item.\n',True),
  ('1. Wash item.\n2. Transfer item.\n','1. Wash item. Transfer item.\n',True),
  ('3 mm specimen\n','mm specimen\n',False),('50 % material\n','% material\n',False),
  ('- 5 degrees\n','5 degrees\n',False),('1. Wash item.\nRepeat step 1.\n','Wash item.\nRepeat step 1.\n',False),
  ('Wash item.\nTransfer item.\n','Transfer item.\nWash item.\n',False),
  ('Incubate item for 2 hours.\n','Incubate item for 3 hours.\n',False),
  ('Do not wash item.\n','Wash item.\n',False),
  ('1. Wash item.\r\n2. Transfer item.\r\n','1. Wash item.\n2. Transfer item.\n',True)]
 for a,b,expected in fixtures:
  av,bv=canonicalize_full_text(a),canonicalize_full_text(b)
  actual=av['evaluation_text']==bv['evaluation_text'];assert actual==expected
  for source,v in [(a,av),(b,bv)]:
   assert canonicalize_full_text(v['evaluation_text'])['evaluation_text']==v['evaluation_text']
   for i,c in enumerate(v['evaluation_text']):
    if not c.isspace():assert ''.join(source[x:y] for x,y in original_ranges(v,i,i+1))==c
  checks.append({'input_a':a,'input_b':b,'expected_same_view':expected,'pass':True})
 return checks

class CachedEncoder:
 """Invoke the original score function with actual saved vectors; no model load."""
 score=core.Encoder.score
 def __init__(self):
  import numpy as np
  from transformers import AutoTokenizer
  self.np=np;config=read(OLD/'step_config.json');self.identity=config['encoder']
  self.paths={Path(p).name:(Path(p),h) for p,h in read(NORMAL/'execution.json')['cached_vectors'].items()}
  self.used={};self.model=SimpleNamespace(max_seq_length=self.identity['max_seq_length'],
    tokenizer=AutoTokenizer.from_pretrained(str(core.ASSETS/'assets/all-mpnet-base-v2'),local_files_only=True))
 def encode(self,texts):
  rows=[]
  for t in texts:
   key=core.digest([self.identity,t])+'.npy'
   if key not in self.paths:raise ValueError('MISSING_EXISTING_CACHE_NO_NEW_EMBEDDING:'+textsha(t))
   p,h=self.paths[key];assert sha(p)==h;v=self.np.load(p,allow_pickle=False);assert v.shape==(768,) and self.np.isfinite(v).all()
   self.used[str(p)]=h;rows.append(v)
  return self.np.asarray(rows)

def run():
 if (OUT/'summary.json').exists():raise ValueError('NEW_VERSION_REQUIRED')
 paths=[Path(__file__),Path(core.__file__),Path(oldnorm.__file__),OLD/'cases.json',OLD/'pairs.json',OLD/'references.json',OLD/'step_results.json',OLD/'step_config.json',NORMAL/'execution.json',PUBLIC/'cases.json',PUBLIC/'pairs.json',ROOT/'prompts/eval_oeq_teacher_rubric.txt']
 plan={'version':VERSION,'inputs':[binding(p) for p in paths],'primary_threshold':.7,'thresholds':[.6,.7,.8],
  'new_judge_calls':0,'new_embeddings_allowed':False,'original_SRSP_preserved_separately':True,'score_formula_and_encoder_unchanged':True,
  'status':'offline_candidate_before_new_judge_requests','no_direct_score_reinterpretation':True,'candidate_not_main_result':True}
 save(OUT/'candidate_plan.json',plan)
 checks=software_checks();cases=read(OLD/'cases.json')['cases'];pairs=read(OLD/'pairs.json');public={c['case_id']:c for c in read(PUBLIC/'cases.json')['cases']}
 refs=read(OLD/'references.json')['references'];old={x['case_id']:x['step_result'] for x in read(OLD/'step_results.json')}
 normalized_refs=[]
 for ref in refs:
  units,_=oldnorm.normalize(ref['steps']);normalized_refs.append({**ref,'steps':units})
 enc=CachedEncoder();views=[];results=[]
 for case in cases:
  cid=case['case_id'];assert case['model_response']==public[cid]['model_response'] and case['specific_question']==public[cid]['specific_question']
  original=core.segment(case['model_response']);assert original==old[cid]['generated_steps']
  view=canonicalize_full_text(case['model_response']);steps=core.segment(view['evaluation_text']);normalized,_=oldnorm.normalize(original)
  assert [x['text'] for x in steps]==[x['text'] for x in normalized],'CANDIDATE_UNITS_DIFFER_FROM_PREVIOUS_SOURCE_PRESERVING_DIAGNOSTIC'
  views.append({'case_id':cid,'question_id':case['question_id'],**view})
  for threshold in plan['thresholds']:
   score=core.score_steps({**case,'model_response':view['evaluation_text']},normalized_refs,enc,threshold)
   results.append({'case_id':cid,'question_id':case['question_id'],'threshold':threshold,'original_answer_sha256':view['original_answer_sha256'],'evaluation_view_sha256':view['evaluation_view_sha256'],
    'original_primary_sr':old[cid]['sr'],'original_primary_sp':old[cid]['sp'],'candidate':score})
 idx={(x['case_id'],x['threshold']):x for x in results};vix={x['case_id']:x for x in views};paired=[]
 for p in pairs:
  for threshold in plan['thresholds']:
   b=idx[p['baseline_case_id'],threshold];v=idx[p['variant_case_id'],threshold]
   paired.append({**p,'threshold':threshold,'same_canonical_fulltext':vix[p['baseline_case_id']]['evaluation_text']==vix[p['variant_case_id']]['evaluation_text'],
    'baseline_sr':b['candidate']['sr'],'variant_sr':v['candidate']['sr'],'baseline_sp':b['candidate']['sp'],'variant_sp':v['candidate']['sp'],
    'delta_sr':v['candidate']['sr']-b['candidate']['sr'],'delta_sp':v['candidate']['sp']-b['candidate']['sp'],
    'original_baseline_sr':b['original_primary_sr'],'original_variant_sr':v['original_primary_sr'],'original_baseline_sp':b['original_primary_sp'],'original_variant_sp':v['original_primary_sp']})
 equivalent=[r for r in paired if r['threshold']==.7 and r['condition'] in ('deterministic_equivalent_representation','adjacent_entry_merge')]
 assert len(equivalent)==6 and all(r['same_canonical_fulltext'] and r['delta_sr']==0 and r['delta_sp']==0 for r in equivalent)
 summary={'status':'completed_offline_candidate_not_new_judge_result','answers':21,'pairs':15,'threshold_rows':63,'paired_threshold_rows':45,
  'same_fulltext_format_pairs':len(equivalent),'same_candidate_SRSP_format_pairs':len(equivalent),'original_direct_scores_not_changed':True,
  'cached_vectors_used':len(enc.used),'new_embeddings':0,'new_model_calls':0,'primary_by_condition':{c:{'pairs':len(rr),'changed_SR_pairs':sum(r['delta_sr']!=0 for r in rr),'changed_SP_pairs':sum(r['delta_sp']!=0 for r in rr)} for c in sorted({p['condition'] for p in paired}) for rr in [[x for x in paired if x['condition']==c and x['threshold']==.7]]},
  'limitation':'Format invariance follows from identical canonical inputs by construction; no evidence of semantic correctness or new judge stability. Original scores and original parser are retained.',
  'actual_command':[sys.executable,*sys.argv]}
 for name,data in [('software_checks.json',checks),('evaluation_views.json',views),('per_answer.json',results),('paired_results.json',paired),('summary.json',summary)]:save(OUT/name,data)
 core.table(OUT/'paired_results.csv',paired)
 assert all(sha(x['path'])==x['sha256'] for x in plan['inputs'])
 save(OUT/'execution.json',{'status':'pass','plan_sha256':sha(OUT/'candidate_plan.json'),'cached_vectors':enc.used,'new_model_calls':0,'new_embeddings':0,'outputs':[binding(OUT/n) for n in ['software_checks.json','evaluation_views.json','per_answer.json','paired_results.json','paired_results.csv','summary.json']],'actual_command':[sys.executable,*sys.argv]})
 print(json.dumps(summary,ensure_ascii=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['run-offline','self-check']);a=p.parse_args()
 if a.command=='self-check':print(json.dumps({'checks':len(software_checks()),'status':'pass'}))
 else:run()
