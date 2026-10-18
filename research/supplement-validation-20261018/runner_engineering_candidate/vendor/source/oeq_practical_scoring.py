"""Explicit revised label/Co candidate contract; no model calls or historical rewrites."""
from copy import deepcopy
import json
from evaluation_contract import json_hash

VERSION = 'practical-rubric-v1-20261015'
RECORD_VERSION = 'oeq-sr-practical-v3-20261015'
SIGNAL_ASSESSABILITY_PROMPT = 'signal-assessability-v3-20261015'
from oeq_sample_marker_applicability import VERSION as SAMPLE_MARKER_APPLICABILITY_PROMPT
LABEL_MISSING_SPEC_POLICY = 'label-missing-spec-disposition-v1'
ALEXA_MISSING_MODEL_POLICY = 'alexa-missing-model-minus-one-v1-20261015'
LABEL_ROLE_PROJECTION_VERSION = 'explicit-dapi-probe-role-v1-20261015'

def _project_legacy_label_records(extraction, facts, selected_route):
    """Preserve source records while restoring the legacy fluor -> target contract.
    Missing target is the legacy empty marker, never a copied probe. Unknown
    provenance is not missing. Colliding dict keys never overwrite a record.
    """
    branch = next((b for b in extraction['branches'] if b['id'] == selected_route), None)
    records, guards, observed_fluors = [], [], {}
    for index, row in enumerate(extraction['labels']):
        if row['branch'] != selected_route:
            continue
        fact = facts.get(('labels', index), {})
        supported = (branch is not None and branch.get('location_status') != 'REVIEW_REQUIRED'
                     and fact.get('branch') == selected_route
                     and fact.get('assertion', {}).get('polarity') == 'AFFIRMED')
        def side(field):
            evidence = fact.get('fields', {}).get(field, {})
            if supported and row.get(field) and evidence.get('status') == 'GROUNDED':
                return row[field], 'STATED'
            if supported and row.get(field) is None and evidence.get('kind') == 'MISSING' and evidence.get('status') == 'MISSING':
                return '', 'MISSING'
            return None, 'UNRESOLVED'
        target, target_state = side('target')
        fluor, fluor_state = side('fluorophore')
        role_projection = None
        # DAPI is an exact existing dye entity, not a target inferred from a probe.
        # Keep the original canonical row untouched; consume its grounded dye role.
        probe, probe_state = side('probe')
        if fluor_state == 'MISSING' and probe_state == 'STATED' and probe == 'DAPI':
            from pathlib import Path
            kb_path = Path(__file__).parent/'KnowledgeBase/method_fluro_compati.json'
            kb = json.loads(kb_path.read_text())
            if any('DAPI' in entry for entry in kb):
                fluor, fluor_state = 'DAPI', 'STATED'
                role_projection = {'version': LABEL_ROLE_PROJECTION_VERSION,
                    'rule': 'EXACT_SOURCE_GROUNDED_DAPI_PROBE_IS_EXISTING_SMALL_MOLECULE_FLUOR',
                    'from_field': 'probe', 'to_consumed_role': 'fluorophore',
                    'entity': 'DAPI', 'source_support': deepcopy(fact.get('fields',{}).get('probe')),
                    'entity_registry': 'KnowledgeBase/method_fluro_compati.json',
                    'registry_sha256': json_hash(kb), 'raw_canonical_unchanged': True}
        if fluor_state == 'STATED':
            from oeq_fluor_lexical_identity import lookup_identity
            from pathlib import Path
            kb = json.loads((Path(__file__).parent/'KnowledgeBase/method_fluro_compati.json').read_text())
            registered = {key for entry in kb for key in entry if key != 'method'}
            fluor, lexical_identity = lookup_identity(fluor, registered)
            if lexical_identity is not None:
                role_projection = {'lexical_identity': lexical_identity, 'raw_canonical_unchanged': True,
                    'source_support': deepcopy(fact.get('fields',{}).get('fluorophore'))}
            observed_fluors[fluor] = ''
        if target_state == 'UNRESOLVED' or fluor_state == 'UNRESOLVED' or not (target or fluor):
            category = 'unresolved'
            guards.append('LABEL_SOURCE_OR_SIDES_UNRESOLVED:' + row['id'])
        else:
            category = 'complete_pair' if target and fluor else 'bare_fluor' if fluor else 'target_only'
        records.append(dict(label_id=row['id'], category=category, target=target,
                            fluorophore=fluor, target_state=target_state, fluorophore_state=fluor_state,
                            probe=row.get('probe'), channel=row.get('channel'),
                            source_row=deepcopy(row), source_fact=deepcopy(fact), role_projection=role_projection))
    if not records:
        guards.append('NO_EXPLICIT_SELECTED_ROUTE_LABELS')
    groups = {}
    for record in records:
        if record['category'] != 'unresolved':
            groups.setdefault(record['fluorophore'], []).append(record)
    markers, collisions = {}, []
    for fluor, group in groups.items():
        targets = list(dict.fromkeys(record['target'] for record in group))
        if len(targets) != 1:
            collisions.append(dict(fluorophore=fluor, targets=targets,
                                   label_ids=[record['label_id'] for record in group]))
            guards.append('LABEL_DICT_KEY_COLLISION:' + fluor)
        else:
            markers[fluor] = targets[0]
    return dict(records=records, guards=guards, collisions=collisions,
                lossless_marker_dict=markers if not guards else None,
                observed_fluor_dict=observed_fluors, aggregate_eligible=not guards,
                aggregate_policy='ALL_SELECTED_SOURCE_RECORDS_REPRESENTABLE_WITHOUT_DICT_COLLISION',
                partial_component_policy='NATIVE_E_DIAGNOSTICS_ONLY_NOT_WHOLE_LABEL_SCORE',
                target_policy='LITERAL_TARGET_AS_LEGACY_MARKER_NO_ONTOLOGY_INFERENCE')

def score_schema(prompt_revision='task-scope-v2-20261015'):
    from oeq_sr_scoring import score_only_output_schema
    schema = score_only_output_schema()
    schema['properties']['rubric_version'] = {'type':'string', 'pattern':'^'+VERSION+'$'}
    schema['required'] += ['rubric_version','label_review']
    decision = {'type':'object','additionalProperties':False,
                'required':['status','reasoning','evidence_basis'], 'properties':{
                    'status':{'type':'string','pattern':'^(SATISFIED|FAILED|UNKNOWN|NOT_APPLICABLE)$'},
                    'reasoning':{'type':'string','minLength':1},
                    'evidence_basis':{'type':'string','minLength':1}}}
    schema['properties']['label_review'] = {'type':'object','additionalProperties':False,
        'required':['task_coverage','necessary_signal_distinction'],
        'properties':{k:deepcopy(decision) for k in ['task_coverage','necessary_signal_distinction']}}
    if prompt_revision in {SIGNAL_ASSESSABILITY_PROMPT, SAMPLE_MARKER_APPLICABILITY_PROMPT}:
        d=schema['properties']['label_review']['properties']['necessary_signal_distinction']
        d['required'].append('assessability_reason')
        d['properties']['assessability_reason']={'type':'string','enum':[
            'ASSESSED','MISSING_SPEC','DOMAIN_UNCERTAINTY','MIXED_UNCERTAINTY','NOT_APPLICABLE']}
    elif prompt_revision not in {'task-scope-v1','task-scope-v2-20261015'}:
        raise ValueError('Unsupported practical prompt revision')
    for metric in schema['properties']['scores']['properties']['correctness']['properties'].values():
        metric['required'] += ['reasoning','evidence_basis']
        metric['properties']['evidence_basis'] = {'type':'string','minLength':1}
        metric['properties']['reasoning']['minLength'] = 1
    return schema


def validate_proposal(proposal, prompt_revision='task-scope-v2-20261015'):
    from oeq_sr_scoring import _validate_score_schema
    _validate_score_schema(proposal, score_schema(prompt_revision))
    if prompt_revision in {SIGNAL_ASSESSABILITY_PROMPT, SAMPLE_MARKER_APPLICABILITY_PROMPT}:
        d=proposal['label_review']['necessary_signal_distinction']
        allowed={'SATISFIED':{'ASSESSED'},'FAILED':{'ASSESSED'},
            'NOT_APPLICABLE':{'NOT_APPLICABLE'},
            'UNKNOWN':{'MISSING_SPEC','DOMAIN_UNCERTAINTY','MIXED_UNCERTAINTY'}}
        if d['assessability_reason'] not in allowed[d['status']]:
            raise ValueError('Signal assessability reason contradicts raw status')
    return deepcopy(proposal)


def score_request(context, assessment, evidence, protocol, paired_representation=None, *, prompt_revision="task-scope-v2-20261015", generation_input=None):
    from experiments.construct_validity.fidelity import text_hash
    if text_hash(protocol) != context['protocol_sha256']:
        raise ValueError('Score request protocol differs from source context')
    # Fresh blinded judgment: no old scores, assessor verdicts, guard reasons,
    # method-identity conclusions, or previous model commentary enter the call.
    payload = {
        'question': context['question_meta'], 'unchanged_protocol': protocol,
        'canonical_extraction_sha256':json_hash(assessment['extraction']),
        'task_evidence_sha256':json_hash(evidence),
        'route_id':evidence.get('route_id'),'reference_id':evidence.get('reference_id'),
        'rubric_version':VERSION,'paired_representation':paired_representation,
        'label_specification_policy':ALEXA_MISSING_MODEL_POLICY,
        'provided_sources':[{k:deepcopy(card[k]) for k in
            ['id','identity','source_document','passages'] if k in card}
            for card in evidence.get('cards',[])],
        'parameter_requirements':deepcopy(evidence.get('parameter_requirements',[])),
        'task_requirements':deepcopy(evidence.get('requirements',[])),
        'c_param_evidence_gate':deepcopy(evidence.get('evidence_gates',{}).get('c_param')),
        'score_output_schema':score_schema(prompt_revision),
    }
    from pathlib import Path
    prompt = (Path(__file__).parent/'prompts/oeq_practical_score_only.txt').read_text()
    if prompt_revision in {'task-scope-v2-20261015',SIGNAL_ASSESSABILITY_PROMPT,SAMPLE_MARKER_APPLICABILITY_PROMPT}:
        prompt += (Path(__file__).parent/'prompts/oeq_practical_task_scope_v2.txt').read_text()
    elif prompt_revision != 'task-scope-v1':
        raise ValueError('Unsupported practical prompt revision')
    if prompt_revision in {SIGNAL_ASSESSABILITY_PROMPT, SAMPLE_MARKER_APPLICABILITY_PROMPT}:
        prompt += (Path(__file__).parent/'prompts/oeq_practical_signal_assessability_v3.txt').read_text()
    if prompt_revision == SAMPLE_MARKER_APPLICABILITY_PROMPT:
        from oeq_sample_marker_applicability import applicability_context, applicability_prompt
        from marker_input_contract import build_marker_input_contract
        payload['applicability_rubric'] = applicability_context()
        payload['marker_input_contract'] = (
            build_marker_input_contract(context['question_meta'], generation_input)
            if generation_input is not None else deepcopy(context.get('marker_input_contract'))
            or build_marker_input_contract(context['question_meta']))
        prompt += applicability_prompt()
    return prompt+'\nSCORING_INPUT_JSON\n'+json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def project_labels(assessment, route_id):
    facts={(row['collection'],row['index']):row for row in assessment['extraction_fidelity']['facts']}
    extraction=deepcopy(assessment['extraction']); selected=[]; selected_facts={}; excluded=[]
    for index,row in enumerate(extraction['labels']):
        fact=facts.get(('labels',index),{})
        polarity=fact.get('assertion',{}).get('polarity')
        if polarity in {'NEGATED','CONDITIONAL'}:
            excluded.append({'source_row':row,'source_fact':deepcopy(fact),
                             'reason':'NOT_AFFIRMED_SELECTED_LABEL'})
            continue
        selected_facts[('labels',len(selected))]=fact
        selected.append(row)
    extraction['labels']=selected
    result = _project_legacy_label_records(extraction,selected_facts,route_id)
    result['excluded_nonselected_records']=excluded
    result['aggregate_policy']='RECORD_LIST_NO_DICT_COLLISION_GATE; TASK_REVIEW_AND_METHOD_FLUOR_MIN_V1'
    result['legacy_dict_aggregate_eligible']=result.pop('aggregate_eligible')
    return result


def alexa_missing_model_penalty(projection):
    """Only explicit grounded fluor-role family names; no fuzzy family lookup.

    Canonical source strings remain unchanged. A specific Alexa model, unknown
    family, probe-only mention, rejected record or other route cannot trigger it.
    """
    ids = [row['label_id'] for row in projection['records']
           if row['fluorophore_state'] == 'STATED'
           and ' '.join(row['fluorophore'].casefold().split()) in {'alexa', 'alexa fluor'}]
    return {'policy_version': ALEXA_MISSING_MODEL_POLICY,
            'eligible_label_ids': ids, 'deduction': 1.0 if ids else 0.0,
            'scope': 'ONCE_PER_ANSWER_RAW_S_LABEL_0_TO_6', 'floor': 0.0,
            'match_policy': 'EXACT_GROUNDED_FLUOR_ROLE_FAMILY_NAME_CASE_WHITESPACE_NORMALIZED',
            'scientific_distinguishability_established': False,
            'c_param_deduplication': 'FUTURE_JUDGE_EXCLUDES_SAME_MISSING_MODEL_DETAIL; HISTORICAL_RAW_NOT_REJUDGED'}


def label_effectiveness(assessment, route_id, quantitative_data, preferences, model_space,
                        targets, effectiveness_fn, review=None, *,
                        alexa_policy=ALEXA_MISSING_MODEL_POLICY):
    """Categorical 0/6 endpoints and min, then versioned Alexa specification deduction.

    A task's no-label applicability is explicit; NOT_APPLICABLE omits that
    criterion, never an invented zero. A genuinely unknown applicable criterion
    stays unknown (except an established zero already bounds the minimum).
    """
    if alexa_policy not in {None, ALEXA_MISSING_MODEL_POLICY}:
        raise ValueError("Unsupported Alexa specification policy")
    projection=project_labels(assessment,route_id)
    per_record=[]
    for row in projection['records']:
        known_target=row['target_state']=='STATED'
        known_fluor=row['fluorophore_state']=='STATED'
        if row['category']=='unresolved' and not (known_target or known_fluor):
            continue
        target=row['target'] if known_target else ''
        fluor=row['fluorophore'] if known_fluor else ''
        raw=effectiveness_fn(quantitative_data,preferences,model_space,{fluor:target},targets)
        keys=(['s_target_match','s_marker_fluor_compat','s_method_fluor_compat','s_label']
              if row['category']!='unresolved' else
              ['s_target_match'] if known_target and not known_fluor else
              ['s_method_fluor_compat'] if known_fluor and not known_target else [])
        per_record.append({'label_id':row['label_id'],'native_input':{fluor:target},
            'input_semantics':('SOURCE_VALUES' if row['category']!='unresolved' else
                'NATIVE_PARTIAL_INPUT_ONLY_NOT_SOURCE_ABSENCE'),
            'legacy_components':{k:raw.get(k) for k in keys},
            'compatibility_audit':raw.get('compatibility_audit')})
    # Method-fluor depends only on grounded fluorophores. No invented pair and
    # no loss of same-fluor/different-target records is needed for this lookup.
    observed=effectiveness_fn(quantitative_data,preferences,model_space,projection['observed_fluor_dict'],targets)
    method_score=observed.get('s_method_fluor_compat')
    unknown_fluor=[r['label_id'] for r in projection['records'] if r['fluorophore_state']=='UNRESOLVED']
    if unknown_fluor and method_score!=0:
        method_score=None
    components={'method_fluor_compatibility':{'score':method_score,'status':'UNKNOWN' if method_score is None else 'TABLE_REPORTED',
        'observed_known_score':observed.get('s_method_fluor_compat'),'unresolved_record_ids':unknown_fluor}}
    values=[method_score]
    for key in ['task_coverage','necessary_signal_distinction']:
        row=(review or {}).get(key) or {'status':'UNKNOWN','reasoning':'Awaiting actual task-specific judge review','evidence_basis':'NOT_RUN'}
        status=row['status']
        if status not in {'SATISFIED','FAILED','UNKNOWN','NOT_APPLICABLE'}:raise ValueError('Invalid label review status')
        score=6.0 if status=='SATISFIED' else 0.0 if status=='FAILED' else None
        components[key]={**deepcopy(row),'score':score}
        missing_spec=(key=='necessary_signal_distinction' and status=='UNKNOWN'
                      and row.get('assessability_reason')=='MISSING_SPEC')
        if missing_spec:
            components[key].update(disposition='NOT_ASSESSED_MISSING_SPEC',
                participates_in_min=False,scientific_distinguishability_established=False)
        if status!='NOT_APPLICABLE' and not missing_spec:values.append(score)
    omitted=[k for k,v in components.items() if v.get('disposition')=='NOT_ASSESSED_MISSING_SPEC']
    coverage={'assessed_components':[k for k,v in components.items() if v['score'] is not None],
        'missing_spec_components':omitted,
        'other_unknown_components':[k for k,v in components.items() if v['status']=='UNKNOWN' and k not in omitted],
        'not_applicable_components':[k for k,v in components.items() if v['status']=='NOT_APPLICABLE'],
        'meaning':'criterion status counts only; no evidence of scientific channel separation'}
    coverage.update(assessed_count=len(coverage['assessed_components']),
        task_relevant_count=3-len(coverage['not_applicable_components']),
        min_component_count=len(values),missing_spec_count=len(omitted),
        partial_assessment=bool(omitted))
    score=0.0 if 0 in values else None if not values or None in values else min(values)
    penalty=alexa_missing_model_penalty(projection) if alexa_policy else None
    if penalty is not None:
        penalty['score_before_penalty']=score
        score=max(0.0, score-penalty['deduction']) if score is not None else None
        penalty['score_after_penalty']=score
        penalty['applied_numeric_deduction']=(penalty['score_before_penalty']-score) if score is not None else None
    return {'score':score,'max_score':6, 'specification_penalty':deepcopy(penalty),
            'assessment_coverage':coverage,'missing_spec_policy':LABEL_MISSING_SPEC_POLICY if omitted else None,'reasoning':'Versioned task coverage / necessary signal distinction / legacy method-fluor minimum',
            **({'missing_reason':'See unresolved applicable label components'} if score is None else {})}, {
        'rubric_version':VERSION,'projection':projection,'components':components,
        'specification_penalty':deepcopy(penalty),
        'assessment_coverage':coverage,'missing_spec_policy':LABEL_MISSING_SPEC_POLICY if omitted else None,'legacy_per_record':per_record,
        'observed_method_fluor_lookup':observed,
        'aggregation':('min of assessed/applicable criteria; only explicit MISSING_SPEC distinction omitted without score; all other UNKNOWN preserved' if omitted else 'min of applicable criteria; UNKNOWN preserved; actual zero bounds min; NOT_APPLICABLE omitted'),
        'numerical_equivalence_claim':'NONE: revised label semantics; native lookup and min operator reused'}


def effectiveness_from_canonical(assessment, evidence, question_metadata, preferences,
                                 model_space, effectiveness_fn, *, protocol, review=None):
    """Opt-in revised label/time wrapper; old entry point and historical scores unchanged."""
    from oeq_sr_assessment import project_effectiveness_inputs
    from oeq_simple_time import project_simple_time
    route=evidence.get('route_id')
    projection=project_effectiveness_inputs(assessment,route,question_metadata,protocol=protocol)
    time=project_simple_time(assessment,protocol,selected_route=route)
    quantitative=deepcopy(projection['quantitative_data'])
    quantitative['total_time_hours']=time['total_time_hours']
    quantitative['time_scope']=time['actual_scope']
    quantitative['time_scope_totals']=time['scope_totals']
    labels=project_labels(assessment,route)
    raw=effectiveness_fn(quantitative,preferences,model_space,
                        labels['lossless_marker_dict'] or {},projection['marker_query_targets'])
    label, audit=label_effectiveness(assessment,route,quantitative,preferences,model_space,
        projection['marker_query_targets'],effectiveness_fn,review)
    scores={k:{'score':raw[k],'max_score':maximum,
        'reasoning':'Native E lookup/formula with explicitly versioned practical input projection',
        **({'missing_reason':'Relevant native inputs or lookup unavailable'} if raw[k] is None else {})}
        for k,maximum in [('s_method',2.5),('s_trans',3),('s_time',3)]}
    time_details=raw.get('time_computation', {})
    scores['s_time'].update(score_qualification=time_details.get('score_qualification'),
        actual_scope=time_details.get('actual_scope'), reference_scope=time_details.get('reference_scope'),
        scope_match_status=time_details.get('scope_match_status'),
        actual_hours=time_details.get('actual_hours'), full_core_hours=time['total_time_hours'],
        reference_confidence=time_details.get('reference_confidence'),
        reference_extrapolated=time_details.get('reference_extrapolated'))
    # Preserve source qualifications at the adopted-score surface, not only in
    # nested arithmetic diagnostics. Existing scores and aggregation stay intact.
    for key in ('scientific_score_status', 'validated_scientific_score',
                'reference_evidence_status', 'phase_applicability_status',
                'scientific_failure_inference_allowed', 'source_audit',
                'reference_evidence_limit', 'scientific_calibration'):
        scores['s_time'][key] = deepcopy(time_details.get(key))
    scores['s_time']['display_label'] = 'Time diagnostic (uncalibrated reference)' if raw['s_time'] is not None else 'Time unknown'
    scores['s_trans'].update(
        score_qualification='RI_REFERENCE_PROXY' if raw['s_trans'] is not None else 'UNKNOWN',
        computation_status=raw.get('_s_trans_status'),
        scientific_score_status='PROXY_NOT_IMAGING_VALIDATION' if raw['s_trans'] is not None else 'UNKNOWN',
        validated_scientific_score=None, imaging_validated=False,
        display_label='RI reference proxy (not imaging validation)')
    scores['s_label']=label
    scores['s_method']['min_score']=-2.5
    projection.update(schema_version=VERSION, quantitative_data=quantitative,
        marker_dict=labels['lossless_marker_dict'] or {}, label_projection=labels,
        time_representation=time)
    from oeq_score_lineage import build_score_lineage
    lineage=build_score_lineage(scores,raw,audit,projection,preferences,model_space)
    return scores,{'canonical_extraction_sha256':json_hash(assessment['extraction']),
        'selected_route':route,'rubric_version':VERSION,'projection':projection,
        'question_metadata':deepcopy(question_metadata),'user_preference_vector':deepcopy(preferences),
        'model_space_sha256':json_hash(model_space),'calculation_diagnostics':raw,
        'label_diagnostics':audit,'score_lineage':lineage,
        'calculation_diagnostics_semantics':'LEGACY_NATIVE_PATH_NOT_FINAL_ADOPTED_SCORES'}
