"""Record the current assistant's source reading; this is NOT a new judge run.

Durations and roles below are transcribed decisions, with exact source spans.
The generic replay entry point only verifies and calculates these decisions.
"""
import copy
import argparse
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b

rows=b.read(OUT/'method_candidate_02/results.json')
byid={r['cell_id']:r for r in rows}
records=[]

def begin(cell):
    row=byid[cell+'__r0'];doc=b.read(row['source_document']['path'])
    docpath=Path(row['source_document']['path'])
    return {'cell_id':row['cell_id'],'question_id':row['question_id'],
        'answer_sha256':doc['answer_sha256'],'source_document':row['source_document'],
        'original_source_document':b.bind(docpath.parent.parent/'original_source_documents'/docpath.name),
        'source_mapping':b.bind(docpath.parent.parent/'source_mappings'/docpath.name),
        'semantic_author':'current assistant / source-assisted author analysis',
        'independent_evaluator':False,'expert_validated':False,'new_model_calls':0,
        'doc':doc,'relations':None,'operations':[], 'scenarios':[],
        'primary_scenario_id':None,'source_findings':[]}

def span(r,n):
    u=next(u for u in r['doc']['units'] if u['unit_id']==f'L{n:04d}')
    result={k:u[k] for k in ['unit_id','start','end']}
    result.update(quote=r['doc']['text'][u['start']:u['end']],answer_sha256=r['answer_sha256'])
    b.verify_span(r['doc']['text'],result)
    return result

def relation(r,fluor,marker,units,basis,**roles):
    return {'fluorophore':fluor,'marker':marker,'source_spans':[span(r,n) for n in units],
            'basis':basis,'roles':roles}

def op(r,n,role,bounds=None,count=1,note='',suffix='',options=None):
    oid=f'L{n:04d}'+suffix
    choices=options
    if choices is None and bounds is not None:
        choices={'reported':{'bounds_hours':list(bounds),'count':count,'basis':note or 'explicit source duration'}}
    result={'operation_id':oid,'role':role,'source_spans':[span(r,n)],'interpretation':note,
            'duration_options':choices or {}}
    r['operations'].append(result)
    return oid

def fixed(r,units,hours,role='core'):
    return [op(r,n,role,[hours,hours]) for n in units]

def excluded(r,units,reason):
    for n in units:op(r,n,'excluded',note=reason)

def selection(r):
    return [{'operation_id':o['operation_id'],'duration_option':next(iter(o['duration_options']))}
            for o in r['operations'] if o['role']=='core']

def scenario(r,ident,description,choices=None,omit=(),primary=False,label_relations=None):
    selected=selection(r)
    for s in selected:
        s['duration_option']=(choices or {}).get(s['operation_id'],s['duration_option'])
    selected=[s for s in selected if s['operation_id'] not in omit]
    result={'scenario_id':ident,'description':description,'selected_operations':selected,
            'omitted_core_operations':list(omit),'selection_uses_achieved_score':False}
    if label_relations is not None:result['label_relations']=label_relations
    r['scenarios'].append(result)
    if primary:r['primary_scenario_id']=ident

def finish(r):
    active={s['unit_id'] for o in r['operations'] for s in o['source_spans']}
    r['unit_review']=[{'source':span(r,int(u['unit_id'][1:])),
        'disposition':'operation_or_scope_decision' if u['unit_id'] in active else 'heading_label_or_explanatory_text'}
        for u in r['doc']['units']]
    r['annotation_scope']='All source units read; numerical scope is reported core incubation, not elapsed laboratory workflow.'
    del r['doc'];records.append(r)

# C01: keep literal spelling and separately retain normalization and repeat sensitivity.
r=begin('R3C01')
r['relations']=[
    relation(r,'Alexa Fluor 647','c-Fos',[2,3,24,28],
        'Chosen C-FoS/AF647 pair is corroborated by c-Fos primary and AF647 secondary in the same answer.',
        source_target_spellings=['C-FoS','c-Fos'],antibody_target='c-Fos',fluorophore='Alexa Fluor 647'),
    relation(r,'DAPI','',[2,32],'Direct nuclear stain; no antibody-target relation is applicable.')]
fixed(r,range(6,10),1)
repeat_options={
    'additional_twice':{'bounds_hours':[1,1],'count':3,'basis':'literal reading: initial incubation plus two repetitions'},
    'total_twice_sensitivity':{'bounds_hours':[1,1],'count':2,'basis':'alternative colloquial reading: two total incubations'}}
op(r,10,'core',options=copy.deepcopy(repeat_options),note='No repeat is silently deleted; two readings are retained.')
op(r,12,'core',[12,12],note='Explicit Time:12 hours accompanies overnight; 8 hours is only the old rubric default when no number is given.')
fixed(r,range(14,18),1)
op(r,18,'core',options=copy.deepcopy(repeat_options),note='PBS is the explicitly sequenced methanol-to-aqueous transition wash.')
excluded(r,[20,22,24,26,28,30,32],'Immunolabeling preparation/incubation, labeling wash or stain: excluded by original core-time scope.')
fixed(r,range(34,38),1)
op(r,38,'core',options=copy.deepcopy(repeat_options))
op(r,40,'core',[.5,.5],count=2,note='Initial incubation plus one explicitly repeated fresh exchange.')
op(r,42,'core',options={
    'original_step_setpoint':{'bounds_hours':[.5,.5],'count':1,
        'basis':'In original unsplit step 13.1 the Time:0.5 h field follows both RI and storage clauses; assign once to its timed RI incubation, consistent with 15–30 min.'},
    'range_only_sensitivity':{'bounds_hours':[.25,.5],'count':1,
        'basis':'Alternative scope interpretation attaches Time only to storage; then the preceding RI range contributes its midpoint.'}},
    note='The original parent step is read before resolving scope; no duplicate 0.5 h storage incubation is added.')
excluded(r,[43],'Store for imaging is a continuing condition. Its trailing field is retained with the original whole-step context, not counted twice.')
original=b.read(r['original_source_document']['path'])
parent=next(u for u in original['units'] if '13.1 Incubation with' in u['text'])
r['original_step_contexts']=[{'start':parent['start'],'end':parent['end'],
    'quote':original['text'][parent['start']:parent['end']],'unit_id':parent['unit_id'],
    'supports_operations':['L0042','L0043'],
    'finding':'Canonical segmentation split one numbered source step into two units, changing local Time-field proximity.'}]
scenario(r,'literal_additional_repeats','Literal initial+two repeats; explicit original-step RI setpoint assigned once.',primary=True)
scenario(r,'total_two_repeat_sensitivity','Same wording read as two total incubations at all three locations.',
         choices={f'L{n:04d}':'total_twice_sensitivity' for n in [10,18,38]})
scenario(r,'range_only_RI_sensitivity','Literal additional repeats; alternative field scope uses RI range midpoint.',
         choices={'L0042':'range_only_sensitivity'})
scenario(r,'range_and_total_two_sensitivity','Both alternative interpretations retained together.',
         choices={**{f'L{n:04d}':'total_twice_sensitivity' for n in [10,18,38]},'L0042':'range_only_sensitivity'})
r['source_findings']=['Primary is an explicit interpretation convention, not evidence that an experiment was performed.',
    'C-FoS/c-Fos identity is resolved locally from multiple source mentions; no global case-insensitive replacement is applied.']
finish(r)

# C02: illustrative dye selection and optional branch must both be explicit.
r=begin('R3C02')
fixed(r,range(6,12),1);op(r,13,'core',[12,12]);fixed(r,range(15,20),1)
excluded(r,[21,22,24,26,27,28,30,32,33,34],'Label preparation, primary/secondary incubation or routine labeling wash.')
fixed(r,range(36,42),1);fixed(r,[43,44,45],.5);fixed(r,[47,48],2)
op(r,50,'core',options={'unreported_transition':{'bounds_hours':None,'count':1,
    'basis':'The briefly rehydrate component has no separate duration; the 24 h belongs to DAPI incubation.'}},suffix='_transition')
op(r,50,'excluded',note='The explicitly stated 24 h DAPI staining duration is excluded.',suffix='_stain')
op(r,51,'core',options={'unreported_dehydration':{'bounds_hours':None,'count':1,
    'basis':'The repeated 80→100 methanol series does not specify all durations.'}},suffix='_dehydration')
op(r,51,'core',[5.5,5.5],suffix='_referenced_repeat',
    note='Referenced 10.1–11.2 exactly expands to 0.5+0.5+0.5+2+2 hours; source sequence overlap remains a caveat.')
excluded(r,[53],'Mounting/imaging or indefinite storage; no additional timed core incubation.')
example_relations=[
    relation(r,'Alexa Fluor 488','c-Fos',[24,30],'Conditional realization of the explicitly supplied e.g. secondary conjugate; not a confirmed unique dye choice.'),
    relation(r,'Alexa Fluor 647','NeuN (RBFOX3)',[2,24,30],'Conditional realization of the explicitly supplied e.g. secondary conjugate.')]
scenario(r,'omit_optional_stain_example_dyes','Omit optional section 12 and instantiate the two example AF conjugates.',
    omit=['L0050_transition','L0051_dehydration','L0051_referenced_repeat'],label_relations=example_relations)
scenario(r,'include_optional_stain_example_dyes','Include optional section 12 and its explicit return through clearing; incomplete transition durations remain unknown.',
    label_relations=example_relations+[relation(r,'DAPI','',[2,50],'Direct stain in the selected optional branch.')])
r['source_findings']=['The primary archived s_label=3 remains as its saved judgment, with example-dye ambiguity visible.',
    'No midpoint is taken for genuinely unreported durations. The complete omit-optional result is conditional.',
    'The command repeat steps 10.1–11.2 and prior to final DBE create ordering ambiguity; 40 h known subtotal is not a full optional-branch runtime.']
finish(r)

# C04: two targets share a dye; retain both pairs rather than overwrite a dict key.
r=begin('R3C04')
r['relations']=[
    relation(r,'Alexa Fluor 647','NeuN (RBFOX3)',[1,23,29],'Explicit chosen pair and matching primary/secondary context.'),
    relation(r,'Alexa Fluor 647','β-III Tubulin (TUJ1)',[1,24,29],'Second explicitly chosen target sharing AF647; retained as another relation.'),
    relation(r,'TO-PRO-3','',[1,34],'Direct nuclear stain; external antibody marker is inapplicable.')]
fixed(r,range(5,11),2);op(r,12,'core',[12,16]);fixed(r,range(14,19),1.5)
excluded(r,[20,21,23,24,26,27,29,31,32,34,35],'Immunolabeling preparation, incubation, stain or associated wash.')
fixed(r,range(37,41),1.5);fixed(r,[41,42],2)
op(r,44,'core',[3,3]);op(r,45,'core',[1.5,1.5],count=2)
op(r,47,'core',[3,3]);op(r,48,'core',[12,24])
excluded(r,[50],'Storage up to 1–2 weeks is retained as a continuing condition, not an initial clearing incubation.')
op(r,51,'core',[1,2],note='Fresh DBE exchange with prescribed 1–2 h equilibration before imaging is a real timed RI-conditioning operation.')
excluded(r,[52],'Image acquisition is excluded.')
scenario(r,'with_prescribed_preimaging_conditioning','All explicitly timed core treatments including the prescribed final fresh DBE equilibration.',primary=True)
scenario(r,'initial_RI_ready_scope','Scope sensitivity stopping at initial RI-ready endpoint, before the later pre-imaging equilibration.',omit=['L0051'])
r['source_findings']=['The chosen-method header is already repaired by the generic Chinese-header candidate.',
    'Reagent RI≈1.56 was mislabeled as sample-target RI in the saved extraction; original s_trans is a KB-based proxy and does not use this answer field.',
    'Labels specify target-fluor pairs; this does not validate clone identity, same-color separation, penetration or the old Cor=1.']
finish(r)

# C05: retain mutually exclusive timing branches, each with a midpoint if bounded.
r=begin('R3C05')
r['relations']=[
    relation(r,'EGFP','',[2,9,50],'Endogenous EGFP provides its own signal; no external marker pair is required.'),
    relation(r,'Alexa Fluor 647','MAP2',[10,17,19,50],'The e.g. in rationale is concretized by the actual AF647 secondary step and imaging channel.',
        antibody_target='MAP2',primary_antibody='anti-MAP2 rabbit polyclonal',carrier='donkey anti-rabbit secondary',fluorophore='Alexa Fluor 647')]
excluded(r,list(range(15,23)),'Pre-clearing label preparation, antibody incubation, label washes or PFA fixation.')
fixed(r,range(25,31),1);op(r,33,'core',[.5,.5])
op(r,34,'untimed_handling',note='Aspiration/transfer has no prescribed incubation; no invented zero-duration scientific measurement.')
op(r,37,'core',[2,2])
op(r,38,'core',options={
    'finite_range':{'bounds_hours':[4,6],'count':1,'basis':'Explicit 4–6 h alternative, midpoint 5 h.'},
    'overnight_default':{'bounds_hours':[8,8],'count':1,'basis':'Explicit overnight alternative mapped to 8 h by the original rubric; not an experimental measurement.'}})
op(r,39,'core',[4,4],note='Only if residual opacity remains; selected or omitted by the declared branch.')
excluded(r,[42,43,44,45],'Long-term storage and later inspection/maintenance; retained but outside initial core-time accumulation.')
op(r,48,'core',[.5,.5],note='Prescribed fresh DBE equilibration is included when evaluating through imaging-ready conditioning.')
excluded(r,[49,50,51,52],'Mounting, imaging or post-imaging storage, with no further timed core incubation.')
for variant in ['finite_range','overnight_default']:
    for extra in [False,True]:
        for scope in ['with_preimaging','initial_RI_ready']:
            omit=([] if extra else ['L0039'])+(['L0048'] if scope=='initial_RI_ready' else [])
            scenario(r,f'{variant}__extra_{int(extra)}__{scope}',
                f'{variant}; residual-opacity extra exchange={extra}; endpoint={scope}.',
                choices={'L0038':variant},omit=omit)
r['source_findings']=['No branch is selected according to its achieved score.',
    'All four source timing branches are presented; the second endpoint is scope sensitivity, not extra model evaluations.',
    'The answer’s FDISCO expansion and operating choices are preserved; a complete score is not scientific endorsement.']
finish(r)

# C07: typical range and explicit Time field are consistent, not a contradiction.
r=begin('R3C07')
r['relations']=[
    relation(r,'tdTomato','',[2,3],'Native fluorescent protein; no external marker pair.'),
    relation(r,'Alexa Fluor 647','β-III Tubulin (TUJ1)',[2,3,14,17],
        'The answer links the parenthesized TUJ1 designation to β-III Tubulin and supplies the exact AF647 secondary.',
        biological_target='β-III Tubulin / TUBB3',parenthetical_designation='TUJ1',
        confirmed_clone=None,
        source_antibody_claim='rabbit polyclonal; retained literally. TUJ1 can be used as a target/marker shorthand, so parentheses alone do not identify or contradict a specific clone.',
        terminology_source='https://www.ptglab.com/products/TUBB3-specific-Antibody-CL488-66375.htm')]
excluded(r,[7,9,10,12,14,15,17,18,19],'Fixative-removal or label-preparation wash, permeabilization/blocking, antibody incubations and label washes.')
fixed(r,range(21,26),1)
op(r,27,'core',options={
    'explicit_setpoint':{'bounds_hours':[1,1],'count':1,'basis':'Explicit Time:1 hour lies within the prose usually 30–60 minute range.'},
    'typical_range_sensitivity':{'bounds_hours':[.5,1],'count':1,'basis':'Sensitivity using the stated typical range instead of the explicit setpoint.'}})
op(r,29,'core',[2,2]);op(r,30,'core',[.5,.5])
excluded(r,[32,33],'Immediate imaging and optional storage are outside core incubation time.')
scenario(r,'explicit_setpoint','Use the explicitly supplied Time field, consistent with the described typical range.',primary=True)
scenario(r,'typical_range_sensitivity','Use the prose typical range midpoint as a sensitivity analysis.',choices={'L0027':'typical_range_sensitivity'})
r['source_findings']=['TUJ1 is used in the same parenthetical β-III Tubulin description; it is not evidence for a second independent biological target.',
    'TUJ1 can name a classic clone or be used as a TUBB3 marker shorthand. The manufacturer counterexample labels a TUBB3-specific/TUJ1 product with clone 1F8G10. Parentheses alone cannot establish clone identity or prove the source rabbit-polyclonal wording wrong.',
    'BABB and FDISCO identity/route issues remain visible in the unchanged answer and stored Cor.']
finish(r)

policy={'version':'source-assisted-semantic-ledger-v1.2-original-parent-context-and-target-shorthand',
    'authorship':'current assistant transcribed source decisions; not independent evaluator output and not expert return',
    'original_rubric':b.bind(ROOT/'prompts/eval_oeq_teacher_rubric.txt'),
    'source_input':b.bind(OUT/'method_candidate_02/results.json'),
    'duration_rules':[
        'Explicit reported numbers take precedence over an overnight default when both describe the same event.',
        'A consistent explicit Time setpoint is used; an accompanying typical range is retained as sensitivity.',
        'Finite numerical ranges use an arithmetic midpoint before scoring, with endpoint scores retained.',
        'Literal repeat twice means two additional repetitions for the declared primary convention; two total is retained as sensitivity.',
        'Antibody/stain/fixation/imaging/routine label-wash times are excluded under the original rubric.',
        'A prescribed fresh-medium RI equilibration is counted; long-term storage and unscheduled later maintenance are separate.',
        'Mutually exclusive branches remain conditional; no best-scoring branch is chosen.',
        'Truly unreported durations remain unknown; recorded partial subtotals are still reported.'
    ],'selection_uses_achieved_score':False,'new_model_calls':0,'expert_validated':False,
    'results':records}
b.save(args.out,policy)
b.save(args.out.with_suffix('.execution.json'),{'command':[sys.executable,*sys.argv],
    'entrypoint':b.bind(__file__),'output':b.bind(args.out),
    'records':len(records),'new_model_calls':0})
print({'records':len(records),'relations':sum(len(r['relations'] or []) for r in records),
       'operations':sum(len(r['operations']) for r in records),'scenarios':sum(len(r['scenarios']) for r in records)})
