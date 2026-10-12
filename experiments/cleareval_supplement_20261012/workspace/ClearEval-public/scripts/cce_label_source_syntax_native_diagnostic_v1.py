"""Read the saved FPC13 source only; native evidence is not rebound in scores."""
import copy, hashlib, json, re, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_label_source_syntax_fix_v1 as fix
R=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
OUT=R/'label_source_syntax_fix_v1/native_diagnostic'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def bind(p):return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def main():
 source=R/'secondary_E5_confirmation_v1';docpath=source/'source_documents/FPC13.json';doc=read(docpath)
 cvpath=R/'label_source_syntax_fix_v1/actual15_01/cases/FPC13/after.json'
 resolved=read(cvpath)['conversion']['source_audit']['resolved']
 record=next(r for r in resolved['intrinsic_signals'] if r['id']=='I0001')
 entity=next(e for e in resolved['entities'] if e['id']==record['entity_id'])
 name=entity['literal_name'];pattern=re.compile(r'\bendogenous\s+'+re.escape(name)+r'(?![\w+\-/])',re.I)
 occurrences=[]
 for unit in doc['units']:
  for m in pattern.finditer(unit['text']):
   start=unit['start']+m.start();end=unit['start']+m.end()
   # Preserve the full literal source sentence as evidence, not a replacement
   # model record; no source ID/ordinal or scores are changed.
   left=max([x.end() for x in re.finditer(r'[.!?]\s+',unit['text'][:m.start()])]+[0])
   cut=re.search(r'[.!?](?:\s|$)',unit['text'][m.end():]);right=m.end()+cut.end() if cut else len(unit['text'])
   occurrences.append({'unit_id':unit['unit_id'],'start':start,'end':end,'quote':doc['text'][start:end],
    'sentence_start':unit['start']+left,'sentence_end':unit['start']+right,
    'sentence':unit['text'][left:right],'answer_sha256':doc['answer_sha256']})
 alternatives=[]
 for uid in dict.fromkeys(r['unit_id'] for r in occurrences):
  proposed=copy.deepcopy(record);proposed['evidence']=fix.boundary.resolve({'unit_id':uid},doc)
  diagnostic=fix.boundary.intrinsic_policy(proposed,entity,resolved['relations'],doc,resolved['entities'])
  alternatives.append({'hypothetical_evidence_unit':uid,'original_predicate_result':diagnostic,
   'only_in_memory_predicate_probe':True,'raw_or_scoring_changed':False})
 result={'status':'read_only_source_diagnostic','anonymous_answer_id':'FPC13','raw_record_id':record['id'],
  'raw_entity':{k:entity[k] for k in ['id','literal_name','kind','usage','name_occurrence']},
  'original_native_evidence':record['evidence'],'original_policy':record['identity_policy'],
  'explicit_native_literal_occurrences':occurrences,'count':len(occurrences),
  'whole_unit_alternative_predicate_probes':alternatives,
  'diagnosis':'The raw native record cites the selected-label unit without a native qualifier. A different source unit contains an explicit endogenous-name declaration; the full unit also contains capability prose and repeated names. This candidate evidence is made visible, not silently substituted into the model record.',
  'no_new_cellular_target_or_compatibility_value':True,'native_fix_implemented':False,
  'new_model_calls':0,'new_scores':0,'bindings':[bind(docpath),bind(cvpath),bind(Path(__file__)),bind(Path(fix.__file__))],
  'actual_command':[sys.executable,*sys.argv]}
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'FPC13_native_source.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
 print(json.dumps({'explicit_native_occurrences':len(occurrences),'raw_evidence':record['evidence']['unit_id'],'candidate_units':[r['unit_id'] for r in occurrences],'hypothetical_unit_gate':[{'unit':r['hypothetical_evidence_unit'],'complete_name':r['original_predicate_result']['complete_name_occurrence'],'affirmative':r['original_predicate_result']['affirmative_use_context'],'native':r['original_predicate_result']['native_source_cue'],'disqualified':r['original_predicate_result']['disqualified_by_capability_alternative_or_negation']} for r in alternatives],'no_scores_changed':True},ensure_ascii=True))
if __name__=='__main__':main()
