"""Narrow software probes and the same syntax configuration on all 15 returns."""
import argparse, contextlib, csv, hashlib, io, json, sys, types
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_label_source_syntax_fix_v1 as fix
import cce_posthoc_scoring_v2 as previous
import cce_namespace_fw5_component_replay_v1 as components
R=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def quiet(f,*a):
 with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):return f(*a)
def probes():
 rows=[];g=fix.build_backend(fix.previous_boundary)
 def record(kind,fixture,actual,expected,detail=None):rows.append({'kind':kind,'fixture':fixture,'actual':actual,'expected':expected,'pass':actual==expected,'detail':detail})
 for name,expected in [('SpectraX 530/615',True),('Unlisted Signal 410/680',True),('SpectraX 530/615 nm',True),('LABEL_A/LABEL_B',False),('DYE_A / DYE_B',False),('A530/B615',False),('SpectraX 530/615 + DYE_B',False),('SpectraX 530/615; DYE_B',False),('SpectraX 530/615/730',False)]:
  support={'context':'Chosen Labeling: ['+name+']'};value=fix.name_atomicity(name,support)
  record('atomic_numeric_designation',name,value['projection_eligible_provisional'],expected,value)
 for text,expected in [('Chosen Labeling: [SpectraX 530/615]',True),('Chosen Labeling: [either SpectraX 530/615 or DYE_B]',False),('Chosen Labeling: [not SpectraX 530/615]',False),('Chosen Labeling: [optional SpectraX 530/615]',False),('Chosen Labeling: [SpectraX 530/615 / DYE_B]',False),('SpectraX 530/615 is a possible label.',False)]:
  record('selected_numeric_name',text,fix.affirmative_entity_use('SpectraX 530/615',text),expected)
 relation_cases=[
 ('The use of DYE_X allows for robust labeling of TARGET_A.','DYE_X','TARGET_A',True),
 ('The use of DYE_X allows for labeling of TARGET_A.','DYE_X','TARGET_A',True),
 ('The use of DYE_X allows for robust labelling of TARGET_A.','DYE_X','TARGET_A',True),
 ('Do not use DYE_X; labeling of TARGET_A is desired.','DYE_X','TARGET_A',False),
 ('The use of DYE_X does not allow for robust labeling of TARGET_A.','DYE_X','TARGET_A',False),
 ('Either use of DYE_X allows for robust labeling of TARGET_A or use DYE_Y.','DYE_X','TARGET_A',False),
 ('Optional use of DYE_X allows for robust labeling of TARGET_A.','DYE_X','TARGET_A',False),
 ('The use of DYE_X allows for robust labeling of TARGET_A; the use of DYE_Y allows for labeling of TARGET_B.','DYE_X','TARGET_B',False),
 ('DYE_X is present; use of DYE_Y allows for robust labeling of TARGET_A.','DYE_X','TARGET_A',False),
 ('DYE_X and DYE_Y allow robust labeling of TARGET_A and TARGET_B.','DYE_X','TARGET_B',False),
 ('The use of DYE_X allows for robust labeling of TARGET_A or TARGET_B.','DYE_X','TARGET_A',False),
 ('The use of DYE_X allows for robust labeling of TARGET_A; do not use DYE_Y for TARGET_B.','DYE_X','TARGET_A',True),
 ('DYE_X and TARGET_A are present.','DYE_X','TARGET_A',False)]
 for text,f,t,expected in relation_cases:
  doc=g.document(text,'SRC_SYNTHETIC_SYNTAX');ev=g.resolve({'unit_id':doc['units'][0]['unit_id']},doc)
  value=g.relation_clause_support(f,t,ev,doc,[])
  record('complete_local_relation',text,value['projection_supported'],expected,value)
 # The composable backend must really expose the environment used by its
 # production binders; downstream adapters may clone these functions again.
 record('composable_environment','relation predicate',g._environment['relation_policy'] is fix.relation_policy,True)
 record('composable_environment','atomicity predicate',g._environment['name_atomicity'] is fix.name_atomicity,True)
 return rows
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--software-only',action='store_true');a=p.parse_args()
 assert not a.out.exists(),'NEW_OUTPUT_REQUIRED';a.out.mkdir(parents=True)
 checks=probes();save(a.out/'software_probes.json',{'checks':len(checks),'passed':sum(r['pass'] for r in checks),'rows':checks})
 assert all(r['pass'] for r in checks),'SOFTWARE_PROBE_FAILURE'
 if a.software_only:print(json.dumps({'checks':len(checks),'passed':len(checks)}));return
 baseline_path=R/'posthoc_uniform_scoring_v2/actual_execution_01/cells.json';baseline={r['cell_id']:r for r in read(baseline_path) if r['cell_id'].startswith('FPC')}
 scorer=fix.make_scorer(previous)
 process=types.FunctionType(components.independent_processing.__code__,{**vars(components),'fw':scorer,'g':scorer.ground},name='syntax_components')
 rows=[];bindings=[bind(__file__),bind(fix.__file__),bind(previous.__file__),bind(fix.previous_boundary.__file__),bind(components.__file__),bind(baseline_path)]
 for directory,ids in [('generation_confirmation_v2',range(2,9)),('secondary_E5_confirmation_v1',range(9,17))]:
  source=R/directory;matrix=read(source/'matrix.json');cases=read(source/'cases.json');cases=cases['cases'] if isinstance(cases,dict) else cases
  assert [r['anonymous_answer_id'] for r in matrix]==['FPC%02d'%i for i in ids]
  bindings.extend([bind(source/'matrix.json'),bind(source/'cases.json')])
  for row,case in zip(matrix,cases):
   aid=row['anonymous_answer_id'];at=source/'run/attempts'/(row['planned_trial_id']+'_1');rawpath=at/'raw_response.txt';docpath=source/'source_documents'/(aid+'.json')
   raw=rawpath.read_bytes().decode('utf8');doc=read(docpath);trial=read(source/'run/trials'/(row['planned_trial_id']+'.json'))
   assert trial['identity']==row['identity'] and trial['status'] in ['success','partial_components','failed']
   assert scorer.ground.rawsha(raw)==baseline[aid]['raw_sha256']
   assert doc==scorer.ground.document(case['model_response'],scorer.ground.source_id_for_case(case))
   old=read(baseline[aid]['posthoc_record']['path']);assert sha(baseline[aid]['posthoc_record']['path'])==baseline[aid]['posthoc_record']['sha256']
   new=quiet(process,raw,doc,case,row['step'])
   assert new['raw_sha256']==old['raw_sha256']
   stable=['c_param','co_order','co_method','co_param','co_chem','s_method','s_trans','s_time','sr','sp','Com','Cor']
   assert all(new['metrics'][k]==old['metrics'][k] for k in stable),(aid,'NONLABEL_METRICS_CHANGED')
   save(a.out/'cases'/aid/'after.json',new)
   change={k:{'before':old['metrics'][k],'after':new['metrics'][k]} for k in new['metrics'] if old['metrics'][k]!=new['metrics'][k]}
   entry={'anonymous_answer_id':aid,'original_status':trial['status'],'raw_sha256':scorer.ground.rawsha(raw),'before_metrics':old['metrics'],'after_metrics':new['metrics'],
    'before_full_conversion':old['full_conversion_success'],'after_full_conversion':new['full_conversion_success'],'metric_changes':change,
    'source_bindings':[bind(rawpath),bind(docpath),bind(source/'run/trials'/(row['planned_trial_id']+'.json'))],
    'prior_posthoc_record':baseline[aid]['posthoc_record'],'new_posthoc_record':bind(a.out/'cases'/aid/'after.json')}
   if new.get('conversion') and old.get('conversion'):
    bef=old['conversion']['source_audit']['resolved'];aft=new['conversion']['source_audit']['resolved']
    entry['relation_deltas']=[{'id':x['id'],'before':x['projection_allowed'],'after':y['projection_allowed'],'before_reason':x['mechanical_relation_state'],'after_reason':y['mechanical_relation_state'],'source':y['evidence']} for x,y in zip(bef['relations'],aft['relations']) if x['projection_allowed']!=y['projection_allowed']]
    entry['atomicity_deltas']=[{'id':x['id'],'literal_name':x['literal_name'],'before':x['name_binding']['atomicity'],'after':y['name_binding']['atomicity'],'source':y['name']} for x,y in zip(bef['entities'],aft['entities']) if x['name_binding']['atomicity']!=y['name_binding']['atomicity']]
   rows.append(entry);bindings+=entry['source_bindings'];print(json.dumps({'id':aid,'metric_changes':change,'relation_deltas':len(entry.get('relation_deltas',[])),'atomicity_deltas':len(entry.get('atomicity_deltas',[]))}),flush=True)
 for b in bindings:assert sha(b['path'])==b['sha256']
 assert len(rows)==15
 save(a.out/'per_answer.json',rows)
 with (a.out/'per_answer.csv').open('w',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['anonymous_answer_id','original_status','label_before','label_after','full_conversion_before','full_conversion_after','metric_changed']);w.writeheader()
  for x in rows:w.writerow({'anonymous_answer_id':x['anonymous_answer_id'],'original_status':x['original_status'],'label_before':x['before_metrics']['s_label'],'label_after':x['after_metrics']['s_label'],'full_conversion_before':x['before_full_conversion'],'full_conversion_after':x['after_full_conversion'],'metric_changed':bool(x['metric_changes'])})
 save(a.out/'summary.json',{'status':'complete_posthoc_syntax_sensitivity','actual_answers':15,'software_checks':len(checks),'software_passed':len(checks),'new_model_calls':0,'new_embeddings':0,
  'same_configuration_all15':True,'direct_and_all_nonlabel_metrics_unchanged':True,'raw_source_original_status_unchanged':True,'KB_values_or_relationships_inferred':False,
  'changed_numeric_answers':[x['anonymous_answer_id'] for x in rows if x['metric_changes']],
  'source_relation_changed_answers':[x['anonymous_answer_id'] for x in rows if x.get('relation_deltas')],
  'source_name_changed_answers':[x['anonymous_answer_id'] for x in rows if x.get('atomicity_deltas')],
  'baseline':'posthoc v2, before later time/target helpers; candidate differs only two source-syntax repairs',
  'bindings':bindings,'actual_command':[sys.executable,*sys.argv],'posthoc_not_new_validation':True,'expert_validated':False})
 print(json.dumps({'actual_answers':15,'checks':len(checks),'changed':[x['anonymous_answer_id'] for x in rows if x['metric_changes']]}))
if __name__=='__main__':main()
