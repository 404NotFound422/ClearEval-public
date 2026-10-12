"""Pre-generation mechanical audit against the frozen five-development inventory.

No calls, repairs, semantic gold labels, held-out inputs, or score changes.
An exact entity string is not a verified biological role or target relation.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, math, re, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_extraction_v1 as grounded

BASE=ROOT/'artifacts/cce_validation/optimizer_20261010'
OUT=BASE/'fact_audit_checker_v1'
INVENTORY=BASE/'validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json'
INVENTORY_SHA='0dd8cb9dedcfcd41ec754011bb276f88d92229e7fbd5b83e410c52a687220b82'
GROUND_SHA='cd9394da51965bd56479f779ed5a6b6c5065bb319fdb7214291edcc7b8fc5b25'
IDS=['A01','A02','A03','A04','A05'];TOL=1e-12
VERSION='frozen-development-fact-audit-v1'

def require(ok,why):
    if not ok:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rawsha(t):return hashlib.sha256(t.encode('utf8')).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,o):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def same(a,b):return a is None and b is None or finite(a) and finite(b) and abs(a-b)<=TOL
def overlap(a,b):return a['start']<b['end'] and b['start']<a['end']
def contains(a,b):return a['start']<=b['start'] and b['end']<=a['end']

def span_check(span,text):
    require(span.get('source_text_sha256',span.get('answer_sha256'))==rawsha(text),'SOURCE_SPAN_HASH_MISMATCH')
    a,b=span['start'],span['end'];require(isinstance(a,int) and isinstance(b,int) and 0<=a<b<=len(text),'SOURCE_SPAN_OFFSETS')
    require(text[a:b]==span['quote'],'SOURCE_SPAN_QUOTE_MISMATCH')
    if 'quote_sha256' in span:require(rawsha(span['quote'])==span['quote_sha256'],'QUOTE_HASH_MISMATCH')
    return True

def source_hours(quote):
    """Independent numeric/unit conversion, not grounded's aggregate or parser."""
    hits=list(re.finditer(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|min|days?|d|小时|分钟|天)(?![A-Za-z])',quote,re.I))
    if len(hits)!=1:return None
    value=float(hits[0][1]);unit=hits[0][2].lower()
    if unit.startswith('min') or unit=='分钟':value/=60
    elif unit.startswith('d') or unit=='天':value*=24
    return value

def verify_inventory():
    require(sha(INVENTORY)==INVENTORY_SHA,'FROZEN_INVENTORY_CHANGED')
    require(sha(Path(grounded.__file__))==GROUND_SHA,'FROZEN_GROUNDED_MODULE_CHANGED')
    inv=read(INVENTORY);source=inv['source_cases'];require(sha(source['path'])==source['sha256'],'INVENTORY_SOURCE_CASE_FILE_CHANGED')
    raw=read(source['path']);cases=raw['cases'];require([c['anonymous_answer_id'] for c in inv['cases']]==IDS,'FIXED_INVENTORY_SELECTION')
    indexed={c['anonymous_answer_id']:c for c in cases};checks=[]
    for row in inv['cases']:
        aid=row['anonymous_answer_id'];case=indexed[aid];text=case['model_response']
        require(row['case_id']==case['case_id'] and row['question_id']==case['question_id'],'INVENTORY_CASE_IDENTITY')
        require(rawsha(text)==row['source']['answer_sha256'] and rawsha(case['specific_question'])==row['source']['question_sha256'],'INVENTORY_TEXT_HASH')
        pointer=row['source']['answer_json_pointer'].split('/')[1:];node=raw
        for key in pointer:node=node[int(key)] if isinstance(node,list) else node[key]
        require(node==text and row['source']['case_file']==source,'INVENTORY_SOURCE_POINTER')
        def walk(x):
            if isinstance(x,dict):
                if {'start','end','quote','source_text_sha256'}<=set(x):span_check(x,text)
                for value in x.values():walk(value)
            elif isinstance(x,list):
                for value in x:walk(value)
        walk(row)
        for comp in row['time']['components']+row['time']['excluded_or_conditional_duration_mentions']:
            require(same(source_hours(comp['duration_span']['quote']),comp['hours']),'INVENTORY_SOURCE_DURATION_UNIT_MISMATCH')
            a=comp['step_label_span']['start'];b=text.find('\n',a);b=len(text) if b<0 else b
            require(rawsha(text[a:b])==comp['full_step_text_sha256'],'INVENTORY_FULL_STEP_LINE_HASH')
        require(same(sum(x['hours'] for x in row['time']['components']),row['time']['computed_sum_hours']),'INVENTORY_INITIAL_SUM')
        checks.append({'anonymous_answer_id':aid,'source_bound':True,'core_components':len(row['time']['components']),
            'explicit_names':len(row['explicit_names_to_retain']),'source_component_sum_hours':row['time']['computed_sum_hours']})
    counts={'methods':len(inv['cases']),'explicit_selected_or_used_entity_names':sum(c['explicit_names'] for c in checks),
            'source_core_duration_components':sum(c['core_components'] for c in checks),
            'explicit_label_target_relations':sum(len(c['explicitly_supported_label_relations']) for c in inv['cases']),
            'ambiguity_groups':sum(len(c['ambiguous_relations_or_alternatives']) for c in inv['cases'])}
    require(all(inv['fixed_denominators'][k]==v for k,v in counts.items()),'INVENTORY_DENOMINATOR_MISMATCH')
    return inv,indexed,checks

def name_audit(expected,entities,available=True):
    rows=[]
    for fact in expected:
        name=fact['name'];exact=[e for e in entities if e['name']['quote']==name]
        contained=[e for e in entities if name in e['name']['quote'] and e['name']['quote']!=name]
        status='exact' if exact else 'contained-only' if contained else 'missing' if available else 'unavailable'
        rows.append({'expected_name':name,'inventory_source_span':fact['source_span'],'status':status,
            'exact_record_ids':[e['id'] for e in exact],'contained_only_record_ids':[e['id'] for e in contained],
            'same_inventory_occurrence_present':any(contains(e['name'],fact['source_span']) or contains(fact['source_span'],e['name']) for e in exact),
            'returned_roles':[{'id':e['id'],'literal_name':e['name']['quote'],'kind':e['kind'],'usage':e['usage']} for e in exact+contained],
            'semantic_role_or_target_verified':False,
            'boundary':'Literal containment such as anti-GFP containing GFP is not exact identity or verified semantic equivalence.'})
    return rows

def duration_audit(components,operations,initial,available=True):
    rows=[]
    for fact in components:
        matches=[o for o in operations if o.get('duration') and contains(fact['duration_span'],o['duration'])]
        observations=[]
        for o in matches:
            actual=source_hours(o['duration']['quote']);parsed=o.get('parsed_duration',{});bound=parsed.get('bounds_hours')
            parsed_agrees=isinstance(bound,list) and len(bound)==2 and same(bound[0],actual) and same(bound[1],actual)
            observations.append({'operation_id':o['id'],'duration_span':o['duration'],'literal_unit_hours':actual,
                'equals_inventory_hours':same(actual,fact['hours']),'saved_parsed_duration_agrees':parsed_agrees,
                'phase':o['phase'],'execution_scope':o['execution_scope'],'repeat_count':o.get('repeat_count'),
                'operation_contains_duration':contains(o['operation'],o['duration']),
                'retained_as_initial_included_operation':o['phase'] in grounded.INCLUDE and o['execution_scope']=='initial',
                'condition_evidence':o.get('condition_evidence')})
        exact=any(r['equals_inventory_hours'] and r['saved_parsed_duration_agrees'] and r['operation_contains_duration'] for r in observations)
        status='source_numeric_retained' if exact else 'span_present_numeric_mismatch' if matches else 'missing' if available else 'unavailable'
        rows.append({'step_label':fact['step_label'],'inventory_hours':fact['hours'],'inventory_duration_span':fact['duration_span'],
            'inventory_scope':'initial_core' if initial else fact.get('excluded_scope','excluded_or_conditional'),
            'status':status,'observations':observations,
            'initial_scope_preserved':any(r['equals_inventory_hours'] and r['retained_as_initial_included_operation'] for r in observations) if initial else None,
            'phase_semantics_verified':False,'multiple_matching_operation_records':len(matches)>1})
    return rows

def relation_audit(expected,g,projection,available):
    ents={e['id']:e for e in g.get('entities',[])};mapping=projection.get('extraction',{}).get('marker_dict',{});rows=[]
    for fact in expected:
        edges=[]
        for edge in g.get('relations',[]):
            f=ents[edge['fluor_entity_id']]['name']['quote'];t=ents[edge['target_entity_id']]['name']['quote']
            if f==fact['label'] and t==fact['target']:
                edges.append({'id':edge['id'],'status':edge['status'],'projection_allowed':edge['projection_allowed'],
                    'mechanical_relation_state':edge['mechanical_relation_state'],'evidence_span':edge['evidence'],
                    'inventory_relation_evidence_overlap':overlap(edge['evidence'],fact['source_span'])})
        projected=mapping.get(fact['label'])==fact['target']
        rows.append({'label':fact['label'],'target':fact['target'],'inventory_source_span':fact['source_span'],
            'returned_exact_endpoint_edges':edges,'edge_retained':bool(edges) if available else None,
            'exact_legacy_projection_retained':projected if available else None,
            'edge_present_but_projection_lost':bool(edges) and not projected if available else None,
            'semantic_relation_verified':False,'inventory_relation_is_expert_gold':False})
    return rows

def ambiguity_audit(expected,g,projection,available):
    rows=[];entities=g.get('entities',[]);ents={e['id']:e for e in entities};mapping=projection.get('extraction',{}).get('marker_dict',{})
    for fact in expected:
        spans=fact.get('source_spans') or [fact['source_span']]
        unresolved=[u for u in g.get('coverage',{}).get('unresolved',[]) if any(overlap(u['evidence'],s) for s in spans)]
        names=fact.get('named_options',[])+fact.get('known_labels',[])+fact.get('known_targets',[])
        records=[e for e in entities if e['name']['quote'] in names]
        edges=[r for r in g.get('relations',[]) if ents[r['fluor_entity_id']]['name']['quote'] in names or ents[r['target_entity_id']]['name']['quote'] in names]
        uncertain=any(e['usage'] in ['alternative','unknown'] for e in records) or any(r['status'] in ['ambiguous','unknown'] for r in edges) or bool(unresolved)
        specific=[{'label':k,'target':v} for k,v in mapping.items() if k in fact.get('known_labels',[]) and v]
        all_options_used=all(any(e['name']['quote']==n and e['usage']=='used' for e in records) for n in fact.get('named_options',[])) if fact.get('named_options') else None
        status='unavailable' if not available else 'specific_projection_for_inventory_ambiguous_group' if specific else 'explicit_ambiguity_retained' if uncertain else 'no_specific_projection_but_ambiguity_not_explicit'
        rows.append({'kind':fact['kind'],'inventory_spans':spans,'status':status,
            'retained_name_records':[{'id':e['id'],'name':e['name']['quote'],'kind':e['kind'],'usage':e['usage']} for e in records],
            'unresolved_evidence':unresolved,'specific_legacy_projections':specific,'all_slash_options_marked_used':all_options_used,
            'semantic_adjudication_pending':True})
    return rows

def audit_case(fact,conversion):
    available=conversion is not None;g=conversion['source_audit']['resolved'] if available else {};projection=conversion['legacy_projection'] if available else {}
    names=name_audit(fact['explicit_names_to_retain'],g.get('entities',[]),available)
    core=duration_audit(fact['time']['components'],g.get('operations',[]),True,available)
    outside=duration_audit(fact['time']['excluded_or_conditional_duration_mentions'],g.get('operations',[]),False,available)
    retained=[r for r in core if r['status']=='source_numeric_retained'];all_retained=len(retained)==len(core) and available
    included=[r for r in core if r['initial_scope_preserved']];clock=projection.get('time_calculation',{});ex=projection.get('extraction',{})
    method_records=[m for m in g.get('method_mentions',[]) if m['name']['quote']==fact['method']['value']]
    ri=fact['RI'];ri_mentions=g.get('ri_mentions',[])
    return {'anonymous_answer_id':fact['anonymous_answer_id'],'question_id':fact['question_id'],
        'conversion_available':available,'names':names,'core_duration_components':core,'excluded_or_conditional_duration_components':outside,
        'method':{'inventory_value':fact['method']['value'],'literal_record_present':bool(method_records) if available else None,
            'projected_method':ex.get('method_name'),'equals_inventory_literal':ex.get('method_name')==fact['method']['value'] if available else None,
            'selection_semantics_verified':False},
        'time_scope_comparison':{'inventory_initial_scope':fact['time']['scope'],'inventory_initial_sum_hours':fact['time']['computed_sum_hours'],
            'expected_core_components':len(core),'retained_numeric_components':len(retained),'returned_initial_included_components':len(included),
            'hours_from_retained_inventory_components':sum(r['inventory_hours'] for r in retained) if retained else None,
            'all_initial_numeric_components_retained':all_retained,'returned_initial_scope_bounds':clock.get('initial_scope_candidate_bounds_hours'),
            'returned_primary_total_hours':ex.get('clearing_total_time_hours'),'primary_total_equals_inventory_initial_scope_sum':same(ex.get('clearing_total_time_hours'),fact['time']['computed_sum_hours']) if available else None,
            'initial_facts_available_despite_primary_NA':all_retained and ex.get('clearing_total_time_hours') is None,
            'primary_NA_with_missing_known_components':available and ex.get('clearing_total_time_hours') is None and not all_retained,
            'returned_conditional_operations':clock.get('conditional_operations'),'returned_endpoint_scope':clock.get('endpoint_scope'),
            'returned_time_issues':clock.get('issues'),'inventory_sum_is_universal_endpoint':False},
        'relations':relation_audit(fact['explicitly_supported_label_relations'],g,projection,available),
        'ambiguities':ambiguity_audit(fact['ambiguous_relations_or_alternatives'],g,projection,available),
        'RI':{'inventory_reagent_value':ri['reagent_value'],'inventory_numeric_span':ri['numeric_source_span'],
            'returned_reagent_value':ex.get('reagent_ri_value'),'reagent_literal_numeric_agreement':same(ri['reagent_value'],ex.get('reagent_ri_value')) if available else None,
            'numeric_span_retained':any(r['role']=='reagent_final' and contains(ri['numeric_source_span'],r['value']) for r in ri_mentions) if ri['numeric_source_span'] else None,
            'sample_target_unknown_preserved':ex.get('sample_ri_value') is None if available else None,
            'RI_role_semantics_verified':False},
        'contract_protocol_time_null_preserved':ex.get('protocol_time_hours') is None if available else None,
        'scientific_or_expert_accuracy_claimed':False}

def load_conversion(batch,cell,source_case):
    """Actual trial and provider identity, never trust a detached replay file."""
    trial_id=cell['planned_trial_id'];p=batch/'run/trials'/f'{trial_id}.json'
    if not p.exists():return None,{'state':'pending_actual_trial','trial_id':trial_id},[]
    t=read(p);require(t['identity']==cell['identity'] and t['case_id']==source_case['case_id'],'ACTUAL_TRIAL_IDENTITY')
    conversion=(t.get('evaluation',{}).get('grounded_extraction_v1') or {}).get('conversion')
    errors=(t.get('evaluation',{}).get('grounded_extraction_v1') or {}).get('conversion_errors')
    files=[p];attempt=batch/'run/attempts'/f'{trial_id}_1';receipt=attempt/'request_receipt.json'
    require(receipt.exists(),'ACTUAL_RECEIPT_MISSING');r=read(receipt);files.append(receipt)
    if conversion is not None:
        provider=attempt/'provider_response.json';require(provider.exists(),'ORIGINAL_PROVIDER_MISSING');files.append(provider)
        body=read(provider);raw=body['response'];doc=grounded.document(source_case['model_response'],source_case['case_id'])
        replay=grounded.convert(raw,doc);require(replay==conversion,'CONVERSION_OR_SOURCE_REPLAY_MISMATCH')
        require(conversion['raw_response_sha256']==rawsha(raw),'RAW_CONTENT_SHA_MISMATCH')
    return conversion,{'state':'auditable_conversion' if conversion is not None else 'actual_trial_without_valid_conversion',
        'trial_id':trial_id,'trial_status':t['status'],'request_id':r['request_id'],'conversion_errors':errors},files

def analyze(batch,out):
    inv,sources,inventory_checks=verify_inventory();freeze=read(OUT/'freeze.json')
    require(freeze['checker_sha256']==sha(__file__),'CHECKER_CHANGED_AFTER_PREGENERATION_FREEZE')
    cases=read(batch/'cases.json')['cases'];indexed={c['anonymous_answer_id']:c for c in cases}
    require(list(indexed)==IDS and len(cases)==5,'BATCH_NOT_EXACT_FIXED_FIVE')
    matrix=read(batch/'matrix.json');cells={c['anonymous_answer_id']:c for c in matrix}
    require(set(cells)==set(IDS) and len(matrix)==5,'BATCH_MATRIX_NOT_EXACT_FIXED_FIVE')
    rows=[];files=[INVENTORY,Path(inv['source_cases']['path']),batch/'cases.json',batch/'matrix.json',OUT/'freeze.json',Path(__file__)]
    for fact in inv['cases']:
        aid=fact['anonymous_answer_id'];case=indexed[aid];original=sources[aid]
        require(all(case[k]==original[k] for k in ['case_id','question_id','model_response','specific_question']),'BATCH_ORIGINAL_TEXT_IDENTITY')
        conversion,provenance,inputs=load_conversion(batch,cells[aid],case);row=audit_case(fact,conversion)
        row['actual_trial']=provenance;row['source_answer_sha256']=rawsha(case['model_response']);rows.append(row);files+=inputs
    name_counts=Counter(r['status'] for c in rows for r in c['names']);duration_counts=Counter(r['status'] for c in rows for r in c['core_duration_components'])
    summary={'version':VERSION,'status':'complete' if all(r['actual_trial']['state']!='pending_actual_trial' for r in rows) else 'pending_actual_trials',
        'batch_out':str(batch.resolve()),'fixed_answers':5,'auditable_conversions':sum(r['conversion_available'] for r in rows),
        'explicit_names_denominator':16,'name_states':dict(name_counts),'core_duration_denominator':31,'core_duration_states':dict(duration_counts),
        'core_initial_scope_retained':sum(bool(d['initial_scope_preserved']) for r in rows for d in r['core_duration_components']),
        'explicit_relation_denominator':3,'exact_endpoint_edges_retained':sum(bool(e['edge_retained']) for r in rows for e in r['relations']),
        'exact_relation_projections_retained':sum(bool(e['exact_legacy_projection_retained']) for r in rows for e in r['relations']),
        'ambiguity_group_denominator':2,'ambiguity_states':dict(Counter(a['status'] for r in rows for a in r['ambiguities'])),
        'all_known_initial_components_retained_answers':sum(r['time_scope_comparison']['all_initial_numeric_components_retained'] for r in rows),
        'primary_NA_with_missing_known_components_answers':sum(r['time_scope_comparison']['primary_NA_with_missing_known_components'] for r in rows),
        'tolerance':TOL,'new_model_calls':0,'expert_labels_created':0,'scientific_accuracy_claimed':False,
        'scope':'Frozen model-source inventory plus mechanical identity/unit/offset diagnostics. Exact strings are not semantic roles; inventory relationships are not expert gold. Missing known components never count as faithful merely because primary total is NA.',
        'inputs':[bind(p) for p in dict.fromkeys(files)],'actual_command':[sys.executable,*sys.argv]}
    save(out/'per_answer.json',rows);save(out/'summary.json',summary);save(out/'inventory_verification.json',inventory_checks)
    lines=['# Grounded development fact audit','',f"Auditable conversions: {summary['auditable_conversions']}/5. Names: {dict(name_counts)} / 16. Initial duration components: {dict(duration_counts)} / 31.",'',
        '| ID | exact / contained / missing / unavailable names | source duration components | initial-scope components | primary time | inventory initial sum |','|---|---|---|---|---|---|']
    for r in rows:
        n=Counter(x['status'] for x in r['names']);t=r['time_scope_comparison'];lines.append(f"| {r['anonymous_answer_id']} | {n['exact']} / {n['contained-only']} / {n['missing']} / {n['unavailable']} | {t['retained_numeric_components']}/{t['expected_core_components']} | {t['returned_initial_included_components']} | {t['returned_primary_total_hours']} | {t['inventory_initial_sum_hours']} |")
    lines+=['','The two time columns use different declared scopes and are not automatically expected to agree. Conditional later operations and missing components remain separate in JSON. An exact entity string does not verify its role; anti-GFP containing GFP is only containment. Relationships and ambiguities still need semantic review. No model calls, source edits, score changes or expert labels.','']
    (out/'README.md').write_text('\n'.join(lines),encoding='utf8');print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs','scope']},ensure_ascii=True))

def self_check():
    inv,_,checks=verify_inventory();doc,payload=grounded.synthetic_fixture();conv=grounded.convert(grounded.canonical(payload),doc);g=conv['source_audit']['resolved'];tests=[]
    def check(name,condition):require(condition,'SYNTHETIC_CHECK:'+name);tests.append({'name':name,'pass':True,'synthetic_only':True})
    def factspan(s):return {'start':s['start'],'end':s['end'],'quote':s['quote'],'source_text_sha256':s['answer_sha256'],'quote_sha256':rawsha(s['quote'])}
    named={'name':'SYNTHETIC_TARGET','source_span':factspan(g['entities'][1]['name'])}
    check('exact_name_is_literal_only',name_audit([named],g['entities'])[0]['status']=='exact')
    changed=copy.deepcopy(g['entities']);changed[1]['name']['quote']='anti-SYNTHETIC_TARGET'
    check('anti_prefix_is_contained_only_not_semantic_equivalence',name_audit([named],changed)[0]['status']=='contained-only')
    check('missing_name_remains_missing',name_audit([named],[])[0]['status']=='missing')
    check('unavailable_conversion_is_not_false_zero_coverage',name_audit([named],[],False)[0]['status']=='unavailable')
    op=g['operations'][0];comp={'step_label':'SYNTHETIC_1','hours':2.0,'duration_span':factspan(op['duration'])}
    audit=duration_audit([comp],g['operations'],True)[0];check('duration_source_unit_scope_retained',audit['status']=='source_numeric_retained' and audit['initial_scope_preserved'])
    modified=copy.deepcopy(g['operations']);modified[0]['parsed_duration']['bounds_hours']=[3,3]
    check('saved_numeric_tampering_detected',duration_audit([comp],modified,True)[0]['status']=='span_present_numeric_mismatch')
    modified=copy.deepcopy(g['operations']);modified[0]['phase']='staining'
    audit=duration_audit([comp],modified,True)[0];check('numeric_fact_survives_scope_disagreement',audit['status']=='source_numeric_retained' and not audit['initial_scope_preserved'])
    modified=copy.deepcopy(g['operations']);modified[0]['duration']['start']+=100;modified[0]['duration']['end']+=100
    check('same_number_wrong_offset_not_matched',duration_audit([comp],modified,True)[0]['status']=='missing')
    expected=[{'label':'SYNTHETIC_FLUOR_101','target':'SYNTHETIC_TARGET','source_span':factspan(g['relations'][0]['evidence'])}]
    ra=relation_audit(expected,g,conv['legacy_projection'],True)[0];check('exact_relation_and_projection_separate',ra['edge_retained'] and ra['exact_legacy_projection_retained'])
    lost=copy.deepcopy(conv['legacy_projection']);lost['extraction']['marker_dict']['SYNTHETIC_FLUOR_101']=''
    check('retained_edge_projection_loss_reported',relation_audit(expected,g,lost,True)[0]['edge_present_but_projection_lost'])
    ambiguity={'kind':'unassigned_secondary_names','source_spans':[factspan(g['relations'][0]['evidence'])],
        'known_labels':['SYNTHETIC_FLUOR_101'],'known_targets':['SYNTHETIC_TARGET']}
    check('specific_mapping_for_declared_ambiguity_is_flagged',ambiguity_audit([ambiguity],g,conv['legacy_projection'],True)[0]['status']=='specific_projection_for_inventory_ambiguous_group')
    uncertain=copy.deepcopy(g);uncertain['relations'][0]['status']='unknown'
    check('withheld_edge_explicit_ambiguity_preserved',ambiguity_audit([ambiguity],uncertain,lost,True)[0]['status']=='explicit_ambiguity_retained')
    wrong=factspan(g['entities'][0]['name']);wrong['start']+=1
    try:span_check(wrong,doc['text'])
    except ValueError:check('inventory_offset_tampering_rejected',True)
    else:raise ValueError('OFFSET_TAMPERING_ACCEPTED')
    check('independent_minutes_conversion',same(source_hours('Time: 30 minutes'),.5))
    batch=BASE/'grounded_development_v1';observed_receipts=list((batch/'run/attempts').glob('*/request_receipt.json'))
    observed_trials=list((batch/'run/trials').glob('*.json'))
    observed_returns=list((batch/'run/attempts').glob('*/provider_response.json'))
    freeze={'version':VERSION,'created_utc':datetime.now(timezone.utc).isoformat(),'checker_sha256':sha(__file__),
        'inventory':bind(INVENTORY),'grounded_module':bind(grounded.__file__),'known_scope':'Only fixed A01–A05 exposed development answers.',
        'original_grounded_batch_receipts_present_at_freeze':len(observed_receipts),
        'candidate_trial_files_present_at_freeze':len(observed_trials),'provider_return_files_present_at_freeze':len(observed_returns),
        'frozen_before_candidate_generation':not observed_receipts,
        'checker_freeze_timing':'During the first live request, before inspecting candidate outputs; only file counts were checked. The fact inventory was already frozen before generation.',
        'candidate_output_contents_inspected_before_checker_freeze':False,
        'fixed_denominators':inv['fixed_denominators'],'rules':['Names: exact vs contained-only vs missing vs unavailable, case sensitive, no aliases.',
          'Time: source offsets plus independent units, parsed values, phase and execution scope separately; known source components survive primary NA.',
          'Relations: exact endpoint strings, source evidence and legacy projection reported separately; no semantic gold assertion.',
          'Ambiguities: explicit uncertainty, all-options-used and specific projection are separate diagnostics.',
          'Actual analysis requires raw provider-to-conversion replay and exact five original question/answer identities.'],
        'new_model_calls':0,'actual_command':[sys.executable,*sys.argv]}
    OUT.mkdir(parents=True,exist_ok=True);save(OUT/'freeze.json',freeze);save(OUT/'software_probes.json',{'status':'pass','synthetic_checks':tests,
        'inventory_identity_checks':checks,'new_model_calls':0,'checker_sha256':sha(__file__),'freeze_sha256':sha(OUT/'freeze.json')})
    print(json.dumps({'status':'pass','synthetic_checks':len(tests),'inventory_cases':len(checks),'checker_sha256':sha(__file__),
        'frozen_before_candidate_generation':freeze['frozen_before_candidate_generation'],
        'candidate_output_contents_inspected_before_checker_freeze':False,'provider_return_files':len(observed_returns),'trial_files':len(observed_trials)}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--self-check',action='store_true');p.add_argument('--analyze',action='store_true');p.add_argument('--batch-out',type=Path);p.add_argument('--out',type=Path)
    args=p.parse_args();require(args.self_check != args.analyze,'CHOOSE_EXACTLY_ONE_ACTION')
    if args.self_check:self_check()
    else:
        require(args.batch_out is not None,'ANALYZE_REQUIRES_BATCH_OUT');analyze(args.batch_out,args.out or args.batch_out/'independent_fact_audit_v1')
