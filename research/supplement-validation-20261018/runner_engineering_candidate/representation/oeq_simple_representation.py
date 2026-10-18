"""Versioned literal operation records shared by candidate and reference.

One numbered source item is one operation. No recipe generation, deduplication,
semantic rewriting, or silent conversion of capability prose into instructions.
Reagents stay in the original operation text; named parameters are copied out.
"""
from copy import deepcopy
import hashlib
import re
from oeq_unit_facts import extract_unit_facts, VERSION as UNIT_FACTS_VERSION

IMPLEMENTATION_VERSION = 'bounded-catalog-assertion-metadata-v1-20261018'
VERSION = 'paired-literal-operation-v3-assertion-propagation'
LEGACY_VERSION = 'paired-literal-operation-v2-range-preservation'
_METADATA = re.compile(r'\((?:Temperature|Time|Duration|metadataTime)\s*:[^()]*\)', re.I)
_FIELD = re.compile(r'(Temperature|Time|Duration|metadataTime|温度|时间|时长)\s*[:：]\s*([^,;；()（）]+)', re.I)
_METADATA = re.compile(r'[（(](?=(?:Temperature|Time|Duration|metadataTime|温度|时间|时长)\s*[:：])[^()（）]*[)）]',re.I)
_LEADING_ZH_NEGATION = re.compile(r'^\s*(?:\d+(?:\.\d+)*[.)、]?\s*)?(?:不要|无需|禁止|不得|切勿|勿|避免)')
_LEADING_ZH_CONDITION = re.compile(r'^\s*(?:\d+(?:\.\d+)*[.)、]?\s*)?(?:可选|如果|若|必要时)')
_METADATA_SCOPE_CUE = re.compile(r'\b(?:not|never|avoid|if|unless|optional|after|before|labeling|staining|storage|clearing|wash|incubate)\b|不要|禁止|不得|切勿|如果|若|可选|标记|染色|固定|保存|存储|透明|孵育|洗涤',re.I)

def normalize_units(text):
    text = re.sub(r'(?<=\d)\s*℃', ' °C', text)
    text = re.sub(r'\b(?:hours?|hrs?)\b', 'h', text, flags=re.I)
    text = re.sub(r'\bminutes?\b', 'min', text, flags=re.I)
    text = re.sub(r'\bdays?\b', 'd', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()

def operation_record(text, *, record_id, branch='main', phase='', number=None, source=None, include_unit_facts=False):
    params = {}
    for block in _METADATA.finditer(text):
        for m in _FIELD.finditer(block.group()):
            key = 'time' if m[1].lower() in {'time', 'duration', 'metadatatime','时间','时长'} else 'temperature'
            params[key] = {'raw': m[2].strip(), 'normalized': normalize_units(m[2].strip())}
    operation = re.sub(r'^\s*\d+(?:\.\d+)*[.)]?\s+', '', _METADATA.sub('', text)).strip()
    # These phrases qualify the same operation, never negate incubation itself.
    manner = [m.group() for m in re.finditer(r'\b(?:without|no|with gentle|with) shaking\b', operation, re.I)]
    endpoints = [m.group() for m in re.finditer(r'\buntil\b[^.;\n]*', operation, re.I)]
    repeats = [m.group() for m in re.finditer(r'\b(?:twice|thrice|\d+\s+times)\b', operation, re.I)]
    # Same literal parameter recognition on both sides, including inline reference prose.
    parameter_mentions=[]
    numeric = r'\d+(?:\.\d+)?'
    # Match the entire literal range before its final unit, never just its endpoint.
    quantity = numeric + r'(?:\s*(?:[-–—]|to)\s*' + numeric + r')?'
    signed_numeric = r'[+−-]?' + numeric
    temperature_quantity = signed_numeric + r'(?:\s*(?:[-–—]|to)\s*' + signed_numeric + r')?'
    patterns={'concentration':quantity + r'\s*%',
              'duration':quantity + r'\s*(?:hours?|hrs?|h|minutes?|min|days?|d)\b',
              'temperature':r'(?<!\w)(?:' + temperature_quantity + r'\s*(?:°C|℃)|RT)(?!\w)'}
    for kind,pattern in patterns.items():
        for m in re.finditer(pattern,text,re.I):
            parameter_mentions.append(dict(kind=kind,raw=m.group(),normalized=normalize_units(m.group()),
                                           start_in_record=m.start(),end_in_record=m.end()))
            bounds = re.match(r'(' + signed_numeric + r')\s*(?:[-–—]|to)\s*(' + signed_numeric + r')', m.group(), re.I)
            if bounds:
                lo, hi = (float(x.replace('−', '-')) for x in bounds.groups())
                parameter_mentions[-1]['numeric_range'] = {
                    'lower': min(lo, hi), 'upper': max(lo, hi),
                    'representative': (lo + hi) / 2,
                    'representative_rule': 'MIDPOINT_ONLY_NOT_REPLACEMENT_FOR_RANGE'}
    parameter_mentions.sort(key=lambda item:item['start_in_record'])
    mode = 'OPERATION'
    if re.match(r'(?i)(?:the\s+\w+\s+is\s+ready|can\s+be|the use of)', operation):
        mode = 'CONTEXT_OR_CAPABILITY'
    if re.match(r'(?i)(?:do not|never|avoid)\b', operation): mode = 'PROHIBITION'
    rendering = normalize_units(operation)
    if params:
        rendering += ' | ' + '; '.join(k + ': ' + v['normalized'] for k,v in params.items())
    row = dict(id=record_id, branch=branch, number=number, phase=phase, raw_text=text,
                operation=operation, reagent_text=operation, reagent_representation='INLINE_LITERAL_NOT_ENTITY_EXTRACTION',
                parameters=params, parameter_mentions=parameter_mentions,
                manner=manner, endpoint_conditions=endpoints, repetition_text=repeats,
                statement_mode=mode, source=deepcopy(source), scoring_text=rendering,
                literal_metadata_blocks=[{'start_in_record':m.start(),'end_in_record':m.end(),'quote':m.group()} for m in _METADATA.finditer(text)])
    # Experimental facts are opt-in; default paired/scoring payload stays legacy.
    if include_unit_facts:
        row['parameter_unit_facts_version'] = UNIT_FACTS_VERSION
        row['parameter_unit_facts'] = extract_unit_facts(text)
    return row

def from_catalog(protocol, catalog, extraction=None):
    if hashlib.sha256(protocol.encode()).hexdigest() != catalog['protocol_sha256']:
        raise ValueError('Source catalog does not match unchanged protocol')
    steps = (extraction or {}).get('steps', [])
    by_start = {s.get('assertion',{}).get('record_span',{}).get('start'):s for s in steps}
    rows=[]
    for r in catalog['records']:
        s=by_start.get(r['start'], {})
        h=r.get('parentheading')
        row=operation_record(protocol[r['start']:r['end']], record_id=s.get('id',r['record_id']),
             branch=s.get('branch','main'), number=r.get('number'),
             phase=protocol[h['start']:h['end']] if h else '',
             source={'record_id':r['record_id'],'start':r['start'],'end':r['end']})
        if s.get('assertion') is not None:
            # Carry only a source-reconstructable scoped assertion; never infer execution.
            from experiments.construct_validity.fidelity import classify_record_assertion
            assertion=s['assertion']
            expected=classify_record_assertion(protocol,assertion['record_span'],assertion.get('heading_span'))
            comparable=deepcopy(assertion)
            if (comparable.get('scope_policy')=='bounded-directive-scope-v3-procedural-adjuncts'
                    and expected.get('scope_policy')=='bounded-directive-scope-v4-leading-zh-condition'):
                comparable['scope_policy']=expected['scope_policy']
            if comparable!=expected or assertion['record_span']['start']!=r['start'] or assertion['record_span']['end']!=r['end']:
                raise ValueError('Candidate assertion differs from its source record')
            row['assertion']=deepcopy(expected)
            if assertion.get('scope_policy') != expected.get('scope_policy'):
                row['assertion_compatibility_audit']={
                    'supplied_scope_policy':assertion.get('scope_policy'),
                    'validated_scope_policy':expected.get('scope_policy'),
                    'source_assertion_revalidated':True}
        # The catalog assertion must not disappear when a model omits a row.
        if not s.get('assertion'):
            row['assertion']=deepcopy(r.get('assertion',{}))
            row['canonical_selection_status']='NOT_SELECTED_BY_THIS_EXTRACTION' if extraction is not None else 'NO_EXTRACTION_SELECTION_PROVIDED'
            if extraction is not None:
                row['assertion']['polarity']='UNKNOWN'
                row['assertion']['scope_reason']='CATALOG_ROW_NOT_SELECTED_BY_THIS_EXTRACTION'
        original_assertion=deepcopy(row.get('assertion'))
        body=re.sub(r'^\s*\d+(?:\.\d+)*[.)、]?\s*','',row['raw_text'])
        heading=re.sub(r'^[#*\s]+','',row['phase'])
        if _LEADING_ZH_NEGATION.search(body) or _LEADING_ZH_NEGATION.search(heading):
            row['assertion'].update(polarity='NEGATED',scope='UNRESOLVED',scope_reason='EXPLICIT_LEADING_CHINESE_PROHIBITION',scope_policy=IMPLEMENTATION_VERSION)
            row['statement_mode']='PROHIBITION'
        elif _LEADING_ZH_CONDITION.search(body) or _LEADING_ZH_CONDITION.search(heading):
            row['assertion'].update(polarity='CONDITIONAL',scope='UNRESOLVED',scope_reason='EXPLICIT_LEADING_CHINESE_CONDITION',scope_policy=IMPLEMENTATION_VERSION)
        notes=[b for b in row.get('literal_metadata_blocks',[]) if _METADATA_SCOPE_CUE.search(b['quote'])]
        if notes and row['assertion'].get('polarity') not in {'NEGATED','CONDITIONAL'}:
            row['assertion'].update(polarity='UNKNOWN',scope='UNRESOLVED',scope_reason='METADATA_HAS_SCOPE_OR_PHASE_WORDS',scope_policy=IMPLEMENTATION_VERSION)
        row['bounded_representation_audit']={'implementation_version':IMPLEMENTATION_VERSION,'original_assertion':original_assertion,'scope_metadata_blocks':notes,'original_text_unchanged':True}
        t=r.get('metadataTime')
        if t:
            row['parameters']['time']={'raw':t['value'],'normalized':normalize_units(t['value']),
                                       'start':t['start'],'end':t['end']}
        from oeq_representation_consistency import repair_record
        rows.extend(repair_record(row,protocol))
    return dict(schema_version=VERSION if any('assertion' in r for r in rows) else LEGACY_VERSION, source_sha256=catalog['protocol_sha256'],
                branches=deepcopy((extraction or {}).get('branches',[{'id':'main','mode':'SERIAL'}])),operations=rows)

def from_reference(evidence):
    """Use the same literal converter; derived imperative rows remain context."""
    rows=[];context=[]
    for r in (evidence.get('sr_inventory') or {}).get('reference_steps',[]):
        row=operation_record(r['text'],record_id=r['reference_step_id'],
               branch=evidence.get('route_id') or 'main',phase=r.get('stage_id',''),
               source={'source_ids':r.get('source_ids',[]),'passage_ids':r.get('passage_ids',{})})
        if r.get('text_origin') != 'EXPLICIT':
            row['statement_mode']='DERIVED_NOT_SOURCE_OPERATION';context.append(row)
        elif row['statement_mode']!='OPERATION':context.append(row)
        else:rows.append(row)
    return dict(schema_version=LEGACY_VERSION,operations=rows,context=context,
                route_id=evidence.get('route_id'),reference_id=evidence.get('reference_id'),
                scope='Source operation coverage; not scientific necessity')
