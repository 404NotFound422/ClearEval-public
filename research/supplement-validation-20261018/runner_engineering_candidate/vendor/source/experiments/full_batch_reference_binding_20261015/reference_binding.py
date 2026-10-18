"""Reusable source-to-question coverage binding. No new science, scoring or models.
Only explicitly registered, independently reviewed source inventory templates are admitted.
Reference selection is explicit; method identity alone does not choose an imaging branch.
"""
import copy,hashlib,json,pathlib,re,sys
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT))
from evaluation_contract import json_hash
from oeq_task_evidence import validate_task_evidence,project_task_evidence

TEMPLATES={
 'macs-original2020-serial-three-v1':{'method':'MACS','task':ROOT/'experiments/real_multiroute_q157_prepare_20261015/source_provider/MACS_task_evidence.json','qid':'157','review':ROOT/'experiments/real_multiroute_q157_prepare_20261015/independent_source_review/verification.json','review_success_key':'all_pass'},
 'scales-original2015-four-sentences':{'method':'ScaleS','task':ROOT/'experiments/p3_real_routes_q21_20261015/sources/ScaleS_task_evidence.json','qid':'21','review':ROOT/'experiments/p3_real_routes_q21_20261015/sources/ScaleS_independent_source_review_frozen.json','review_success_key':'all_pass'},
 'idisco-dec2016-lightsheet':{'method':'iDISCO+','task':HERE/'q1_reference_augmentation/task_evidence.json','qid':'1','review':ROOT/'experiments/full_batch_partial_independent_review_20261015/q1_augmentation_review.json','review_success_key':'all_checks'},
 'fdisco2019-clearing-storage':{'method':'FDISCO','task':HERE/'q2_reference_augmentation/task_evidence.json','qid':'2','review':ROOT/'experiments/q2_fdisco_reference_independent_review_20261015/verification.json','review_success_key':'all_pass'},
}
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verified_template(reference_key):
 if reference_key not in TEMPLATES:raise ValueError('No independently reviewed source inventory for reference key')
 info=TEMPLATES[reference_key];lock=read(HERE/'source_template_lock.json')[reference_key]
 if sha(info['task'])!=lock['task_file_sha256'] or sha(info['review'])!=lock['review_file_sha256']:
  raise ValueError('Reviewed source template or independent review bytes changed')
 review=read(info['review'])
 if review.get(info['review_success_key']) is not True:raise ValueError('Source scope review has not passed')
 task=read(info['task'])[info['qid']];validate_task_evidence(task)
 return info,task,lock

def question_obligations(question):
 text=question['question'];phrase='关键试剂、条件和时间';reqs=[]
 if phrase not in text:raise ValueError('Explicit three-field request absent; needs its own textual obligations')
 base=text.rindex(phrase)
 for rid,quote in [('KEY_REAGENTS','关键试剂'),('KEY_CONDITIONS','条件'),('KEY_TIMES','时间')]:
  start=text.index(quote,base);reqs.append({'id':rid,'kind':'COMPLETENESS','necessary':True,'text':'Report '+quote+' as explicitly requested; presence does not establish scientific correctness.','reference_role':'CONSTRAINT','scope':'GLOBAL','evidence_ids':[],'question_span':{'start':start,'end':start+len(quote),'quote':quote}})
 return reqs

def bind_question(question,method_identity,*,reference_key,branch='main',protocol=None,branch_selection=None):
 """Bind an explicitly selected reviewed reference, never infer valid parameters.
 method_identity must be the audited original canonical method identity object.
 A reference version is the declared comparison source, not a candidate claim.
 """
 info,template,lock=verified_template(reference_key)
 if method_identity.get('status')!='SATISFIED' or method_identity.get('branches')!={branch:[info['method']]}:
  raise ValueError('Canonical method/branch identity does not exactly match selected source')
 text=question['question'];compact=re.sub(r'\s+','',text)
 scope='随后仅列出透明处理、RI匹配和保存/成像前处理步骤'
 if scope not in compact:raise ValueError('Question output scope differs from reviewed clearing/RI/storage scope')
 if reference_key=='idisco-dec2016-lightsheet':
  if not isinstance(protocol,str) or not isinstance(branch_selection,dict):
   raise ValueError('BLOCKED_REFERENCE_BRANCH: explicit candidate imaging evidence required')
  from experiments.construct_validity.fidelity import validate_span,classify_record_assertion
  span=branch_selection.get('span',{});validate_span(protocol,span)
  if branch_selection.get('kind')!='EXPLICIT_IMAGING_MODALITY' or branch_selection.get('branch')!=branch:
   raise ValueError('BLOCKED_REFERENCE_BRANCH: selected branch evidence mismatch')
  if not re.search(r'light[- ]sheet|光片',span['quote'],re.I):
   raise ValueError('BLOCKED_REFERENCE_BRANCH: no light-sheet declaration in bound span')
  assertion=classify_record_assertion(protocol,span)
  if assertion.get('polarity')!='AFFIRMED' or assertion.get('scope')!='RECORD':
   raise ValueError('BLOCKED_REFERENCE_BRANCH: nonaffirmed or unresolved imaging statement')
 reqs=question_obligations(question)
 source_inventory=template['routes']['main']['sr_inventory'];inventory=copy.deepcopy(source_inventory)
 inventory.update(route_id=branch,inventory_id=f"q{question['question_id']}-{reference_key}-coverage-v1",coverage_scope='This question explicitly requests clearing, RI matching and storage/pre-imaging only; declared source-reference comparison, not sample/label applicability or experimental adequacy.')
 task={'schema_version':'fixed-task-evidence-v1','question_id':question['question_id'],'question':text,'cards':copy.deepcopy(template['cards']),'requirements':reqs,'routes':{branch:{'sr_inventory':inventory,'correctness_checks':{'co_method':[],'co_param':[],'co_order':[],'co_chem':[]},'parameter_requirements':[r['id'] for r in reqs],'submetrics':{}}},'metadata':{'status':'REUSED_REVIEWED_SOURCE_SAME_OUTPUT_SCOPE','question_object_sha256':json_hash(question),'scientific_truth':None,'expert_gold':False,'reference_key':reference_key,'explicit_reference_selection':True,'candidate_source_version_claimed':False,'sample_label_applicability':None,'source_template':lock,'reused_fields':['cards','reference_steps','required_stages','source_context_only'],'not_reused':['question obligations','candidate facts','matching matrix','scores','scientific correctness constraints'],'candidate_raw_modified':False,'branch_selection_evidence':copy.deepcopy(branch_selection)}}
 validate_task_evidence(task);projection=project_task_evidence(task,branch)
 if projection['inventory_evidence']['status']!='BOUND':raise ValueError('Reviewed source inventory failed original binding guards')
 assert all(projection['evidence_gates'][m]['status']=='UNRESOLVED' for m in ['co_method','co_param','co_order','co_chem'])
 return task,projection
