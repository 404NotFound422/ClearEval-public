"""Boundary examples and archived-source conformance, without model calls."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public');BASE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_selected_label_source_v1 as c
import cce_scoped_midpoint_scorer_v1 as b

policy=b.read(BASE.parent/'typed_label_revision/policy_with_sources.json')
catalog=['C-FoS','Npas4 (IEGs)','β-III Tubulin (TUJ1)','Tuj1','NeuN (RBFOX3)','MAP2']
checks=[]
def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
def doc(text):
    units=[];pos=0
    for i,line in enumerate(text.splitlines(keepends=True)):
        units.append({'unit_id':f'L{i+1:04d}','start':pos,'end':pos+len(line),'text':line});pos+=len(line)
    return {'text':text,'units':units,'answer_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest()}
def parse(text):return c.extract(doc(text),policy,catalog)
def pairs(text):return [(r['fluorophore'],r['marker']) for r in parse(text)['relations']]

check('target_dye_not_antibody_identity',pairs('Chosen Labeling: [MAP2 + AF488]')==[('Alexa Fluor 488','MAP2')])
check('native_GFP_no_invented_marker',pairs('Chosen Labeling: [GFP (内源)]')==[('GFP','')])
check('amplification_GFP_is_still_explicit_target',pairs('Chosen Labeling: [GFP (内源)+AF488]')==[('Alexa Fluor 488','GFP')])
check('native_EGFP_direct_DAPI',pairs('Chosen Labeling: [EGFP (endogenous), DAPI]')==[('EGFP',''),('DAPI','')])
check('two_targets_one_dye_not_overwritten',pairs('Chosen Labeling: [NeuN + AF647, MAP2 + AF647]')==[('Alexa Fluor 647','NeuN'),('Alexa Fluor 647','MAP2')])
x=parse('Chosen Labeling: [β-III Tubulin (TUJ1) + Alexa Fluor (647)]')
check('TUJ1_authored_target_not_extra_clone',x['ready'] and len(x['relations'])==1 and x['relations'][0]['clone_identity_inferred'] is False)
check('parenthesized_wavelength',pairs('Chosen Labeling: [MAP2 + Alexa Fluor (647)]')==[('Alexa Fluor 647','MAP2')])
check('Chinese_chosen_header',parse('第1行（所选荧光/标记策略 + 透明方法）：[MAP2 + AF647, TO-PRO-3（核染）] + FDISCO')['ready'])
check('candidate_list_not_chosen',not parse('Candidate Labeling: [MAP2 + AF647]')['ready'])
check('negated_choice_not_selected',not parse('Not Chosen Labeling: [MAP2 + AF647]')['ready'])
check('or_is_not_unique_choice',not parse('Chosen Labeling: [MAP2 + AF488 or AF647]')['ready'])
check('optional_is_not_unconditional_choice',not parse('Chosen Labeling: [DAPI (optional)]')['ready'])
check('target_without_dye_does_not_invent_relation',not parse('Chosen Labeling: [MAP2, DAPI]')['ready'])
check('two_targets_unsplit_need_resolution',not parse('Chosen Labeling: [MAP2 + NeuN + AF647]')['ready'])
check('distinct_catalog_targets_not_assumed_aliases',not parse('Chosen Labeling: [c-Fos (Npas4) + AF647]')['ready'])
check('generic_AF_unique_actual_dye',pairs('Chosen Labeling: [MAP2 + Alexa Fluor]\n1.1 Incubate with Alexa Fluor 647 secondary antibody.')[0]==('Alexa Fluor 647','MAP2'))
check('example_alone_does_not_choose_dye',pairs('Chosen Labeling: [MAP2 + Alexa Fluor]\n1.1 Incubate with secondary antibody (e.g., Alexa Fluor 647).')[0]==('Alexa Fluor','MAP2'))
check('multiple_actual_dyes_do_not_choose_best',not parse('Chosen Labeling: [MAP2 + Alexa Fluor]\n1.1 Incubate with AF488 antibody.\n1.2 Incubate with AF647 antibody.')['ready'])
check('header_body_conflict_visible',not parse('Chosen Labeling: [MAP2 + AF488]\n1.1 Incubate with AF647 antibody.')['ready'])

canonical=b.read(BASE/'canonical32_03/results.json');historical=b.read(BASE/'archived67_03/results.json')
for name,rows in [('canonical',canonical),('historical',historical)]:
    for r in rows:
        if 'metrics' not in r:continue
        check(name+':no_finite_label_lost:'+r['cell_id'],not b.finite(r['baseline_metrics']['s_label']) or b.finite(r['metrics']['s_label']))
        check(name+':source_hash:'+r['cell_id'],b.bind(r['source_document']['path'])==r['source_document'])
        d=b.read(r['source_document']['path'])
        for relation in r['proposal']['relations']:
            for span in relation['source_spans']:b.verify_span(d['text'],span)
check('all_24_controlled_scores_exactly_preserved',all(not r['changes'] for r in canonical if r['cell_id'].startswith('R3E2')))
prior={r['cell_id']:r for r in b.read(BASE.parent/'semantic_source_revision/semantic_04/results.json')}
agreement=[]
for r in canonical:
    if r['cell_id'] not in ['R3C01__r0','R3C04__r0','R3C05__r0','R3C07__r0']:continue
    author=prior[r['cell_id']]['source_assisted_metrics']['s_label']
    check('source_assisted_label_score_concordance:'+r['cell_id'],r['metrics']['s_label']==author)
    agreement.append({'cell_id':r['cell_id'],'source_rule_s_label':r['metrics']['s_label'],'prior_assistant_source_s_label':author,
        'independent_reference':False,'relations':len(r['proposal']['relations'])})
output={'checks_passed':len(checks),'checks':checks,'prior_assistant_concordance':agreement,
    'synthetic_examples_not_real_observations':19,'new_model_calls':0,
    'development_conformance_not_independent_accuracy':True}
b.save(BASE/'validation.json',output)
print(json.dumps({k:v for k,v in output.items() if k not in ['checks','prior_assistant_concordance']},ensure_ascii=False))
