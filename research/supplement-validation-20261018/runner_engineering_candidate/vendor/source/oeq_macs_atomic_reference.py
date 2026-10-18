"""Hash-locked mechanical MACS R0/R1/R2 source provider, no scoring change.

DERIVED remains DERIVED. Only the three independently reviewed serial source
occurrences are admitted; arbitrary derived reference prose stays excluded.
"""
from copy import deepcopy
import hashlib,json
from pathlib import Path
from oeq_simple_representation import operation_record,from_catalog
from oeq_atomic_alignment import execution_status
KEY='macs-original2020-serial-three-v1'
HOME=Path(__file__).resolve().parent/'experiments/real_multiroute_q157_prepare_20261015'
TASK_SHA='3f2dbb0e0d721780b2dae008b10bb6b62f6c320c9b9f5c546c3a8176745fe3ce'

def _template():
    from experiments.full_batch_reference_binding_20261015.reference_binding import verified_template
    _,template,registry_lock=verified_template(KEY)
    if registry_lock['task_file_sha256']!=TASK_SHA:raise ValueError('MACS source task changed')
    card=template['cards'][0];doc=card['source_document'];text=doc['text']
    if hashlib.sha256(text.encode()).hexdigest()!=doc['sha256']:raise ValueError('MACS source text hash changed')
    for p in card['passages']:
        if text[p['start']:p['end']]!=p['quote']:raise ValueError('MACS source passage mismatch')
    return template,{'task_sha256':TASK_SHA,'review_sha256':registry_lock['review_file_sha256'],'source_sha256':doc['sha256']}

def source_reference():
    template,lock=_template();card=template['cards'][0];parent=next(x for x in card['passages'] if x['id']=='serial_r0_r1_r2');rows=[]
    source={'start':parent['start'],'end':parent['end'],'quote':parent['quote'],'text_sha256':card['source_document']['sha256'],'url':card['identity']['url']}
    for i,(ref,name) in enumerate(zip(template['routes']['main']['sr_inventory']['reference_steps'],['MACS‐R0','MACS‐R1','MACS‐R2']),1):
        expected=f'Fixed samples were incubated in 20–30 mL {name} solution in 50 mL conical tubes with gentle shaking.'
        if ref['text_origin']!='DERIVED' or ref['text']!=expected or name not in parent['quote']:raise ValueError('MACS occurrence differs from mechanical source expansion')
        row=operation_record(ref['text'],record_id=ref['reference_step_id'],phase=ref['stage_id'],source=source)
        row.update(text_origin='DERIVED',parent_record_id='serial_r0_r1_r2',occurrence_index=i,occurrence_count=3,source_passage_ids=['serial_r0_r1_r2'],admission='EXACT_SOURCE_LOCKED_MECHANICAL_SERIAL_EXPANSION')
        rows.append(row)
    return {'operations':rows,'source_sha256':lock['source_sha256'],'reference_id':KEY,'scope':'Three sequential original reagent treatments; no invented times/storage or scientific necessity'}

def bind_source(question,assessment):
    from oeq_task_evidence import project_task_evidence
    from experiments.full_batch_reference_binding_20261015.reference_binding import question_obligations
    template,_=_template();branches=assessment['method_identity'].get('branches',{})
    if assessment['method_identity'].get('status')!='SATISFIED' or len(branches)!=1 or next(iter(branches.values()))!=['MACS']:raise ValueError('MACS provider requires one validated MACS route')
    route=next(iter(branches));task=deepcopy(template);task['question_id']=question['question_id'];task['question']=question['question'];task['requirements']=question_obligations(question)
    entry=task['routes'].pop('main');entry['sr_inventory']['route_id']=route;entry['parameter_requirements']=[r['id'] for r in task['requirements']];task['routes']={route:entry}
    return project_task_evidence(task,route)

def check_source(question,assessment,evidence,key):
    if key!=KEY:raise ValueError('Unsupported MACS source key')
    if evidence!=bind_source(question,assessment):raise ValueError('MACS task/reference reconstruction mismatch')
    source_reference();_,lock=_template()
    return {'reference_key':KEY,'source_template_lock':lock,'metric_contract':'UNCHANGED_CONTINUOUS_RAW_COSINE_SR_SP','scientific_certified':False}

def paired(protocol,context,assessment,evidence):
    check_source(context['question_meta'],assessment,evidence,KEY)
    candidate=from_catalog(protocol,context['source_record_catalog'],assessment['extraction']);excluded=[];kept=[]
    for row in candidate['operations']:
        (kept if execution_status(row)=='ASSERTED_OPERATION' else excluded).append(row)
    candidate['operations']=kept;candidate['excluded_nonexecution']=excluded
    return {'candidate':candidate,'reference':source_reference(),'consumer_version':KEY,'metric_contract':'UNCHANGED_CONTINUOUS_RAW_COSINE_SR_SP','scope':'Literal source operations with source-bound conditional execution excluded; candidate wording retained'}
