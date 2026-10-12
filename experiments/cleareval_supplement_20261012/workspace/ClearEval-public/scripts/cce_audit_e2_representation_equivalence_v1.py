"""Read-only exact E2 text/parameter audit; reuse saved similarity maxima.

No embeddings, judge calls, scoring changes, or confirmation inputs.
"""
import argparse, collections, csv, difflib, hashlib, json, re, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cce_validation as core
ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
B=R/'grounded_controls_v11'
OLD=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_controls_v1'
MECHANISM=OLD.parent/'grounded_controls_v7_step_mechanism_v1'
INPUTS={}
def h(x):return hashlib.sha256(x).hexdigest()
def bind(p):
 p=Path(p).resolve();v={'path':str(p),'sha256':h(p.read_bytes())};INPUTS[str(p)]=v;return v
def read(p):bind(p);return json.loads(Path(p).read_text(encoding='utf8'))
def require(x,m):
 if not x:raise AssertionError(m)
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def narrow(x):return re.sub(r'^\s*\d+(?:\.\d+)*[.)]?\s+','',x.strip())
def normalize(x):return re.sub(r'\s+',' ',re.sub(r'(?m)^[ \t]*(?:\d+(?:\.\d+)*\.?|-)\s+','',x)).strip()
def delta_bytes(before,after):
 a,b=before.encode('utf8'),after.encode('utf8');changes=[];rebuilt=[]
 for tag,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
  rebuilt.append(b[k:l] if tag!='equal' else a[i:j])
  if tag!='equal':changes.append({'type':tag,'baseline_byte_start':i,'baseline_byte_end':j,'variant_byte_start':k,'variant_byte_end':l,
    'removed_utf8_hex':a[i:j].hex(),'inserted_utf8_hex':b[k:l].hex()})
 require(b''.join(rebuilt)==b,'BYTE_DIFF_RECONSTRUCTION')
 return {'baseline_utf8_sha256':h(a),'variant_utf8_sha256':h(b),'exact_byte_reconstruction':True,'changes':changes}
def raw_trial(row):
 tid=row['planned_trial_id'];at=B/'run/attempts'/f'{tid}_1';trial=read(B/'run/trials'/f'{tid}.json')
 require(trial['identity']==row['identity'] and trial['status'] in ['success','failed'],'TERMINAL_IDENTITY')
 for x in trial['bound_artifacts']:require(bind(x['path'])['sha256']==x['sha256'],'TRIAL_ARTIFACT_DRIFT')
 rawp=at/'raw_source_bound_content.txt';raw=read(rawp);num=read(at/'numeric_result.json');receipt=read(at/'request_receipt.json')
 require(receipt['request_id']==trial['request_id'] and receipt['trial_id']==tid,'RECEIPT_IDENTITY')
 return {'trial':bind(B/'run/trials'/f'{tid}.json'),'raw':bind(rawp),'numeric':bind(at/'numeric_result.json'),
  'request_receipt':bind(at/'request_receipt.json'),'status':trial['status'],'scores':raw['scores'],
  'score_evidence':raw['score_evidence'],'metrics':num['metrics']}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=R/'E2_representation_equivalence_audit_v1');a=ap.parse_args()
 require(not a.out.exists(),'NEW_OUTPUT_REQUIRED');a.out.mkdir(parents=True);(a.out/'diffs').mkdir()
 cases={x['case_id']:x for x in read(B/'cases.json')['cases']};matrix={x['case_id']:x for x in read(B/'matrix.json')}
 pairs=[x for x in read(B/'pairs.json') if x['condition'] in ['deterministic_equivalent_representation','adjacent_entry_merge']]
 steps={x['case_id']:x for x in read(OLD/'step_results.json')};savedmechanism={x['pair_id']:x for x in read(MECHANISM/'per_pair.json')}
 granularity=read(ROOT/'artifacts/cce_validation/controls/granularity_edits.json');edits={x['question_id']:x for x in granularity['edits']}
 numbering_edits=read(ROOT/'artifacts/cce_validation/controls/edits.json');bind(ROOT/'scripts/cce_prepare.py');bind(core.__file__);bind(__file__)
 reports=[];refrows=[];steprows=[]
 for p in pairs:
  bc,vc=(cases[p[k]] for k in ['baseline_case_id','variant_case_id']);bt,vt=bc['model_response'],vc['model_response'];qid=p['question_id'];kind=p['condition']
  name=f'q{qid}_'+('numbering' if kind.startswith('deterministic') else 'merge');br,vr=matrix[bc['case_id']],matrix[vc['case_id']]
  for c,r in [(bc,br),(vc,vr)]:
   require(h(c['model_response'].encode())==r['step']['answer_sha256']==steps[c['case_id']]['answer_sha256'],'ACTUAL_STEP_INPUT_HASH')
   require(h(c['specific_question'].encode())==r['step']['question_sha256'],'QUESTION_INPUT_HASH')
   for asset in r['assets'].values():require(bind(asset['path'])['sha256']==asset['sha256'],'MATRIX_ASSET_HASH')
  require(bc['specific_question']==vc['specific_question'] and bc['references']==vc['references'],'PAIR_SCIENTIFIC_CONTEXT')
  difference=delta_bytes(bt,vt);write(a.out/'diffs'/f'{name}.byte_changes.json',difference)
  patch=b''.join(difflib.diff_bytes(difflib.unified_diff,bt.encode().splitlines(True),vt.encode().splitlines(True),fromfile=b'baseline',tofile=b'variant'))
  (a.out/'diffs'/f'{name}.utf8.diff').write_bytes(patch)
  nb,nv=normalize(bt),normalize(vt);require(nb==nv,'RESIDUAL_FULLTEXT_CHANGED')
  row={'question_id':qid,'condition':kind,'baseline_case_id':bc['case_id'],'variant_case_id':vc['case_id'],
   'baseline_id':br['anonymous_answer_id'],'variant_id':vr['anonymous_answer_id'],
   'baseline_sha256':h(bt.encode()),'variant_sha256':h(vt.encode()),'specific_question_and_references_equal':True,
   'full_text_equal_after_structural_prefix_and_whitespace_normalization':True,'normalized_content_sha256':h(nb.encode()),
   'all_remaining_numeric_tokens_equal':re.findall(r'\d+(?:\.\d+)?',nb)==re.findall(r'\d+(?:\.\d+)?',nv),
   'all_nonprefix_word_and_punctuation_characters_equal':True,'difference':str(a.out/'diffs'/f'{name}.byte_changes.json'),
   'meaning_boundary':'Exact preservation of residual source text and numeric values; typography/hierarchy changed. Not expert proof of every semantic consequence.'}
  if kind.startswith('deterministic'):
   changed,n=re.subn(r'(?m)^(\s*)\d+(?:\.\d+)*\s+',r'\1- ',bt)
   require(changed==vt,'ORIGINAL_NUMBERING_EDIT_NOT_REPRODUCED')
   matches=[]
   for m in re.finditer(r'(?m)^(\s*)\d+(?:\.\d+)*\s+',bt):
    end=bt.find('\n',m.end());end=len(bt) if end<0 else end
    matches.append({'start':m.start(),'end':m.end(),'removed_prefix':m.group(),'retained_line_body':bt[m.end():end]})
   row.update(numbering_regex_replay_exact=True,changed_prefix_count=n,changed_prefixes=matches)
  else:
   e=edits[qid];require(h(bt.encode())==e['baseline_text_sha256'] and h(vt.encode())==e['variant_text_sha256'],'MERGE_SOURCE_HASH')
   original=[narrow(bt[m['original_start']:m['original_end']]) for m in e['original_operation_to_merged_entry']]
   require(all(h(x.encode())==m['operation_text_sha256'] for x,m in zip(original,e['original_operation_to_merged_entry'])),'ORIGINAL_OPERATION_CHANGED')
   entries=[narrow(x) for x in vt.splitlines() if re.match(r'^\d+\.\s',x)]
   grouped=[' '.join(original[i] for i in group) for group in e['groups_of_original_indices']]
   require(entries==grouped,'GROUPED_OPERATION_CONTENT_CHANGED')
   order=[i for group in e['groups_of_original_indices'] for i in group];require(order==list(range(len(original))),'MERGE_OPERATION_ORDER')
   row.update(original_operation_count=len(original),merged_entry_count=len(entries),exact_grouped_operations_preserved=True,
    operation_order_and_full_content_preserved=True,groups_of_original_indices=e['groups_of_original_indices'],
    comparison_uses_frozen_canonical_baseline=True)
  bp,vp=steps[bc['case_id']]['step_result'],steps[vc['case_id']]['step_result']
  for case,step,mr in [(bc,bp,br),(vc,vp,vr)]:
   segmented=core.segment(case['model_response']);require(segmented==step['generated_steps'],'ORIGINAL_SEGMENTATION_REPLAY')
   require(step['sr']==mr['step']['sr'] and step['sp']==mr['step']['sp'],'FROZEN_SRSP_IDENTITY')
   srn=sum(z['similarity']>=.7 for z in step['matches']);spn=sum(z>=.7 for z in step['generated_max_similarity'])
   require(srn/step['reference_n']==step['sr'] and spn/step['generated_n']==step['sp'],'SAVED_MAXIMA_COUNT')
   steprows.append({'case_id':case['case_id'],'anonymous_answer_id':mr['anonymous_answer_id'],
    'reference_n':step['reference_n'],'generated_n':step['generated_n'],'sr_numerator':srn,'sp_numerator':spn,
    'sr':step['sr'],'sp':step['sp'],'reference_truncated':step['reference_truncated'],'generated_truncated':step['generated_truncated'],
    'generated_max_similarity':step['generated_max_similarity'],'generated_steps':step['generated_steps']})
  require(bp['reference_id']==vp['reference_id'],'REFERENCE_CHANGED')
  for x,y in zip(bp['matches'],vp['matches']):
   refrows.append({'question_id':qid,'condition':kind,'reference_index':x['reference_index'],
    'baseline_similarity':x['similarity'],'variant_similarity':y['similarity'],'baseline_matched':x['matched'],'variant_matched':y['matched'],
    'baseline_generated_index':x['generated_index'],'variant_generated_index':y['generated_index'],
    'baseline_generated_text':x['generated_text'],'variant_generated_text':y['generated_text'],
    'reference_text':x['reference_text']})
  row['step_mechanism']={k:savedmechanism[p['pair_id']][k] for k in ['baseline_sr','variant_sr','baseline_sp','variant_sp','baseline_generated_n','variant_generated_n','reference_match_transitions']}
  row['segmented_text_sequence_equal']=[x['text'] for x in bp['generated_steps']]==[x['text'] for x in vp['generated_steps']]
  row['reference_and_generated_truncation_counts']=[bp['reference_truncated'],bp['generated_truncated'],vp['reference_truncated'],vp['generated_truncated']]
  reports.append(row)
 # Exact original q2 judge proposals, not new scores.
 q2=next(p for p in pairs if p['question_id']==2 and p['condition'].startswith('deterministic'))
 reasoning={name:raw_trial(matrix[q2[key]]) for name,key in [('baseline','baseline_case_id'),('numbered','variant_case_id')]}
 for name,key in [('baseline','baseline_case_id'),('numbered','variant_case_id')]:
  case=cases[q2[key]];source=case['model_response'];reasoning[name]['source_mentions']={
   'pH':[{'start':m.start(),'end':m.end(),'quote':m.group()} for m in re.finditer(r'\bpH\b',source)],
   'dark':[{'start':m.start(),'end':m.end(),'quote':source[max(0,source.rfind('\n',0,m.start())+1):source.find('\n',m.end()) if source.find('\n',m.end())>=0 else len(source)]} for m in re.finditer(r'\bdark\b',source,re.I)]}
 write(a.out/'six_pairs.json',reports);write(a.out/'saved_step_maxima.json',steprows);write(a.out/'reference_maximum_transitions.json',refrows);write(a.out/'q2_original_c_param_reasoning.json',reasoning)
 summary={'status':'completed_read_only_audit','pairs':6,'numbering_pairs':3,'adjacent_merge_pairs':3,
  'all_residual_fulltexts_identical':all(x['full_text_equal_after_structural_prefix_and_whitespace_normalization'] for x in reports),
  'all_parameter_numeric_sequences_equal':all(x['all_remaining_numeric_tokens_equal'] for x in reports),
  'numbering_prefix_counts':{str(x['question_id']):x['changed_prefix_count'] for x in reports if 'changed_prefix_count' in x},
  'merge_operation_counts':{str(x['question_id']):[x['original_operation_count'],x['merged_entry_count']] for x in reports if 'original_operation_count' in x},
  'q2_c_param':[reasoning[x]['scores']['completeness']['c_param']['score'] for x in ['baseline','numbered']],
  'q2_other_four_direct_scores_equal':reasoning['baseline']['scores']['correctness']==reasoning['numbered']['scores']['correctness'],
  'numeric_scores_or_threshold_changed':False,'new_judge_calls':0,'new_embeddings':0,'new_stability_observations':0,
  'conclusion':'No parameter/text loss detected in these six frozen edits. Numbering changes layout/hierarchy; merge changes encoder segment composition. Exact reasons and maxima are preserved, without identifying a unique latent cause for judge variation.'}
 # Correctness reasoning may differ despite all four numeric proposals agreeing.
 summary['q2_other_four_direct_scores_equal']=all(reasoning['baseline']['scores']['correctness'][k]['score']==reasoning['numbered']['scores']['correctness'][k]['score'] for k in ['co_order','co_method','co_param','co_chem'])
 write(a.out/'summary.json',summary)
 write(a.out/'verification.json',{'status':'pass','inputs':list(INPUTS.values()),'all_input_hashes_unchanged':all(h(Path(x['path']).read_bytes())==x['sha256'] for x in INPUTS.values()),
  'outputs':[{'path':str(p),'sha256':h(p.read_bytes())} for p in a.out.rglob('*') if p.is_file()],
  'actual_command':sys.argv,'new_judge_calls':0,'new_embeddings':0,'original_segment_replay_count':len(steprows)})
 print(json.dumps(summary,ensure_ascii=False));print('summary_sha256',h((a.out/'summary.json').read_bytes()))
if __name__=='__main__':main()
