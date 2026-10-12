"""Narrow synthetic checks and one saved-source projection; no score or call."""
import copy,hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_dangling_target_label_view_v1 as h
import cce_grounded_extraction_v11 as g
import cce_posthoc_scoring_v3 as scorer
R2=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
OUT=R2/'dangling_target_label_view_v1/author_01'

def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def call(payload,doc):return h.convert_with_isolation(g.canonical(payload),doc,None,scorer.convert)
def main():
 checks=[]
 def check(name,ok):checks.append({'name':name,'pass':bool(ok)})
 def rejects(name,payload,doc):
  try:call(payload,doc)
  except Exception as exc:checks.append({'name':name,'pass':True,'error':str(exc)});return
  checks.append({'name':name,'pass':False})
 d,p=g.synthetic_fixture();before=copy.deepcopy(p)
 cv=call(p,d)
 check('valid_input_exact_original_conversion',cv==scorer.convert(g.canonical(p),d,None))
 bad=copy.deepcopy(p);bad['grounded_extraction']['relations'][0]['t']='undeclared_target'
 raw=g.canonical(bad);cv=call(bad,d);a=cv['dangling_target_label_view_v1']
 check('original_raw_and_wire_preserved',a['original_raw']==raw and a['original_wire_payload']==bad)
 check('only_target_status_ordinal_changed',all(a['changes'][0]['derived_record'][k]==bad['grounded_extraction']['relations'][0][k] for k in ['i','f','e','fo']))
 check('relation_stays_unknown',cv['source_audit']['resolved']['relations'][0]['status']=='unknown' and not cv['source_audit']['resolved']['relations'][0]['projection_allowed'])
 check('used_pair_stays_in_denominator',len(cv['label_occurrence_projection']['pairs'])==1 and cv['label_occurrence_projection']['pairs'][0]['marker_literal'] is None)
 check('original_failure_not_promoted',a['original_full_conversion_success'] is False and a['original_failure']['message']=='RELATION_DANGLING_ENTITY')
 check('original_scores_unchanged',cv['wire_payload']['scores']==bad['scores'])
 check('input_objects_unchanged',p==before and bad['grounded_extraction']['relations'][0]['t']=='undeclared_target')
 q=copy.deepcopy(bad);q['grounded_extraction']['relations'][0]['f']='undeclared_fluor';rejects('dangling_fluor_rejected',q,d)
 q=copy.deepcopy(bad);q['grounded_extraction']['source_id']='WRONG';rejects('wrong_source_rejected',q,d)
 q=copy.deepcopy(bad);q['grounded_extraction']['relations'].append(copy.deepcopy(q['grounded_extraction']['relations'][0]));rejects('duplicate_relation_still_rejected',q,d)
 q=copy.deepcopy(bad);q['grounded_extraction']['entities'][0]['n']='MISSING_NAME';rejects('bad_name_still_rejected',q,d)
 # A good relation remains supported when a separate dangling relation is
 # retained unknown. No graph-wide deletion and no target propagation.
 q=copy.deepcopy(p);r=copy.deepcopy(bad['grounded_extraction']['relations'][0]);r['i']='relation2';q['grounded_extraction']['relations'].append(r)
 cc=call(q,d);rr=cc['source_audit']['resolved']['relations']
 check('valid_pair_retained_beside_unknown',rr[0]['projection_allowed'] and not rr[1]['projection_allowed'] and len(cc['label_occurrence_projection']['pairs'])==2)
 # Explicit chosen-native source is independent of a dangling target.
 text=d['text'].replace('SYNTHETIC_FLUOR_101-labeled SYNTHETIC_TARGET','Chosen Labeling: [REPORTER_A (endogenous)]')
 nd=g.document(text,d['source_id']);np=copy.deepcopy(p);e=np['grounded_extraction']
 e['entities']=[{'i':'E1','n':'REPORTER_A','a':0,'u':'L0002','k':'fluorophore','s':'used'}]
 e['relations']=[{'i':'R1','f':'E1','t':'undeclared_target','e':'L0002','s':'explicit','fo':0,'to':0}]
 e['intrinsic_signals']=[{'i':'I1','e':'E1','u':'L0002','s':'source_declared'}]
 nc=call(np,nd)
 check('valid_native_retained_beside_unknown',any(x['kind']=='source_native_identity_encoding' for x in nc['label_occurrence_projection']['pairs']) and any(x['marker_literal'] is None for x in nc['label_occurrence_projection']['pairs']))
 save(OUT/'software_checks.json',{'checks':checks,'passed':sum(x['pass'] for x in checks),'total':len(checks)})
 if not all(x['pass'] for x in checks):raise AssertionError([x['name'] for x in checks if not x['pass']])
 rows=read(R2/'secondary_E5_posthoc_analysis_v1/actual_v3_01/per_answer.json')
 row=next(x for x in rows if x['anonymous_answer_id']=='FPC16')
 dp=Path(row['source_document']['path']);rp=Path(row['raw_response']['path'])
 source=read(dp);raw=rp.read_bytes().decode('utf8')
 assert sha(dp)==row['source_document']['sha256'] and sha(rp)==row['raw_response']['sha256']
 actual=h.convert_with_isolation(raw,source,None,scorer.convert)
 save(OUT/'FPC16.json',{'original_status':row['status'],'original_full_conversion_success':row['posthoc_full_conversion'],
  'source_document':row['source_document'],'raw_response':row['raw_response'],
  'isolation':actual['dangling_target_label_view_v1'],
  'label_projection':actual['label_occurrence_projection'],'score_recomputed':False,
  'dependency_view_conversion_succeeded':True,'original_full_status_promoted':False})
 result={'status':'pass','module_sha256':sha(h.__file__),'software_checks':len(checks),
  'actual_projection':'FPC16','original_full_conversion_success':False,
  'actual_dependency_view_succeeded':True,'new_scores':0,'new_model_calls':0,
  'command':'python scripts/cce_probe_dangling_target_label_view_v1.py'}
 save(OUT/'summary.json',result);print(json.dumps(result,ensure_ascii=True))
if __name__=='__main__':main()
