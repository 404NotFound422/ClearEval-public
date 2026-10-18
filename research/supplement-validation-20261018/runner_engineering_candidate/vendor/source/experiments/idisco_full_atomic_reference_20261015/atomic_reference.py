"""Experimental source-backed treatment occurrences; never imported by production.

Atomization is symmetric: an explicit serial series/repeat is expanded, a reagent
mixture is not. Total group time is not copied into per-occurrence duration.
Scope selection is explicit and precedes embedding; no score-driven selection.
"""
from copy import deepcopy
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from oeq_simple_representation import operation_record, normalize_units
HERE=Path(__file__).resolve().parent
VERSION='idisco-dec2016-atomic-occurrence-v1-diagnostic'
URL='https://idisco.info/wp-content/uploads/2015/04/whole-mount-staining-bench-protocol-methanol-dec-2016.pdf'
PHASES={'pretreatment','immunolabeling','clearing','ri_matching_storage'}
SCOPES={'requested_clearing':{'clearing','ri_matching_storage'},'supplemental_full_answer':PHASES}

def atomize(group, *, repeat_count=None):
    """Shared declarative expansion, used for both source and candidate groups.

    repeat_range requires a caller's explicit versioned scenario. Resolved rows
    preserve range and scenario; the caller must report alternatives, not optimize.
    """
    g=deepcopy(group)
    if 'repeat_range' in g:
        lo,hi=g['repeat_range']
        if repeat_count is None or not lo <= repeat_count <= hi:
            raise ValueError('Explicit repeat scenario required within source range')
        count=repeat_count
    else: count=g.get('repeat',1)
    treatments=g.get('serial_treatments') or [g['treatment']]*count
    rows=[]
    for i,t in enumerate(treatments,1):
        suffix=''
        if g.get('temperature'): suffix+=' (Temperature: '+g['temperature']+')'
        if g.get('duration_each'): suffix+=' (Time: '+g['duration_each']+')'
        r=operation_record(t,record_id=f"{g['id']}.{i:02d}",phase=g['phase'],source=g.get('source'))
        r['raw_text']=t+suffix
        for key, field in [('temperature','temperature'),('time','duration_each')]:
            if g.get(field): r['parameters'][key]={'raw':g[field],'normalized':normalize_units(g[field])}
        if r['parameters']: r['scoring_text']+=' | '+'; '.join(k+': '+v['normalized'] for k,v in r['parameters'].items())
        r.update(comparison_phase=g['phase'],operation_role=g['role'],parent_group_id=g['id'],occurrence_index=i,
                 occurrence_count=len(treatments),normalization='EXPLICIT_SERIAL_TREATMENT_EXPANSION',
                 group_parameters=deepcopy(g.get('group_parameters',{})),
                 source_repeat_range=g.get('repeat_range'),repeat_scenario=repeat_count if 'repeat_range' in g else None)
        if g.get('shared_annotations'): r['shared_annotations']=deepcopy(g['shared_annotations'])
        rows.append(r)
    return rows

def _source_groups():
    text=(HERE/'source/idisco_dec2016_raw.txt').read_text()
    sections={}
    for name,start,end in [('p','Sample Pretreatment with Methanol','Alternative Pretreatment'),('i','Immunolabeling','Can store in'),('c','\nClearing\n','\nImaging\n')]:
        a=text.index(start); b=text.index(end,a+len(start)); fragment=text[a:b]
        matches=list(re.finditer(r'^([0-9]+)\. ',fragment,re.M))
        for j,m in enumerate(matches):
            x=a+m.start(); y=a+(matches[j+1].start() if j+1<len(matches) else len(fragment))
            sections[(name,int(m[1]))]={'start':x,'end':y,'quote':text[x:y].rstrip(),'page':3 if name=='c' else 2,
                'url':URL,'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
    groups=[]
    def add(id,phase,role,treatment='',**kw):
        section,num=id.split('-')[:2]
        groups.append(dict(id='REF-'+id,phase=phase,role=role,treatment=treatment,source=sections[(section,int(num))],**kw))
    add('p-1','pretreatment','dehydration',serial_treatments=[f'Dehydrate with {x}% methanol/H2O.' for x in (20,40,60,80,100)],duration_each='1h')
    add('p-2','pretreatment','methanol_wash','Wash with 100% methanol.',duration_each='1h')
    add('p-2-chill','pretreatment','chilling','Chill the sample in the current methanol solution.',temperature='4 °C')
    add('p-3','pretreatment','mixed_solvent_exchange','Incubate in 66% DCM / 33% Methanol with shaking.',temperature='RT',duration_each='Overnight')
    add('p-4','pretreatment','methanol_wash','Wash in 100% Methanol.',temperature='RT',repeat=2)
    add('p-4-chill','pretreatment','chilling','Chill the sample in the current methanol solution.',temperature='4 °C')
    add('p-5','pretreatment','bleaching','Bleach in chilled fresh 5% H2O2 in methanol (1 volume 30% H2O2 to 5 volumes MeOH).',temperature='4 °C',duration_each='overnight')
    add('p-6','pretreatment','rehydration',serial_treatments=[f'Rehydrate with {x}% methanol/H2O.' for x in (80,60,40,20)]+['Rehydrate with PBS.'],duration_each='1h',temperature='RT')
    add('p-7','pretreatment','detergent_wash','Wash in PTx.2.',repeat=2,temperature='RT',duration_each='1h')
    add('i-1','immunolabeling','permeabilization','Incubate samples in Permeabilization Solution.',temperature='37 °C',duration_each='n/2 days (max. 2 days)')
    add('i-2','immunolabeling','blocking','Block in Blocking Solution.',temperature='37 °C',duration_each='n/2 days (max. 2 days)')
    add('i-3','immunolabeling','primary_labeling','Incubate with primary antibody in PTwH/5% DMSO/3% Donkey Serum.',temperature='37 °C',duration_each='n days')
    add('i-4','immunolabeling','primary_wash','Wash in PTwH.',repeat_range=[4,5],group_parameters={'time':'until the next day','scope':'ENTIRE_REPEAT_GROUP','per_occurrence_time':'UNSPECIFIED'})
    add('i-5','immunolabeling','secondary_labeling','Incubate with secondary antibody in PTwH/3% Donkey Serum.',temperature='37 °C',duration_each='n days')
    add('i-6','immunolabeling','secondary_wash','Wash in PTwH.',repeat_range=[4,5],group_parameters={'time':'until the next day','scope':'ENTIRE_REPEAT_GROUP','per_occurrence_time':'UNSPECIFIED'})
    add('c-1','clearing','dehydration',serial_treatments=[f'Dehydrate in {x}% methanol/H2O.' for x in (20,40,60,80,100,100)],temperature='RT',duration_each='1hr',group_parameters={'optional_after_series':'Can be left optionally overnight at RT at this point.','scope':'AFTER_SERIES_NOT_EACH_OCCURRENCE'})
    add('c-2','clearing','mixed_solvent_exchange','Incubate in 66% DCM / 33% Methanol with shaking.',temperature='RT',duration_each='3H')
    add('c-3','clearing','pure_solvent_wash','Incubate in 100% DCM with shaking to wash the MeOH.',repeat=2,duration_each='15 minutes')
    add('c-4','ri_matching_storage','ri_matching','Incubate in DiBenzyl Ether (DBE) without shaking.',shared_annotations=['The tube should be filled almost completely with DBE to prevent oxidation.','Before imaging, invert the tube a couple of times to finish mixing.'])
    for g in groups:
        if g['phase']=='immunolabeling':g['shared_annotations']=['Perform all steps in closed tubes. Fully fill tubes to prevent oxidation.']
    return groups

def reference(repeat_count=4):
    groups=_source_groups(); rows=[]
    for g in groups: rows.extend(atomize(g,repeat_count=repeat_count if 'repeat_range' in g else None))
    return {'schema_version':VERSION,'operations':rows,'groups':groups,'repeat_scenario':repeat_count,
      'scope_boundary':'Fixed specimen; methanol pretreatment + immunolabeling + clearing. Sample collection/fixation excluded as already completed; no decalcification added.',
      'symbolic_duration':'n is specimen-dependent per source page 1. No universal seven-day value or numeric overnight conversion.',
      'buffer_definitions_source':{'url':URL+'#page=1','policy':'Named source buffers retained; not silently treated as separate reagent operations.'},
      'source_pdf':str(ROOT/'experiments/q6_fixed_task_evidence_20261014/source/idisco_dec2016.pdf')}

def candidate(pair_candidate):
    rows=[]; groups=[]
    for old in pair_candidate['operations']:
        h=old['phase'].lower();t=old['operation'];tl=t.lower(); raw=old['raw_text']
        if 'refractive' in h: phase='ri_matching_storage'
        elif 'dehydration and' in h:phase='clearing'
        elif 'immunolabel' in h or 'permeabilization' in h:phase='immunolabeling'
        elif 'pre-treatment' in h:phase='pretreatment'
        else:raise ValueError('Unmapped candidate phase; fail closed: '+h)
        role='unresolved'
        if phase=='ri_matching_storage': role='storage' if 'storage' in tl else 'ri_matching'
        elif 'h2o2' in tl:role='bleaching'
        elif 'permeabilization solution' in tl:role='permeabilization'
        elif 'blocking solution' in tl:role='blocking'
        elif 'primary antibody' in tl:role='primary_labeling'
        elif 'secondary antibody' in tl:role='secondary_labeling'
        elif 'wash with ptwh' in tl:role='primary_wash' if old['id']=='S017' else 'secondary_wash'
        elif '66%' in tl and ('dcm' in tl or 'dichloromethane' in tl):role='mixed_solvent_exchange'
        elif 'dcm' in tl:role='pure_solvent_wash'
        elif 'triton' in tl:role='detergent_wash'
        elif 'methanol' in tl:role='rehydration' if phase=='pretreatment' and 8<=int(old['id'][1:])<=12 else 'dehydration'
        elif 'pbs' in tl:role='rehydration'
        params=old['parameters'];g=dict(id=old['id'],phase=phase,role=role,treatment=t,source=old['source'])
        if 'temperature' in params:g['temperature']=params['temperature']['raw']
        repeat=re.search(r'with\s+(\d+)\s+solution changes',raw,re.I)
        if repeat:
            g['repeat']=int(repeat[1]);g['group_parameters']={'time':re.search(r'Time:\s*([^,)]+)',raw)[1],'scope':'ENTIRE_REPEAT_GROUP','per_occurrence_time':'UNSPECIFIED','interpretation':'N solution changes represented as N wash occurrences; initial-bath ambiguity retained.'}
        elif 'time' in params:g['duration_each']=params['time']['raw']
        groups.append(g);rows.extend(atomize(g))
    return {'schema_version':VERSION,'source_sha256':pair_candidate['source_sha256'],'operations':rows,'groups':groups,
      'phase_annotation_policy':'Reviewed Q13 heading map; roles are diagnostic labels, never embedding constraints. Not a general semantic parser.'}

def select_scope(pair,scope):
    if scope not in SCOPES:raise ValueError('Explicit supported scope required')
    phases=SCOPES[scope];out={'schema_version':VERSION,'comparison_scope':scope,'selected_phases':sorted(phases)}
    for side in ('candidate','reference'):
        source=pair[side];out[side]={**deepcopy(source),'operations':[deepcopy(r) for r in source['operations'] if r['comparison_phase'] in phases],
        'excluded_operations':[{'id':r['id'],'phase':r['comparison_phase'],'reason':'OUTSIDE_EXPLICIT_COMPARISON_SCOPE'} for r in source['operations'] if r['comparison_phase'] not in phases]}
    return out

def build():
    oldpath=next((ROOT/'experiments/practical_expanded_cohort_preselection_20261015/formal_results').rglob('q13_paired_representation.json'))
    old=json.loads(oldpath.read_text());cand=candidate(old['candidate'])
    for repeat in (4,5):
        ref=reference(repeat)
        (HERE/f'reference_full_wash{repeat}.json').write_text(json.dumps(ref,ensure_ascii=False,indent=2)+'\n')
        for scope in SCOPES:
            p=select_scope({'candidate':cand,'reference':ref},scope)
            (HERE/f'paired_{scope}_wash{repeat}.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
    (HERE/'candidate_atomic.json').write_text(json.dumps(cand,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':build()
