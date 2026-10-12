"""Read-only failure tracing; no repair, provider call, or frozen-output mutation."""
from pathlib import Path
import argparse,copy,hashlib,json,re,sys
from datetime import datetime,timezone
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_extraction_v1 as g
import evaluator_integrity as integrity
import cce_audit_grounded_facts_v1 as fact_checker
BASE=ROOT/'artifacts/cce_validation/optimizer_20261010'
BATCH=BASE/'grounded_development_v1';OUT=BASE/'grounded_failure_diagnostics_v1'
def require(ok,why):
    if not ok:raise ValueError(why)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def save(p,o):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def compact_span(s):return {k:s[k] for k in ['unit_id','start','end','answer_sha256']}|{'quote_sha256':g.rawsha(s['quote'])}

def relation_trace(payload,doc):
    ground=payload.get('grounded_extraction',{});entities={e['id']:e for e in ground.get('entities',[])};rows=[]
    for rel in ground.get('relations',[]):
        row={'relation_id':rel.get('id'),'declared_status':rel.get('status'),'endpoints':[]}
        try:evidence=g.resolve(rel['evidence'],doc);row['relation_evidence']=compact_span(evidence)
        except Exception as exc:row['evidence_error']=str(exc);rows.append(row);continue
        originals=[];local_usable=True
        for role,key in [('fluor','fluor_entity_id'),('target','target_entity_id')]:
            eid=rel.get(key);result={'role':role,'entity_id':eid,'id_declared':eid in entities}
            if eid not in entities:
                result['classification']='dangling_id_in_actual_return';local_usable=False;row['endpoints'].append(result);continue
            entity=entities[eid];result.update({'declared_kind':entity.get('kind'),'declared_usage':entity.get('usage')})
            try:name=g.resolve(entity['name'],doc)
            except Exception as exc:result['name_error']=str(exc);local_usable=False;row['endpoints'].append(result);continue
            result['complete_literal_name']=name['quote'];result['selected_entity_mention']=compact_span(name)
            result['selected_mention_inside_relation_evidence']=evidence['start']<=name['start'] and name['end']<=evidence['end']
            matches=[]
            for hit in re.finditer(re.escape(name['quote']),evidence['quote']):
                start=evidence['start']+hit.start();end=evidence['start']+hit.end();prior=doc['text'][max(0,start-8):start];after=doc['text'][end:evidence['end']]
                left_clipped=start>0 and bool(re.match(r'\w',doc['text'][start-1])) and bool(re.match(r'\w',name['quote'][0]))
                right_clipped=end<len(doc['text']) and bool(re.match(r'\w',doc['text'][end])) and bool(re.match(r'\w',name['quote'][-1]))
                anti_prefix=bool(re.search(r'anti[- ]$',prior,re.I)) and not name['quote'].lower().startswith('anti')
                numeric_suffix=bool(re.match(r'^\s+\d{2,4}\b(?!\s*[%％])',after))
                matches.append({'start':start,'end':end,'literal_name_sha256':g.rawsha(doc['text'][start:end]),
                    'exact_full_string':doc['text'][start:end]==name['quote'],'clipped_alphanumeric_boundary':left_clipped or right_clipped,
                    'additional_anti_qualifier':anti_prefix,'additional_numeric_suffix':numeric_suffix,
                    'mechanically_usable_same_full_identity':not(left_clipped or right_clipped or anti_prefix or numeric_suffix)})
            result['relation_local_literal_mentions']=matches
            usable=[m for m in matches if m['mechanically_usable_same_full_identity']]
            result['unique_relation_local_complete_mention']=len(usable)==1
            if not result['selected_mention_inside_relation_evidence'] and len(usable)==1:
                result['classification']='different_source_occurrence_same_complete_literal_available'
            elif result['selected_mention_inside_relation_evidence']:result['classification']='selected_occurrence_already_bound'
            else:result['classification']='no_unique_unqualified_same_identity_local_mention'
            local_usable=local_usable and len(usable)==1
            originals.append({**entity,'name':name});row['endpoints'].append(result)
        row['cross_mention_literal_link_possible_without_rewriting_raw']=local_usable
        if local_usable and len(originals)==2:
            allentities=[]
            for ent in entities.values():
                try:allentities.append({**ent,'name':g.resolve(ent['name'],doc)})
                except Exception:pass
            allowed,why=g.lexical_relation(originals[0]['name']['quote'],originals[1]['name']['quote'],evidence,allentities)
            row['existing_separate_lexical_relation_gate']={'allowed':allowed,'reason':why,
                'probe_scope':'Only this relation rule on source-resolved names. No altered conversion, score, or successful trial is generated.'}
        row['semantic_coreference_or_target_truth_confirmed']=False;rows.append(row)
    return rows

def scan_spans(payload,doc):
    checks=[]
    def walk(x,path):
        if isinstance(x,dict):
            if set(x)=={'unit_id','quote','occurrence'}:
                try:r=g.resolve(x,doc);checks.append({'path':path,'resolved':True,**compact_span(r)})
                except Exception as exc:checks.append({'path':path,'resolved':False,'error':str(exc),'requested_unit_id':x.get('unit_id'),'quote_sha256':g.rawsha(x.get('quote',''))})
            else:
                for k,v in x.items():walk(v,path+'.'+k)
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,path+'['+str(i)+']')
    walk(payload,'$');return checks

def duration_fields_trace(payload,doc,fact):
    """Independent field diagnostics even when an earlier relation aborts convert.

    No recovered/modified payload is sent to the old runner. The independent
    numeric parser only diagnoses facts retained in raw spans.
    """
    ground=payload.get('grounded_extraction',{});rows=[]
    for op in ground.get('operations',[]):
        row={'operation_id':op.get('id'),'declared_phase':op.get('phase'),'declared_execution_scope':op.get('execution_scope'),
            'listed_in_timeline':op.get('id') in ground.get('timeline',{}).get('operation_ids',[])}
        try:
            operation=g.resolve(op['operation'],doc)
            if op.get('duration') is None:row.update({'duration_supplied':False,'current_duration_parser':{'state':'missing','unique_hours':None}})
            else:
                duration=g.resolve(op['duration'],doc);parsed=g.duration_value(duration['quote'])
                row.update({'duration_supplied':True,'duration_span':compact_span(duration),'duration_exact_quote':duration['quote'],
                    'duration_inside_operation':operation['start']<=duration['start'] and duration['end']<=operation['end'],
                    'operation_and_duration_same_source_unit':operation['unit_id']==duration['unit_id'],
                    'current_duration_parser':parsed,'independent_numeric_unit_hours':fact_checker.source_hours(duration['quote']),
                    'time_field_prefix_present':bool(re.match(r'^\s*Time\s*[:：]',duration['quote'],re.I)),
                    'non_numeric_prefix_blocks_current_fullmatch':parsed['state']=='unsupported_duration_expression' and fact_checker.source_hours(duration['quote']) is not None})
        except Exception as exc:row['source_or_duration_error']=str(exc)
        rows.append(row)
    components=[]
    for comp in fact['time']['components']:
        expected=comp['duration_span'];matches=[]
        for row in rows:
            s=row.get('duration_span')
            if s and expected['start']<=s['start'] and s['end']<=expected['end']:
                matches.append({'operation_id':row['operation_id'],'source_span_retained':True,
                    'source_numeric_hours_equal_inventory':fact_checker.same(row['independent_numeric_unit_hours'],comp['hours']),
                    'current_fullmatch_unique_hours':row['current_duration_parser']['unique_hours'],
                    'current_fullmatch_equals_inventory':fact_checker.same(row['current_duration_parser']['unique_hours'],comp['hours']),
                    'phase':row['declared_phase'],'execution_scope':row['declared_execution_scope'],
                    'listed_in_timeline':row['listed_in_timeline'],'duration_inside_operation':row['duration_inside_operation'],
                    'operation_and_duration_same_source_unit':row['operation_and_duration_same_source_unit']})
        components.append({'inventory_step_label':comp['step_label'],'inventory_hours':comp['hours'],
            'inventory_duration_span':expected,'matching_raw_operations':matches,
            'literal_source_numeric_component_retained':any(m['source_numeric_hours_equal_inventory'] for m in matches),
            'current_fullmatch_component_retained':any(m['current_fullmatch_equals_inventory'] for m in matches),
            'v1_strict_operation_containment_pass':any(m['source_numeric_hours_equal_inventory'] and m['duration_inside_operation'] for m in matches)})
    known=[c for c in components if c['literal_source_numeric_component_retained']]
    return {'operations':rows,'initial_core_components':components,'expected_initial_core_components':len(components),
        'literal_source_numeric_core_components_retained':len(known),'current_fullmatch_core_components_retained':sum(c['current_fullmatch_component_retained'] for c in components),
        'retained_known_initial_component_sum_hours':sum(c['inventory_hours'] for c in known) if known else None,
        'inventory_initial_component_sum_hours':fact['time']['computed_sum_hours'],
        'all_known_initial_components_still_present_in_raw':len(known)==len(components),
        'strict_operation_containment_core_components':sum(c['v1_strict_operation_containment_pass'] for c in components),
        'timeline_excluded_phase_ids':[r['operation_id'] for r in rows if r['listed_in_timeline'] and r['declared_phase'] in g.EXCLUDE],
        'timeline_noninitial_scope_ids':[r['operation_id'] for r in rows if r['listed_in_timeline'] and r['declared_execution_scope']!='initial'],
        'current_fullmatch_prefix_failure_count':sum(bool(r.get('non_numeric_prefix_blocks_current_fullmatch')) for r in rows),
        'diagnostic_scope':'Raw source fields only. Literal numeric retention does not require passing the separate v1 operation-quote containment gate; both are reported. Independent unit parsing is not a corrected conversion, an EGES input, or a scientific duration gold.'}

def remaining_fields_trace(payload,doc,fact):
    ground=payload.get('grounded_extraction',{});entities=[];ri=[];edges=[];operations={}
    for entity in ground.get('entities',[]):
        try:entities.append({**entity,'name':g.resolve(entity['name'],doc)})
        except Exception:pass
    for op in ground.get('operations',[]):
        try:operations[op['id']]=g.resolve(op['operation'],doc)
        except Exception:pass
    for row in ground.get('ri_mentions',[]):
        entry={'id':row['id'],'declared_role':row['role']}
        try:
            span=g.resolve(row['value'],doc);quote=span['quote'];entry['span']=compact_span(span);entry['exact_quote']=quote
            current=float(quote.strip()) if re.fullmatch(g.NUMBER,quote.strip()) else None
            labelled=re.fullmatch(r'\s*(?:RI|refractive\s+index|折射率)\s*(?:=|:|：|≈|~)?\s*('+g.NUMBER+r')\s*',quote,re.I)
            entry.update({'current_v1_numeric_projection':current,'literal_RI_labelled_unique_number':float(labelled[1]) if labelled else None,
                'source_RI_present_but_current_projection_cannot_parse':current is None and labelled is not None})
        except Exception as exc:entry['error']=str(exc)
        ri.append(entry)
    for row in ground.get('precedence_edges',[]):
        a,b=row['before_id'],row['after_id'];entry={'before_id':a,'after_id':b,'ids_exist':a in operations and b in operations}
        if entry['ids_exist']:
            entry.update({'before_operation_span':compact_span(operations[a]),'after_operation_span':compact_span(operations[b]),
                'direction_agrees_with_document_order':operations[a]['start']<operations[b]['start']})
        try:
            ev=g.resolve(row['evidence'],doc);entry['evidence_span']=compact_span(ev)
            entry['explicit_order_cue_in_quote']=bool(re.search(r'\bbefore\b|\bafter\b|\bthen\b|\bnext\b|followed by|之后|之前|然后',ev['quote'],re.I))
        except Exception as exc:entry['evidence_error']=str(exc)
        entry['scientific_dependency_proved']=False;edges.append(entry)
    names=fact_checker.name_audit(fact['explicit_names_to_retain'],entities)
    return {'raw_names_literal_inventory_diagnostic':names,'RI_fields':ri,'precedence_edges':edges,
        'backward_document_order_edges':sum(e.get('direction_agrees_with_document_order') is False for e in edges),
        'scope':'Actual raw field diagnosis despite rejected full conversion. No projected score or scientific dependency is produced.'}

def analyze():
    OUT.mkdir(parents=True,exist_ok=True);matrix=read(BATCH/'matrix.json');cases={c['anonymous_answer_id']:c for c in read(BATCH/'cases.json')['cases']};traces=[];pending=[]
    protected=[Path(g.__file__),ROOT/'scripts/cce_audit_grounded_facts_v1.py',g.OUT/'plan.json',g.OUT/'schema.json',BASE/'fact_audit_checker_v1/freeze.json']
    before={str(p):sha(p) for p in protected}
    inventory,_,_=fact_checker.verify_inventory();facts={c['anonymous_answer_id']:c for c in inventory['cases']}
    for cell in matrix:
        aid=cell['anonymous_answer_id'];trial_id=cell['planned_trial_id'];path=BATCH/'run/trials'/f'{trial_id}.json'
        if not path.exists():pending.append(aid);continue
        t=read(path);require(t['identity']==cell['identity'],'TRIAL_IDENTITY_MISMATCH')
        if t['status']!='failed':
            traces.append({'anonymous_answer_id':aid,'trial_id':trial_id,'status':t['status'],'failure_analysis_not_applicable':True,'inputs':[bind(path)]});continue
        case=cases[aid];doc=g.document(case['model_response'],case['case_id']);attempt=BATCH/'run/attempts'/f'{trial_id}_1';provider=attempt/'provider_response.json';receipt=attempt/'request_receipt.json'
        errors=(t.get('evaluation',{}).get('grounded_extraction_v1') or {}).get('conversion_errors')
        trace={'anonymous_answer_id':aid,'trial_id':trial_id,'status':t['status'],'recorded_conversion_errors':errors,
            'inputs':[bind(path),bind(receipt),bind(BATCH/'cases.json'),bind(BATCH/'matrix.json')],
            'unchanged_module_sha256':sha(g.__file__),'diagnostic_does_not_repair_or_rescore':True}
        if provider.exists():
            trace['inputs'].append(bind(provider));body=read(provider);raw=body.get('response','');trace['raw_response_sha256']=g.rawsha(raw)
            try:payload=integrity.parse_judge_object(raw)
            except Exception as exc:trace['strict_parse']={'pass':False,'error':str(exc)}
            else:
                trace['strict_parse']={'pass':True}
                try:g.convert(raw,doc)
                except Exception as exc:
                    trace['reproduced_conversion_error']={'type':type(exc).__name__,'reason':str(exc)}
                    require(not errors or any(e['reason']==str(exc) for e in errors),'FAILURE_DID_NOT_REPRODUCE')
                else:trace['conversion_now_succeeded_unexpectedly']=True
                try:g.validate_shape(payload,g.schema());trace['schema_shape_pass']=True
                except Exception as exc:trace['schema_shape_pass']=False;trace['schema_shape_error']=str(exc)
                trace['span_checks']=scan_spans(payload,doc)
                trace['relations']=relation_trace(payload,doc)
                trace['duration_field_diagnostics']=duration_fields_trace(payload,doc,facts[aid])
                trace['duration_inventory_binding']=bind(fact_checker.INVENTORY)
                trace['remaining_field_diagnostics']=remaining_fields_trace(payload,doc,facts[aid])
        p=OUT/'traces'/f'{aid}.json'
        if p.exists() and read(p)!=trace:
            previous=read(p);require(all(k in trace and trace[k]==v for k,v in previous.items() if k!='duration_field_diagnostics'),'EXISTING_FAILURE_TRACE_FACT_CHANGED')
            save(OUT/'relation_only_snapshots'/f'{aid}_{sha(p)}.json',previous)
        save(p,trace)
        traces.append(trace)
    failures=[t for t in traces if t['status']=='failed'];summary={'status':'complete' if not pending else 'partial_actual_trials',
        'completed_trials':len(traces),'actual_failed_trials':len(failures),'pending_ids':pending,
        'recorded_error_reasons':[{'id':t['anonymous_answer_id'],'errors':t.get('recorded_conversion_errors')} for t in failures],
        'source_span_failures':sum(sum(not s['resolved'] for s in t.get('span_checks',[])) for t in failures),
        'failure_traces':[bind(OUT/'traces'/f"{t['anonymous_answer_id']}.json") for t in failures],
        'new_provider_calls':0,'new_scoring_results':0,'expert_labels_created':0,'frozen_files_unchanged':all(sha(p)==h for p,h in before.items()),
        'protected_sha256':before,'actual_command':[sys.executable,*sys.argv],'script_sha256':sha(__file__)}
    require(summary['frozen_files_unchanged'],'FROZEN_FILES_CHANGED')
    save(OUT/f'summary_{len(traces)}of5.json',summary);save(OUT/'summary.json',summary)
    lines=['# Grounded v1 failure trace','',f"Completed {len(traces)}/5; failures {len(failures)}. This is read-only diagnosis, not repaired output or a successful score.",'']
    for t in failures:
        lines.append('## '+t['anonymous_answer_id']);lines.append('')
        lines.append('Recorded and reproduced error: `'+str(t.get('reproduced_conversion_error',{}).get('reason',t.get('recorded_conversion_errors')))+'`.')
        for r in t.get('relations',[]):
            for e in r['endpoints']:
                lines.append('- '+r['relation_id']+' / '+e['role']+': '+e.get('classification','unresolved')+'.')
            if r.get('existing_separate_lexical_relation_gate'):
                q=r['existing_separate_lexical_relation_gate'];lines.append('- Separate lexical relationship gate: '+str(q['allowed'])+' (`'+q['reason']+'`). A cross-mention identity fix alone therefore does not establish complete conversion or scientific correctness.')
        if t.get('duration_field_diagnostics'):
            d=t['duration_field_diagnostics'];lines.append('- Raw initial components retained: '+str(d['literal_source_numeric_core_components_retained'])+'/'+str(d['expected_initial_core_components'])+'; current duration fullmatch retains '+str(d['current_fullmatch_core_components_retained'])+'. Prefix-related parser failures: '+str(d['current_fullmatch_prefix_failure_count'])+'.')
            lines.append('- Excluded-phase IDs in initial timeline: '+str(d['timeline_excluded_phase_ids'])+'; noninitial scope IDs: '+str(d['timeline_noninitial_scope_ids'])+'. These are diagnostics only; no repaired total or score is produced.')
        lines.append('')
    lines+=['## Next-version proposal (not implemented here)','',
        '- Keep immutable entity primary spans. A relation can instead carry relation-local mention IDs or exact offsets; require the same complete identity, preserved qualifiers/numeric suffixes, source bounds and an unambiguous local occurrence. Save the derived link beside raw data, never move the header span in the raw response.',
        '- Permit a nullable target for explicitly unknown/ambiguous relations, or a separate unresolved-endpoint record. Such records must never project guessed targets. A literal `unknown` ID remains invalid when it is not declared. The current schema offers uncertainty flags but cannot express an absent relation endpoint directly.',
        '- Prefer source-candidate IDs when copied spans fail. Reject wrong IDs or ambiguous resolution; do not introduce fuzzy quote correction.',
        '- Keep relation lexical policy separate from mention identity. A string occurrence passing does not prove the target relationship. Preserve known entities and time components even if one relationship cannot be projected.',
        '- Wait for all five failure classes before proposing one versioned intervention. No frozen v1 module, checker, raw provider response, score, or human label is changed.','']
    (OUT/'README.md').write_text('\n'.join(lines),encoding='utf8')
    log=OUT/'execution_commands.json';logs=read(log) if log.exists() else [];logs.append({'utc':datetime.now(timezone.utc).isoformat(),'command':[sys.executable,*sys.argv],'summary_sha256':sha(OUT/'summary.json'),'new_provider_calls':0});save(log,logs)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['failure_traces','protected_sha256']},ensure_ascii=True))

if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();analyze()
