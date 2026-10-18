"""Source-locked FDISCO occurrence provider for the existing atomic consumer.

English source and candidate wording are retained. This is a clearing/RI/storage
representation, not a new metric, label review, or method capability score.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from oeq_simple_representation import operation_record,from_catalog
from oeq_atomic_alignment import VERSION,candidate_from_records,pair_scope,execution_status,annotate
KEYS={f'fdisco2019-atomic-clearing-thf100x{n}-v3':n for n in (2,3)}
PRIMARY_KEY=next(iter(KEYS))
SOURCE=Path(__file__).resolve().parent/'experiments/fdisco_representation_pilot_20261014/source/fdisco_clearing_excerpt.txt'
SHA='35c9600df019b29483e752b96daae7276da0eab669106435b72c78722f51ac1d'
POLICY={'primary':'100% THF twice; selected a priori, independent of candidate/score',
        'sensitivity':'100% THF thrice; always report alongside primary; never maximize',
        'timing':'tissue/size-dependent table S1 unresolved; no per-step duration fabricated',
        'scope':'requested clearing, RI and storage only; labeling is separate excluded audit',
        'language':'English source/candidate retained; no translation or generated protocol'}

def _template():
    from experiments.full_batch_reference_binding_20261015.reference_binding import verified_template
    _,template,lock=verified_template('fdisco2019-clearing-storage')
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SHA:raise ValueError('FDISCO cached source changed')
    if template['cards'][0]['source_document']['text']!=SOURCE.read_text():raise ValueError('FDISCO template/source mismatch')
    return template,lock

def source_reference(key):
    if key not in KEYS:raise ValueError('Unsupported FDISCO atomic key')
    template,_=_template();card=template['cards'][0];passages={p['id']:p for p in card['passages']}
    n=KEYS[key];rows=[]
    specs=[('dehydration',v,'fdisco_02') for v in [50,70,80]+[100]*n]
    specs += [('ri-matching',None,'fdisco_03'),('storage',None,'fdisco_07')]
    for i,(stage,percent,pid) in enumerate(specs,1):
        p=passages[pid]
        if stage=='dehydration':
            water=' in dH2O' if percent<100 else ''
            text=f'Tissues were dehydrated with {percent}% (vol/vol) THF{water} (pH adjusted to 9.0 with triethylamine).'
        elif stage=='ri-matching':text=p['quote']
        else:text=p['quote'].replace('After FDISCO clearing, the tissues','The tissues')
        shared=['fdisco_04','fdisco_05','fdisco_06'] if stage!='storage' else []
        if stage!='storage':text+=' '+passages['fdisco_04']['quote']+' '+passages['fdisco_05']['quote']
        anchor={'start':p['start'],'end':p['end'],'quote':p['quote'],'text_sha256':SHA,'url':card['identity']['url']}
        r=operation_record(text,record_id=f'FD{i:02d}',phase=stage,source=anchor)
        r.update(comparison_phase='clearing' if stage=='dehydration' else 'ri_matching_storage',
                 strict_operation_roles=True,text_origin='DERIVED',occurrence_index=i if stage=='dehydration' else 1,
                 occurrence_count=3+n if stage=='dehydration' else 1,parent_record_id=pid,
                 source_passage_ids=[pid]+shared,stage_id=stage,
                 shared_condition_scope={'pH9':'THF only','4C_slight_shaking_dark':'dehydration and RI; storage has separate source condition'},
                 timing_status='TISSUE_SIZE_DEPENDENT_TABLE_S1_UNRESOLVED' if stage!='storage' else 'STORAGE_DURATION_UNSPECIFIED')
        rows.append(r)
    return {'schema_version':VERSION,'operations':annotate(rows,trusted_reference_phase=True),'policy':deepcopy(POLICY),'repeat_scenario':n,'source_sha256':SHA}

def bind_source(question,assessment,key):
    from experiments.full_batch_reference_binding_20261015.reference_binding import question_obligations
    from oeq_task_evidence import project_task_evidence
    branches=assessment['method_identity'].get('branches',{})
    if assessment['method_identity'].get('status')!='SATISFIED' or len(branches)!=1 or next(iter(branches.values()))!=['FDISCO']:
        raise ValueError('FDISCO source requires one validated FDISCO route')
    route=next(iter(branches));template,_=_template();inv=deepcopy(template['routes']['main']['sr_inventory'])
    inv.update(route_id=route,inventory_id=f"q{question['question_id']}:{key}",reference_id=key,coverage_scope=POLICY['scope'])
    old={r['stage_id']:r for r in inv['reference_steps']};rows=source_reference(key)['operations'];new=[]
    for r in rows:
        x=deepcopy(old[r['stage_id']]);x.update(reference_step_id=r['id'],text=r['raw_text'],text_origin='DERIVED',
            atomic_expansion={'source':r['source'],'occurrence_index':r['occurrence_index'],'occurrence_count':r['occurrence_count'],'source_passage_ids':r['source_passage_ids']})
        new.append(x)
    inv['reference_steps']=new
    for stage in inv['required_stages']:stage['reference_step_ids']=[r['id'] for r in rows if r['stage_id']==stage['stage_id']]
    requirements=question_obligations(question)
    task={'schema_version':'fixed-task-evidence-v1','question_id':question['question_id'],'question':question['question'],
          'cards':deepcopy(template['cards']),'requirements':requirements,
          'routes':{route:{'sr_inventory':inv,'correctness_checks':{k:[] for k in ['co_order','co_method','co_param','co_chem']},
                           'parameter_requirements':[r['id'] for r in requirements],'submetrics':{}}}}
    return project_task_evidence(task,route)

def check_source(question,assessment,evidence,key):
    from oeq_task_evidence import validate_selected_task_evidence
    validate_selected_task_evidence(evidence)
    if evidence!=bind_source(question,assessment,key):raise ValueError('FDISCO exact source/task reconstruction mismatch')
    _,lock=_template()
    return {'reference_key':key,'source_template_lock':lock,'source_sha256':SHA,'atomic_version':VERSION,'policy':POLICY,
            'metric_contract':'UNCHANGED_CONTINUOUS_RAW_COSINE_SR_SP','scientific_certified':False}

def paired(protocol,context,assessment,evidence,key):
    candidate=candidate_from_records(from_catalog(protocol,context['source_record_catalog'],assessment['extraction']))
    pair=pair_scope(candidate,source_reference(key),'requested_clearing',method='FDISCO')
    pair['candidate']['excluded_nonexecution']=[r for r in pair['candidate']['operations'] if execution_status(r)!='ASSERTED_OPERATION']
    pair['candidate']['operations']=[r for r in pair['candidate']['operations'] if execution_status(r)=='ASSERTED_OPERATION']
    pair['candidate']['source_sha256']=candidate['source_sha256'];pair['consumer_version']=key
    pair['policy']=deepcopy(POLICY);pair['metric_contract']='UNCHANGED_CONTINUOUS_RAW_COSINE_SR_SP'
    return pair
