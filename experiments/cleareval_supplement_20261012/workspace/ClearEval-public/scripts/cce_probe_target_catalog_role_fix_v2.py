"""Real saved-pair zero witnesses and limited role/scope probes, no model calls."""
from pathlib import Path
import contextlib,copy,hashlib,io,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_target_catalog_role_fix_v2 as fix
import cce_grounded_offline_scoring_v1 as numeric
import cce_label_occurrence_diagnostic_v1 as labels
R2=ROOT/'artifacts/cce_validation/optimizer_round2_20261010'
OUT=R2/'target_catalog_role_fix_v2/actual_01'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
    runner,registry=numeric.runtime();targets={q:runner.QUESTION_META_KB[registry.questions[str(q)]['question_id']]['marker_query_targets'] for q in [2,21,22]}
    beforefiles=[bind(Path(runner.__file__)),bind(ROOT/'KnowledgeBase/tissue.json'),bind(ROOT/'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json')]
    checks=[]
    def check(name,ok,evidence=None):checks.append({'name':name,'pass':bool(ok),'evidence':evidence})
    original=runner._match_marker_to_targets('GFP',targets[21],fluor_name='GFP')
    with fix.using_target_catalog_fix(runner,targets[21]) as trace:new=runner._match_marker_to_targets('GFP',targets[21],fluor_name='GFP')
    check('authored_target_options_recover_existing_GFP_EGFP_alias',original is False and new is True,trace)
    original_expand=runner._expand_marker_candidates
    with fix.using_target_catalog_fix(runner,[]) as name_trace:
        runner._match_marker_to_targets('NeuroTrace 530/615',[],fluor_name='NeuroTrace 530/615')
        unchanged_expand=runner._expand_marker_candidates is original_expand
    check('ordinary_entity_slash_not_rewritten',unchanged_expand and name_trace['target_match_calls'][0]['marker']=='NeuroTrace 530/615' and name_trace['target_match_calls'][0]['option_targets']==[],name_trace)
    arbitrary={'marker_name':'SIGNAL_A / SIGNAL_B'}
    check('untyped_target_string_not_split',len(fix.target_options(arbitrary))==1)
    typed={'marker_name':'530 / 615','marker_slot':'recommended_marker_1','source_tissue_xlsx_row':1,'query_path':'virtual'}
    check('numeric_wavelength_not_target_options',len(fix.target_options(typed))==1)
    check('parenthesized_slash_not_split',len(fix.target_options({**typed,'marker_name':'SIGNAL (R / S)'}))==1)
    q2=fix.marker_scope_lookup(runner,'MAP2','Alexa Fluor 488',targets[2]);q21=fix.marker_scope_lookup(runner,'MAP2','Alexa Fluor 488',targets[21])
    check('q2_exact_authored_scope_MAP2',q2['value'] is True and q2['selected_row_indices']==[0],q2)
    check('q21_one_known_one_unknown_scope',q21['value'] is None and q21['status']=='applicable_scope_unknown',q21)
    neun488=fix.marker_scope_lookup(runner,'NeuN','Alexa Fluor 488',targets[2]);neun594=fix.marker_scope_lookup(runner,'NeuN','Alexa Fluor 594',targets[2])
    check('author_parenthetical_NeuN_alias',neun488['value'] is True and neun488['selected_row_indices']==[1],neun488)
    check('missing_AF594_column_stays_unknown',neun594['value'] is None and neun594['column'] is None,neun594)
    reporter=fix.marker_scope_lookup(runner,'GFP','GFP',targets[21])
    check('authored_KB_option_found_but_null_not_filled',reporter['selected_row_indices']==[93] and reporter['value'] is None and reporter['status']=='applicable_scope_unknown',reporter)
    # No new alias is created between different target choices.
    check('GFP_not_matched_to_DiO_only',not runner._match_marker_to_targets('GFP',[{**targets[21][-1],'marker_name':'DiO'}],fluor_name='GFP'))
    bad=copy.deepcopy(runner.TISSUE_KB);same=copy.deepcopy(bad[0]);same['AlexaFluor 488']=0;bad.append(same)
    originalrows=runner.TISSUE_KB;runner.TISSUE_KB=bad
    try:conflict=fix.marker_scope_lookup(runner,'MAP2','Alexa Fluor 488',targets[2])
    finally:runner.TISSUE_KB=originalrows
    check('same_scope_conflict_not_max',conflict['value'] is None and conflict['status']=='conflicting_authored_values_unresolved',conflict)
    # Each selected scope must independently support the same value. A second
    # known scope is not itself a reason to throw away evidence.
    for cells,expected,status in [([1,1],True,'all_applicable_scopes_have_same_authored_value'),([0,0],False,'all_applicable_scopes_have_same_authored_value'),([0,1],None,'applicable_scopes_disagree'),([1,None],None,'applicable_scope_unknown')]:
        synthetic=[];requested=[]
        for i,value in enumerate(cells):
            r=copy.deepcopy(originalrows[0]);r['结构/细胞类型']='SYNTHETIC_SCOPE_'+str(i);r['AlexaFluor 488']=value;synthetic.append(r)
            requested.append({**targets[2][1],'structure_or_cell_subtype':r['结构/细胞类型']})
        runner.TISSUE_KB=synthetic
        try:tested=fix.marker_scope_lookup(runner,'MAP2','Alexa Fluor 488',requested)
        finally:runner.TISSUE_KB=originalrows
        check('cross_scope_'+str(cells),tested['value'] is expected and tested['status']==status,tested)
    # Actual preserved projections, not new extraction/model claims.
    source=R2/'secondary_E5_confirmation_v1';matrix=read(source/'matrix.json');cases=read(source/'cases.json')['cases'];witnesses=[]
    for aid in ['FPC12','FPC13','FPC14','FPC15']:
        row=next(r for r in matrix if r['anonymous_answer_id']==aid);case=next(c for c in cases if c['anonymous_answer_id']==aid)
        attempt=source/'run/attempts'/(row['planned_trial_id']+'_1');archived=read(attempt/'component_result.json')
        if aid=='FPC15':
            cvpath=R2/'name_concentration_boundary_v1/actual_01/candidate_conversion.json';numpath=R2/'name_concentration_boundary_v1/actual_01/candidate_numeric.json';cv=read(cvpath);oldnum=read(numpath)
        else:cvpath=attempt/'component_result.json';numpath=cvpath;cv=archived['conversion'];oldnum=archived['numeric']
        projection=cv['label_occurrence_projection'];target=targets[case['question_id']]
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            value=fix.score_label_occurrences(labels.score_label_occurrences,projection,runner,oldnum['quantitative_data'],oldnum['user_preference_vector'],target)
        components=copy.deepcopy(oldnum['component_numeric_proposals']);components['s_label']=value['s_label'];newmetrics=numeric.derive(components,row['step'],True)
        witnesses.append({'anonymous_answer_id':aid,'question_id':case['question_id'],'projection_source':bind(cvpath),'numeric_source':bind(numpath),
          'original_frozen_fw3_metrics':archived['metrics'],'pre_target_fix_metrics':oldnum['metrics'],'candidate_metrics':newmetrics,
          'pre_target_fix_label_calculation':oldnum['occurrence_label_calculation'],'candidate_label_calculation':value,
          'source_or_raw_rewritten':False,'FPC15_includes_prior_SDS_boundary_fix':aid=='FPC15'})
        assert all(newmetrics[k]==oldnum['metrics'][k] for k in ['c_param','co_order','co_method','co_param','co_chem','sr','sp'])
    check('actual_zero_can_become_unknown_not_forced_finite',any(w['pre_target_fix_metrics']['s_label']==0 and w['candidate_metrics']['s_label'] is None for w in witnesses),
      [{'id':w['anonymous_answer_id'],'before':w['pre_target_fix_metrics']['s_label'],'after':w['candidate_metrics']['s_label']} for w in witnesses])
    assert all(c['pass'] for c in checks)
    assert beforefiles==[bind(x['path']) for x in beforefiles]
    summary={'status':'posthoc_data_access_candidate_tested','checks':len(checks),'passed':sum(c['pass'] for c in checks),'actual_witnesses':len(witnesses),
      'new_model_requests':0,'new_extraction_calls':0,'formula_changed':False,'KB_changed':False,'production_activated':False,
      'code_bindings':[bind(Path(__file__)),bind(fix.__file__),bind(labels.__file__)],
      'original_file_bindings':beforefiles,'source_case_metadata':bind(source/'cases.json'),
      'actual_command':'python scripts/cce_probe_target_catalog_role_fix_v2.py'}
    save(OUT/'software_probes.json',checks);save(OUT/'zero_change_witnesses.json',witnesses);save(OUT/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=True))
if __name__=='__main__':main()
