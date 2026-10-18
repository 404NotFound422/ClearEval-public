"""Explicit iDISCO+ clearing-only atomic consumer; no question or answer whitelist.

Only the exact hash-locked source occurrence inventory is admitted as DERIVED.
The version changes representation, not continuous SR/SP aggregation.
"""
from copy import deepcopy
import json
from oeq_atomic_source_projection import HOME,_locked
from oeq_atomic_alignment import VERSION,source_reference,candidate_from_records,pair_scope,execution_status
KEY='idisco-dec2016-atomic-clearing-v3'
SCOPE='requested_clearing'

def _expected(question,assessment):
    from experiments.full_batch_reference_binding_20261015.reference_binding import question_obligations
    from oeq_task_evidence import project_task_evidence
    _locked()
    branches=assessment['method_identity'].get('branches',{})
    if assessment['method_identity'].get('status')!='SATISFIED' or len(branches)!=1 or next(iter(branches.values()))!=['iDISCO+']:
        raise ValueError('Atomic clearing source requires one validated iDISCO+ route')
    route=next(iter(branches))
    frozen=json.loads((HOME/'requested_clearing_projection_v1.json').read_text())
    inventory=deepcopy(frozen['sr_inventory'])
    inventory.update(route_id=route,inventory_id=f"q{question['question_id']}:{KEY}",reference_id=KEY,
                     coverage_scope='EXPLICIT_REQUESTED_CLEARING_SOURCE_OCCURRENCES; no sample adequacy certification')
    requirements=question_obligations(question)
    task={'schema_version':'fixed-task-evidence-v1','question_id':question['question_id'],'question':question['question'],
          'cards':deepcopy(frozen['cards']),'requirements':requirements,'formula':deepcopy(frozen['formula']),
          'routes':{route:{'sr_inventory':inventory,'correctness_checks':{k:[] for k in ['co_order','co_method','co_param','co_chem']},
                           'parameter_requirements':[r['id'] for r in requirements],'submetrics':{}}}}
    evidence=project_task_evidence(task,route)
    # Independently verify every mechanical occurrence against the source template.
    references={r['id']:r for r in source_reference()['operations']}
    for row in inventory['reference_steps']:
        ref=references[row['reference_step_id']]
        if row['text_origin']!='DERIVED' or row['text']!=ref['raw_text'] or row['atomic_expansion']['source']!=ref['source']:
            raise ValueError('Atomic source occurrence differs from verified anchor')
    return evidence

def bind_source(question,assessment):
    return _expected(question,assessment)

def check_source(question,assessment,evidence,key):
    if key!=KEY:raise ValueError('Unsupported atomic consumer key')
    from oeq_task_evidence import validate_selected_task_evidence
    validate_selected_task_evidence(evidence)
    if evidence!=_expected(question,assessment):raise ValueError('Atomic source projection differs from exact versioned task/source reconstruction')
    return {'reference_key':KEY,'atomic_version':VERSION,'scope':SCOPE,'source_template_lock':_locked(),
            'metric_contract':'UNCHANGED_CONTINUOUS_RAW_COSINE_SR_SP; typed eligibility is separate diagnostic',
            'scientific_certified':False}

def paired(protocol,context,assessment,evidence):
    from oeq_simple_representation import from_catalog
    candidate=candidate_from_records(from_catalog(protocol,context['source_record_catalog'],assessment['extraction']))
    pair=pair_scope(candidate,source_reference(),SCOPE,method='iDISCO+')
    excluded=[];executed=[]
    for row in pair['candidate']['operations']:
        if execution_status(row)=='ASSERTED_OPERATION':executed.append(row)
        else:excluded.append(row)
    pair['candidate']['operations']=executed
    pair['candidate']['excluded_nonexecution']=excluded
    pair['candidate']['source_sha256']=candidate['source_sha256']
    pair['consumer_version']=KEY
    pair['official_score']=False # representation is not itself a score
    pair['coverage_policy']='LOCAL_UNKNOWN_SCOPE_RETAINED_IN_AUDIT; explicit nonexecution excluded; no whole-answer rejection'
    pair['metric_contract']='UNCHANGED_CONTINUOUS_RAW_COSINE_SR_SP'
    return pair
