"""Resolve a source-explicit wash backreference inside one labeling section."""
import copy,re
import cce_protocol_time_scope_v2 as phase
VERSION='source-numbered-local-label-wash-backreference-v1'
REPEAT=re.compile(r'^\s*(\d+)\.(\d+)\s+Repeat\s+step\s+(\d+)\.(\d+)\s*\(\s*Wash\s*\)',re.I)
NUMBER=re.compile(r'^\s*(\d+)\.(\d+)\s+')

def derive_audit(original,doc):
    audit=copy.deepcopy(original);changes=[];ops=audit['resolved']['operations']
    for repeated in ops:
        span=repeated['operation'];m=REPEAT.match(span['quote'])
        if not m or m[1]!=m[3] or int(m[4])>=int(m[2]):continue
        if phase.CORE.search(span['quote']) or phase.UNCERTAIN.search(span['quote']):continue
        unit=next(u for u in doc['units'] if u['unit_id']==span['unit_id'])
        if span['quote'].strip()!=unit['text'].strip():continue
        section=phase.section(doc,span)
        if not section or not phase.LABEL.search(section['title']['text']):continue
        source_targets=[u for u in section['body'] if (n:=NUMBER.match(u['text'])) and n[1]==m[3] and n[2]==m[4]]
        if len(source_targets)!=1:continue
        target=source_targets[0]
        if not target['start']<span['start'] or not phase.PBS.search(target['text']) or phase.CORE.search(target['text']) or phase.UNCERTAIN.search(target['text']):continue
        preceding=section['body'][:section['body'].index(target)]
        if not any(re.search(r'antibod|immuno',u['text'],re.I) and re.search(r'incubat|stain|label',u['text'],re.I) for u in preceding):continue
        returned=[o for o in ops if o['operation']['unit_id']==target['unit_id'] and o['operation']['quote'].strip()==target['text'].strip()]
        if len(returned)!=1:continue
        for op in [returned[0],repeated]:
            if op['phase']=='routine_wash':continue
            changes.append({'operation_id':op['id'],'original_phase':op['phase'],'derived_phase':'routine_wash',
                'basis':'explicit_Wash_numbered_backreference_within_same_source_labeling_section',
                'evidence':copy.deepcopy([section['title'],*preceding,target,unit]),
                'raw_duration_and_repeat_count_unchanged':True})
            op['phase']='routine_wash'
    audit['posthoc_local_wash_backreference']={'version':VERSION,'changes':changes,'repeat_count_inferred':False,'raw_modified':False}
    return audit,copy.deepcopy(audit['posthoc_local_wash_backreference'])
