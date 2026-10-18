"""Practical rubric recorded import through the existing staged CLI.

No model/encoder calls. All missing stages remain explicit, and a new contract
namespace separates these records from historical staged/canonical SR results.
"""
from copy import deepcopy
from marker_input_contract import generation_input_from_entry
import json
from pathlib import Path
from evaluation_contract import json_hash,sha256_file
from evaluator_integrity import parse_judge_object
from oeq_practical_scoring import VERSION as RUBRIC,validate_proposal,score_schema,effectiveness_from_canonical
from oeq_simple_representation import from_catalog,from_reference
from oeq_score_bounds import diagnostic_bounds
from oeq_exact_zero_aggregate import resolve_practical_exact_zero
from experiments.cce_completeness_revision_20261013.sr_completeness_adapter import metrics_from_matrix,score_completeness,compose_cce

VERSION='practical-staged-import-v1'


def _demand_binding(registry,questions,profile):
    return {'profile':profile,
        'selected_vectors_sha256':json_hash({str(q['question_id']):registry.get(q['question_id'],q['question']) for q in questions}),
        'registry_provenance':deepcopy(getattr(registry,'provenance',{}))}


def _paired_inventory(evidence,pair):
    inventory=deepcopy(evidence['sr_inventory'])
    inventory['inventory_id']+=':paired-literal-v1';inventory['reference_id']+=':source-operations-v1'
    kept={r['id']:r for r in pair['reference']['operations']}
    inventory['reference_steps']=[dict(r,text=kept[r['reference_step_id']]['scoring_text'])
        for r in inventory['reference_steps'] if r['reference_step_id'] in kept]
    for key in ['required_stages','required_transitions']:
        inventory[key]=[dict(r,reference_step_ids=[x for x in r['reference_step_ids'] if x in kept])
            for r in inventory[key] if any(x in kept for x in r['reference_step_ids'])]
    return inventory


def bind_source_operations(question,assessment,reference_key):
    """Bind a declared existing source template to literal task obligations.

    This does not introduce scientific constraints or require the candidate to
    claim the source's imaging branch. Only the source operations are compared.
    """
    from oeq_macs_atomic_reference import KEY as MACS_KEY, bind_source as bind_macs
    if reference_key==MACS_KEY:return bind_macs(question,assessment)
    from oeq_fdisco_atomic_reference import KEYS as FDISCO_KEYS, bind_source as bind_fdisco
    if reference_key in FDISCO_KEYS:return bind_fdisco(question,assessment,reference_key)
    from oeq_atomic_reference_v3 import KEY as GENERIC_ATOMIC_KEY, bind_source as bind_generic_atomic
    if reference_key==GENERIC_ATOMIC_KEY:return bind_generic_atomic(question,assessment)
    from oeq_atomic_source_projection import KEY as ATOMIC_KEY, bind_source
    if reference_key==ATOMIC_KEY:return bind_source(question,assessment)
    from experiments.full_batch_reference_binding_20261015.reference_binding import verified_template,question_obligations
    from oeq_task_evidence import project_task_evidence
    info,template,lock=verified_template(reference_key)
    branches=assessment['method_identity'].get('branches',{})
    if len(branches)!=1:raise ValueError('Select a single actual candidate route before source binding')
    route=next(iter(branches));requirements=question_obligations(question)
    inventory=deepcopy(template['routes']['main']['sr_inventory'])
    inventory.update(route_id=route,inventory_id=f"q{question['question_id']}-{reference_key}-practical-source-operations-v1",
        coverage_scope='Declared source-operation comparison only; no inferred imaging requirement or sample/label applicability certification')
    task={'schema_version':'fixed-task-evidence-v1','question_id':question['question_id'],'question':question['question'],
        'cards':deepcopy(template['cards']),'requirements':requirements,
        'routes':{route:{'sr_inventory':inventory,'correctness_checks':{k:[] for k in ['co_order','co_method','co_param','co_chem']},
            'parameter_requirements':[r['id'] for r in requirements],'submetrics':{}}}}
    evidence=project_task_evidence(task,route)
    _check_source(question,assessment,evidence,reference_key)
    return evidence


def _check_source(question,assessment,evidence,key):
    """Source operations comparison only, not imposing a source imaging branch.

    This revised source scope is explicit: derived explanatory/imaging-context
    rows are excluded by the shared representation and are not obligations.
    """
    from oeq_macs_atomic_reference import KEY as MACS_KEY, check_source as check_macs
    if key==MACS_KEY:return check_macs(question,assessment,evidence,key)
    from oeq_fdisco_atomic_reference import KEYS as FDISCO_KEYS, check_source as check_fdisco
    if key in FDISCO_KEYS:return check_fdisco(question,assessment,evidence,key)
    from oeq_atomic_reference_v3 import KEY as GENERIC_ATOMIC_KEY, check_source as check_generic_atomic
    if key==GENERIC_ATOMIC_KEY:return check_generic_atomic(question,assessment,evidence,key)
    from oeq_atomic_source_projection import KEY as ATOMIC_KEY, check_source
    if key==ATOMIC_KEY:return check_source(question,assessment,evidence,key)
    from oeq_task_evidence import validate_selected_task_evidence
    from experiments.full_batch_reference_binding_20261015.reference_binding import verified_template,question_obligations
    evidence=validate_selected_task_evidence(evidence)
    if evidence['question_id']!=question['question_id'] or evidence['question']!=question['question']:
        raise ValueError('Reference belongs to another original question')
    info,template,lock=verified_template(key);route=evidence['route_id']
    if assessment['method_identity'].get('status')!='SATISFIED' or assessment['method_identity'].get('branches')!={route:[info['method']]}:
        raise ValueError('Actual canonical method does not match selected source template')
    if evidence['cards']!=template['cards']:raise ValueError('Reference source text differs from reviewed template')
    if evidence['requirements']!=question_obligations(question):raise ValueError('Task obligations differ from original question')
    inv=evidence['sr_inventory'];expected=template['routes']['main']['sr_inventory']
    for field in ['reference_steps','required_stages','required_transitions','sources','reference_id']:
        if inv[field]!=expected[field]:raise ValueError('Source inventory differs from reviewed template: '+field)
    return {'reference_key':key,'source_template_lock':lock,
        'scope':'REPORTED_SOURCE_OPERATIONS_ONLY; no inferred required imaging modality, sample adequacy, or scientific certification'}


def _build_pair(protocol,context,assessment,evidence,reference_key):
    """One versioned pair constructor shared by prepare and import."""
    from oeq_macs_atomic_reference import KEY as MACS_KEY, paired as macs_pair
    if reference_key==MACS_KEY:return macs_pair(protocol,context,assessment,evidence)
    from oeq_fdisco_atomic_reference import KEYS as FDISCO_KEYS, paired as fdisco_pair
    if reference_key in FDISCO_KEYS:return fdisco_pair(protocol,context,assessment,evidence,reference_key)
    from oeq_atomic_reference_v3 import KEY as GENERIC_ATOMIC_KEY, paired as generic_atomic_pair
    if reference_key==GENERIC_ATOMIC_KEY:return generic_atomic_pair(protocol,context,assessment,evidence)
    from oeq_atomic_source_projection import KEY as ATOMIC_KEY, paired
    if reference_key==ATOMIC_KEY:return paired(protocol,context,assessment,evidence)
    return {'candidate':from_catalog(protocol,context['source_record_catalog'],assessment['extraction']),
            'reference':from_reference(evidence)}


def calculate_record(*,question,protocol,assessment,evidence,pair,step,inventory,proposal,
                     actual_raw,question_metadata,preferences,model_space,effectiveness_fn,
                     prompt_revision,source_audit):
    """Single production arithmetic path, after caller validates actual bindings."""
    from sample_scope_runtime import SCOPE
    scoped = SCOPE.unresolved(question)
    if scoped is not None:
        return scoped
    from integration_qualification import demand_status
    qualification = demand_status(question, preferences)
    effects,inputs=effectiveness_from_canonical(assessment,evidence,question_metadata,preferences,model_space,
        effectiveness_fn,protocol=protocol,review=proposal['label_review'])
    effects['s_method'].update(score_qualification=qualification['s_method_use'], demand_projection_status=qualification['projection_status'], scientific_certified=False)
    cp=deepcopy(proposal['scores']['completeness']['c_param'])
    if evidence['evidence_gates']['c_param']['status']!='BOUND':
        cp={'score':None,'missing_reason':'C_param evidence unbound'}
    com=score_completeness(step,cp['score'],inventory=inventory,c_param_missing_reason=cp.get('missing_reason'),c_param_provenance=step['provenance'])
    raw={k:v['score'] for k,v in proposal['scores']['correctness'].items()}
    raw.update({k:v['score'] for k,v in effects.items()});raw['c_param']=cp['score']
    corvals=[raw[k]/m if raw[k] is not None else None for k,m in [('co_order',3),('co_method',2),('co_param',2),('co_chem',1)]]
    effvals=[((raw[k]/m+1)/2 if k=='s_method' else raw[k]/m) if raw[k] is not None else None
        for k,m in [('s_method',2.5),('s_label',6),('s_trans',3),('s_time',3)]]
    cor=None if None in corvals else sum(corvals)/4;eff=None if None in effvals else sum(effvals)/4
    cce=compose_cce(com,correctness=cor,effectiveness=eff,
        correctness_missing_reason='Relevant Co component unknown' if cor is None else None,
        effectiveness_missing_reason='Relevant E component unknown' if eff is None else None)
    cce=resolve_practical_exact_zero(cce)
    # Arithmetic is unchanged; every aggregate carries the dependent diagnostic
    # qualification so a valid execution cannot be mistaken for scientific validation.
    cce['score_qualification'] = 'DIAGNOSTIC_UNVALIDATED'
    cce['scientific_certified'] = False
    cce['component_qualifications'] = {
        key: {field: deepcopy(effects[key].get(field)) for field in
              ('score_qualification', 'scientific_score_status', 'reference_evidence_status', 'display_label')}
        for key in ('s_time', 's_trans')}

    record={'schema_version':VERSION,'rubric_version':RUBRIC,'prompt_revision':prompt_revision,
        'question_id':question['question_id'],'technical_status':'VALID','status':'ACTUAL_JUDGE_AND_ENCODER_REPLAYED',
        'official_scores':None,'scientific_certified':False,'original_question':question,'original_protocol':protocol,
        'actual_score_raw':actual_raw,'score_proposal':proposal,'paired_representation':pair,'paired_inventory':inventory,
        'step_metrics':step,'effectiveness_scores':effects,'effectiveness_input':inputs,'raw_scores':raw,
        'calculated_scores':cce,'source_reference_audit':source_audit,'cli_teacher_calls':0,'cli_encoder_calls':0}
    record['demand_qualification'] = qualification
    record['calculated_scores']['demand_qualification'] = {k:qualification[k] for k in ('projection_status','s_method_use','aggregate_IA_use','scientific_certified')}
    try:record['bounds_diagnostic']=diagnostic_bounds(record)
    except (ValueError,KeyError,TypeError) as exc:
        record['bounds_diagnostic']={'status':'UNAVAILABLE','reason':str(exc),
            'reason_code':getattr(exc,'code','INVALID_DIAGNOSTIC_INPUT'),
            'input_field':getattr(exc,'field',None),
            'input_fields':getattr(exc,'fields',[]),'replaces_point_scores':False}
    return record


def _load_actual_item(question,entry,spec,*,runner,model_space,encoder,offset,source,output_schema,metric_ablation=None,matching_repair=None):
    from oeq_scientific import apply_assessment
    context=source(spec['canonical']['generation_context']);rawtext=source(spec['canonical']['raw'],json_value=False)
    if context['question_meta']!=question or context['protocol_sha256']!=__import__('hashlib').sha256(entry['model_response'].encode()).hexdigest():
        raise ValueError('Original question/answer differs from canonical generation context')
    c=spec['canonical']
    if c['actual_prompt_sha256']!=context['prompt_sha256'] or c['schema_sha256']!=json_hash(output_schema('canonical')):
        raise ValueError('Original canonical request/schema binding mismatch')
    if __import__('hashlib').sha256(context['prompt'].encode()).hexdigest()!=context['prompt_sha256']:
        raise ValueError('Canonical prompt bytes changed')
    assessment=apply_assessment(parse_judge_object(rawtext),context,entry['model_response'])
    canonical_replay={'mode':'CURRENT_VALIDATOR_REPLAY','derived_audit_drift':False}
    if 'recorded_assessment' in c:
        retained=source(c['recorded_assessment'])
        if (retained.get('canonical_proposal')!=parse_judge_object(rawtext)
                or retained.get('canonical_status')!='VALIDATED'
                or retained.get('protocol_sha256')!=context['protocol_sha256']):
            raise ValueError('Recorded canonical assessment does not bind original actual raw/protocol')
        frozen=retained['canonical_assessment']
        # The original judge bound this historical extraction, including its
        # derived audit flags. Preserve that exact input rather than silently
        # substitute a later validator's verdict for it.
        semantic=lambda a:{k:v for k,v in a['extraction'].items() if k not in {'field_audit','scoring_eligible'}}
        if semantic(frozen)!=semantic(assessment):
            raise ValueError('Historical and current canonical source facts differ')
        canonical_replay={'mode':'EXPLICIT_RECORDED_CANONICAL_ASSESSMENT',
            'derived_audit_drift':frozen['extraction']!=assessment['extraction'],
            'frozen_extraction_sha256':json_hash(frozen['extraction']),
            'current_extraction_sha256':json_hash(assessment['extraction']),
            'source_fields_identical':True,'raw_proposal_identical':True}
        assessment=frozen
    evidence=source(spec['reference']['projection'])
    source_audit=_check_source(question,assessment,evidence,spec['reference']['source_reference_key'])
    pair=source(spec['paired_representation'])
    rebuilt=_build_pair(entry['model_response'],context,assessment,evidence,spec['reference']['source_reference_key'])
    if rebuilt!=pair:raise ValueError('Paired representation differs from current shared source projection')
    scoretext=source(spec['score']['raw'],json_value=False)
    structured=spec.get('structured_judgment')
    if structured is not None:
        from oeq_structured_judgment import VERSION as STRUCTURED_VERSION, repair_request, replay
        if structured!=STRUCTURED_VERSION:raise ValueError('Unsupported structured judgment')
        proposal=parse_judge_object(scoretext)
    else:proposal=validate_proposal(parse_judge_object(scoretext),spec['score']['prompt_revision'])
    prompt=source(spec['score']['actual_prompt'],json_value=False)
    payload=parse_judge_object(prompt.split('\nSCORING_INPUT_JSON\n',1)[1])
    from oeq_practical_scoring import score_request
    expected_prompt=score_request(context,assessment,evidence,entry['model_response'],pair,
        prompt_revision=spec['score']['prompt_revision'], generation_input=generation_input_from_entry(entry))
    if structured is not None:expected_prompt,_=repair_request(expected_prompt)
    if prompt!=expected_prompt:raise ValueError('Actual score request differs from versioned template and complete bound source payload')
    binding={'canonical_extraction_sha256':json_hash(assessment['extraction']),
             'task_evidence_sha256':json_hash(evidence),'route_id':evidence['route_id'],
             'reference_id':evidence['reference_id'],'rubric_version':RUBRIC}
    for key,value in binding.items():
        if proposal[key]!=value or payload[key]!=value:raise ValueError('Actual score binding mismatch: '+key)
    if payload['question']!=question or payload['unchanged_protocol']!=entry['model_response'] or payload['paired_representation']!=pair:
        raise ValueError('Actual score prompt differs from original task/answer/pair')
    expected_schema=parse_judge_object(expected_prompt.split('\nSCORING_INPUT_JSON\n',1)[1])['score_output_schema']
    if payload['score_output_schema']!=expected_schema or spec['score']['schema_sha256']!=json_hash(expected_schema):
        raise ValueError('Score output schema changed')
    structured_audit=None
    if structured is not None:
        original_proposal=deepcopy(proposal)
        proposal,structured_audit=replay(proposal,payload)
        for block,key in [('completeness','c_param'),('correctness','co_method'),('correctness','co_param')]:
            if proposal['scores'][block][key]['score']!=original_proposal['scores'][block][key]['score']:
                raise ValueError('Raw/derived structured grade contradiction: '+key)
        structured_audit['raw_proposal']=original_proposal
        proposal.pop('parameter_slot_review');proposal.pop('correctness_attribution')
        proposal=validate_proposal(proposal,spec['score']['prompt_revision'])
    nr=len(pair['reference']['operations']);ng=len(pair['candidate']['operations'])
    matrix=[r[offset+nr:offset+nr+ng] for r in encoder['cosine_similarity'][offset:offset+nr]]
    if matrix!=source(spec['encoder']['matrix']):raise ValueError('Matrix differs from actual encoder output')
    inventory=_paired_inventory(evidence,pair)
    expected=source(spec['encoder']['step_metrics'])
    step=metrics_from_matrix(inventory,matrix,[r['id'] for r in pair['candidate']['operations']],provenance=expected['provenance'])
    if step!=expected:raise ValueError('SR/SP differs from actual matrix replay')
    archived_step=deepcopy(step)
    if matching_repair is not None:
        from oeq_capacity_matching import capacity_metrics
        if matching_repair=='identity-role-occurrence-presence-v2-20261015':
            from oeq_presence_matching import presence_metrics
            step=presence_metrics(inventory,matrix,pair,provenance=expected['provenance'])
        else:
            step=capacity_metrics(inventory,matrix,pair,provenance=expected['provenance'])
    record=calculate_record(question=question,protocol=entry['model_response'],assessment=assessment,evidence=evidence,
        pair=pair,step=step,inventory=inventory,proposal=proposal,actual_raw=scoretext,
        question_metadata=runner.QUESTION_META_KB[question['question_id']],preferences=runner.fixed_demands().get(question['question_id'],question['question']),
        model_space=model_space,effectiveness_fn=runner.calculate_effectiveness_score,
        prompt_revision=spec['score']['prompt_revision'],source_audit=source_audit)
    if matching_repair is not None:
        record['schema_version']=('practical-presence-matching-posthoc-v2' if matching_repair=='identity-role-occurrence-presence-v2-20261015' else 'practical-capacity-matching-candidate-v1')
        record['matching_repair']={'version':matching_repair,'archived_step_metrics':archived_step,
            'frozen_reference_sha256':json_hash(inventory),'frozen_pair_sha256':json_hash(pair),
            'frozen_matrix_sha256':json_hash(matrix),'judge_and_encoder_reused':True}
    if metric_ablation is not None:
        from oeq_metric_ablation import append_metric_ablation
        append_metric_ablation(record,matrix,metric_ablation)
    if structured_audit is not None:
        record['structured_judgment']=structured_audit
        record['schema_version']='practical-structured-criteria-v2-20261015'
    record['input_manifest_item']=deepcopy(spec)
    record['canonical_replay']=canonical_replay
    return record


def _practical_dependency_hashes():
    """Include score-input and formula contracts in immutable replay revisions."""
    from oeq_staged_assessment import dependency_hashes
    dependencies=dependency_hashes()
    for name in ['integration_qualification.py','requirement_facts.py','archived_annotations.json','demand_qualification.py','integration_archived_demands.json','sample_scope_runtime.py','oeq_score_lineage.py','oeq_effectiveness_data_lock.py','dataset/Q+AR/src/model_space_signed.json','oeq_fdisco_atomic_reference.py','oeq_atomic_reference_v3.py','oeq_atomic_alignment.py','oeq_atomic_source_projection.py','evaluation_contract.py','oeq_ri_reference.py','oeq_practical_assessment.py','oeq_practical_scoring.py','oeq_simple_representation.py','oeq_simple_time.py','oeq_score_bounds.py','oeq_exact_zero_aggregate.py','oeq_sample_marker_applicability.py','prompts/oeq_sample_marker_applicability_v4.txt','marker_input_contract.py','verified_marker_aliases.py']:
        dependencies[name]=sha256_file(Path(__file__).parent/name)
    for name in ['oeq_structured_judgment.py','oeq_fluor_lexical_identity.py','oeq_source_parameter_slots.py','source_parameter_contract.json']:
        dependencies[name]=sha256_file(Path(__file__).parent/name)
    return dependencies


async def evaluate_recorded_batch(manifest,*,runner,output_dir):
    from oeq_staged_assessment import validate_manifest,source,_atomic,dependency_hashes,MODE
    from oeq_sr_assessment import output_schema,_validate_encoder_output
    if manifest.get('rubric_revision')!=RUBRIC:raise ValueError('Unknown practical rubric revision')
    metric_ablation=None
    if 'metric_ablation' in manifest:
        from oeq_metric_ablation import validate_config
        metric_ablation=validate_config(manifest['metric_ablation'])
        if metric_ablation is None:raise ValueError('Explicit metric_ablation cannot be null')
    matching_repair=manifest.get('matching_repair')
    if 'matching_repair' in manifest:
        from oeq_capacity_matching import VERSION as MATCH_VERSION
        if matching_repair not in (MATCH_VERSION,'identity-role-occurrence-presence-v2-20261015'):raise ValueError('Unsupported matching_repair contract')
        if metric_ablation is not None:raise ValueError('Matching repair and old metric ablation cannot be combined')
    questions,entries,space=validate_manifest(manifest);qs={str(q['question_id']):q for q in questions}
    if manifest.get('practical_action') == 'prepare':
        return prepare_requests(manifest,questions,entries,output_dir=output_dir,source=source,atomic=_atomic,mode=MODE)
    if manifest.get('practical_action','import') != 'import':
        raise ValueError('practical_action must be prepare or import; model execution is external to this import boundary')
    from oeq_effectiveness_data_lock import validate as validate_effectiveness_data
    data_binding=validate_effectiveness_data(manifest.get('effectiveness_data_lock'),runner)
    ordered=manifest['practical_encoder']['question_order']
    if len(ordered)!=len(set(ordered)) or set(ordered)!=set(qs):raise ValueError('Encoder question order must match declared batch exactly')
    texts=[];offsets={}
    for q in ordered:
        pair=source(manifest['items'][q]['paired_representation']);offsets[q]=len(texts)
        texts += [r['scoring_text'] for r in pair['reference']['operations']]+[r['scoring_text'] for r in pair['candidate']['operations']]
    encoder=source(manifest['practical_encoder']['actual_output']);config=source(manifest['practical_encoder']['config'])
    _validate_encoder_output(encoder,texts,config)
    dependencies=_practical_dependency_hashes()
    if any(v.get('reference',{}).get('source_reference_key')=='macs-original2020-serial-three-v1' for v in manifest['items'].values()):
        for name in ['oeq_macs_atomic_reference.py','oeq_simple_representation.py','oeq_atomic_alignment.py','experiments/construct_validity/fidelity.py','experiments/construct_validity/compact_grounding.py','oeq_scientific.py']:
            dependencies[name]=sha256_file(Path(__file__).parent/name)
    if metric_ablation is not None:
        from oeq_metric_ablation import dependency_hashes as ablation_dependencies
        dependencies.update(ablation_dependencies())
    if matching_repair is not None:
        dependencies['oeq_capacity_matching.py']=sha256_file(Path(__file__).parent/'oeq_capacity_matching.py')
        if matching_repair=='identity-role-occurrence-presence-v2-20261015':
            dependencies['oeq_presence_matching.py']=sha256_file(Path(__file__).parent/'oeq_presence_matching.py')
    demand_binding=_demand_binding(runner.fixed_demands(),questions,getattr(runner,'DEMAND_PROFILE',None))
    contract={'mode':MODE,'schema':VERSION,'manifest_sha256':json_hash(manifest),'dependencies':dependencies,
              'demand_binding':demand_binding}
    revision=json_hash(contract);target=Path(output_dir)/MODE/revision;target.mkdir(parents=True,exist_ok=True)
    items=[] # Compute the complete batch in memory; publish only after the final data-lock check.
    for entry in entries:
        q=str(entry['question_id']);spec=manifest['items'].get(q,{})
        try:
            record=_load_actual_item(qs[q],entry,spec,runner=runner,model_space=space,encoder=encoder,offset=offsets[q],source=source,output_schema=output_schema,metric_ablation=metric_ablation,matching_repair=matching_repair)
        except (ValueError,TypeError,KeyError,OSError,AssertionError) as exc:
            record={'schema_version':VERSION,'question_id':entry['question_id'],'technical_status':'BLOCKED',
                'reason':str(exc),'input_manifest_item':deepcopy(spec),'cli_teacher_calls':0,'cli_encoder_calls':0,
                'official_scores':None,'scientific_certified':False}
        items.append({**entry,'evaluation':record})
    valid=[x['evaluation'] for x in items if x['evaluation']['technical_status']=='VALID']
    complete=[r for r in valid if r['calculated_scores']['IA'] is not None
              and all(r['calculated_scores'].get(k) is not None for k in ('Com','Cor','Eff'))]
    summary={'assessment_mode':MODE,'schema_version':VERSION,'rubric_revision':RUBRIC,'declared_questions':len(entries),
        'technical_valid_count':len(valid),'blocked_count':len(entries)-len(valid),'point_complete_count':len(complete),
        'joint_point_mean_IA':sum(r['calculated_scores']['IA'] for r in complete)/len(complete) if complete else None,
        'joint_mean_scope':'ONLY_COMPLETE_POINT_RECORDS; not all-question performance',
        'score_qualification':'DIAGNOSTIC_UNVALIDATED',
        'display_label':'Diagnostic aggregate (time uncalibrated; RI proxy)',
        'point_coverage':len(complete)/len(entries) if entries else 0,
        'exact_bound_aggregate_count':sum(r['calculated_scores'].get('aggregate_resolution',{}).get('status')=='DERIVED_EXACT_BOUND' for r in valid),
        'per_question':[{'question_id':r['question_id'],'point_IA':r['calculated_scores']['IA'],
             'score_qualification':r['calculated_scores'].get('score_qualification','UNKNOWN_LEGACY_QUALIFICATION_ABSENT'),
             'component_qualifications':r['calculated_scores'].get('component_qualifications',{}),
             'demand_qualification':r.get('demand_qualification', {'projection_status':'UNKNOWN_LEGACY_QUALIFICATION_ABSENT','scientific_certified':False}),
             'bounds':r['bounds_diagnostic'],
             'aggregate_resolution':r['calculated_scores'].get('aggregate_resolution')} for r in valid],
        'cli_teacher_calls':0,'cli_encoder_calls':0,'scientific_certified':False,'official_scores':None}
    result=target/f"evaluation_results_{manifest.get('model_name','recorded')}_{manifest.get('shot_type','1-shot')}.json"
    validate_effectiveness_data(data_binding,runner) # reject concurrent file or in-memory drift before publishing
    summary['effectiveness_data_lock']=data_binding
    _atomic(target/'manifest.json',{'contract':contract,'input_manifest':manifest})
    for item in items:_atomic(target/'items'/f"q{item['question_id']}.json",item['evaluation'])
    _atomic(result,items);_atomic(target/'summary.json',summary)
    return {'result_path':str(result),'summary_path':str(target/'summary.json'),'revision':revision,'summary':summary,'cli_teacher_calls':0,'cli_encoder_calls':0}


def prepare_requests(manifest,questions,entries,*,output_dir,source,atomic,mode):
    """Export next real requests. Never invent absent canonical output or call a model."""
    from oeq_sr_assessment import output_schema
    from oeq_practical_scoring import score_request
    from oeq_scientific import apply_assessment
    metric_ablation=None
    if 'metric_ablation' in manifest:
        from oeq_metric_ablation import validate_config
        metric_ablation=validate_config(manifest['metric_ablation'])
        if metric_ablation is None:raise ValueError('Explicit metric_ablation cannot be null')
    from oeq_effectiveness_data_lock import capture as capture_effectiveness_data
    data_binding=capture_effectiveness_data()
    qs={str(q['question_id']):q for q in questions}
    dependencies={name:sha256_file(Path(__file__).parent/name) for name in
        ['oeq_score_lineage.py','oeq_effectiveness_data_lock.py','dataset/Q+AR/src/model_space_signed.json','oeq_practical_assessment.py','oeq_practical_scoring.py','prompts/oeq_practical_score_only.txt','prompts/oeq_practical_task_scope_v2.txt','prompts/oeq_practical_signal_assessability_v3.txt','oeq_sample_marker_applicability.py','prompts/oeq_sample_marker_applicability_v4.txt','marker_input_contract.py','verified_marker_aliases.py']}
    if any(v.get('reference',{}).get('source_reference_key')=='idisco-dec2016-atomic-clearing-v1' for v in manifest['items'].values()):
        dependencies['oeq_atomic_source_projection.py']=sha256_file(Path(__file__).parent/'oeq_atomic_source_projection.py')
    if 'atomic_alignment' in manifest or any(v.get('reference',{}).get('source_reference_key') in {'idisco-dec2016-atomic-clearing-v3','fdisco2019-atomic-clearing-thf100x2-v3','fdisco2019-atomic-clearing-thf100x3-v3'} for v in manifest['items'].values()):
        for name in ['oeq_fdisco_atomic_reference.py','oeq_atomic_alignment.py','oeq_atomic_reference_v3.py','oeq_atomic_source_projection.py','oeq_simple_time.py']:
            dependencies[name]=sha256_file(Path(__file__).parent/name)
    if metric_ablation is not None:
        from oeq_metric_ablation import dependency_hashes as ablation_dependencies
        dependencies.update(ablation_dependencies())
    for name in ['oeq_macs_atomic_reference.py','oeq_simple_representation.py','experiments/construct_validity/fidelity.py','experiments/construct_validity/compact_grounding.py','oeq_scientific.py']:
        dependencies[name]=sha256_file(Path(__file__).parent/name)
    for name in ['oeq_structured_judgment.py','oeq_fluor_lexical_identity.py','oeq_source_parameter_slots.py','source_parameter_contract.json']:
        dependencies[name]=sha256_file(Path(__file__).parent/name)
    revision=json_hash({'manifest':manifest,'prepare_dependencies':dependencies})
    target=Path(output_dir)/mode/revision/'prepared';target.mkdir(parents=True,exist_ok=True)
    requests=[];encoder_texts=[];atomic_requests=[]
    for entry in entries:
        q=str(entry['question_id']);spec=manifest['items'][q];canonical=spec['canonical'];context=source(canonical['generation_context'])
        if context['question_meta']!=qs[q] or context['protocol_sha256']!=__import__('hashlib').sha256(entry['model_response'].encode()).hexdigest():
            raise ValueError('Original task/answer differs from prepared context')
        if 'atomic_alignment' in manifest:
            from oeq_atomic_alignment import prepare_atomic_pair
            atomic_pair=prepare_atomic_pair(entry['model_response'],context,manifest['atomic_alignment'])
            pair_path=target/f'q{q}_automatic_atomic_pair.json'
            atomic(pair_path,atomic_pair)
            atomic(target/f'q{q}_automatic_atomic_encoder_request.json',{'texts':
                [r['scoring_text'] for side in ('reference','candidate') for r in atomic_pair[side]['operations']],
                'status':'REQUEST_ONLY_NOT_ENCODER_OUTPUT','alignment_version':atomic_pair['schema_version']})
            atomic_requests.append({'question_id':entry['question_id'],'pair_path':str(pair_path),
                'pair_sha256':sha256_file(pair_path),'scope':atomic_pair['scope'],'scope_status':atomic_pair['scope_status'],
                'reference_rows':len(atomic_pair['reference']['operations']),'candidate_rows':len(atomic_pair['candidate']['operations']),
                'unknown_candidate_roles':sum(r['operation_role']=='unresolved' for r in atomic_pair['candidate']['operations']),
                'official_score_changes':False})
        if 'raw' not in canonical:
            text=context['prompt'];stage='canonical';schema=output_schema('canonical')
        else:
            assessment=apply_assessment(parse_judge_object(source(canonical['raw'],json_value=False)),context,entry['model_response'])
            reference=spec['reference']
            evidence=(source(reference['projection']) if 'projection' in reference else
                      bind_source_operations(qs[q],assessment,reference['source_reference_key']))
            _check_source(qs[q],assessment,evidence,reference['source_reference_key'])
            atomic(target/f'q{q}_reference_projection.json',evidence)
            pair=_build_pair(entry['model_response'],context,assessment,evidence,reference['source_reference_key'])
            if metric_ablation is not None:
                from oeq_metric_ablation import validate_pair
                validate_pair(pair)
                atomic(target/f'q{q}_metric_ablation_config.json',metric_ablation)
            text=score_request(context,assessment,evidence,entry['model_response'],pair,
                               prompt_revision=manifest.get('prompt_revision','task-scope-v2-20261015'), generation_input=generation_input_from_entry(entry))
            schema=score_schema(manifest.get('prompt_revision','task-scope-v2-20261015'))
            if spec.get('structured_judgment') is not None:
                from oeq_structured_judgment import VERSION as STRUCTURED_VERSION, repair_request
                if spec['structured_judgment']!=STRUCTURED_VERSION:raise ValueError('Unsupported structured judgment')
                text,structured_payload=repair_request(text);schema=structured_payload['score_output_schema']
            stage='score_only';atomic(target/f'q{q}_paired_representation.json',pair)
            encoder_texts.extend([r['scoring_text'] for r in pair['reference']['operations']]+[r['scoring_text'] for r in pair['candidate']['operations']])
        request=target/f'q{q}_{stage}_request.txt';request.write_text(text)
        schema_path=target/f'q{q}_{stage}_schema.json';atomic(schema_path,schema)
        requests.append({'question_id':entry['question_id'],'next_stage':stage,'request_path':str(request),
            'request_sha256':sha256_file(request),'schema_path':str(schema_path),'schema_sha256':json_hash(schema),
            'status':'EXPORTED_NOT_EXECUTED','raw_return_contract':'Save exact provider text unchanged, then supply path+sha256 in the same stage manifest; no score-based retries'})
    atomic(target/'effectiveness_data_lock.json',data_binding)
    if capture_effectiveness_data()!=data_binding:raise ValueError('Actual signed capability data changed during prepare')
    if encoder_texts:atomic(target/'encoder_texts.json',{'texts':encoder_texts,'status':'REQUEST_ONLY_NOT_ENCODER_OUTPUT'})
    summary={'assessment_mode':mode,'schema_version':VERSION,'action':'prepare','requests':requests,
        'judge_execution':'EXTERNAL_PROVIDER_REQUIRED; raw import supported, native automatic provider execution not claimed',
        'cli_teacher_calls':0,'cli_encoder_calls':0,'manifest_sha256':json_hash(manifest),'dependencies':dependencies,'effectiveness_data_lock':data_binding}
    if atomic_requests:summary['automatic_atomic_prepare']=atomic_requests
    if metric_ablation is not None:summary['metric_ablation']={'config':metric_ablation,'stage':'COMPUTED_ONLY_AFTER_VALIDATED_IMPORT','judge_input_unchanged_by_switch':True,'default_scores_replaced':False}
    atomic(target/'preparation.json',summary)
    return {'result_path':str(target/'preparation.json'),'summary_path':str(target/'preparation.json'),
        'revision':revision,'summary':summary,'cli_teacher_calls':0,'cli_encoder_calls':0}
