"""Consume explicit operation-local time under the original E phase definition."""
import math
import re
from oeq_simple_representation import from_catalog
from experiments.construct_validity.compact_grounding import build_record_catalog

VERSION='time-consumer-v8-audit-conservative-macs-actions'
# A bounded semantic mapping, not a new recipe or a free-text parser. The frozen
# iDISCO December 2016 pretreatment source explicitly calls this mixture bleach.
DECOLORIZATION_SOURCE = {
    'source_id': 'idisco-dec2016-full',
    'locator': 'https://idisco.info/wp-content/uploads/2015/04/whole-mount-staining-bench-protocol-methanol-dec-2016.pdf',
    'quote': 'Bleach in chilled fresh 5%H2O2 in methanol',
    'rule': 'Pretreatment chilled 5% H2O2 in methanol is decolorization; use answer time only',
}

def source_backed_decolorization(row):
    text=row['operation'].casefold();phase=row['phase'].casefold()
    return (bool(re.search(r'(?:pre-treatment|pretreatment|bleaching)', phase))
            and bool(re.search(r'5\s*%\s*h2o2\s+in\s+methanol', text))
            and ('chilled' in text or 'bleaching' in phase))


def active_label_phase_text(phase):
    """Remove completed-labeling context; shared without changing time policy."""
    return re.sub(r'\b(?:post[-\s]+|after\s+)(?:immunolabel(?:ing)?|labell?ing|staining)\b', '', phase)


def phase_semantics(phase):
    """Translate bounded phase vocabulary only; keep source strings untouched."""
    for zh, en in (
        ('透明化前准备', 'pretreatment'), ('透明化后', 'post-clearing'),
        ('免疫标记后', 'post-labeling'), ('染色后', 'post-staining'),
        ('成像前处理', 'imaging preparation'), ('折射率匹配', 'refractive index matching'),
        ('ri 匹配', 'ri matching'), ('ri匹配', 'ri matching'),
        ('脱脂', 'delipidation'), ('脱水', 'dehydration'),
        ('透明化', 'clearing'), ('脱色', 'decolorization'), ('脱钙', 'decalcification'),
        ('免疫标记', 'immunolabeling'), ('染色', 'staining'),
        ('预处理', 'pretreatment'), ('透化', 'permeabilization'),
        ('封闭', 'blocking'), ('固定', 'fixation'), ('保存', 'storage')):
        phase = phase.replace(zh, ' ' + en + ' ')
    return phase


def phase_role(row):
    text=row['operation'].casefold(); phase=phase_semantics(row['phase'].casefold())
    if row['statement_mode']!='OPERATION':return 'EXCLUDED_STATEMENT'
    # Reuse the source-verified assertion; optional/conditional records are not
    # mandatory elapsed time, even if a clearing heading is inherited.
    polarity = row.get('assertion', {}).get('polarity')
    if polarity in {'CONDITIONAL', 'NEGATED'}:return 'EXCLUDED_STATEMENT'
    # Do not resolve conflicting explicit MACS purposes via rule ordering.
    if re.search(r'\bmacs[-– ]r[012]\b', text):
        excluded_purpose=bool(re.search(r'抗体|\bantibod(?:y|ies)\b|保存|储存|贮存|\bstor(?:e|age|ing)\b|洗涤|漂洗|\b(?:wash|rinse|remove)\b',text))
        equilibration=bool(re.search(r'平衡|均衡|\bequilibr',text))
        multiple_actions=bool(re.search(r'[；;。].*\b(?:store|incubate|wash|rinse)\b',text))
        if excluded_purpose and (equilibration or multiple_actions):return 'UNRESOLVED'
    if re.match(r'(?:避光)?(?:密封)?保存|^(?:储存|贮存)', text):return 'STORAGE'
    if re.match(r'成像前.*(?:脱泡|装样)|将.*转移至.*成像(?:样品仓|池)', text):return 'IMAGING_PREPARATION'
    if re.match(r'(?:脱色|漂白|脱钙)', text):return 'CORE'
    if re.search(r'(?:一抗|二抗|抗体孵育)', text):return 'LABELING'
    if re.search(r'(?:封闭液|透化液)', text):return 'OTHER_EXCLUDED'
    if re.match(r'(?:store|storage|transfer and store)\b',text):return 'STORAGE'
    if re.match(r'(?:mount|image|imaging|degas|debubble)\b|transfer\b.*\bimaging (?:chamber|cell)\b',text):return 'IMAGING_PREPARATION'
    if re.search(r'\b(?:bleach(?:ing)?|decolou?rization|decalcification)\b',text):return 'CORE'
    if source_backed_decolorization(row):return 'CORE'
    if re.search(r'\b(?:primary|secondary) antibod|\bincubat(?:ion|e)\b[^.]*\bantibod(?:y|ies)\b',text):return 'LABELING'
    if re.search(r'\b(?:permeabilization|blocking) solution\b',text):return 'OTHER_EXCLUDED'
    # Posthoc bounded action rules: medium presence alone never defines a phase.
    # A named MACS incubation is processing, even when its carrier contains PBS.
    macs = bool(re.search(r'\bmacs[-– ]r[012]\b', text))
    clean=text.replace('*','')
    # A named medium cannot override the operation's purpose. Compound or
    # conflicting purposes stay unknown rather than donating time to CORE.
    if macs:
        clauses=[c.strip() for c in re.split(r'[。；;]|(?<!\d)\.(?!\d)',clean) if c.strip()]
        storage=bool(re.search(r'保存|储存|贮存|\bstor(?:e|age|ing)\b',clean))
        antibody=bool(re.search(r'抗体|\bantibod(?:y|ies)\b',clean))
        washing=bool(re.search(r'洗涤|漂洗|洗去|洗除|去除|\b(?:wash|rinse|remove)\b',clean))
        equilibration=bool(re.search(r'平衡|均衡|\bequilibr',clean))
        if antibody:
            return 'UNRESOLVED' if equilibration else 'LABELING'
        if storage:
            return 'UNRESOLVED' if equilibration else 'STORAGE'
        if washing and re.search(r'\bpbs\b',clean):
            return 'UNRESOLVED' if equilibration or len(clauses)>1 else 'ROUTINE_WASH'
        if re.search(r'\b(?:immunolabel|labeling|labelling|staining)',active_label_phase_text(phase)):
            return 'UNRESOLVED'
        bound_incubation=bool(re.match(r'^incubat(?:ion|e)\s+(?:with|in)\s+(?:fresh\s+)?macs[-– ]r[012]\b', clean))
        bound_equilibration=bool(re.search(r'(?:在|置于|转入|更换新鲜)(?:新鲜)?[^。；;]*macs[-– ]r[012][^。；;]*(?:孵育|均衡|平衡)', clean))
        if (bound_incubation or bound_equilibration) and len(clauses)==1:
            return 'CORE'
        if bound_incubation or bound_equilibration:
            return 'UNRESOLVED'
    if re.match(r'(?:短期|长期)保存', text):return 'STORAGE'
    # These are handling/imaging actions, not additional clearing incubations.
    if re.match(r'全程使用.*(?:转移|夹持)|将.*固定于成像支架|成像介质使用', text):
        return 'IMAGING_PREPARATION'

    # An explicitly shared clearing/staining incubation contributes its stated
    # elapsed duration once. The mixed heading cannot erase the clearing action.
    if re.search(r'\b(?:to clear (?:the )?tissue|for (?:tissue )?clearing|delipidation|refractive index matching|ri matching)\b',text):return 'CORE'
    # Ordinary buffer washing is excluded by the original scope. Do not treat a
    # PBS-containing clearing cocktail or a clearing-reagent transition as this.
    wash_heading=re.sub(r'^[\s#*\d.()、]+|[\s:*：]+$', '', phase)
    if re.search(r'\bpbs\b',text) and (wash_heading in {'wash','washing'} or 'remove residual fixative' in text or bool(re.search(r'漂洗.*(?:pfa|固定液).*残留', text))):return 'ROUTINE_WASH'
    # Post/after-labeling describes an ended phase, not a labeling action.
    # Explicit primary/secondary antibody operations were already excluded above.
    active_label_phase = active_label_phase_text(phase)
    if re.search(r'\b(?:immunolabel|labeling|labelling|staining)',active_label_phase):return 'LABELING'
    # Existing extractor's core_solvents/core_actions include these solvent
    # processing steps. An inherited pretreatment heading must not erase them.
    solvent_operation=(bool(re.match(r'(?:incubat(?:ion|e)|wash)\b',text)) and
        bool(re.search(r'\b(?:methanol|ethanol|meoh|etoh|dcm|dichloromethane|thf|tetrahydrofuran)\b',text)))
    if solvent_operation:return 'CORE'
    if re.search(r'(?:permeabilization|blocking)',phase):return 'OTHER_EXCLUDED'
    if re.search(r'\b(?:pbs|ptx(?:\.2)?)\b',text) and not re.search(r'\b(?:scales?\w*|cubic\w*|rims|dbe|babb)\b',text):return 'ROUTINE_WASH'
    if re.search(r'(?:clearing|dehydration|ri matching|refractive index.*matching|delipidation)',phase):return 'CORE'
    if re.search(r'(?:pre-treatment|pretreatment|permeabilization|fixation)',phase):return 'OTHER_EXCLUDED'
    if re.search(r'\b(?:delipidation|refractive index matching|ri matching)\b',text):return 'CORE'
    return 'UNRESOLVED'


def scoped_time_totals(rows, route_ok=True):
    """Keep v4 total and explicit final-stage subtotal separate; never infer a recipe."""
    final = []
    last_label = max((i for i, r in enumerate(rows) if r['phase_role'] == 'LABELING'), default=-1)
    clearing_only = last_label < 0 and not any(re.search(
        r'pretreatment|pre-treatment|bleach|rehydrat|permeabili|blocking|fixation', phase_semantics(r['phase'].casefold()), re.I) for r in rows)
    for i, row in enumerate(rows):
        phase = phase_semantics(row['phase'].casefold())
        # Bounded explicit headings only. Pretreatment dehydration is not final.
        final_heading = (bool(re.search(r'\bfinal\b.*(?:dehydration|delipidation|clearing)', phase))
                         or bool(re.search(r'(?:^|[\s\d])clearing(?:$|\s)', phase))
                         or bool(re.search(r'(?:refractive index.*matching|ri matching)', phase))
                         or ((clearing_only or (last_label >= 0 and i > last_label)) and bool(re.search(r'dehydration|delipidation', phase))))
        if final_heading and not re.search(r'(?:pretreatment|pre-treatment|bleach|rehydrat)', phase):
            if row['phase_role'] in {'CORE', 'UNRESOLVED'}:
                final.append(row)
    def summary(selected):
        known = [r['duration'] for r in selected if r['status'] == 'INCLUDED']
        unknown = [r['step_id'] for r in selected if r['status'] != 'INCLUDED']
        total = math.fsum(d['representative_hours'] for d in known) if known else None
        return {'total_time_hours': total if selected and not unknown and route_ok else None,
                'known_sum_hours': total, 'local_unknowns': unknown,
                'step_ids': [r['step_id'] for r in selected],
                'status': 'COMPLETE_EXPLICIT_FIELDS' if selected and not unknown and route_ok else 'UNRESOLVED',
                'duration_assumptions': [r['step_id'] for r in selected if r.get('duration') and
                    r['duration'].get('representative_kind') != 'exact_scalar']}
    return {'full_core_v4': summary([r for r in rows if r['phase_role'] in {'CORE','UNRESOLVED'}]),
            'final_clearing_module': summary(final)}

def project_simple_time(assessment, protocol, selected_route='main'):
    # Lazy import keeps the existing numerical conversion as the single policy.
    from oeq_sr_assessment import _duration_scoring_value
    representation=from_catalog(protocol,build_record_catalog(protocol),assessment['extraction'])
    branches={b['id']:b for b in representation['branches']}
    selected=branches.get(selected_route,{})
    route_ok=selected.get('mode')=='SERIAL'
    rows=[];values=[];unknowns=[]
    for row in representation['operations']:
        if row['branch']!=selected_route:continue
        role=phase_role(row);literal=row['parameters'].get('time',{}).get('raw')
        duration=_duration_scoring_value(literal)
        if literal and re.fullmatch(r'(?i)\s*(?:overnight(?:\s*\(ON\))?|ON|过夜)\s*',literal):
            duration={'bounds_h':[8.,8.],'representative_hours':8.,'representative_kind':'original_rubric_overnight_8h'}
        status='EXCLUDED_FROM_ORIGINAL_TIME_SCOPE'
        if role=='CORE':
            if duration and route_ok:
                values.append(dict(step_id=row['id'],source_text=literal,**duration));status='INCLUDED'
            else:status='LOCAL_DURATION_UNRESOLVED';unknowns.append(row['id'])
        elif role=='UNRESOLVED':status='LOCAL_PHASE_UNRESOLVED';unknowns.append(row['id'])
        rows.append(dict(step_id=row['id'],phase=row['phase'],phase_role=role,time_raw=literal,
                         duration=duration,status=status,source=row['source'],
                         phase_source=DECOLORIZATION_SOURCE if source_backed_decolorization(row) else None))
    total=math.fsum(v['representative_hours'] for v in values) if values else None
    bounds=[math.fsum(v['bounds_h'][k] for v in values) for k in (0,1)] if values else None
    return dict(schema_version=VERSION,actual_scope='full_core_v4',scope_totals=scoped_time_totals(rows,route_ok),total_time_hours=total if not unknowns else None,known_sum_hours=total,total_bounds_h=bounds if not unknowns else None,known_sum_bounds_h=bounds,rows=rows,
                duration_values=values,local_unknowns=unknowns,
                route_status='SERIAL' if route_ok else 'UNRESOLVED',
                total_kind='KNOWN_INCLUDED_FIELDS_SUM' if unknowns else 'INCLUDED_FIELDS_SUM',
                policy='Original E core phases; local unknowns retained; no repeat multiplication or route-wide lexical rejection')
