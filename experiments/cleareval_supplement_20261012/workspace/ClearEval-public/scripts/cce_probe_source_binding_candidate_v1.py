"""Small offline source-binding checks plus three saved-result projections."""
import copy
import hashlib
import json
import sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_source_binding_candidate_v1 as h

OUT=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/source_binding_candidate_v1/author_03'
R2=OUT.parents[1]
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def doc(text):return h.backend.document(text,'SRC_SYNTHETIC')
def pair(text,f='FLUOR_A',t='TARGET_A'):
 d=doc(text);return h.explicit_pair_candidates(f,t,d,[])
def target(text):return h.visualization_target_candidates('FLUOR_A',doc(text))
def native(text,chosen='**Chosen Labeling:** [REPORTER_A]\n',usage='used'):
 d=doc(chosen+text);u=d['units'][0];support=h._span(d,u);name,binding=h.backend.bind_literal_name('REPORTER_A',support,d,0)
 e={'id':'E1','literal_name':'REPORTER_A','kind':'fluorophore','usage':usage,'name':name,'name_binding':binding}
 return h.native_declaration_candidates(e,d)

def main():
 checks=[]
 def check(name,ok):checks.append({'name':name,'pass':bool(ok)})
 check('existing_chosen_pair',len(pair('**Chosen Labeling:** [TARGET_A + FLUOR_A]\n'))==1)
 check('duplicate_pair_not_unique',len(pair('**Chosen Labeling:** [TARGET_A + FLUOR_A]\n**Selected Labeling:** [TARGET_A + FLUOR_A]\n'))==2)
 check('negated_pair_not_supported',not pair('**Chosen Labeling:** [not TARGET_A + FLUOR_A]\n'))
 check('alternative_pair_not_supported',not pair('**Chosen Labeling:** [either TARGET_A + FLUOR_A or TARGET_B + FLUOR_A]\n'))
 check('anti_prefix_not_truncated',not pair('**Chosen Labeling:** [anti-TARGET_A + FLUOR_A]\n'))
 check('different_target_not_borrowed',not pair('**Chosen Labeling:** [TARGET_B + FLUOR_A]\n'))
 check('visualization_literal_target',target('The use of FLUOR_A allows for visualization of TARGET_A in the sample.\n')[0]['literal_target']=='TARGET_A')
 check('visualization_negation',not target('Do not use FLUOR_A; The use of FLUOR_A does not allow visualization of TARGET_A.\n'))
 check('visualization_alternative',not target('The use of FLUOR_A allows for visualization of TARGET_A or TARGET_B in the sample.\n'))
 check('visualization_two_targets',not target('The use of FLUOR_A allows for visualization of TARGET_A and TARGET_B in the sample.\n'))
 check('visualization_different_fluor',not target('The use of FLUOR_B allows for visualization of TARGET_A in the sample.\n'))
 check('visualization_duplicate_not_unique',len(target('The use of FLUOR_A allows for visualization of TARGET_A in the sample.\nThe use of FLUOR_A allows for visualization of TARGET_A in the sample.\n'))==2)
 check('visualization_clipped_suffix_rejected',not target('The use of FLUOR_A2 allows for visualization of TARGET_A in the sample.\n'))
 check('visualization_example_without_if',not target('For example, the use of FLUOR_A allows for visualization of TARGET_A in the sample.\n'))
 check('visualization_eg_no_sentence_detachment',not target('e.g. The use of FLUOR_A allows for visualization of TARGET_A in the sample.\n'))
 check('visualization_optionally',not target('Optionally, the use of FLUOR_A allows for visualization of TARGET_A in the sample.\n'))
 check('native_explicit_combination',len(native('The combination of endogenous REPORTER_A and exogenous TARGET_A labeling provides dual observation.\n'))==1)
 check('native_capability_not_use',not native('This method can preserve endogenous REPORTER_A well.\n'))
 check('native_example_not_use',not native('For example, use endogenous REPORTER_A if appropriate.\n'))
 check('native_example_without_if',not native('For example, use of endogenous REPORTER_A provides contrast.\n'))
 check('native_eg_no_sentence_detachment',not native('e.g. Use of endogenous REPORTER_A provides contrast.\n'))
 check('native_optionally',not native('Optionally, use of endogenous REPORTER_A provides contrast.\n'))
 check('native_negation',not native('Do not use endogenous REPORTER_A.\n'))
 check('native_alternative',not native('Use endogenous REPORTER_A or REPORTER_B.\n'))
 check('native_not_chosen',not native('Use endogenous REPORTER_A.\n',chosen='REPORTER_A is mentioned.\n'))
 check('native_raw_negated',not native('Use endogenous REPORTER_A.\n',usage='negated'))
 check('native_duplicate_not_unique',len(native('Use endogenous REPORTER_A.\nUse endogenous REPORTER_A.\n'))==2)
 check('native_name_suffix_no_alias',not native('Use endogenous REPORTER_A2.\n'))
 save(OUT/'software_probes.json',{'checks':checks,'passed':sum(x['pass'] for x in checks),'total':len(checks),'calls':0,'module_sha256':sha(Path(h.__file__))})
 if not all(x['pass'] for x in checks):raise AssertionError([x['name'] for x in checks if not x['pass']])
 actual=[]
 for aid,batch,source in [('FPC03','first7_posthoc','generation_confirmation_v2'),('FPC13','secondary8_posthoc','secondary_E5_confirmation_v1'),('FPC15','secondary8_posthoc','secondary_E5_confirmation_v1')]:
  pp=R2/'posthoc_uniform_scoring_v3/actual_execution_01/cells'/batch/aid/'posthoc.json';dp=R2/source/'source_documents'/f'{aid}.json'
  prior=read(pp)['conversion'];d=read(dp);snapshot=copy.deepcopy(prior);after=h.apply_conversion(prior,d)
  assert prior==snapshot and after['wire_payload']==prior['wire_payload'] and after['source_audit']==prior['source_audit']
  assert h.apply_conversion(after,d)==after
  rec={'anonymous_answer_id':aid,'source_document':{'path':str(dp),'sha256':sha(dp)},'prior_posthoc':{'path':str(pp),'sha256':sha(pp)},
    'original_wire':{k:prior['wire_payload']['grounded_extraction'][k] for k in ['relations','intrinsic_signals']},
    'original_projection':prior['label_occurrence_projection'],'candidate_projection':after['label_occurrence_projection'],
    'candidate_audit':after['source_binding_candidate_v1'],'raw_and_resolved_unchanged':True,'idempotent':True,
    'score_recomputed':False,'KB_values_added':False}
  save(OUT/f'{aid}.json',rec)
  actual.append({'answer_id':aid,'applied':rec['candidate_audit']['applied'],'remaining_uncertainties':after['label_occurrence_projection']['explicit_label_uncertainties'],'output':str(OUT/f'{aid}.json')})
 save(OUT/'summary.json',{'status':'pass_author_software_and_three_actual_source_projections','module_sha256':sha(Path(h.__file__)),
  'software_probes':len(checks),'actual_source_documents':3,'actual':actual,'new_model_calls':0,'new_numeric_scores':0,
  'posthoc_selected_diagnostic_not_confirmation':True,'command':'python scripts/cce_probe_source_binding_candidate_v1.py'})
 print(json.dumps({'status':'pass','software_probes':len(checks),'actual':[{k:x[k] for k in ['answer_id','remaining_uncertainties']} for x in actual]},ensure_ascii=True))

if __name__=='__main__':main()
