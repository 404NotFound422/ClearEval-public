"""Build a source-bound core-incubation ledger from saved operation records.

The model's original records remain intact. Source scope, explicit Time fields,
repetitions and alternatives are interpreted in a separate candidate ledger.
No missing duration is replaced with zero and no scenario is selected by score.
"""
from __future__ import annotations
import copy,itertools,re
import cce_grounded_extraction_v11 as ground
import cce_reported_operation_scope_v1 as scopes
import cce_time_heading_scope_v1 as headings
b=scopes.b
VERSION='source-time-ledger-v1.2'
TIME=re.compile(r'\bTime\s*[:：]\s*([^\n,，;；)）]*)',re.I)
OPTIONAL=re.compile(r'\bif\b|\boptional\b|\bwhen needed\b|\bas needed\b|如果|若需|如需|可选',re.I)
UNTIMED_HANDLING=re.compile(r'\b(?:remove|aspirat\w*|label\s+vials|verify\s+optical)\b|吸去|吸除|移除|检查透明',re.I)
DWELL=re.compile(r'incubat|equilibrat|浸泡|孵育|静置|平衡|continue|继续',re.I)
POSTFIX_WASH=re.compile(r'post[- ]fixation\s+wash|去除残余固定|洗去.*固定',re.I)
WASH=re.compile(r'\bwash(?:es|ing)?\b|洗涤|清洗',re.I)
PREP=re.compile(scopes.PREP_HEADING.pattern+r'|核染',re.I)
CORE_ACTION=re.compile(r'\b(?:re[- ]?hydrat\w*|re[- ]?dehydrat\w*)\b|再脱水|再次脱水|重新脱水|复水',re.I)
REPEAT_WORD={'once':1,'twice':2,'one':1,'two':2,'three':3,'four':4,'一':1,'二':2,'两':2,'三':3}


def source_span(doc,unit,start=None,end=None):
    start=unit['start'] if start is None else start;end=unit['end'] if end is None else end
    return {'unit_id':unit['unit_id'],'start':start,'end':end,'quote':doc['text'][start:end],
            'answer_sha256':doc['answer_sha256']}


def phase(op,doc):
    span=op['operation'];unit=next(u for u in doc['units'] if u['unit_id']==span['unit_id'])
    history=scopes.preceding_heading(doc,span);heading=history[-1] if history else None
    title=heading['title'] if heading else ''
    # "Pre-clearing immunostaining" names labeling performed before clearing.
    # It is not a dual-purpose clearing stage merely because it contains clearing.
    clean=re.sub(r'\b(?:pre|post)[- ]clearing\b|\bbefore\s+(?:organic\s+solvent\s+)?(?:clearing|steps)\b|透明前|透明后','',title,flags=re.I)
    prep=bool(PREP.search(clean) and not scopes.CORE_HEADING.search(clean))
    text=unit['text']
    if op['phase'] in ground.EXCLUDE and CORE_ACTION.search(text):
        return {'role':'core','basis':'one saved labeling record also contains an explicit core reagent transition; its duration must be separated',
            'mixed_duration_scope':True,'heading':heading}
    if op['phase'] in ground.EXCLUDE:
        return {'role':'excluded','basis':'saved explicit excluded phase','original_phase':op['phase'],'heading':heading}
    if POSTFIX_WASH.search(title+' '+text) and headings.BUFFER.search(text):
        return {'role':'excluded','basis':'explicit routine post-fixation buffer wash','heading':heading}
    if prep and not CORE_ACTION.search(text):
        return {'role':'excluded','basis':'source labeling/preparation heading','heading':heading}
    if op['phase']=='reagent_transition_wash':
        if WASH.search(title):
            for earlier in reversed(history[:-1]):
                if WASH.search(earlier['title']):continue
                if PREP.search(earlier['title']) and not scopes.CORE_HEADING.search(earlier['title']):
                    return {'role':'excluded','basis':'wash section within explicit antibody/labeling sequence, including repeat-only records',
                        'heading':heading,'preceding_phase_heading':earlier}
                break
        support=scopes.preparation_evidence(op,doc)
        if support.get('supported') and headings.BUFFER.search(text):
            return {'role':'excluded','basis':'routine wash within explicit labeling sequence','heading_support':support}
    if op['phase'] in ground.INCLUDE:
        if not TIME.search(text) and UNTIMED_HANDLING.search(text) and not DWELL.search(text):
            return {'role':'untimed_handling','basis':'explicit handling without an incubation or equilibration duration; elapsed handling time not estimated','heading':heading}
        return {'role':'core','basis':'saved core phase, reconciled with explicit source heading','heading':heading}
    if UNTIMED_HANDLING.search(text) and not DWELL.search(text):
        return {'role':'untimed_handling','basis':'untimed non-incubation action','heading':heading}
    return {'role':'unknown','basis':'source does not resolve saved unknown phase','heading':heading}


def parse_field(field):
    """Finite ranges are midpoint conventions; disjunctions stay alternatives."""
    if re.search(r'\bat least\b|\bat most\b|\bup to\b|\bmore than\b|\bless than\b|[≤≥<>]|至少|至多|不超过',field,re.I):
        return {'options':[],'issue':'one_sided_duration_bound_has_no_declared_midpoint','field':field}
    options=[];segments=re.split(r'\s+or\s+|或者|或',field,flags=re.I)
    for i,segment in enumerate(segments):
        matches=list(ground.DURATION.finditer(segment))
        # overnight (ON) is one duration expression, not two incubations.
        if len(matches)>1 and all(m[1] is None for m in matches):matches=matches[:1]
        if len(matches)!=1:return {'options':[],'issue':'unparsed_or_multiple_Time_field_durations','field':field}
        m=matches[0];value=ground.duration_value(m[0],8)
        prefix=segment[:m.start()]
        mult=re.search(r'(\d+)\s*[×x*]\s*$',prefix,re.I)
        count=int(mult[1]) if mult else 1
        if count<1:return {'options':[],'issue':'nonpositive_repeat_count','field':field}
        bounds=value['bounds_hours']
        if bounds is None:return {'options':[],'issue':'unknown_Time_field_duration','field':field}
        options.append({'option_id':'field_'+str(i),'bounds_hours':bounds,'count':count,
            'literal':m[0],'expression':segment,'count_in_field':bool(mult),
            'overnight_default':not value.get('source_numeric',True),
            'each_in_field':bool(re.search(r'\beach\b|每',segment,re.I))})
    return {'options':options,'field':field,'issue':None,'disjunction':len(options)>1}


def repeat_interpretation(text,option):
    if option['count_in_field']:return {'count':option['count'],'basis':'multiplication explicitly in Time field'}
    if re.search(r'\btotal\b|总(?:计|共|洗涤|时间|孵育)|合计',text,re.I) and not option['each_in_field']:
        return {'count':1,'basis':'Time field states total duration; no second multiplication'}
    m=re.search(r'\brepeat(?:ed)?\s+(once|twice|one|two|three|four|\d+)(?:\s+times)?\b',text,re.I)
    if m:
        number=int(m[1]) if m[1].isdigit() else REPEAT_WORD[m[1].lower()]
        return {'count':number+1,'basis':'literal initial incubation plus stated additional repeats',
                'source_literal':m[0],'alternative_total_count_sensitivity':number if number>1 else None}
    m=re.search(r'重复[^。；;()（）]{0,25}?共\s*(\d+)\s*次',text)
    if not m:m=re.search(r'(?:洗涤|清洗|重复)\s*(\d+)\s*次',text)
    if m:return {'count':int(m[1]),'basis':'explicit total count','source_literal':m[0]}
    if option['each_in_field']:
        return {'count':None,'basis':'per-repeat duration without a numeric count'}
    if re.search(r'\brepeat\s+(?:steps?\s*)?\d+\.\d+|重复\s*\d+\.\d+',text,re.I):
        return {'count':None,'basis':'cross-step repetition needs source reference expansion'}
    return {'count':1,'basis':'one separately represented timed operation; again is not itself an optional branch'}


def parent_Time(op,doc,original,mapping,operations,roles):
    if not (original and mapping):return None
    uid=op['operation']['unit_id'];mapped=next(u for u in mapping['evaluation_units_to_original'] if u['evaluation_unit_id']==uid)
    if len(mapped['original_unit_ids'])!=1:return None
    oid=mapped['original_unit_ids'][0];parent=next(u for u in original['units'] if u['unit_id']==oid)
    members={u['evaluation_unit_id'] for u in mapping['evaluation_units_to_original'] if oid in u['original_unit_ids']}
    relevant=[o for o in operations if o['operation']['unit_id'] in members]
    core=[o for o in relevant if roles[o['id']]['role']=='core']
    fields=list(TIME.finditer(parent['text']))
    storage=[o for o in relevant if o['phase']=='storage']
    if len(core)==1 and core[0]['id']==op['id'] and storage and len(fields)==1:
        return {'field':fields[0][1],'source':source_span(original,parent),
            'rule':'one original numbered step with one timed core incubation and a continuing storage clause; count the single Time field once',
            'original_step_id':oid,'canonical_child_ids':sorted(members)}
    return None


def duration_options(op,doc,original,mapping,operations,roles):
    unit=next(u for u in doc['units'] if u['unit_id']==op['operation']['unit_id']);text=unit['text']
    if roles[op['id']].get('mixed_duration_scope'):
        return {'options':[],'issue':'combined_labeling_and_core_transition_duration_unreported','source':source_span(doc,unit)}
    cumulative=op.get('source_cumulative_duration')
    if cumulative:
        block=cumulative['source_block'];span=block['cumulative_span']
        b.verify_span(doc['text'],span)
        for key in ['initial_unit','continuation_unit']:
            u=block[key];assert doc['text'][u['start']:u['end']]==u['text']
        assert cumulative['aggregation']=='replace_initial_contribution_with_cumulative_total_not_add'
        bounds=ground.duration_value(span['quote'],8)['bounds_hours']
        assert bounds==block['cumulative_duration']['bounds_hours']==op['parsed_duration']['bounds_hours']
        return {'options':[{'option_id':'source_cumulative_total','bounds_hours':bounds,'count':1,
            'source':{**span,'answer_sha256':doc['answer_sha256']},
            'basis':'reuse the source-verified cumulative continuation total; replace initial duration, do not add recurrence intervals',
            'source_cumulative_duration':copy.deepcopy(cumulative),'repeat_interpretation':{'count':1,'basis':'explicit cumulative total'}}],
            'issue':None,'source':span,'basis':'retained source-bound cumulative duration'}
    fields=list(TIME.finditer(text));parent=None
    if len(fields)>1:
        # A model can cite one action within a merged source unit.
        fields=[m for m in fields if op['operation']['start']<=unit['start']+m.start() and unit['start']+m.end()<=op['operation']['end']]
    if len(fields)==1:
        parsed=parse_field(fields[0][1]);field_source=source_span(doc,unit,unit['start']+fields[0].start(),unit['start']+fields[0].end())
        basis='explicit source Time field'
    elif not fields and (parent:=parent_Time(op,doc,original,mapping,operations,roles)):
        parsed=parse_field(parent['field']);field_source=parent['source'];basis=parent['rule']
    elif not fields and op.get('duration'):
        parsed=parse_field(op['duration']['quote']);field_source=op['duration'];basis='saved source-bound operation duration without a Time field'
    else:
        return {'options':[],'issue':'missing_or_unbound_operation_duration','source':source_span(doc,unit),'field_count':len(fields)}
    if parsed['issue']:return {**parsed,'source':field_source,'basis':basis}
    options=[]
    for option in parsed['options']:
        repeat=repeat_interpretation(text,option)
        if repeat['count'] is None:return {'options':[],'issue':'unresolved_repeat','repeat':repeat,'source':field_source}
        options.append({**option,'count':repeat['count'],'repeat_interpretation':repeat,'source':field_source,'basis':basis})
    prose=[]
    for m in ground.DURATION.finditer(text[:fields[0].start()] if len(fields)==1 else text):
        role,_=ground.duration_role(m[0],text[max(0,m.start()-80):m.start()],text[m.end():m.end()+120])
        if role!='duration':continue
        value=ground.duration_value(m[0],8)
        prose.append({'literal':m[0],'bounds_hours':value['bounds_hours'],'source_numeric':value.get('source_numeric',False),
            'source':source_span(doc,unit,unit['start']+m.start(),unit['start']+m.end())})
    conflicts=[]
    if len(options)==1 and options[0].get('count',1)==1:
        field_bounds=options[0]['bounds_hours']
        for item in prose:
            if not item['source_numeric'] or item['bounds_hours'] is None:continue
            lo,hi=item['bounds_hours']
            if hi<field_bounds[0] or field_bounds[1]<lo:conflicts.append(item)
        # Retain both source readings when they actually disagree; no fabricated
        # average across incompatible statements, and no score-based selection.
        for item in conflicts:
            if item['bounds_hours'] not in [o['bounds_hours'] for o in options]:
                options.append({'option_id':'conflicting_prose_'+str(len(options)),'bounds_hours':item['bounds_hours'],'count':1,
                    'source':item['source'],'basis':'explicit prose conflicts with Time field; separate conditional reading',
                    'repeat_interpretation':{'count':1,'basis':'single source duration'}})
    return {'options':options,'issue':None,'source':field_source,'basis':basis,'original_parent_context':parent,
        'point_convention':'midpoint within each explicit finite range; no averaging across alternative routes',
        'prose_numeric_mentions':prose,'conflicting_prose_readings':conflicts,
        'explicit_field_precedence_declared':bool(fields or parent)}


def source_title(item,conversion,doc):
    span=item['span'];unit=next(u for u in doc['units'] if u['unit_id']==span['unit_id'])
    titles=scopes.preceding_heading(doc,{'start':unit['end']})
    if not any(t['start']==unit['start'] for t in titles):
        return headings.title_evidence(item,conversion,doc)
    after=scopes.preceding_heading(doc,{'start':len(doc['text'])+1})
    end=next((t['start'] for t in after if t['start']>=unit['end']),len(doc['text']))
    children=[o for o in conversion['source_audit']['resolved']['operations'] if unit['end']<=o['operation']['start']<end]
    leads=[x for x in conversion['source_audit']['inventory'] if x['kind']=='operation_record_lead' and unit['end']<=x['span']['start']<end]
    represented=all(any(o['operation']['unit_id']==x['span']['unit_id'] for o in children) for x in leads)
    return {'supported':bool(children) and represented,'reason':'source_phase_title_with_recorded_action_children',
            'source':source_span(doc,unit),'child_operation_ids':[o['id'] for o in children]}


def build(conversion,doc,original=None,mapping=None):
    audit=conversion['source_audit'];source=audit['resolved'];operations=source['operations']
    roles={op['id']:phase(op,doc) for op in operations};entries=[];issues=[]
    if source['timeline']['mode']!='serial':issues.append({'kind':'source_schedule_not_serial','mode':source['timeline']['mode']})
    for op in operations:
        unit=next(u for u in doc['units'] if u['unit_id']==op['operation']['unit_id'])
        b.verify_span(doc['text'],op['operation'])
        record={'operation_id':op['id'],'source':source_span(doc,unit),'raw_phase':op['phase'],
            'raw_execution_scope':op['execution_scope'],'raw_parsed_duration':op.get('parsed_duration'),
            'raw_repeat_count':op.get('repeat_count'),'scope':roles[op['id']]}
        if record['scope']['role']=='unknown':issues.append({'kind':'unknown_operation_scope','operation_id':op['id']})
        if record['scope']['role']=='core':
            duration=duration_options(op,doc,original,mapping,operations,roles);record['duration']=duration
            if duration['issue']:issues.append({'kind':duration['issue'],'operation_id':op['id']})
            heading=record['scope'].get('heading') or {}
            optional=OPTIONAL.search(unit['text']);heading_optional=OPTIONAL.search(heading.get('title',''))
            if optional or heading_optional:
                record['branch_group']='heading:'+str(heading['start']) if heading_optional else 'operation:'+op['id']
                record['branch_source']=heading if heading_optional else source_span(doc,unit)
            else:record['branch_group']=None
        entries.append(record)
    # Explicit action candidates outside every saved operation remain visible.
    unrepresented=[]
    for item in audit['inventory']:
        if item['kind']!='operation_record_lead' or item['coverage_state']=='covered_operation_record':continue
        title=source_title(item,conversion,doc)
        if not title['supported']:unrepresented.append({'candidate':item,'title_check':title})
    if unrepresented:issues.append({'kind':'unrepresented_source_action_candidates','records':unrepresented})
    core=[r for r in entries if r['scope']['role']=='core']
    if not core:issues.append({'kind':'no_reported_core_incubations'})
    groups=sorted({r['branch_group'] for r in core if r.get('branch_group')})
    dimensions=[('branch:'+g,[False,True]) for g in groups]
    dimensions += [('duration:'+r['operation_id'],list(range(len(r['duration']['options'])))) for r in core if len(r['duration']['options'])>1]
    scenarios=[]
    for number,values in enumerate(itertools.product(*(options for _,options in dimensions))):
        selection=dict(zip([name for name,_ in dimensions],values));parts=[];unknown=[];omitted=[]
        for r in core:
            if r['branch_group'] and not selection['branch:'+r['branch_group']]:omitted.append(r['operation_id']);continue
            options=r['duration']['options']
            if not options:unknown.append(r['operation_id']);continue
            option=options[selection.get('duration:'+r['operation_id'],0)]
            parts.append({'operation_id':r['operation_id'],'option_id':option['option_id'],'bounds_hours':[x*option['count'] for x in option['bounds_hours']],
                'repeat_count':option['count'],'duration_bounds_hours':option['bounds_hours'],'source':option['source']})
        bounds=[sum(p['bounds_hours'][i] for p in parts) for i in [0,1]]
        global_issues=[x for x in issues if 'operation_id' not in x or x['operation_id'] not in omitted]
        complete=bool(parts) and not unknown and not global_issues
        scenarios.append({'scenario_id':f'S{number:03d}','selection':selection,'contributions':parts,'omitted_core_operations':omitted,
            'unknown_duration_operations':unknown,'issues':global_issues,'known_subtotal_bounds_hours':bounds,
            'bounds_hours':bounds if complete else None,'hours':sum(bounds)/2 if complete else None})
    primary=scenarios[0]['hours'] if len(scenarios)==1 else None
    return {'version':VERSION,'answer_sha256':doc['answer_sha256'],'operations':entries,'issues':issues,'scenarios':scenarios,
        'hours':primary,'single_unbranched_point':len(scenarios)==1 and primary is not None,
        'conditional_group_count':len(groups),'schedule_convention':'sum reported serial core incubation durations',
        'elapsed_laboratory_time_claimed':False,'model_raw_modified':False,'new_model_calls':0,
        'selection_uses_achieved_score':False,'expert_validated':False}
