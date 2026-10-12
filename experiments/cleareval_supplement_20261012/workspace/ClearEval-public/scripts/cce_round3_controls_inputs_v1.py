"""Prepare the authorized public 12-text/9-pair/24-request E2 panel; no judge API.

One canonical baseline per task. All text choices freeze before any new step
result is computed. Original segment/encoder/threshold/formula are preserved.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,os,re,sys
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_validation as core
R3=ROOT/'artifacts/cce_validation/optimizer_round3_20261011'
OUT=R3/'representation_repair/controlled_panel_v1'
PUBLIC=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/grounded_controls_v11'
OLD=ROOT/'artifacts/cce_validation/judges/local_controls_supplement_v2'
GRAN=ROOT/'artifacts/cce_validation/controls/granularity_edits.json'
SPECS={2:{'baseline':'E2_13','merge':'E2_19','operations':9,'delete':[6,7,8,9]},
       21:{'baseline':'E2_15','merge':'E2_20','operations':11,'delete':[9,10,11]},
       22:{'baseline':'E2_17','merge':'E2_21','operations':16,'delete':[13,14,15,16]}}
ORDER=['baseline','numbering','merge','necessary_step_deletion']
ORDINAL=re.compile(r'^(?P<prefix>\d+\. )(?P<body>[^\r\n]*)(?P<newline>\r?\n)?$',re.M)
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rawsha(t):return hashlib.sha256(t.encode('utf8')).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def span(text,a,b,**extra):
 return {'start':a,'end':b,'utf8_start':len(text[:a].encode()),'utf8_end':len(text[:b].encode()),
  'text':text[a:b],'text_sha256':rawsha(text[a:b]),**extra}
def operations(text):
 found=list(ORDINAL.finditer(text));indices=[int(m.group('prefix').split('.')[0]) for m in found]
 if indices!=list(range(1,len(indices)+1)):raise ValueError('NOT_CONSECUTIVE_CANONICAL_OPERATIONS')
 return found
def apply_edits(text,edits):
 answer=text
 for e in sorted(edits,key=lambda x:x['start'],reverse=True):
  assert answer[e['start']:e['end']]==e['text'];answer=answer[:e['start']]+e['replacement']+answer[e['end']:]
 return answer

class OriginalEncoder:
 score=core.Encoder.score
 def __init__(self):
  import numpy as np
  from transformers import AutoTokenizer
  self.np=np;self.identity=read(OLD/'step_config.json')['encoder']
  assets=core.ASSETS/'assets/all-mpnet-base-v2'
  weights=assets/'model.safetensors'
  if not weights.exists():weights=assets/'pytorch_model.bin'
  assert sha(weights)==self.identity['weights_sha256']
  self.model=SimpleNamespace(tokenizer=AutoTokenizer.from_pretrained(str(assets),local_files_only=True),max_seq_length=self.identity['max_seq_length'])
  self.assets=assets;self.real_model=None;self.used={};self.created={}
  self.caches=[core.OUT/'embedding_cache']
  for p in read(core.OUT/'representation_normalization_v1/execution.json')['cached_vectors']:
   parent=Path(p).parent
   if parent not in self.caches:self.caches.append(parent)
 def encode(self,texts):
  vectors=[]
  for text in texts:
   key=core.digest([self.identity,text])+'.npy';p=next((root/key for root in self.caches if (root/key).is_file()),None)
   if p is None:
    p=OUT/'new_embedding_cache'/key
    if not p.exists():
     if self.real_model is None:
      os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
      import torch
      torch.set_num_threads(2)
      import torch._library.utils
      torch._library.utils.get_source=lambda stacklevel:'round3-local-encoder:0'
      from sentence_transformers import SentenceTransformer
      self.real_model=SentenceTransformer(str(self.assets),device='cpu')
      assert self.real_model.max_seq_length==self.identity['max_seq_length']
     p.parent.mkdir(parents=True,exist_ok=True)
     value=self.real_model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
     self.np.save(p,value);self.created[str(p)]=sha(p)
   vector=self.np.load(p,allow_pickle=False)
   assert vector.shape==(768,) and self.np.isfinite(vector).all()
   self.used[str(p)]=sha(p);vectors.append(vector)
  return self.np.asarray(vectors)

def prepare():
 if (OUT/'input_freeze.json').exists():raise ValueError('INPUTS_ALREADY_FROZEN_NEW_VERSION_REQUIRED')
 source=read(PUBLIC/'cases.json')['cases'];byid={c['anonymous_answer_id']:c for c in source}
 gran={r['question_id']:r for r in read(GRAN)['edits']};cases=[];edits=[];pairs=[];matrix=[]
 for qid,spec in SPECS.items():
  base=byid[spec['baseline']];merged=byid[spec['merge']];text=base['model_response'];ops=operations(text)
  assert len(ops)==spec['operations'] and base['question_id']==qid==merged['question_id']
  assert base['specific_question']==merged['specific_question'] and base['references']==merged['references']
  assert rawsha(text)==gran[qid]['baseline_text_sha256'] and rawsha(merged['model_response'])==gran[qid]['variant_text_sha256']
  header=text[:ops[0].start()];assert merged['model_response'].startswith(header)
  merged_ops=operations(merged['model_response']);groups=gran[qid]['groups_of_original_indices']
  assert len(merged_ops)==len(groups)
  for m,indices in zip(merged_ops,groups):
   assert m.group('body')==' '.join(ops[i].group('body') for i in indices)
  numbering_edits=[span(text,m.start(),m.start()+len(m.group('prefix')),replacement='- ',operation_index=i+1) for i,m in enumerate(ops)]
  numbered=apply_edits(text,numbering_edits)
  delete_edits=[span(text,ops[i-1].start(),ops[i-1].end(),replacement='',operation_index=i) for i in spec['delete']]
  deleted=apply_edits(text,delete_edits)
  assert numbered[:ops[0].start()]==header and deleted.startswith(header)
  # Exact edit replay proves all non-edited characters, not only numbers, survive.
  assert re.sub(r'(?m)^- ','',numbered)==ORDINAL.sub(lambda m:m.group('body')+(m.group('newline') or ''),text)
  assert [m.group('body') for m in operations(deleted)]==[m.group('body') for i,m in enumerate(ops,1) if i not in spec['delete']]
  purpose=[span(text,m.start(),m.end(),classification='retained_rationale_or_selection_not_replacement_operation') for m in re.finditer(r'[^\n]*(?:RI matching|refractive index|transparen|clear)[^\n]*',header,re.I)]
  texts={'baseline':text,'numbering':numbered,'merge':merged['model_response'],'necessary_step_deletion':deleted}
  ids={}
  for condition in ORDER:
   cid=f'round3_control_q{qid:03d}_{condition}_v1';aid=f'R3E2_Q{qid:03d}_{condition}';ids[condition]=cid
   c=copy.deepcopy(base);c.update(case_id=cid,anonymous_answer_id=aid,condition=condition,
      model_response=texts[condition],answer_sha256=rawsha(texts[condition]),question_sha256=rawsha(base['specific_question']),
      source_case_id=base['case_id'],source_case_file=str(PUBLIC/'cases.json'),
      source_scope='previously_exposed_development_task_same_canonical_fulltext_baseline',
      formal_eligible=False,expert_confirmation=None,
      round3_provenance={'baseline_anonymous_answer_id':spec['baseline'],'merge_anonymous_answer_id':spec['merge'] if condition=='merge' else None,
        'same_baseline_for_all_three_variants':True,'new_case_id_does_not_change_identical_source_content_hash':True})
   cases.append(c)
   for repeat in range(2):matrix.append({'cell_id':aid+f'__repeat{repeat}','case_id':cid,'anonymous_answer_id':aid,'question_id':qid,'condition':condition,'repeat':repeat,'phase':'E2','attempt':1,'planned_model':'same_ROOT_selected_judge_for_all24','answer_sha256':c['answer_sha256'],'question_sha256':c['question_sha256']})
  for condition in ORDER[1:]:pairs.append({'pair_id':f'round3_q{qid}_{condition}_pair_v1','question_id':qid,'condition':condition,'baseline_case_id':ids['baseline'],'variant_case_id':ids[condition],
    'paired_repeats':[0,1],'scientific_necessity':'source_supported_module_scope_pending_expert' if condition=='necessary_step_deletion' else None,
    'expected':'scientific_content_invariant_but_original_SRSP_granularity_may_change' if condition!='necessary_step_deletion' else 'reference_module_coverage_sensitivity_not_all_metrics_must_decrease'})
  edits.append({'question_id':qid,'baseline_case_id':ids['baseline'],'original_baseline':bind(PUBLIC/'cases.json'),
    'baseline_source_id':spec['baseline'],'baseline_text_sha256':rawsha(text),'numbering_prefix_edits':numbering_edits,
    'merge_groups_original_zero_based_indices':groups,'merge_provenance':bind(GRAN),'merge_verbatim_operation_sequence':True,
    'deletion_spans':delete_edits,'deleted_operation_indices':spec['delete'],
    'deletion_scope':'RI and storage module including downstream uses of the RI medium; not one atomic step',
    'q22_additional_deleted_relative_to_old_panel':qid==22,'retained_rationale_mentions':purpose,
    'all_other_text_bytes_reproducible_from_edit_replay':True,'necessity_status':'source_supported_development_pending_expert'})
 assert len(cases)==12 and len(pairs)==9 and len(matrix)==24 and len({c['case_id'] for c in cases})==12
 refs=read(OLD/'references.json')
 for name,data in [('cases.json',{'cases':cases}),('pairs.json',pairs),('planned_matrix.json',matrix),('edits.json',edits),('references.json',refs)]:save(OUT/name,data)
 deps=[Path(__file__),Path(core.__file__),PUBLIC/'cases.json',PUBLIC/'pairs.json',GRAN,OLD/'references.json',OLD/'step_config.json',OLD/'step_results.json',
       ROOT/'artifacts/cce_validation/reference_recovery/supplement_bound/evidence_manifest.json',ROOT/'prompts/eval_oeq_teacher_rubric.txt']
 freeze={'status':'inputs_fixed_before_new_step_results_and_new_judge_results','new_model_calls':0,'new_embeddings_allowed_local_only':True,
  'planned_cases':12,'planned_pairs':9,'planned_requests':24,'repeat_policy':'two new actual requests per identical frozen text, no retries',
  'root_approved_qids_and_deletions':SPECS,'thresholds':[.6,.7,.8],'primary_threshold':.7,'original_encoder':read(OLD/'step_config.json')['encoder'],
  'original_formula_segment_and_reference_policy_unchanged':True,'conditional_reference_scope_not_expert_qualified':True,
  'source_inputs':[bind(p) for p in deps],'frozen_inputs':[bind(OUT/n) for n in ['cases.json','pairs.json','planned_matrix.json','edits.json','references.json']],
  'actual_command':[sys.executable,*sys.argv]}
 save(OUT/'input_freeze.json',freeze)
 print(json.dumps({'status':freeze['status'],'cases':12,'pairs':9,'requests':24,'out':str(OUT),'new_model_calls':0}))

def score():
 if (OUT/'summary.json').exists():raise ValueError('STEP_RESULTS_ALREADY_EXIST')
 frozen=read(OUT/'input_freeze.json')
 for b in frozen['source_inputs']+frozen['frozen_inputs']:assert sha(b['path'])==b['sha256']
 cases=read(OUT/'cases.json')['cases'];pairs=read(OUT/'pairs.json');refs=read(OUT/'references.json')['references'];enc=OriginalEncoder();rows=[]
 archived={r['case_id']:r['step_result'] for r in read(OLD/'step_results.json')}
 index={c['case_id']:c for c in cases}
 for c in cases:
  for threshold in frozen['thresholds']:
   step=core.score_steps(c,refs,enc,threshold)
   rows.append({'case_id':c['case_id'],'anonymous_answer_id':c['anonymous_answer_id'],'question_id':c['question_id'],'condition':c['condition'],'threshold':threshold,
     'answer_sha256':c['answer_sha256'],'question_sha256':c['question_sha256'],'references_sha256':core.digest(c['references']),'step_result':step})
   if threshold==.7 and c['condition'] in ('baseline','merge'):
    suffix='order_canonical_baseline' if c['condition']=='baseline' else 'adjacent_entry_merge'
    old=archived[f'gemini-3-pro__q{c["question_id"]}__{suffix}__supplement_v2']
    assert step==old,'ARCHIVED_ORIGINAL_STEP_RESULT_DRIFT'
 steps={(r['case_id'],r['threshold']):r for r in rows};paired=[];primary={}
 for r in rows:
  if r['threshold']==.7:
   c=index[r['case_id']];s=r['step_result'];selected=next(x for x in refs if x['reference_id']==s['reference_id'])
   primary[c['case_id']]={k:r[k] for k in ['answer_sha256','question_sha256','question_id','references_sha256']}
   primary[c['case_id']].update(sr=s['sr'],sp=s['sp'],reference_id=s['reference_id'],candidate_reference_ids=s['candidate_reference_ids'],selected_reference_sha256=core.digest(selected),
     source_bindings=[bind(OUT/'input_freeze.json'),bind(OUT/'cases.json'),bind(OUT/'references.json')],step_source='new_actual_original_core_reparse_score_on_edited_fulltext',formal_eligible=False)
 for p in pairs:
  for threshold in frozen['thresholds']:
   a=steps[p['baseline_case_id'],threshold]['step_result'];b=steps[p['variant_case_id'],threshold]['step_result']
   paired.append({**p,'threshold':threshold,'baseline_sr':a['sr'],'variant_sr':b['sr'],'delta_sr':b['sr']-a['sr'],'baseline_sp':a['sp'],'variant_sp':b['sp'],'delta_sp':b['sp']-a['sp'],'baseline_generated_n':a['generated_n'],'variant_generated_n':b['generated_n'],'reference_n':a['reference_n']})
 for name,data in [('step_results.json',rows),('step_inputs_t070.json',primary),('paired_steps.json',paired)]:save(OUT/name,data)
 core.table(OUT/'paired_steps.csv',paired)
 for b in frozen['source_inputs']+frozen['frozen_inputs']:assert sha(b['path'])==b['sha256']
 summary={'status':'complete_offline_inputs_and_original_steps_no_judge_requests','cases':12,'pairs':9,'planned_new_requests':24,'step_rows':36,'pair_threshold_rows':27,
  'primary_threshold':.7,'new_model_calls':0,'existing_vectors_used':len(enc.used)-len(enc.created),'new_embeddings':len(enc.created),
  'source_refs_conditional_pending_expert':True,'archive_baseline_and_merge_exact_full_step_results_reverified':6,
  'primary_pairs':[r for r in paired if r['threshold']==.7],'actual_command':[sys.executable,*sys.argv]}
 save(OUT/'summary.json',summary)
 save(OUT/'execution.json',{'status':'pass','input_freeze':bind(OUT/'input_freeze.json'),'cached_vectors':enc.used,'created_vectors':enc.created,
  'outputs':[bind(OUT/n) for n in ['step_results.json','step_inputs_t070.json','paired_steps.json','paired_steps.csv','summary.json']],
  'new_model_calls':0,'actual_command':[sys.executable,*sys.argv]})
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','score']);a=p.parse_args();prepare() if a.action=='prepare' else score()
