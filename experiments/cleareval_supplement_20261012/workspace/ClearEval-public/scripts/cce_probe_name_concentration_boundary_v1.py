"""Isolated post-hoc FPC15 replay plus narrow boundary probes; zero requests."""
from pathlib import Path
import contextlib, hashlib, io, json, sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_name_concentration_boundary_v1 as fix
import cce_fieldwise_scoring_v3 as fw
g=fw.ground
sourcebase=fw.previous.previous.fieldwise_base
R2=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
SOURCE=R2/'secondary_E5_confirmation_v1'
OUT=R2/'name_concentration_boundary_v1'/'actual_01'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
    original=sourcebase.omitted_numeric_name_suffix;candidate=fix.bind_original(original)
    probes=[]
    for tail,expected in [(' 0.5%',False),(' 0.5 mM',False),(' 0.5 mg/mL',False),(' 10%',False),(' 647',True),(' 488 0.5%',True),(' 123 (clone)',True),(' 6470',True),(' 0.5',True),(' 2 hours',False)]:
        got=candidate(tail);probes.append({'kind':'suffix','source_suffix':tail,'old':original(tail),'new':got,'expected':expected,'pass':got==expected})
    oldhashes={str(Path(m.__file__)):sha(m.__file__) for m in [g,sourcebase,fw,fw.previous,fw.previous.previous]}
    oldfn=sourcebase.omitted_numeric_name_suffix;sourcebase.omitted_numeric_name_suffix=candidate
    try:
        for text,name,expected in [('Use SDS 0.5%.\n','SDS',True),('Use Alexa Fluor 647.\n','Alexa Fluor',False),('Use anti-RECEPTOR.\n','RECEPTOR',False),('Use DAPI.\n','PI',False),('Use REPORTER+.\n','REPORTER',False),('Use CLONE 123.\n','CLONE',False),('Use SDS 0.5%; also SDS 1%.\n','SDS',True)]:
            doc=g.document(text,'SRC_SYNTHETIC_BOUNDARY');unit=doc['units'][0];support=sourcebase.resolve({'unit_id':unit['unit_id']},doc)
            audit=sourcebase.name_occurrence_inventory(name,support,doc);got=bool(audit['complete_occurrences'])
            probes.append({'kind':'full_boundary','source':text,'literal_name':name,'new_inventory':audit,'expected_has_complete':expected,'pass':got==expected})
        assert all(x['pass'] for x in probes)
        matrix=read(SOURCE/'matrix.json');row=next(r for r in matrix if r['anonymous_answer_id']=='FPC15')
        cases=read(SOURCE/'cases.json')['cases'];case=next(c for c in cases if c['anonymous_answer_id']=='FPC15')
        attempt=SOURCE/'run/attempts'/(row['planned_trial_id']+'_1');rawpath=attempt/'raw_response.txt'
        raw=rawpath.read_bytes().decode('utf-8');docpath=SOURCE/'source_documents/FPC15.json';doc=read(docpath)
        old=read(attempt/'component_result.json');rawhash=hashlib.sha256(raw.encode()).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            cv=fw.convert(raw,doc,case);num=fw.score_conversion(case,cv,row['step'])
        entity=next(e for e in cv['source_audit']['resolved']['entities'] if e['id']=='E006')
        result={'status':'posthoc_candidate_replay_completed','original_status_preserved':True,'new_model_requests':0,
          'original_full_failure':old['full_conversion_or_scoring_failure'],'original_metrics':old['metrics'],
          'candidate_metrics':num['metrics'],'candidate_label_calculation':num['occurrence_label_calculation'],
          'candidate_bound_entity':entity,'raw_sha256':rawhash,'original_raw_sha256':old['raw_sha256'],
          'step_inputs':row['step'],'raw_changed':False,'source_changed':False,'formula_or_KB_changed':False,
          'activation_scope':'isolated subprocess dynamic helper substitution only; not activated in any frozen scorer',
          'source_bindings':[bind(rawpath),bind(docpath),bind(attempt/'component_result.json'),bind(SOURCE/'matrix.json'),bind(SOURCE/'cases.json')],
          'code_bindings':[bind(Path(__file__)),bind(fix.__file__)]+[bind(p) for p in oldhashes],
          'actual_command':'python scripts/cce_probe_name_concentration_boundary_v1.py'}
        assert rawhash==old['raw_sha256']
        assert num['metrics']['sr']==old['metrics']['sr'] and num['metrics']['sp']==old['metrics']['sp']
        assert all(num['metrics'][k]==old['metrics'][k] for k in ['c_param','co_order','co_method','co_param','co_chem'])
        save(OUT/'candidate_conversion.json',cv);save(OUT/'candidate_numeric.json',num);save(OUT/'result.json',result)
    finally:sourcebase.omitted_numeric_name_suffix=oldfn
    assert all(sha(p)==h for p,h in oldhashes.items())
    save(OUT/'software_probes.json',{'checks':len(probes),'passed':sum(x['pass'] for x in probes),'checks_details':probes,'frozen_source_bytes_unchanged':True})
    print(json.dumps({'checks':len(probes),'status':result['status'],'old_label':old['metrics']['s_label'],'new_label':num['metrics']['s_label'],'new_HV':num['metrics']['HV'],'new_model_requests':0},ensure_ascii=True))
if __name__=='__main__':main()
