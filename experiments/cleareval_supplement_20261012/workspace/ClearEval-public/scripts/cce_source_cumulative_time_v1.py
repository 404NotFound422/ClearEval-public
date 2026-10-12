"""Bind an explicit source cumulative duration to its unique local operation.

This posthoc extraction repair retains the raw initial duration, recurrence
interval and cumulative total separately. It replaces, never adds, the initial
contribution only when the source block gives one unambiguous cumulative total.
"""
import copy,re
import cce_protocol_time_scope_v1 as scope
import cce_protocol_time_scope_v2 as phase_scope
import cce_source_local_wash_scope_v1 as wash_scope
g=scope.g
VERSION='source-local-cumulative-incubation-time-posthoc-v1'
FIRST=re.compile(r'^\s*(\d+)\.(\d+)\s+Incubation\s+with\s+([^,(;\n]+)',re.I)
TOTAL=re.compile(r'^\s*(\d+)\.(\d+)\s+Replace\s+([^;\n]+?)\s+every\s+([^;\n]+);\s*repeat\s+incubation\s+for\s+total\s+([^;\n]+?)\s*[.]?\s*$',re.I)
UNCERTAIN=re.compile(r'\b(?:additional|further|another|extra|optional(?:ly)?|if|unless|either|or|instead|not|without)\b',re.I)

def source_blocks(doc):
    blocks=[];units=doc['units']
    for index,u in enumerate(units):
        m=TOTAL.fullmatch(u['text'])
        if not m or UNCERTAIN.search(u['text']):continue
        previous_index=index-1
        while previous_index>=0 and not units[previous_index]['text'].strip():previous_index-=1
        if previous_index<0:continue
        first=units[previous_index];f=FIRST.match(first['text'])
        if not f or f[1]!=m[1] or int(f[2])+1!=int(m[2]) or f[3].strip()!=m[3].strip() or UNCERTAIN.search(first['text']):continue
        # More than one same-object antecedent in this numbered parent makes
        # the scope unresolved, even when one happens to be nearest.
        candidates=[]
        for earlier in reversed(units[:index]):
            top=scope.TOP.fullmatch(earlier['text'].strip().strip('*'))
            if top:break
            e=FIRST.match(earlier['text'])
            if e and e[1]==m[1] and e[3].strip()==m[3].strip():candidates.append(earlier)
        if len(candidates)!=1:continue
        total_text=m[5].strip().rstrip('.');interval_text=m[4].strip()
        total=g.duration_value(total_text);interval=g.duration_value(interval_text)
        if total.get('unique_hours') is None or interval.get('unique_hours') is None:continue
        start=u['start']+m.start(5);end=start+len(total_text)
        total_span={'unit_id':u['unit_id'],'start':start,'end':end,'quote':doc['text'][start:end]}
        start_i=u['start']+m.start(4);end_i=start_i+len(interval_text)
        interval_span={'unit_id':u['unit_id'],'start':start_i,'end':end_i,'quote':doc['text'][start_i:end_i]}
        if not(0<interval['unique_hours']<=total['unique_hours']):continue
        blocks.append({'initial_unit':copy.deepcopy(first),'continuation_unit':copy.deepcopy(u),
            'material_literal':f[3].strip(),'cumulative_span':total_span,'interval_span':interval_span,
            'cumulative_duration':total,'recurrence_interval':interval,
            'basis':'adjacent_numbered_same_object_repeat_incubation_explicit_total_no_additional_modifier'})
    return blocks

def derive_audit(original,doc):
    if original['source_binding']['answer_sha256']!=doc['answer_sha256'] or g.rawsha(doc['text'])!=doc['answer_sha256']:raise ValueError('SOURCE_IDENTITY_MISMATCH')
    audit=copy.deepcopy(original);changes=[]
    for block in source_blocks(doc):
        first,follow=block['initial_unit'],block['continuation_unit']
        matches=[o for o in audit['resolved']['operations'] if o['operation']['unit_id']==first['unit_id'] and o['operation']['quote'].strip()==first['text'].strip()]
        # An already returned continuation requires a different duplicate-count
        # policy; this adapter does not silently drop such a model record.
        if len(matches)!=1 or any(o['operation']['unit_id']==follow['unit_id'] for o in audit['resolved']['operations']):continue
        op=matches[0];old=op['parsed_duration'];total=block['cumulative_duration']
        if op['phase'] not in g.INCLUDE or op['execution_scope']!='initial' or op['repeat_count']!=1 or old.get('unique_hours') is None or total['unique_hours']<old['unique_hours']:continue
        if not op.get('duration_binding',{}).get('valid'):continue
        record={'operation_id':op['id'],'original_duration_ref':copy.deepcopy(op['duration']),
            'original_parsed_duration':copy.deepcopy(old),'derived_parsed_duration':copy.deepcopy(total),
            'source_block':copy.deepcopy(block),'aggregation':'replace_initial_contribution_with_cumulative_total_not_add',
            'model_raw_modified':False,'source_missing_extraction_repaired_posthoc':True}
        op['parsed_duration']=copy.deepcopy(total);op['source_cumulative_duration']=record
        for row in audit['inventory']:
            span=row['span']
            if row['kind']=='duration' and span['start']==block['cumulative_span']['start'] and span['end']==block['cumulative_span']['end']:
                record.setdefault('original_inventory_rows',[]).append(copy.deepcopy(row))
                row['coverage_state']='covered_time_evidence';row['posthoc_cumulative_block_binding']=op['id']
            elif row['kind']=='operation_record_lead' and span['unit_id']==follow['unit_id']:
                record.setdefault('original_inventory_rows',[]).append(copy.deepcopy(row))
                row['coverage_state']='covered_operation_record';row['posthoc_cumulative_block_binding']=op['id']
        changes.append(record)
    audit['posthoc_source_cumulative_time']={'version':VERSION,'changes':changes,'raw_modified':False,'original_time_score_function_changed':False}
    return audit,copy.deepcopy(audit['posthoc_source_cumulative_time'])

def apply_conversion(original,doc,case=None):
    """Composable source phase + cumulative projection; no scoring dependency."""
    conversion=copy.deepcopy(original)
    audit,phase_changes=phase_scope.derive_audit(original['source_audit'],doc)
    audit,wash_changes=wash_scope.derive_audit(audit,doc)
    audit,changes=derive_audit(audit,doc)
    audit['resolved']['timeline']['operation_ids']=[o['id'] for o in sorted(audit['resolved']['operations'],key=lambda x:x['operation']['start']) if o['phase'] in g.INCLUDE and o['execution_scope']=='initial']
    derived=phase_scope.project(audit)
    conversion['source_audit']=audit
    projection=conversion['legacy_projection']
    projection['time_calculation']=derived['time_calculation']
    projection['extraction']['clearing_total_time_hours']=derived['extraction']['clearing_total_time_hours']
    projection['component_input_state']['s_time']=derived['component_input_state']['s_time']
    conversion['legacy_runner_payload']['extraction']=copy.deepcopy(projection['extraction'])
    conversion['legacy_runner_content']=g.canonical(conversion['legacy_runner_payload'])
    conversion['posthoc_protocol_time_scope_processing']={'version':phase_scope.VERSION,'source_scope_changes':phase_changes,'raw_modified':False}
    conversion['posthoc_source_cumulative_time_processing']=changes
    conversion['posthoc_local_wash_backreference_processing']=wash_changes
    assert conversion['wire_payload']==original['wire_payload']
    for key in original['legacy_projection']['extraction']:
        if key!='clearing_total_time_hours':assert projection['extraction'][key]==original['legacy_projection']['extraction'][key]
    return conversion
