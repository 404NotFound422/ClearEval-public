"""Prospective, read-only E2 source audit. No converter, scorer or model is run.

Eight fixed C05 source components are measured separately from cached BioPro
steps. Raw relation assertions retain their own denominator, including rejected
claims and unavailable/truncated outputs. Mechanical gate results are not gold.
"""
from __future__ import annotations
import argparse,copy,importlib.util,math,re,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_round2_followup_runner_v11 as runner
j=runner.j;g=runner.grounded;require=runner.require;bind=runner.bind
BASE=runner.BASE;OUT=BASE/'E2_source_audit_v11'
REGRESSION=BASE/'regression_design_v1'
EXPECTED=REGRESSION/'expected_facts.json'
REGRESSION_CHECKER=REGRESSION/'check_regressions.py'
MERGES=ROOT/'artifacts/cce_validation/controls/granularity_edits.json'
OLD_MECHANISM=ROOT/'artifacts/cce_validation/optimizer_20261010/root_review_preparation_v1/C05_mechanism_addendum/evidence.json'
POLICY={'version':'round2_E2_source_audit_v11','planned_answers':21,'planned_pairs':15,
 'C05':{'baseline_id':'E2_15','variant_id':'E2_20','components_per_arm':8,
  'retention':'one exact source-span operation, literal replay, valid record binding and unchanged expected finite hours',
  'unavailable_conversion':'eight NA, not zero retained and not pass','raw_selection_separate':True,
  'phase_scope_recorded_not_forced':True,'whole_core_timing_not_forced':True},
 'raw_relations':{'all_strictly_parseable_raw_relation_rows_counted':True,'no_conversion_required_to_enumerate_claims':True,
  'explicit_claim_states':['mechanical_gate_pass','mechanical_gate_reject','unresolved_source_binding'],
  'nonexplicit_states':['declared_unknown','declared_ambiguous'],'truncated_or_unparseable_count':'unknown, never zero wrong',
  'gate_rejection_does_not_repair_raw_claim':True,'mechanical_gate_is_not_semantic_precision_gold':True},
 'score_reasons':'verbatim score/reason fields retained; deletion/missing lexical flags are review leads, not automatic errors',
 'BioPro_SR_SP':'only unchanged verified original step exports, never improved by this source audit',
 'new_model_calls':0,'new_embeddings':0,'score_recomputation':False,'full_converter_reexecution':False}

def regression_checker():
    spec=importlib.util.spec_from_file_location('round2_frozen_retention_checker',REGRESSION_CHECKER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def inputs():
    cases,steps,pairs=runner.checked_inputs('E2');expected=j.read(EXPECTED)
    require(len(expected['C05_lossless_representation_components'])==8,'FIXED_EIGHT_COMPONENTS')
    return cases,steps,pairs,expected

def narrow(text):return re.sub(r'^\s*\d+(?:\.\d+)*[.)]?\s+','',text.strip())

def merge_evidence(cases):
    indexed={c['anonymous_answer_id']:c for c in cases};a=indexed['E2_15'];b=indexed['E2_20']
    edit=next(x for x in j.read(MERGES)['edits'] if x['question_id']==21)
    require(g.rawsha(a['model_response'])==edit['baseline_text_sha256'] and g.rawsha(b['model_response'])==edit['variant_text_sha256'],'FROZEN_MERGE_SOURCE_DRIFT')
    operations=[narrow(a['model_response'][m['original_start']:m['original_end']]) for m in edit['original_operation_to_merged_entry']]
    hashes=[g.rawsha(t)==m['operation_text_sha256'] for t,m in zip(operations,edit['original_operation_to_merged_entry'])]
    entries=[narrow(t) for t in b['model_response'].splitlines() if re.match(r'^\d+\.\s',t)]
    grouped=[' '.join(operations[i] for i in group) for group in edit['groups_of_original_indices']]
    require(all(hashes) and entries==grouped,'LOSSLESS_GROUPING_NOT_REPRODUCED')
    return {'baseline_answer_sha256':a['answer_sha256'],'variant_answer_sha256':b['answer_sha256'],
        'all_original_operation_hashes_equal':all(hashes),'exact_grouped_operation_entries_equal':entries==grouped,
        'original_operation_count':len(operations),'merged_entry_count':len(entries),'original_operation_multiset_preserved_in_grouping':True,
        'whole_source_deleted':False,'whitespace_and_numbering_not_claimed_byte_identical':True,
        'source_edit':bind(MERGES),'old_mechanism':bind(OLD_MECHANISM)}

def component_rows(doc,conversion,expected,aid,raw=None):
    helper=regression_checker();rows=[]
    operations=raw.get('grounded_extraction',{}).get('operations',[]) if isinstance(raw,dict) else None
    if not isinstance(operations,list):operations=None
    for item in expected['C05_lossless_representation_components']:
        span=item['source_pairs'][aid]
        require(doc['answer_sha256']==span['answer_sha256'] and doc['text'][span['start']:span['end']]==span['quote'],'FIXED_COMPONENT_SOURCE_CHANGED')
        if conversion is None:retained={'passed':None,'matching_records':None,'reason':'no_valid_saved_conversion'}
        else:retained=helper.retained_duration(doc,conversion,{'span':span,'hours':item['expected_hours']})
        raw_claims=None if operations is None else []
        for index,op in enumerate(operations or []):
            try:
                if not isinstance(op,dict) or not isinstance(op.get('d'),str):continue
                duration=g.resolve({'candidate_id':op['d']},doc)
                if helper.same_span(duration,span):raw_claims.append({'raw_pointer':f'/grounded_extraction/operations/{index}',
                    'operation_id':op.get('i'),'operation_reference':op.get('o'),'duration_reference':op['d'],
                    'phase':op.get('p'),'scope':op.get('s'),'not_conversion_acceptance':True})
            except (ValueError,KeyError,TypeError):continue
        rows.append({'answer_id':aid,'component_id':item['component_id'],'expected_hours':item['expected_hours'],
            'source_span':span,'raw_matching_duration_claims':raw_claims,**retained})
    return rows

def strict_raw(raw):
    if raw is None:return None,'provider_generated_text_unavailable'
    try:return runner.base.integrity.parse_judge_object(raw),None
    except Exception as exc:return None,type(exc).__name__+': '+str(exc)

def resolved_entity(raw,doc,schema):
    g.validate_shape(raw,schema)
    support=g.resolve({'unit_id':raw['u']},doc)
    name,binding=g.bind_literal_name(raw['n'],support,doc,raw['a'])
    return {'id':raw['i'],'literal_name':raw['n'],'name':name,'name_binding':binding,
        'kind':raw['k'],'usage':raw['s'],'supporting_evidence':support,'name_occurrence':raw['a']}

def raw_relation_audit(raw,doc):
    if raw is None:return {'state':'raw_unavailable','raw_relation_denominator':None,'rows':None}
    wire=raw.get('grounded_extraction') if isinstance(raw,dict) else None
    if not isinstance(wire,dict) or not isinstance(wire.get('relations'),list):
        return {'state':'raw_relation_collection_unavailable','raw_relation_denominator':None,'rows':None}
    relations=wire['relations'];entities=wire.get('entities');rows=[];resolved={};errors={}
    envelope_errors=[]
    if wire.get('source_id')!=doc['source_id']:envelope_errors.append('raw_source_id_not_bound_to_document')
    if wire.get('schema_version')!=g.VERSION:envelope_errors.append('raw_schema_version_not_bound_to_frozen_converter')
    schema=g.schema_for_document(doc)['properties']['grounded_extraction']['properties']
    if isinstance(entities,list):
        ids=[e.get('i') for e in entities if isinstance(e,dict)]
        for entity in entities:
            if not isinstance(entity,dict):continue
            eid=entity.get('i')
            try:
                require(ids.count(eid)==1,'DUPLICATE_ENTITY_ID')
                resolved[eid]=resolved_entity(entity,doc,schema['entities']['items'])
            except Exception as exc:errors[str(eid)]=type(exc).__name__+': '+str(exc)
    for index,relation in enumerate(relations):
        row={'raw_pointer':f'/grounded_extraction/relations/{index}','raw_claim':relation,'state':'unresolved_source_binding',
            'explicit_claim_repaired':False,'semantic_gold':False}
        try:
            require(not envelope_errors,';'.join(envelope_errors))
            g.validate_shape(relation,schema['relations']['items'])
            row['raw_status']=relation['s'];f=resolved.get(relation['f']);t=resolved.get(relation['t'])
            if relation['s'] in ['unknown','ambiguous']:
                row['state']='declared_'+relation['s'];row['source_binding_still_separate']=True
            else:
                require(f is not None and t is not None,'DECLARED_ENDPOINT_SOURCE_UNRESOLVED')
                evidence=g.resolve(g._expand_ref(relation['e']),doc)
                scope=g.relation_clause_support(f['name']['quote'],t['name']['quote'],evidence,doc,list(resolved.values()))
                fo=g._endpoint_occurrence_audit(f,evidence,relation['fo'],doc);to=g._endpoint_occurrence_audit(t,evidence,relation['to'],doc)
                fc=g._selected_clause_endpoint_audit(fo,'fluor',scope);tc=g._selected_clause_endpoint_audit(to,'target',scope)
                eligible=(scope['projection_supported'] and f['kind'] in ['fluorophore','fluorescent_protein'] and f['id']!=t['id']
                    and f['name_binding']['atomicity']['projection_eligible_provisional'] and t['name_binding']['atomicity']['projection_eligible_provisional']
                    and fo['valid'] and to['valid'] and fc['valid'] and tc['valid'])
                row.update(state='mechanical_gate_pass' if eligible else 'mechanical_gate_reject',label=f['name']['quote'],target=t['name']['quote'],
                    evidence=evidence,clause_scope=scope,declared_endpoint_binding={'fluor':fo,'target':to,'fluor_clause':fc,'target_clause':tc},
                    gate_rejection_does_not_make_raw_explicit_claim_correct=True)
        except Exception as exc:row['source_binding_error']=type(exc).__name__+': '+str(exc)
        rows.append(row)
    return {'state':'strict_raw_relations_enumerated','raw_relation_denominator':len(relations),'rows':rows,
        'envelope_identity_valid':not envelope_errors,'envelope_identity_errors':envelope_errors,
        'entity_binding_errors':errors,'state_counts':dict(Counter(r['state'] for r in rows)),
        'mechanical_gate_pass_not_expert_precision':True}

def reasoning_records(raw):
    if raw is None:return None
    rows=[]
    def visit(value,path):
        if isinstance(value,dict):
            for key,item in value.items():visit(item,path+'/'+str(key))
        elif isinstance(value,list):
            for index,item in enumerate(value):visit(item,path+'/'+str(index))
        elif isinstance(value,str):
            terms=re.findall(r'\b(?:missing|omitted|deleted|absent|removed|incomplete)\b|删除|缺少|缺失|遗漏|不完整',value,re.I)
            rows.append({'raw_pointer':path,'text':value,'text_sha256':g.rawsha(value),'missing_or_deletion_lexical_flags':terms,
                'automatic_error_judgment':False,'flags_require_contextual_review':True})
    visit(raw.get('scores',{}),'/scores');visit(raw.get('score_evidence',[]),'/score_evidence')
    return rows

def policy_inputs():
    return [Path(__file__),Path(g.__file__),Path(runner.__file__),REGRESSION_CHECKER,EXPECTED,REGRESSION/'freeze.json',
        MERGES,OLD_MECHANISM,*runner.source_paths('E2'),runner.PAIR_SOURCE]

def draft():
    require(not (OUT/'freeze.json').exists(),'RULES_ALREADY_FROZEN_DO_NOT_REWRITE')
    cases,steps,pairs,expected=inputs();source=merge_evidence(cases)
    for aid in ['E2_15','E2_20']:
        case=next(c for c in cases if c['anonymous_answer_id']==aid);doc=g.document(case['model_response'],g.source_id_for_case(case))
        require(len(component_rows(doc,None,expected,aid))==8,'SOURCE_COMPONENT_COUNT')
    OUT.mkdir(parents=True,exist_ok=True);j.save(OUT/'policy.json',POLICY);j.save(OUT/'source_representation_evidence.json',source)
    check=self_check();j.save(OUT/'software_probes.json',check)
    j.save(OUT/'draft_manifest.json',{'status':'prospective_draft_not_frozen','bindings':[bind(p) for p in policy_inputs()],
        'actual_command':[sys.executable,*sys.argv],'new_model_calls':0})
    print(j.canonical({'status':'draft_ready','checks':check['count'],'new_model_calls':0}))

def freeze(args):
    require(not (OUT/'freeze.json').exists(),'FREEZE_ALREADY_EXISTS')
    review=j.read(args.independent_review)
    require(review.get('status')=='pass' and review.get('script_sha256')==j.filehash(__file__),'INDEPENDENT_RULE_REVIEW_REQUIRED')
    require(j.read(OUT/'policy.json')==POLICY,'POLICY_CHANGED');base_inputs=j.read(OUT/'draft_manifest.json')['bindings'];runner.base.verify_bindings(base_inputs)
    counts=runner.budget.counts();require(counts['phase']['E2']==0,'MUST_FREEZE_BEFORE_FIRST_NEW_E2_REQUEST')
    j.save(OUT/'freeze.json',{'status':'frozen_before_round2_E2_generation','frozen_utc':j.now(),'script_sha256':j.filehash(__file__),
        'bindings':base_inputs+[bind(OUT/'policy.json'),bind(OUT/'source_representation_evidence.json'),bind(OUT/'software_probes.json'),bind(args.independent_review)],
        'E2_requests_at_freeze':0,'package_requests_at_freeze':counts['package'],'fixed_C05_components_per_arm':8,
        'new_model_calls':0,'new_embeddings':0,'actual_command':[sys.executable,*sys.argv]})
    print(j.canonical({'status':'rules_frozen_before_E2','new_model_calls':0}))

def analyze(args):
    require(args.batch_out.resolve().is_relative_to(BASE) and not any(x in str(args.batch_out).lower() for x in ['confirmation','holdout','sealed']),'EXPOSED_E2_SCOPE_ONLY')
    frozen=j.read(OUT/'freeze.json');require(frozen['script_sha256']==j.filehash(__file__),'FROZEN_SOURCE_AUDIT_CODE_DRIFT')
    runner.base.verify_bindings(frozen['bindings']);require(frozen['E2_requests_at_freeze']==0,'AUDIT_WAS_NOT_PROSPECTIVE')
    plan,cases,matrix,contracts=runner.validate(args.batch_out);require(plan['phase']=='E2','E2_ONLY_NO_CONFIRMATION_ACCESS')
    summary=runner.terminal_summary(args.batch_out,21);indexed={c['case_id']:c for c in cases};expected=j.read(EXPECTED)
    observations=[];all_relations=[];components=[];bindings=[bind(OUT/'freeze.json'),bind(args.batch_out/'plan.json'),bind(args.batch_out/'matrix.json'),
        bind(args.batch_out/'cases.json'),bind(args.batch_out/'completion_summary.json'),bind(args.batch_out/'analysis_verification.json')]
    for row in matrix:
        trial=runner.terminal_identity(args.batch_out,row);c=indexed[row['case_id']];aid=row['anonymous_answer_id'];tid=row['planned_trial_id']
        attempt=args.batch_out/'run/attempts'/f'{tid}_1';provider_path=attempt/'provider_response.json';provider=j.read(provider_path) if provider_path.exists() else None
        raw=provider.get('response') if isinstance(provider,dict) else None;parsed,parse_error=strict_raw(raw)
        doc=j.read(row['assets']['source_document']['path']);cv=trial['evaluation']['grounded_extraction_v11']['conversion']
        if cv is not None:
            require(isinstance(raw,str) and cv['raw_response_sha256']==g.rawsha(raw) and cv['wire_payload']==parsed,'SAVED_CONVERSION_RAW_IDENTITY')
            require(j.read(attempt/'source_bound_conversion.json')==cv,'SAVED_CONVERSION_FILE_CHANGED')
        rel=raw_relation_audit(parsed,doc)
        observations.append({'answer_id':aid,'trial_id':tid,'status':trial['status'],'failure_stage':trial['evaluation']['failure_stage'],
            'strict_raw_parseable':parsed is not None,'raw_parse_error':parse_error,'raw_relation_denominator':rel['raw_relation_denominator'],
            'relation_gate_counts':rel.get('state_counts'),'raw_relation_state':rel['state'],'saved_conversion_available':cv is not None,
            'original_steps':row['step'],'original_steps_reused_not_v11_improvement':True})
        all_relations.extend({'answer_id':aid,'trial_status':trial['status'],**r} for r in (rel['rows'] or []))
        if aid in ['E2_15','E2_20']:
            components.extend(component_rows(doc,cv,expected,aid,parsed))
            j.save(args.output/(aid+'_raw_reasoning.json'),reasoning_records(parsed))
        bindings.extend([bind(args.batch_out/'run/trials'/f'{tid}.json'),*trial['bound_artifacts'],row['assets']['source_document']])
    sides={}
    for aid in ['E2_15','E2_20']:
        group=[r for r in components if r['answer_id']==aid];available=all(r['passed'] is not None for r in group)
        sides[aid]={'fixed_components':8,'measurement_available':available,'retained':sum(r['passed'] is True for r in group) if available else None,
            'unavailable_components':sum(r['passed'] is None for r in group)}
    source=merge_evidence(cases);bycase={r['case_id']:r for r in matrix};pair_rows=[]
    for p in j.read(args.batch_out/'pairs.json'):
        a,b=(bycase[p[k]] for k in ['baseline_case_id','variant_case_id']);ar=next(r for r in observations if r['answer_id']==a['anonymous_answer_id']);br=next(r for r in observations if r['answer_id']==b['anonymous_answer_id'])
        both=ar['saved_conversion_available'] and br['saved_conversion_available']
        both_technical=ar['status']=='success' and br['status']=='success'
        pair_rows.append({**p,'baseline_id':ar['answer_id'],'variant_id':br['answer_id'],'baseline_status':ar['status'],'variant_status':br['status'],
            'both_saved_conversions':both,'both_arms_technical_complete':both_technical,
            'source_fact_pair_comparison_available':both and both_technical,'failed_pair_is_not_zero_change':True,
            'baseline_original_sr':a['step']['sr'],'variant_original_sr':b['step']['sr'],'baseline_original_sp':a['step']['sp'],'variant_original_sp':b['step']['sp'],
            'C05_fixed_eight_comparison':sides if ar['answer_id']=='E2_15' and br['answer_id']=='E2_20' else None,
            'C05_paired_retained_delta':sides['E2_20']['retained']-sides['E2_15']['retained']
                if ar['answer_id']=='E2_15' and br['answer_id']=='E2_20' and both and both_technical
                    and all(sides[k]['retained'] is not None for k in ['E2_15','E2_20']) else None,
            'other_pair_fact_gold_not_added':True})
    totals={'status':'complete_read_only_source_diagnostic_not_scientific_acceptance','planned_answers':21,'terminal_answers':len(observations),
        'planned_pairs':15,'fixed_C05_per_arm':8,'C05':sides,'C05_lossless_source_evidence':source,
        'strictly_parseable_raw_answers':sum(r['strict_raw_parseable'] for r in observations),
        'raw_relation_rows_observed':len(all_relations),'answers_with_unknown_relation_denominator':sum(r['raw_relation_denominator'] is None for r in observations),
        'raw_relation_gate_counts':dict(Counter(r['state'] for r in all_relations)),
        'all_relation_denominator_known':all(r['raw_relation_denominator'] is not None for r in observations),
        'failed_or_unparseable_outputs_are_not_zero_wrong_relations':True,'original_SR_SP_not_modified':True,
        'new_model_calls':0,'new_embeddings':0,'conversions_reexecuted':0,'scores_recomputed':0,'expert_labels':0,
        'input_bindings':list({b['path']:b for b in bindings}.values()),'actual_command':[sys.executable,*sys.argv]}
    for name,rows in [('observations',observations),('C05_components',components),('all_raw_relations',all_relations),('all_15_pairs',pair_rows)]:runner.write_table(args.output,name,rows)
    j.save(args.output/'summary.json',totals);print(j.canonical({k:totals[k] for k in ['status','C05','strictly_parseable_raw_answers','raw_relation_gate_counts','new_model_calls']}))

def self_check():
    checks=[]
    def check(name,value):require(value,'AUDIT_SOFTWARE_CHECK:'+name);checks.append({'name':name,'pass':True})
    helper=regression_checker();check('original_retention_helper_tests',all(r['pass'] for r in helper.self_checks()))
    d,payload=g.synthetic_fixture();raw=copy.deepcopy(payload)
    a=raw_relation_audit(raw,d);check('valid_pair_mechanical_gate_pass',a['rows'][0]['state']=='mechanical_gate_pass')
    for key,value in [('source_id','WRONG_SOURCE'),('schema_version','UNRECOGNIZED_VERSION')]:
        changed=copy.deepcopy(raw);changed['grounded_extraction'][key]=value
        wrong=raw_relation_audit(changed,d)
        check('wrong_envelope_'+key,wrong['raw_relation_denominator']==1 and not wrong['envelope_identity_valid']
            and wrong['rows'][0]['state']=='unresolved_source_binding')
    raw['grounded_extraction']['relations'][0]['to']=99
    a=raw_relation_audit(raw,d);check('wrong_endpoint_mechanical_reject',a['rows'][0]['state']=='mechanical_gate_reject')
    raw['grounded_extraction']['relations'][0].update(s='unknown',to=None,t=None,fo=None)
    a=raw_relation_audit(raw,d);check('unknown_raw_not_false_assertion',a['rows'][0]['state']=='declared_unknown')
    a=raw_relation_audit(None,d);check('unparseable_denominator_unknown',a['rows'] is None and a['raw_relation_denominator'] is None)
    check('empty_valid_relations_zero_known',raw_relation_audit({'grounded_extraction':{'relations':[],'entities':[]}},d)['raw_relation_denominator']==0)
    check('duplicate_json_not_repaired',strict_raw('{"scores":{},"scores":{}}')[0] is None)
    reasoning=reasoning_records({'scores':{'completeness':{'reasoning':'Some details are missing.'}}})
    check('reason_lexeme_not_automatic_wrong',reasoning[0]['missing_or_deletion_lexical_flags']==['missing'] and reasoning[0]['automatic_error_judgment'] is False)
    return {'status':'pass','count':len(checks),'checks':checks,'script_sha256':j.filehash(__file__),
        'new_model_calls':0,'no_full_conversion_or_scoring':True,'actual_command':[sys.executable,*sys.argv]}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['draft','freeze','analyze']);p.add_argument('--independent-review',type=Path)
    p.add_argument('--batch-out',type=Path,default=BASE/'grounded_controls_v11');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.action=='draft':draft()
    elif a.action=='freeze':require(a.independent_review is not None,'INDEPENDENT_REVIEW_PATH_REQUIRED');freeze(a)
    else:
        a.output=(a.output or OUT/'actual_analysis').resolve();require(a.output.is_relative_to(BASE),'NEW_ROUND_OUTPUT_ONLY')
        require(not a.output.exists(),'DO_NOT_OVERWRITE_SOURCE_AUDIT');a.output.mkdir(parents=True)
        analyze(a)

if __name__=='__main__':main()
