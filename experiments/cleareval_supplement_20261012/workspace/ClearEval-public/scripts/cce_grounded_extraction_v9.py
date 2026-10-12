"""Candidate source-bound extraction contract. Offline only; no model-call command.

One joint response retains the original score schema and adds evidence-record
arrays. Exact-span validity and arithmetic are software properties, not gold
scientific labels. The old EGES implementation and knowledge base are untouched.
"""
from __future__ import annotations
import argparse, copy, difflib, hashlib, json, math, re, sys
from pathlib import Path
from decimal import Decimal
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import evaluator_integrity as integrity
import cce_judges as judges
import cce_output_identity_v2 as baseline
import cce_alternative_development as helper
OUT=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/grounded_extraction_v9'
VERSION='source_bound_extraction_v9'
DRAFT_REVISION='01_compact_typed_wire_local_endpoints_and_operation_extents'
CONFIGURED_NUM_CTX=98304
SECTION3='3. 荧光兼容性与实验数据提取 Prompt (Data Extraction for Fluorescence Compatibility)'
INCLUDE={'delipidation','decalcification','decolorization','ri_matching','clearing_treatment','reagent_transition_wash'}
EXCLUDE={'fixation','antibody_incubation','staining','labeling_preparation','imaging','routine_wash','storage'}
SPAN={'type':'object','additionalProperties':False,'required':['unit_id','quote','occurrence'],
      'properties':{'unit_id':{'type':'string'},'quote':{'type':'string','minLength':1},'occurrence':{'type':'integer','minimum':0}}}
CANDIDATE_REF={'type':'object','additionalProperties':False,'required':['candidate_id'],
               'properties':{'candidate_id':{'type':'string','pattern':'^C[0-9]+$'}}}
UNIT_REF={'type':'object','additionalProperties':False,'required':['unit_id'],
          'properties':{'unit_id':{'type':'string','pattern':'^L[0-9]+$'}}}
DURATION_REF={'type':'object','additionalProperties':False,'required':['candidate_id'],
              'properties':{'candidate_id':{'type':'string','pattern':'^D[0-9]+$'}}}
RI_REF={'type':'object','additionalProperties':False,'required':['candidate_id'],
        'properties':{'candidate_id':{'type':'string','pattern':'^R[0-9]+$'}}}
CLAUSE_REF={'type':'object','additionalProperties':False,'required':['clause_id'],
            'properties':{'clause_id':{'type':'string','pattern':'^Q[0-9]+$'}}}
OPERATION_REF={'anyOf':[UNIT_REF,{'type':'object','additionalProperties':False,'required':['candidate_id'],
    'properties':{'candidate_id':{'type':'string','pattern':'^O[0-9]+$'}}}]}
REPEAT_REF={'type':'object','additionalProperties':False,'required':['candidate_id'],
    'properties':{'candidate_id':{'type':'string','pattern':'^P[0-9]+$'}}}
NULL_REPEAT_REF={'anyOf':[REPEAT_REF,{'type':'null'}]}
# Model-visible references never contain free-form quotes. SPAN above is an
# internal exact-source representation, not a schema branch.
PRECISE_REF=DURATION_REF
CONTEXT_REF=UNIT_REF
RELATION_REF={'anyOf':[UNIT_REF,CLAUSE_REF]}
REF=UNIT_REF
NULLSPAN={'anyOf':[UNIT_REF,{'type':'null'}]}
NULL_PRECISE_REF={'anyOf':[DURATION_REF,{'type':'null'}]}

def obj(properties):return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}
def arr(items):return {'type':'array','items':items}
def enum(*values):return {'type':'string','enum':list(values)}
TEXT={'type':'string'}
ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]*$'}
DIRECT=('c_param','co_order','co_method','co_param','co_chem')

def _expanded_schema():
    old=json.loads((baseline.OUT/'final_output_schema.json').read_text(encoding='utf8'))
    common={'id':ID,'fluor_entity_id':ID,'evidence':RELATION_REF}
    relationship={'anyOf':[
        obj({**common,'target_entity_id':ID,'status':{'const':'explicit'}}),
        obj({**common,'target_entity_id':{'anyOf':[ID,{'type':'null'}]},'status':enum('ambiguous','unknown')})]}
    ground=obj({'schema_version':{'const':VERSION},'source_id':TEXT,
        'method_mentions':arr(obj({'id':ID,'literal_name':{'type':'string','minLength':1},'name_occurrence':{'type':'integer','minimum':0},'supporting_evidence':UNIT_REF,'usage':enum('selected','mentioned','alternative','negated','unknown')})),
        'entities':arr(obj({'id':ID,'literal_name':{'type':'string','minLength':1},'name_occurrence':{'type':'integer','minimum':0},'supporting_evidence':UNIT_REF,'kind':enum('fluorophore','fluorescent_protein','target','antibody','unknown'),
                            'usage':enum('used','mentioned','alternative','negated','unknown')})),
        'relations':arr(relationship),
        'intrinsic_signals':arr(obj({'id':ID,'entity_id':ID,'evidence':CONTEXT_REF,'status':enum('source_declared','ambiguous','unknown')})),
        'operations':arr(obj({'id':ID,'operation':OPERATION_REF,'phase':enum(*(sorted(INCLUDE|EXCLUDE)+['unknown'])),
                              'duration':NULL_PRECISE_REF,'repeat_evidence':NULL_REPEAT_REF,
                              'execution_scope':enum('initial','conditional_or_future','unknown'),
                              'condition_evidence':NULLSPAN})),
        'timeline':obj({'mode':enum('serial','parallel','alternative','unknown'),'operation_ids':arr(ID),
                        'relation_evidence':NULLSPAN,'completeness':enum('complete','partial','unknown')}),
        'precedence_edges':arr(obj({'before_id':ID,'after_id':ID,'evidence':REF})),
        'total_time_claims':arr(obj({'id':ID,'duration':PRECISE_REF,'scope':enum('clearing_total','whole_protocol','unknown')})),
        'ri_mentions':arr(obj({'id':ID,'value':RI_REF,'role':enum('reagent_final','sample_target','unknown')})),
        'coverage':obj({'entities':enum('complete','partial','unknown'),'time_operations':enum('complete','partial','unknown'),
                        'core_time_operations':enum('complete','partial','unknown'),
                        'unresolved':arr(obj({'evidence':REF,'reason':TEXT}))})})
    evidence=arr(obj({'metric':enum(*DIRECT),'answer_spans':arr(REF),
        'basis':enum('observed','absence','insufficient','mixed'),
        'rubric_basis':{'type':'string','minLength':1}}))
    return obj({'scores':old['properties']['scores'],'score_evidence':evidence,'grounded_extraction':ground})

def schema_catalog(spec):
    """Compact shape documentation; the full schema travels in Ollama format.

    This is generated from the actual decoder schema, not a populated example.
    Required keys, enums and nullability survive the compact representation.
    """
    if spec==REF:return 'SourceRef'
    if spec==NULLSPAN:return 'SourceRef | null'
    if spec==DURATION_REF:return 'DurationCandidateRef'
    if spec==RI_REF:return 'RICandidateRef'
    if spec==CLAUSE_REF:return 'ClauseRef'
    if spec==REPEAT_REF:return 'RepeatCandidateRef'
    if spec==CANDIDATE_REF:return 'CandidateRef'
    if 'anyOf' in spec and all('target_entity_id' in v.get('properties',{}) for v in spec['anyOf']):return 'Relation'
    if 'anyOf' in spec:return ' | '.join(str(schema_catalog(s)) for s in spec['anyOf'])
    if 'const' in spec:return 'constant '+canonical(spec['const'])
    if 'enum' in spec:return 'enum '+canonical(spec['enum'])
    if spec.get('type')=='object':return {k:schema_catalog(v) for k,v in spec['properties'].items()}
    if spec.get('type')=='array':return [schema_catalog(spec['items'])]
    kind=spec.get('type','value');kind=' | '.join(kind) if isinstance(kind,list) else kind
    for k in ['minimum','maximum','minLength','pattern']:
        if k in spec:kind+=' '+k+'='+str(spec[k])
    return kind

def require(ok,code):
    if not ok:raise ValueError(code)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rawsha(text):return hashlib.sha256(text.encode('utf8')).hexdigest()
def canonical(o):return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def source_id_for_case(case):return 'SRC_'+rawsha(case['specific_question']+'\0'+case['model_response'])[:24]
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def save(p,o):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def document(text,source_id):
    require(isinstance(text,str) and text.strip(),'EMPTY_SOURCE')
    units=[];start=0
    for i,part in enumerate(text.splitlines(keepends=True)):
        units.append({'unit_id':f'L{i+1:04d}','start':start,'end':start+len(part),'text':part});start+=len(part)
    require(''.join(u['text'] for u in units)==text,'LOSSLESS_DOCUMENT_FAILURE')
    return {'source_id':source_id,'answer_sha256':rawsha(text),'offset_convention':'Python Unicode code points; end exclusive; no normalization',
            'text':text,'units':units}

def resolve_span(ref,doc):
    require(isinstance(ref,dict) and set(ref)=={'unit_id','quote','occurrence'},'SPAN_SHAPE')
    unit=next((u for u in doc['units'] if u['unit_id']==ref['unit_id']),None)
    require(unit is not None and isinstance(ref['quote'],str) and bool(ref['quote']),'SPAN_UNIT_OR_QUOTE')
    n=ref['occurrence'];require(isinstance(n,int) and not isinstance(n,bool) and n>=0,'SPAN_OCCURRENCE')
    # Overlapping exact matches are counted; no fuzzy correction or Unicode normalization.
    hits=[m.start() for m in re.finditer('(?='+re.escape(ref['quote'])+')',unit['text'])]
    require(n<len(hits),'SPAN_QUOTE_NOT_FOUND')
    start=unit['start']+hits[n];end=start+len(ref['quote'])
    require(doc['text'][start:end]==ref['quote'],'SPAN_RAW_SOURCE_MISMATCH')
    return {**ref,'source_id':doc['source_id'],'start':start,'end':end,'answer_sha256':doc['answer_sha256'],
            'context_start':unit['start'],'context_end':unit['end'],'context':unit['text']}

def clause_inventory(doc):
    """Pre-enumerate the existing relation policy's clause boundaries.

    A clause ID chooses source extent only. It does not assert a relation, strip
    global alternatives, or change the legacy relation-policy function.
    """
    rows=[]
    for unit in doc['units']:
        context=unit['text'];header=LABEL_FIELD.match(context)
        clauses=label_clauses(context) if header else []
        if not clauses:
            depth=0;begin=0
            for index,char in enumerate(context):
                if char in '([{':depth+=1
                elif char in ')]}':depth=max(0,depth-1)
                elif char==';' and depth==0:
                    clauses.append({'start':begin,'end':index});begin=index+1
            clauses.append({'start':begin,'end':len(context)})
        for clause in clauses:
            a=clause['start'];b=clause['end']
            while a<b and context[a].isspace():a+=1
            while b>a and context[b-1].isspace():b-=1
            if a==b:continue
            quote=context[a:b]
            occ=sum(m.start()<a for m in re.finditer('(?='+re.escape(quote)+')',context))
            rows.append({'clause_id':f'Q{len(rows)+1:04d}',
                'span':resolve_span({'unit_id':unit['unit_id'],'quote':quote,'occurrence':occ},doc),
                'role':'source_extent_only_not_relationship_confirmation'})
    return rows


def operation_inventory(doc):
    """Source-only complete contiguous record extents, not phase assignments.

    Boundaries require top-level punctuation/numbering, or a completed explicit
    parameter parenthesis followed by a new action head. Qualifying introductory
    text stays in the following extent. Full-unit context is never narrowed.
    """
    action=r'(?:incubat(?:ion|e|ing)|stor(?:age|e|ing)|wash(?:ing)?|rins(?:e|ing)|transfer(?:ring)?|immers(?:ion|e)|soak(?:ing)?|mount(?:ing)?|equilibrat(?:ion|e|ing)|dehydrat(?:ion|e|ing)|clear(?:ing)?)\b'
    qualified=r'(?:(?:before|after|if|when|once|for\s+(?:repeated|future))\b[^;\n]*?,\s*)?'
    new_head=re.compile(r'^\s*(?:\d+(?:\.\d+)*[.)]\s*)?'+qualified+action,re.I)
    rows=[]
    for unit in doc['units']:
        text=unit['text'];cuts=[0];reasons={0:'source_unit_start'};stack=[]
        for index,char in enumerate(text):
            if char in '([{':stack.append((char,index));continue
            if char in ')]}':
                opened=stack.pop() if stack else None
                if not stack and opened and opened[0]=='(' and char==')':
                    body=text[opened[1]+1:index]
                    if re.search(r'(?:^|[,;]\s*)(?:Temperature|Time)\s*:',body,re.I) and new_head.match(text[index+1:]):
                        pos=index+1
                        while pos<len(text) and text[pos].isspace():pos+=1
                        if pos<len(text):cuts.append(pos);reasons[pos]='completed_explicit_parameter_record_then_action'
                continue
            if stack:continue
            if char.isspace() and text[:index].strip():
                numbered=re.match(r'\s*(\d+(?:\.\d+)*[.)]\s+)'+qualified+action,text[index:],re.I)
                if numbered:
                    pos=index
                    while pos<len(text) and text[pos].isspace():pos+=1
                    cuts.append(pos);reasons[pos]='explicit_inline_numbered_action'
            if char in ';.' and new_head.match(text[index+1:]):
                # A decimal point cannot terminate a numbered or numeric record.
                if char=='.' and index>0 and text[index-1].isdigit():continue
                pos=index+1
                while pos<len(text) and text[pos].isspace():pos+=1
                if pos<len(text):cuts.append(pos);reasons[pos]='top_level_punctuation_then_action'
        cuts=sorted(set(cuts));ends=cuts[1:]+[len(text)]
        for begin,end in zip(cuts,ends):
            a,b=begin,end
            while a<b and text[a].isspace():a+=1
            while b>a and (text[b-1].isspace() or text[b-1]==';'):b-=1
            quote=text[a:b]
            if not quote:continue
            # Keep source uncertainty. Do not emit a chopped numeric-only span.
            if not record_action_heads(quote) and not re.match(r'^\d+(?:\.\d+)*[.)]\s+',quote):continue
            occurrence=sum(m.start()<a for m in re.finditer('(?='+re.escape(quote)+')',text))
            rows.append({'candidate_id':f'O{len(rows)+1:04d}','kind':'operation_span',
                'span':resolve_span({'unit_id':unit['unit_id'],'quote':quote,'occurrence':occurrence},doc),
                'boundary_evidence':{'start_rule':reasons[begin],'source_unit_start':unit['start'],'source_unit_end':unit['end'],
                    'full_unit_context_preserved':True,'scope_phase_and_action_semantics_inferred':False},
                'role':'source_extent_only_not_operation_or_scope_confirmation'})
    return rows


def repeat_inventory(doc):
    rows=[]
    # These forms are precisely those accepted by repeat_count. No xN, range,
    # total-plus-additional interpretation, or numerical conversion is added.
    pattern=re.compile(r'(?<![\w.\-])(?:\d+\s*(?:times|cycles|次)|twice|once|两次|一次)(?!\w)',re.I)
    for unit in doc['units']:
        for match in pattern.finditer(unit['text']):
            quote=match.group()
            if repeat_count({'quote':quote}) is None:continue
            before=unit['text'][:match.start()]
            if re.search(r'\d\s*[-–—]\s*$',before):continue
            occurrence=sum(m.start()<match.start() for m in re.finditer('(?='+re.escape(quote)+')',unit['text']))
            rows.append({'candidate_id':f'P{len(rows)+1:04d}','kind':'repeat_literal',
                'span':resolve_span({'unit_id':unit['unit_id'],'quote':quote,'occurrence':occurrence},doc),
                'role':'source_literal_only_not_operation_assignment_or_repeat_semantics_confirmation'})
    return rows

def repeat_declaration_inventory(doc,repeats):
    """Source recall for explicit repetition claims, including unsupported forms.

    These are not selectable P values. They prevent an unreferenced literal
    repeat declaration from becoming the default single performance.
    """
    rows=[];seen=set()
    patterns=[re.compile(r'(?<!\w)(?:-?\d+(?:\s*[-–—]\s*\d+)?|several|multiple|many|one|two|three|four|five)\s*(?:times|cycles)(?!\w)',re.I),
              re.compile(r'\brepeat\b[^.;\n]*',re.I)]
    sources=[r['span'] for r in repeats]
    for unit in doc['units']:
        for pattern in patterns:
            for match in pattern.finditer(unit['text']):
                quote=match.group();occ=sum(m.start()<match.start() for m in re.finditer('(?='+re.escape(quote)+')',unit['text']))
                sources.append(resolve_span({'unit_id':unit['unit_id'],'quote':quote,'occurrence':occ},doc))
    for span in sorted(sources,key=lambda s:(s['start'],s['end'])):
        key=(span['start'],span['end'])
        if key in seen:continue
        seen.add(key)
        supported=[r['candidate_id'] for r in repeats if span['start']<=r['span']['start'] and r['span']['end']<=span['end']]
        rows.append({'declaration_id':f'E{len(rows)+1:04d}','span':span,'eligible_repeat_candidate_ids':supported,
            'status':'supported_literal_requires_operation_assignment' if supported else 'unsupported_or_unspecified_repetition_literal',
            'not_a_model_reference_or_numeric_fact':True})
    return rows



def operation_eligibility_metadata(doc,registry):
    """Expose unchanged binding guard results before generation, not gold labels.

    No resolver is invoked here: it would recursively rebuild the registry.
    The precise O marker is the same marker resolved O references carry into
    repeat_source_binding. Existing source spans and inventory rows survive.
    """
    durations=[r for r in registry['records'] if r['kind']=='duration']
    for row in registry['operation_candidates']:
        operation={**row['span'],'candidate_reference':{'candidate_id':row['candidate_id'],'kind':'operation_span'}}
        row['eligible_duration_candidate_ids']=[r['candidate_id'] for r in durations if record_binding(operation,r['span'],doc)['valid']]
        row['eligible_repeat_candidate_ids']=[r['candidate_id'] for r in registry['repeat_candidates'] if repeat_source_binding(operation,r['span'],doc,registry)['valid']]
    return registry


def candidate_registry(doc):
    rows=evidence_inventory(doc);clauses=clause_inventory(doc)
    require(len({r['candidate_id'] for r in rows})==len(rows),'DUPLICATE_SOURCE_CANDIDATE_ID')
    repeats=repeat_inventory(doc)
    content={'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],'enumerator_version':VERSION,
        'records':rows,'clauses':clauses,'operation_candidates':operation_inventory(doc),'repeat_candidates':repeats,
        'repeat_declarations':repeat_declaration_inventory(doc,repeats)}
    content=operation_eligibility_metadata(doc,content)
    return {**content,'registry_sha256':rawsha(canonical(content))}

def resolve(ref,doc,registry=None):
    if isinstance(ref,dict) and set(ref)=={'unit_id'}:
        unit=next((u for u in doc['units'] if u['unit_id']==ref['unit_id']),None)
        require(unit is not None and bool(unit['text']),'UNIT_REFERENCE_NOT_IN_CURRENT_SOURCE')
        return {'unit_id':unit['unit_id'],'quote':unit['text'],'occurrence':0,
            'source_id':doc['source_id'],'start':unit['start'],'end':unit['end'],'answer_sha256':doc['answer_sha256'],
            'context_start':unit['start'],'context_end':unit['end'],'context':unit['text'],
            'unit_reference':{'source_unit_sha256':rawsha(unit['text']),'raw_unit_text_preserved':True,
                'wide_evidence_not_atomic_identity':True}}
    if isinstance(ref,dict) and set(ref)=={'candidate_id'}:
        require(isinstance(ref['candidate_id'],str) and re.fullmatch(r'[DROP][0-9]+',ref['candidate_id']),'CANDIDATE_ID_SHAPE')
        expected=candidate_registry(doc) if registry is None else registry
        require(expected['source_id']==doc['source_id'] and expected['answer_sha256']==rawsha(doc['text']),'CANDIDATE_REGISTRY_SOURCE_MISMATCH')
        require(expected==candidate_registry(doc),'CANDIDATE_REGISTRY_CONTENT_DRIFT')
        rows=[r for r in expected['records']+expected['operation_candidates']+expected['repeat_candidates'] if r['candidate_id']==ref['candidate_id']]
        require(len(rows)==1,'CANDIDATE_ID_NOT_IN_CURRENT_SOURCE')
        item=rows[0];span=item['span']
        original=resolve_span({k:span[k] for k in ['unit_id','quote','occurrence']},doc)
        require(original==span,'REGISTERED_CANDIDATE_SOURCE_SPAN_DRIFT')
        return {**span,'candidate_reference':{'candidate_id':item['candidate_id'],'kind':item['kind'],
            'registry_sha256':expected['registry_sha256'],'enumerator_version':expected['enumerator_version'],
            'selection_is_not_semantic_confirmation':True}}
    if isinstance(ref,dict) and set(ref)=={'clause_id'}:
        require(isinstance(ref['clause_id'],str) and re.fullmatch(r'Q[0-9]+',ref['clause_id']),'CLAUSE_ID_SHAPE')
        expected=candidate_registry(doc) if registry is None else registry
        require(expected['source_id']==doc['source_id'] and expected['answer_sha256']==rawsha(doc['text']),'CLAUSE_REGISTRY_SOURCE_MISMATCH')
        require(expected==candidate_registry(doc),'CLAUSE_REGISTRY_CONTENT_DRIFT')
        rows=[r for r in expected['clauses'] if r['clause_id']==ref['clause_id']]
        require(len(rows)==1,'CLAUSE_ID_NOT_IN_CURRENT_SOURCE')
        span=rows[0]['span'];original=resolve_span({k:span[k] for k in ['unit_id','quote','occurrence']},doc)
        require(original==span,'REGISTERED_CLAUSE_SOURCE_SPAN_DRIFT')
        return {**span,'clause_reference':{'clause_id':ref['clause_id'],'registry_sha256':expected['registry_sha256'],
            'full_unit_context_preserved':True,'selection_is_not_semantic_confirmation':True}}
    raise ValueError('MODEL_SOURCE_REF_MUST_BE_ID_ONLY')

def validate_shape(value,spec,path='$'):
    if 'anyOf' in spec:
        good=False
        for choice in spec['anyOf']:
            try:validate_shape(value,choice,path);good=True;break
            except ValueError:pass
        require(good,'SCHEMA_ANYOF:'+path);return
    if 'const' in spec:require(value==spec['const'],'SCHEMA_CONST:'+path)
    if 'enum' in spec:require(value in spec['enum'],'SCHEMA_ENUM:'+path)
    kind=spec.get('type');kinds=kind if isinstance(kind,list) else [kind] if kind else []
    def matches(k):return {'null':value is None,'object':isinstance(value,dict),'array':isinstance(value,list),
        'string':isinstance(value,str),'integer':isinstance(value,int) and not isinstance(value,bool),
        'number':isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value),
        'boolean':isinstance(value,bool)}.get(k,False)
    if kinds:require(any(matches(k) for k in kinds),'SCHEMA_TYPE:'+path)
    if isinstance(value,dict):
        props=spec.get('properties',{});require(set(spec.get('required',[]))<=set(value),'SCHEMA_REQUIRED:'+path)
        if spec.get('additionalProperties') is False:require(set(value)<=set(props),'SCHEMA_EXTRA:'+path)
        for k,v in value.items():
            if k in props:validate_shape(v,props[k],path+'.'+k)
    if isinstance(value,list):
        for i,v in enumerate(value):validate_shape(v,spec.get('items',{}),path+f'[{i}]')
    if isinstance(value,str):
        if 'minLength' in spec:require(len(value)>=spec['minLength'],'SCHEMA_SHORT:'+path)
        if 'pattern' in spec:require(re.search(spec['pattern'],value) is not None,'SCHEMA_PATTERN:'+path)
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if 'minimum' in spec:require(value>=spec['minimum'],'SCHEMA_MINIMUM:'+path)
        if 'maximum' in spec:require(value<=spec['maximum'],'SCHEMA_MAXIMUM:'+path)

NUMBER=r'\d+(?:\.\d+)?'
UNIT=r'(?:hours?|hrs?|h|days?|d|minutes?|mins?|min|seconds?|secs?|s|weeks?|小时|分钟|秒|天|周)'
DURATION=re.compile(r'(?<![\w.])('+NUMBER+r')(?:\s*[-–—~至]\s*('+NUMBER+r'))?\s*('+UNIT+r')(?![A-Za-z])|\bovernight(?:\s*\(ON\))?\b|\bON\b|过夜',re.I)
def duration_value(text,overnight_hours=None):
    match=DURATION.fullmatch(text.strip())
    if not match:return {'state':'unsupported_duration_expression','bounds_hours':None,'unique_hours':None}
    if match.group(1) is None:
        return {'state':'legacy_overnight_convention' if overnight_hours is not None else 'unspecified_overnight',
                'bounds_hours':[overnight_hours,overnight_hours] if overnight_hours is not None else None,
                'unique_hours':overnight_hours,'source_numeric':False}
    lo=Decimal(match.group(1));hi=Decimal(match.group(2) or match.group(1));require(lo<=hi,'REVERSED_DURATION_RANGE')
    u=match.group(3).casefold()
    factor=Decimal(1)/Decimal(60) if u.startswith('min') or u=='分钟' else Decimal(1)/Decimal(3600) if u.startswith('s') or u=='秒' else Decimal(24) if u.startswith('d') or u=='天' else Decimal(168) if u.startswith('week') or u=='周' else Decimal(1)
    low,high=float(lo*factor),float(hi*factor)
    return {'state':'explicit_exact' if low==high else 'explicit_range','bounds_hours':[low,high],
            'unique_hours':low if low==high else None,'source_numeric':True}

def duration_role(quote,left,right):
    spatial=r'(?:morphological|anatomical|spatial|volumetric|structural|cellular|high[- ]resolution|light[- ]sheet|confocal|fluorescen(?:ce|t)|whole[- ](?:organ|brain))'
    endpoint=r'(?:imaging|images?|reconstruction|visuali[sz]ation|rendering|mapping|morphology|analysis|context)'
    if re.fullmatch(r'\d+\s*D',quote) and re.match(r'^\s*(?:'+spatial+r'\s+(?:or\s+)?){0,4}'+endpoint+r'\b',right,re.I):
        return 'dimensional_expression_lead','uppercase ND followed by a bounded spatial/adjective imaging phrase; original occurrence retained'
    if re.search(r'\b(?:every|each)\s*$|每\s*$',left,re.I):
        return 'recurrence_interval_lead','explicit every/each interval; not an additive operation duration'
    return 'duration',None

def evidence_inventory(doc):
    records=[]
    # Read existing names as recall leads only; no compatibility values or new
    # aliases participate in extraction or scoring. Longer exact names win.
    kb=read(ROOT/'KnowledgeBase/method_fluro_compati.json')
    marker_names=sorted({k for row in kb for k in row if k!='method'},key=lambda s:(-len(s),s))
    method_names=sorted({row['method'] for row in kb},key=lambda s:(-len(s),s))
    patterns=[('duration',DURATION),('number',re.compile(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])')),
        ('ri_value_lead',re.compile(r'(?<!\w)(?:RI|refractive\s+index|折射率)\s*(?:=|:|：|≈|~)\s*\d+(?:\.\d+)?(?!\w)(?!\.\d)(?!\s*[%％])(?!\s*[-–—]\s*\d)',re.I)),
        ('numbered_name_lead',re.compile(r'\b[A-Z][A-Za-z-]*(?:\s+[A-Za-z-]+){0,2}\s+\d{2,4}\b')),
        ('known_marker_name_lead',re.compile(r'(?<![\w-])(?:'+'|'.join(re.escape(s) for s in marker_names)+r')(?![\w-])',re.I)),
        ('known_method_name_lead',re.compile(r'(?<![\w-])(?:'+'|'.join(re.escape(s) for s in method_names)+r')(?![\w-])',re.I)),
        ('declared_field_lead',re.compile(r'(?im)^\s*(?:\*\*)?(?:Chosen\s+Method|Fluorescen(?:t|ce)\s+(?:Label|Marker)s?|Method|标记|方法)[^\n]*'))]
    for category,pattern in patterns:
        for match in pattern.finditer(doc['text']):
            if category=='numbered_name_lead' and re.match(r'\s*[%％]',doc['text'][match.end():]):
                # Percentage-bearing process headings are numeric parameter
                # leads, not distinguishing name suffixes. They remain in the
                # complete numeric inventory and unchanged original source.
                continue
            unit=next((u for u in doc['units'] if u['start']<=match.start() and match.end()<=u['end']),None)
            if unit is None:continue
            quote=match.group();local=match.start()-unit['start'];occ=sum(1 for h in re.finditer('(?='+re.escape(quote)+')',unit['text']) if h.start()<local)
            kind,classification=duration_role(quote,doc['text'][unit['start']:match.start()],doc['text'][match.end():unit['end']]) if category=='duration' else (category,None)
            records.append({'candidate_id':f'C{len(records)+1:04d}','kind':kind,
                'span':resolve_span({'unit_id':unit['unit_id'],'quote':quote,'occurrence':occ},doc),
                'role':'recall_candidate_not_scientific_gold',
                **({'original_candidate_kind':category,'non_additive_classification':classification,'source_text_unchanged':True} if classification else {})})
    seen={(r['span']['start'],r['span']['end']) for r in records}
    for unit in doc['units']:
        if re.search(r'protocol\s+steps|实验步骤|操作步骤',unit['text'],re.I):break
        field=re.match(r'^\s*(?:\*\*)?([^:\n]{1,60})[:：]',unit['text'])
        if not field or not re.search(r'label|marker|method|标记|方法',field[1],re.I):continue
        for match in re.finditer(r'(?<![\w-])[A-Za-z][A-Za-z0-9_-]*(?![\w-])',unit['text']):
            a,b=unit['start']+match.start(),unit['start']+match.end()
            if (a,b) in seen:continue
            quote=match.group();occ=sum(1 for h in re.finditer('(?='+re.escape(quote)+')',unit['text']) if h.start()<match.start())
            records.append({'candidate_id':f'C{len(records)+1:04d}','kind':'metadata_word_lead',
                'span':resolve_span({'unit_id':unit['unit_id'],'quote':quote,'occurrence':occ},doc),
                'role':'source_word_only_not_complete_entity_identity_or_usage'});seen.add((a,b))
    for unit in doc['units']:
        if not record_action_heads(unit['text']):continue
        quote=unit['text'].strip()
        parent=re.match(r'^\s*(\d+)(?:[.)]\s+|\s+)',quote)
        has_children=bool(parent and not DURATION.search(quote) and any(re.match(r'^\s*'+re.escape(parent[1])+r'\.\d+\b',u['text']) for u in doc['units'] if u['start']>unit['start']))
        records.append({'candidate_id':f'C{len(records)+1:04d}','kind':'action_section_heading_lead' if has_children else 'operation_record_lead',
            'span':resolve_span({'unit_id':unit['unit_id'],'quote':quote,'occurrence':0},doc),
            'role':'lexical_action_record_recall_not_core_phase_or_completeness_gold'})
    # Types are encoded in fixed-schema IDs, without changing recall categories,
    # source spans, ordering or the existing coverage rules.
    for index,row in enumerate(records,1):
        prefix='D' if row['kind']=='duration' else 'R' if row['kind']=='ri_value_lead' else 'C'
        row['candidate_id']=f'{prefix}{index:04d}'
    return records

def repeat_count(span):
    if span is None:return 1
    text=span['quote'].strip()
    m=re.fullmatch(r'(\d+)\s*(?:times|cycles|次)',text,re.I)
    if m:return int(m[1]) if int(m[1])>0 else None
    return {'twice':2,'once':1,'两次':2,'一次':1}.get(text.casefold())

def lexical_relation(fluor,target,span,entities):
    text=span['quote'];context=span['context'];f,t=re.escape(fluor),re.escape(target)
    # Deliberately narrow, versioned lexical evidence gate; co-occurrence alone never maps targets.
    patterns=[rf'{f}\s*[-–]?\s*(?:conjugated|labeled|labelled)\s+(?:anti[- ]*)?{t}',
              rf'(?:anti[- ]*)?{t}\s+(?:conjugated|labeled|labelled)\s+(?:with|to)\s+{f}',
              rf'{f}\s*(?:标记|偶联)\s*(?:的)?\s*{t}']
    if re.search(r'\b(?:not|without|either|respectively|or)\b|不|或者|分别',context,re.I):return False,'negation_or_alternative_or_inferred_assignment'
    if not any(re.search(p,text,re.I) for p in patterns):return False,'relationship_not_mechanically_explicit'
    return True,'explicit_lexical_relation_only_not_scientific_confirmation'

def omitted_numeric_name_suffix(trailing):
    number=re.match(r'^\s+\d+\b',trailing)
    if not number:return False
    # Distinguish a written amount from an identity suffix using only explicit
    # source units. No lexicon/alias inference, and no number is appended.
    quantity=re.match(r'\s*(?:[%％]|(?:micro|milli|nano|pico)?molar\b|[munpμµ]M\b|m[gl]\b|[μµ]g\b|hours?\b|minutes?\b|days?\b)',trailing[number.end():],re.I)
    return not bool(quantity)

LABEL_FIELD=re.compile(r'^\s*(?:\*\*)?(?:(?:Chosen|Selected)\s+(?:Label(?:l?ing)?|Marker|Signal)s?|Fluorescen(?:t|ce)\s+(?:Label|Marker)s?|荧光标记|选用标记)\s*[:：]\s*(?:\*\*)?\s*',re.I)

def label_clauses(context):
    """Source positions of top-level list clauses, never inferred entities."""
    header=LABEL_FIELD.match(context)
    if not header:return []
    start=header.end();end=len(context.rstrip())
    while start<end and context[start] in '[ \t':start+=1
    while end>start and context[end-1] in '] \t\r\n*':end-=1
    rows=[];depth=0;begin=start
    for index in range(start,end):
        char=context[index]
        if char in '([{':depth+=1
        elif char in ')]}':depth=max(0,depth-1)
        elif char in ',;，；' and depth==0:
            rows.append((begin,index));begin=index+1
    rows.append((begin,end));result=[]
    for a,b in rows:
        while a<b and context[a].isspace():a+=1
        while b>a and context[b-1].isspace():b-=1
        if a<b:result.append({'start':a,'end':b,'text':context[a:b]})
    return result

def paired_clause_syntax(text):
    """A bounded separator audit, not an entity parser or relation generator.

    Terminal '+' belongs to an endpoint. Exactly one possible binary separator
    is required; adjacent plus signs, alternatives and generic positive-cell
    descriptions remain unresolved. No KB names or answer IDs are consulted.
    """
    value=text.strip().rstrip('.。')
    if '++' in value or re.search(r'[/;；]|\b(?:and|or|either|not|without|respectively|alternative)\b|或者|分别|不使用',value,re.I):return None
    def atom(raw):
        raw=raw.strip()
        # A native annotation is evidence about a name, not a second identity.
        raw=re.sub(r'\s*\((?:native|endogenous|intrinsic|内源|原生)\)\s*$','',raw,flags=re.I).strip()
        body=raw[:-1] if raw.endswith('+') else raw
        if not body or body.startswith('+') or '+' in body:return None
        if not re.search(r'[A-Za-z\u0370-\u03ff]',body):return None
        if re.search(r'\b(?:cells?|neurons?|positive|negative|populations?|samples?|ions?|tissue|signal)\b',body,re.I):return None
        # Bare chemical symbols/charge prefixes cannot establish a binary pair.
        if re.fullmatch(r'[A-Z][a-z]?\d*',body) and not raw.endswith('+'):return None
        if not (re.match(r'[A-Z\u0370-\u03ff]',body) or re.search(r'[a-z][A-Z]|_',body)):return None
        return raw
    possible=[]
    for index,char in enumerate(value):
        if char!='+':continue
        left=atom(value[:index]);right=atom(value[index+1:])
        if left is not None and right is not None:
            possible.append({'separator_offset':index,'left_complete_name':left,'right_complete_name':right,
                'source_clause':text,'status':'binary_separator_syntax_only_no_entities_or_relations_inferred'})
    return possible[0] if len(possible)==1 else None

def plus_boundary_audit(literal,start,end,doc):
    unit=next(u for u in doc['units'] if u['start']<=start and end<=u['end'])
    if end>=unit['end'] or doc['text'][end]!='+':
        return {'is_separator':False,'terminal_suffix_omitted':False,'reason':'no_immediate_plus'}
    for clause in label_clauses(unit['text']):
        parsed=paired_clause_syntax(clause['text'])
        if parsed is None:continue
        separator=unit['start']+clause['start']+parsed['separator_offset']
        if separator==end and parsed['left_complete_name']==literal:
            return {'is_separator':True,'terminal_suffix_omitted':False,'reason':'unique_binary_plus_in_declared_label_clause',
                'source_unit_id':unit['unit_id'],'clause_start':unit['start']+clause['start'],
                'clause_end':unit['start']+clause['end'],'separator_offset':separator,
                'other_literal_not_created_as_entity':True,'relation_not_inferred':True}
    return {'is_separator':False,'terminal_suffix_omitted':True,'reason':'plus_is_suffix_or_unresolved_not_safe_to_clip'}

def local_name_mentions(name,evidence,doc):
    results=[]
    for match in re.finditer(re.escape(name),evidence['quote']):
        a=evidence['start']+match.start();b=evidence['start']+match.end()
        left=a>0 and bool(re.match(r'\w',doc['text'][a-1])) and bool(re.match(r'\w',name[0]))
        right=b<len(doc['text']) and bool(re.match(r'\w',doc['text'][b])) and bool(re.match(r'\w',name[-1]))
        anti=bool(re.search(r'anti[- ]$',doc['text'][max(0,a-8):a],re.I)) and not name.lower().startswith('anti')
        suffix=omitted_numeric_name_suffix(doc['text'][b:evidence['context_end']])
        plus=plus_boundary_audit(name,a,b,doc)
        punctuation=plus['terminal_suffix_omitted']
        results.append({'start':a,'end':b,'quote':doc['text'][a:b],'answer_sha256':doc['answer_sha256'],
            'same_complete_literal':not(left or right or anti or suffix or punctuation),
            'clipped_boundary':left or right,'additional_anti_qualifier':anti,'additional_numeric_suffix':suffix,
            'additional_punctuation_suffix':punctuation,'plus_boundary_audit':plus})
    return results

def relation_policy(f,t,evidence,entities):
    # Identity binding and semantic relationship evidence are different gates.
    ok,why=lexical_relation(f,t,evidence,entities)
    if ok:return ok,why
    if why=='negation_or_alternative_or_inferred_assignment':return False,why
    text=evidence['quote'].strip();ff,tt=re.escape(f),re.escape(t)
    label_header=r'(?:Fluorescen(?:t|ce)\s+(?:Label|Marker)s?|(?:Chosen|Selected)\s+(?:Label(?:l?ing)?|Marker)s?|荧光标记|选用标记)\s*[:：]'
    summary=bool(evidence.get('declared_label_clause') or re.search(label_header,evidence['context'],re.I))
    # A full field quote and its bare pair are equivalent representations.
    # Match only a recognized optional field head and one terminal punctuation;
    # never rewrite the stored quote, offsets, identity, or relationship claim.
    pair=bool(re.fullmatch(r'(?:(?i:'+label_header+r')\s*)?(?:'+tt+r'(?:\s*\([^)]*\))?\s*\+\s*'+ff+r'|'+ff+r'\s*\+\s*'+tt+r')\s*[.!?。！？]?',text))
    if summary and pair:return True,'explicit_single_pair_in_label_summary_not_expert_confirmed'
    # A full UnitRef may contain several independent explicit pairs. Inspect each
    # bounded clause, preserving literal endpoint identity and each source span.
    # The caller already requires unique complete mentions and explicit status.
    context=evidence['context'];local_pairs=[]
    for clause in label_clauses(context):
        parsed=paired_clause_syntax(clause['text'])
        if parsed is None:continue
        a=evidence['context_start']+clause['start'];b=evidence['context_start']+clause['end']
        if not(evidence['start']<=a and b<=evidence['end']):continue
        if {parsed['left_complete_name'],parsed['right_complete_name']}=={f,t}:
            local_pairs.append((a,b))
    if len(local_pairs)==1:return True,'explicit_local_binary_pair_in_declared_label_summary_not_expert_confirmed'
    # A use/purpose clause can explicitly name an anatomical target without
    # asserting a chemical conjugation. Do not infer a target from cooccurrence.
    purpose=bool(re.search(ff+r'[^.;]*\b(?:for|to label|labels)\s+'+tt+r'(?:\b|$)',text,re.I))
    if purpose:return True,'explicit_named_use_or_label_purpose_not_expert_confirmed'
    return False,'relationship_not_mechanically_explicit'

def relation_clause_support(f,t,evidence,doc,entities):
    """Bind a claimed edge to one source clause; do not infer an edge or name.

    Original evidence and primary entity spans remain unchanged. A full unit
    may mention a target in other pairs, but a repeated occurrence of the same
    claimed pair is unresolved unless the supplied RawSpan disambiguates it.
    Local context includes a clause's negation even when the quote omits it.
    """
    context=evidence['context'];header=LABEL_FIELD.match(context)
    clauses=label_clauses(context) if header else []
    body=context[header.end():] if header else context
    global_alternative=bool(re.match(r'\s*(?:\[\s*)?(?:either|neither)\b',body,re.I))
    if not clauses:
        # Outside an explicitly declared label list, only a top-level semicolon
        # supplies a safe local boundary. No splitting on prose commas/names.
        depth=0;begin=0
        for index,char in enumerate(context):
            if char in '([{':depth+=1
            elif char in ')]}':depth=max(0,depth-1)
            elif char==';' and depth==0:
                clauses.append({'start':begin,'end':index,'text':context[begin:index]});begin=index+1
        clauses.append({'start':begin,'end':len(context),'text':context[begin:]})
    candidates=[]
    for clause in clauses:
        a=evidence['context_start']+clause['start'];b=evidence['context_start']+clause['end']
        while a<b and doc['text'][a].isspace():a+=1
        while b>a and doc['text'][b-1].isspace():b-=1
        lo=max(a,evidence['start']);hi=min(b,evidence['end'])
        if lo>=hi:continue
        scoped={**evidence,'start':lo,'end':hi,'quote':doc['text'][lo:hi],
            'context_start':a,'context_end':b,'context':doc['text'][a:b],
            'declared_label_clause':bool(header),'derived_source_clause':True}
        mentions={'fluor':local_name_mentions(f,scoped,doc),'target':local_name_mentions(t,scoped,doc)}
        counts={key:sum(item['same_complete_literal'] for item in values) for key,values in mentions.items()}
        # Do not discard a repeated/ambiguous clause and choose another one.
        if not all(counts[key]>0 for key in ['fluor','target']):continue
        if counts!={'fluor':1,'target':1}:ok,why=False,'complete_endpoint_identity_ambiguous_in_local_clause'
        elif global_alternative:ok,why=False,'global_either_or_neither_scope_unresolved'
        else:ok,why=relation_policy(f,t,scoped,entities)
        candidates.append({'source_clause':{'unit_id':evidence['unit_id'],'start':a,'end':b,
                'quote':doc['text'][a:b],'answer_sha256':doc['answer_sha256'],
                'quote_sha256':rawsha(doc['text'][a:b])},
            'covered_evidence':{'start':lo,'end':hi,'quote':doc['text'][lo:hi]},
            'complete_endpoint_counts':counts,'mentions':mentions,'projection_supported':ok,'reason':why})
    unique=len(candidates)==1
    selected=candidates[0] if unique else None
    return {'projection_supported':bool(unique and selected['projection_supported']),
        'reason':selected['reason'] if unique else ('multiple_source_clauses_for_claimed_pair_unresolved' if candidates else 'complete_endpoint_identity_absent_or_ambiguous_in_relation_evidence'),
        'candidate_clauses':candidates,'selected_clause_index':0 if unique else None,
        'global_alternative_scope':global_alternative,'original_evidence_preserved':True,
        'complete_names_or_relationships_inferred':False,
        'selected_mentions':selected['mentions'] if unique else {'fluor':[],'target':[]}}

def record_action_heads(text):
    # Direct/nominal action heads only; a purpose phrase is not another order.
    actions=[]
    pattern=re.compile(r'(?:^|[;.,]\s+|\b(?:and|then)\s+)(?:\d+(?:\.\d+)*[.)]?\s*)?(incubat(?:ion|e|ing)|stor(?:age|e|ing)|wash(?:ing)?|rins(?:e|ing)|transfer(?:ring)?|immers(?:ion|e)|soak(?:ing)?|mount(?:ing)?|equilibrat(?:ion|e|ing)|dehydrat(?:ion|e|ing)|clear(?:ing)?)\b',re.I)
    for match in pattern.finditer(text):
        prefix=text[:match.start()]
        if match[1].lower().endswith('ing') and re.search(r'\bfor\b[^.;]*$',prefix,re.I):continue
        # A nominal process in a rationale is not an omitted command. Do not
        # remove imperative `clear X` or `and clearing X for ...` records.
        if match[1].lower()=='clearing' and re.match(r'\s+(?:process|procedure)\b',text[match.end():],re.I):continue
        actions.append(match[1])
    return actions

def record_binding(operation,value,doc):
    """A lexical binding guard, never semantic operation-assignment proof."""
    unit=next(u for u in doc['units'] if u['unit_id']==operation['unit_id'])
    envelope={'unit_id':unit['unit_id'],'start':unit['start'],'end':unit['end'],'text_sha256':rawsha(unit['text'])}
    contained=operation['start']<=value['start'] and value['end']<=operation['end']
    if contained:
        durations=[m for m in DURATION.finditer(operation['quote']) if duration_role(m.group(),operation['quote'][:m.start()],operation['quote'][m.end():])[0]=='duration'];actions=record_action_heads(operation['quote'])
        valid=len(durations)==1 and len(actions)<=1
        return {'valid':valid,'mode':'inside_operation_quote' if valid else 'ambiguous_multioperation_or_multiduration_quote',
            'record_envelope':envelope,'quoted_duration_count':len(durations),'quoted_action_heads':actions,
            'semantic_assignment_verified':False,'guard_scope':'literal duration count and narrow action-head enumeration, not exhaustive NLP'}
    if value['unit_id']!=operation['unit_id']:return {'valid':False,'mode':'different_source_units','record_envelope':envelope}
    durations=[m for m in DURATION.finditer(unit['text']) if duration_role(m.group(),unit['text'][:m.start()],unit['text'][m.end():])[0]=='duration'];actions=record_action_heads(unit['text'])
    valid=len(durations)==1 and len(actions)==1
    return {'valid':valid,'mode':'same_source_record_unique_action_and_duration' if valid else 'ambiguous_source_record',
        'record_envelope':envelope,'record_duration_count':len(durations),'record_action_heads':actions,
        'semantic_assignment_verified':False}

def exact_identity_mention_coverage(candidate,entities,doc):
    """Cross-mention identity only; never extend usage or infer a target."""
    span=candidate['span'];matches=[]
    uncertainty=re.compile(r'\b(?:not|without|either|or|alternative|instead|absent)\b|不|或者|替代|任选',re.I)
    for entity in entities:
        primary=entity['name']
        if primary['quote']!=span['quote']:continue
        literal=local_name_mentions(primary['quote'],span,doc)
        if len(literal)!=1 or not literal[0]['same_complete_literal']:continue
        # A repeated same spelling in a negative/alternative context is still a
        # real mention, but its usage requires its own record or unresolved span.
        if uncertainty.search(span['context']) or uncertainty.search(primary['context']):continue
        if entity['usage']!='used':continue
        matches.append(entity['id'])
    return {'covered':bool(matches),'source_entity_ids':matches,'kind':'exact_literal_identity_only',
        'target_or_new_usage_inferred':False,'candidate_span':span}

def parse_ri_literal(text):
    stripped=text.strip()
    if re.fullmatch(NUMBER,stripped):return float(stripped),'explicit_numeric_quote'
    match=re.fullmatch(r'(?:RI|refractive\s+index|折射率)\s*(?:=|:|：|≈|~)?\s*('+NUMBER+r')',stripped,re.I)
    if match:return float(match[1]),'explicit_RI_label_and_unique_numeric_value'
    return None,'no_supported_unique_RI_numeric_expression'

def labeling_preparation_basis(operation,doc):
    """Check a model-proposed phase against bounded, traceable section syntax.

    A generic preparation heading does not prove an exclusion. Permeabilization
    plus blocking additionally requires a labeled ancestor or the immediately
    following same-level labeling section; the operation cannot declare a core
    clearing function. This remains provisional lexical evidence, not phase gold.
    """
    unit=next(u for u in doc['units'] if u['unit_id']==operation['unit_id'])
    numbered=re.match(r'^\s*(\d+(?:\.\d+)*)(?:[.)])?\s+',unit['text'])
    operation_number=numbered[1] if numbered else None
    headings=[]
    for candidate in doc['units']:
        text=candidate['text'].strip();m=re.match(r'^(\d+(?:\.\d+)*)(?:[.)])?\s+(.+)$',text)
        md=re.match(r'^(#{1,6})\s+(.+)$',text)
        if m and not DURATION.search(text):
            child=any(re.match(r'^\s*'+re.escape(m[1])+r'\.\d+\b',u['text']) for u in doc['units'] if u['start']>candidate['start'])
            if child:headings.append({'unit':candidate,'number':m[1],'level':len(m[1].split('.')),'kind':'numbered','title':m[2]})
        elif md:headings.append({'unit':candidate,'number':None,'level':len(md[1]),'kind':'markdown','title':md[2]})
    ancestors=[h for h in headings if h['unit']['start']<unit['start'] and h['kind']=='numbered' and
        operation_number and operation_number.startswith(h['number']+'.')]
    if ancestors:
        latest=max(ancestors,key=lambda h:(h['level'],h['unit']['start']))
    else:
        stack=[]
        for h in headings:
            if h['unit']['start']>=unit['start']:break
            if h['kind']!='markdown':continue
            while stack and stack[-1]['level']>=h['level']:stack.pop()
            stack.append(h)
        ancestors=stack;latest=stack[-1] if stack else None
    label=re.compile(r'\b(?:immunostain\w*|immunolabel\w*|staining|label(?:l?ing)?)\b|免疫染色|标记',re.I)
    context=None;relation=None
    if latest and label.search(latest['title']):context=latest;relation='explicit_labeling_parent_heading'
    elif latest and re.search(r'permeabili\w*\s+(?:and|&)\s+block\w*|透化.*封闭',latest['title'],re.I):
        labelled=[h for h in ancestors if label.search(h['title'])]
        if labelled:context=labelled[-1];relation='explicit_labeling_ancestor_heading'
        else:
            later=[h for h in headings if h['unit']['start']>latest['unit']['start'] and h['kind']==latest['kind'] and h['level']<=latest['level']]
            next_heading=later[0] if later else None
            if next_heading and next_heading['level']==latest['level'] and label.search(next_heading['title']):
                context=next_heading;relation='immediately_following_same_level_labeling_section'
    source_supported=context is not None
    mixed=bool(re.search(r'delipid|decalcif|decolor|RI\s+match|refractive\s+index\s+match|clearing\s+reagent|脱脂|脱钙|脱色|折射率',operation['quote'],re.I))
    def span(heading):
        if not heading:return None
        row=heading['unit'];return resolve_span({'unit_id':row['unit_id'],'quote':row['text'].strip(),'occurrence':0},doc)
    return {'supported':source_supported and not mixed,'source_heading':span(latest),'labeling_context_heading':span(context),
        'section_relation':relation,'operation_number':operation_number,
        'possible_core_function':mixed,'unknown_or_multifunction_not_automatically_excluded':True,
        'model_phase_not_overwritten':True,'scientific_phase_confirmed':False}

def intrinsic_policy(record,entity,relations,doc,all_entities=None):
    evidence=record['evidence'];name=entity['name']['quote'];mentions=local_name_mentions(name,evidence,doc)
    native=r'\b(?:native|endogenous|intrinsic)\b|内源|原生|自发报告信号'
    bad=r'\b(?:not|without|either|or|alternative|may|can|lost|quenched|absent|instead|like)\b|\boptimi[sz]ed\s+to\b|e\.g\.|不|备选|替代|例如|比如'
    affirmative=r'\b(?:select(?:ed)?|chosen|use(?:d)?|retain(?:ed)?|preserv(?:ed)?)\b|选用|选择|采用|保留'
    parts=re.split(r'[,;\[\]，；]',evidence['quote']);local=[p for p in parts if name in p]
    clause=local[0] if len(local)==1 else evidence['quote']
    complete=sum(m['same_complete_literal'] for m in mentions)==1
    native_cue=bool(re.search(native,clause,re.I))
    positive=bool(re.search(affirmative,evidence['context'],re.I))
    disqualified=bool(re.search(bad,clause,re.I) or re.search(r'\b(?:method|technique)\b[^.;]*(?:\bcan\b|\bmay\b|\boptimi[sz]ed\s+to\b)|方法[^。]*(?:能够|可以)',evidence['context'],re.I))
    conflicts=[]
    for unit in doc['units']:
        if name not in unit['text']:continue
        if re.search(native,unit['text'],re.I) and re.search(r'\b(?:not\s+used|lost|quenched|absent|antibody[- ]only)\b|不使用|已丢失|仅抗体',unit['text'],re.I):
            conflicts.append({'unit_id':unit['unit_id'],'start':unit['start'],'end':unit['end'],'reason':'conflicting_native_signal_statement'})
    all_entities=all_entities or [entity];byid={x['id']:x for x in all_entities}
    samekey={x['id'] for x in all_entities if x['name']['quote']==name}
    external=[r['id'] for r in relations if r['fluor_entity_id'] in samekey]
    incoming=[r['id'] for r in relations if r['target_entity_id'] in samekey and r['fluor_entity_id'] not in samekey]
    conditional=bool(re.search(r'\b(?:if|when|unless|condition(?:al)?|in another)\b|如果|条件|另一',evidence['context'],re.I))
    collisions=[x['id'] for x in all_entities if x['id']!=entity['id'] and x['name']['quote']==name and
        (x['kind']!=entity['kind'] or x['usage']!=entity['usage'] or re.search(r'\b(?:if|unless|condition(?:al)?|in another)\b|如果|条件|另一',x['name']['context'],re.I))]
    incoming_scope=[r['id'] for r in relations if r['id'] in incoming and re.search(r'\b(?:if|unless|condition(?:al)?|in another)\b|如果|条件|另一',r['evidence']['context'],re.I)]
    atomic=entity.get('name_binding',{}).get('atomicity',{}).get('projection_eligible_provisional',True)
    ok=record['status']=='source_declared' and atomic and entity['kind']=='fluorescent_protein' and entity['usage']=='used' and complete and native_cue and positive and not disqualified and not conflicts and not external and not collisions and not conditional and not incoming_scope
    return {'projection_allowed':ok,'predicate':'source_declared_intrinsic_identity','relation_not_self_binding':True,
        'local_mentions':mentions,'complete_name_occurrence':complete,'native_source_cue':native_cue,
        'affirmative_use_context':positive,'disqualified_by_capability_alternative_or_negation':disqualified,
        'source_conflicts':conflicts,'explicit_external_relation_conflicts':external,
        'outgoing_same_literal_key_claims':external,'incoming_target_claims_not_same_key_conflicts':incoming,
        'literal_identity_collisions':collisions,'conditional_identity_context':conditional,'incoming_scope_uncertainty':incoming_scope,
        'atomic_name_projection_eligible':atomic,
        'question_or_recommendation_metadata_used':False,'biological_preservation_or_task_fulfillment_confirmed':False,
        'affirmative_proposed_usage_is_not_observed_experimental_execution':True,
        'legacy_identity_serialization':{name:name} if ok else None}

def affirmative_entity_use(name,text):
    escaped=re.escape(name)
    declared=bool(re.search(r'(?:chosen|selected)\s+(?:label(?:l?ing)?|marker|signal)s?\s*[:：][^\n]*'+escaped,text,re.I))
    # A chosen-field heading does not make every member of its explicit
    # alternative group used. Other affirmative operations remain independent.
    groups=[part for part in re.split(r'[,;，；]',text) if re.search(escaped,part)]
    if any(re.search(r'/|\b(?:either|or|alternative)\b|备选|任选|或者',part,re.I) for part in groups):declared=False
    operative=bool(re.search(r'\b(?:incubat\w*|stain\w*|detect\w*|use[ds]?|apply|add)\b[^.;\n]*'+escaped,text,re.I) or re.search(escaped+r'[^.;\n]*\bis\s+used\b',text,re.I))
    return declared or operative

def mentioned_usage_support(entity):
    text=entity['name']['context'];name=entity['name']['quote']
    cue=bool(re.search(r'e\.g\.|\bfor example\b|\bsuch as\b|\blike\b|\boptimi[sz]ed\s+to\b|\bcan preserve\b|\bcapabilit\w*\b|例如|比如',text,re.I))
    affirmative=affirmative_entity_use(name,text)
    negative=bool(re.search(r'\bnot\b|\bwithout\b|不使用|不用',text,re.I))
    return {'supported':cue and not affirmative and not negative,'source_capability_or_example_cue':cue,
        'same_record_affirmative_use_cue':affirmative,'negation_cue':negative,
        'source_span':entity['name'],'not_projected_as_used':True,'scientific_usage_confirmed':False}

def name_atomicity(literal,support):
    """Public syntax diagnostic, independent of exact binding and any name KB.

    Punctuation alone never invalidates an exact source identity. Only bounded
    composite-list cues withhold projection; neither outcome is semantic gold.
    """
    reasons=[]
    if re.search(r'\S\s*/\s*\S',literal):reasons.append('slash_composite_syntax')
    if re.search(r'\S\s*[;；]\s*\S',literal):reasons.append('semicolon_composite_syntax')
    if re.search(r'\S\s+\+\s+\S',literal):reasons.append('separated_plus_composite_syntax')
    if LABEL_FIELD.match(support['context']) and paired_clause_syntax(literal):reasons.append('declared_label_binary_plus_composite_syntax')
    if '++' in literal:reasons.append('consecutive_plus_syntax_unresolved')
    # Do not classify chemical locants such as 2,2-prime as a comma list.
    pieces=[x.strip() for x in re.split(r'(?<!\d)[,，](?!\d)',literal)]
    header=bool(re.search(r'(?:chosen|selected|fluorescent)\s+(?:methods?|labels?|label(?:l?ing)|markers?|signals?)\s*[:：]',support['context'],re.I))
    parallel_ids=len(pieces)>1 and all(re.fullmatch(r'[A-Z][A-Z0-9_-]*',x) for x in pieces)
    outer_list=literal.startswith('[') and literal.endswith(']')
    if len(pieces)>1 and (parallel_ids or header or outer_list):reasons.append('comma_list_context_or_parallel_identifiers')
    return {'state':'unresolved_composite_syntax' if reasons else 'no_composite_syntax_detected_provisional',
        'projection_eligible_provisional':not reasons,'reasons':reasons,
        'punctuation_itself_is_not_hard_failure':True,'complete_literal_retained':True,
        'KB_membership_used':False,'semantic_atomicity_confirmed':False,
        'policy':'Slash/semicolon/separated-plus or comma plus list context/parallel uppercase identifiers withhold projection. Other punctuation and unknown multiword names are retained provisionally; no entities are split or inferred.'}

def bind_literal_name(literal,support,doc,name_occurrence):
    """Exact selected occurrence of a complete literal inside full-unit support.

    These public lexical guards reject field/list representations. A surviving
    unknown name remains a literal identity proposal, not a semantic gold label.
    The explicit index counts all exact substrings BEFORE any boundary filtering.
    """
    require(isinstance(literal,str) and bool(literal) and literal==literal.strip(),'NAME_WHITESPACE_NOT_IDENTITY')
    require(not re.search(r'[\r\n]|^\s*(?:\*\*|#{1,6}\s)|(?:chosen|selected)\s+(?:method|label(?:l?ing)?s?|markers?|signals?)\s*[:：]|^(?:method|labels?|markers?|方法|标记)\s*[:：]',literal,re.I),'NONATOMIC_NAME_FIELD_HEADER')
    require(not re.search(r'\b(?:is selected|is used|can preserve|optimized to|optimi[sz]ed for)\b',literal,re.I),'NONATOMIC_NAME_ASSERTION')
    require(isinstance(name_occurrence,int) and not isinstance(name_occurrence,bool) and name_occurrence>=0,'NAME_OCCURRENCE_INVALID')
    raw_hits=list(re.finditer('(?='+re.escape(literal)+')',support['quote']))
    require(name_occurrence<len(raw_hits),'NAME_OCCURRENCE_NOT_FOUND')
    selected_start=support['start']+raw_hits[name_occurrence].start()
    hits=[];rejections=[]
    for m in re.finditer('(?='+re.escape(literal)+')',support['quote']):
        start=support['start']+m.start();end=start+len(literal)
        before=doc['text'][max(0,start-32):start];after=doc['text'][end:support['context_end']]
        why=[]
        if start>0 and re.match(r'\w',doc['text'][start-1]) and re.match(r'\w',literal[0]):why.append('CLIPPED_NAME_START')
        if re.search(r'\banti[-\s]+$',before,re.I):why.append('OMITTED_ANTIBODY_IDENTITY_PREFIX')
        if end<len(doc['text']) and re.match(r'\w',doc['text'][end]) and re.match(r'\w',literal[-1]):why.append('CLIPPED_NAME_END')
        if plus_boundary_audit(literal,start,end,doc)['terminal_suffix_omitted']:why.append('OMITTED_PUNCTUATION_IDENTITY_SUFFIX')
        if omitted_numeric_name_suffix(after):why.append('OMITTED_DISTINGUISHING_NUMERIC_SUFFIX')
        if why:rejections.append({'start':start,'end':end,'reasons':why});continue
        hits.append((start,end))
    rejected_selected=next((r for r in rejections if r['start']==selected_start),None)
    require(rejected_selected is None,rejected_selected['reasons'][0] if rejected_selected else 'SELECTED_NAME_BOUNDARY')
    selected=[h for h in hits if h[0]==selected_start];require(len(selected)==1,'SELECTED_NAME_NOT_COMPLETE')
    start,end=selected[0];unit=next(u for u in doc['units'] if u['unit_id']==support['unit_id'])
    occurrences=[m.start() for m in re.finditer('(?='+re.escape(literal)+')',unit['text'])]
    narrow=resolve_span({'unit_id':unit['unit_id'],'quote':literal,'occurrence':occurrences.index(start-unit['start'])},doc)
    return narrow,{'literal_name':literal,'supporting_evidence':copy.deepcopy(support),'derived_name_span':copy.deepcopy(narrow),
        'atomicity':name_atomicity(literal,support),
        'name_occurrence':name_occurrence,'occurrence_index_basis':'all_exact_literal_occurrences_in_full_unit_before_boundary_validation',
        'exact_occurrences_in_support':len(raw_hits),'complete_occurrences_in_support':len(hits),'rejected_substring_occurrences':rejections,'record_id_or_KB_used_to_infer_name':False,
        'plus_boundary_audit':plus_boundary_audit(literal,start,end,doc),
        'atomicity_guard':'hard field/assertion guard plus separate nonfatal composite syntax audit; exact literal binding is independent of atomicity',
        'semantic_identity_confirmed':False,'original_support_preserved':True}

def repeat_source_binding(operation,repeat,doc,registry):
    """New reference-assignment guard; repeat_count and time arithmetic unchanged."""
    inside=operation['unit_id']==repeat['unit_id'] and operation['start']<=repeat['start'] and repeat['end']<=operation['end']
    candidates=[r for r in registry['repeat_candidates'] if operation['start']<=r['span']['start'] and r['span']['end']<=operation['end']]
    actions=record_action_heads(operation['quote'])
    precise=operation.get('candidate_reference',{}).get('kind')=='operation_span'
    declarations=[r for r in registry['repeat_declarations'] if operation['start']<=r['span']['start'] and r['span']['end']<=operation['end']]
    unsupported=[r for r in declarations if not r['eligible_repeat_candidate_ids']]
    valid=inside and len(candidates)==1 and not unsupported and (len(actions)<=1 if precise else len(actions)==1)
    return {'valid':bool(valid),'mode':'selected_operation_extent' if precise else 'full_unit_unique_action_and_repeat',
        'repeat_inside_selected_operation':inside,'repeat_candidates_in_operation':len(candidates),
        'action_heads_in_operation':actions,'reason':None if valid else 'repeat_not_uniquely_bound_to_selected_operation_extent',
        'repeat_declarations_in_operation':copy.deepcopy(declarations),'unsupported_declarations':copy.deepcopy(unsupported),
        'full_original_unit_context_preserved':operation['context']==next(u['text'] for u in doc['units'] if u['unit_id']==operation['unit_id']),
        'semantic_repeat_claim_confirmed':False}

def _audit_expanded_payload(payload,doc):
    require(rawsha(doc['text'])==doc['answer_sha256'] and document(doc['text'],doc['source_id'])['units']==doc['units'],'DOCUMENT_HASH_OR_UNIT_BINDING')
    validate_shape(payload,_expanded_schema());integrity.validate_score_proposals(payload['scores'])
    g=payload['grounded_extraction'];require(g['source_id']==doc['source_id'],'SOURCE_ID_MISMATCH')
    registry=candidate_registry(doc);score_evidence=copy.deepcopy(payload['score_evidence'])
    require(len(score_evidence)==len(DIRECT) and {e['metric'] for e in score_evidence}==set(DIRECT),'SCORE_EVIDENCE_EXACT_FIVE_UNIQUE')
    for e in score_evidence:
        e['answer_spans']=[resolve(s,doc,registry) for s in e['answer_spans']]
        if e['basis'] in ['observed','mixed']:require(bool(e['answer_spans']),'OBSERVED_SCORE_EVIDENCE_REQUIRES_SPAN')
        if e['basis']=='absence':require(not e['answer_spans'],'ABSENCE_EVIDENCE_IS_NOT_A_QUOTED_PRESENT_FACT')
        require(bool(e['rubric_basis'].strip()),'EMPTY_SCORE_RUBRIC_BASIS')
    result=copy.deepcopy(g);allids=set();used_spans=[]
    def resolved(ref):
        value=resolve(ref,doc,registry);used_spans.append(value);return value
    for group,fields in [('method_mentions',['supporting_evidence']),('entities',['supporting_evidence']),('relations',['evidence']),
        ('intrinsic_signals',['evidence']),('operations',['operation','duration','repeat_evidence','condition_evidence']),('total_time_claims',['duration']),('ri_mentions',['value'])]:
        for r in result[group]:
            require(r['id'] not in allids,'DUPLICATE_RECORD_ID');allids.add(r['id'])
            for field in fields:
                if r[field] is not None:
                    r[field]=resolved(r[field]);candidate=r[field].get('candidate_reference')
                    if field=='duration':require(candidate and candidate['kind']=='duration','CANDIDATE_KIND_NOT_DURATION_EVIDENCE')
                    if group=='ri_mentions' and field=='value':require(candidate and candidate['kind']=='ri_value_lead','CANDIDATE_KIND_NOT_RI_EVIDENCE')
                    if field=='operation' and candidate:require(candidate['kind']=='operation_span','CANDIDATE_KIND_NOT_OPERATION_EVIDENCE')
                    if field=='repeat_evidence':require(candidate and candidate['kind']=='repeat_literal','CANDIDATE_KIND_NOT_REPEAT_EVIDENCE')
            if 'literal_name' in r:
                r['name'],r['name_binding']=bind_literal_name(r['literal_name'],r['supporting_evidence'],doc,r['name_occurrence'])
                used_spans.append(r['name'])
    if result['timeline']['relation_evidence'] is not None:result['timeline']['relation_evidence']=resolved(result['timeline']['relation_evidence'])
    for r in result['coverage']['unresolved']:r['evidence']=resolved(r['evidence'])
    entities={e['id']:e for e in result['entities']};ops={o['id']:o for o in result['operations']}
    result['duplicate_literal_identity_audit']=[{'literal_name':name,'entity_ids':[e['id'] for e in result['entities'] if e['name']['quote']==name],
        'records_preserved_not_silently_merged':True,'semantic_equivalence_confirmed':False}
        for name in sorted({e['name']['quote'] for e in result['entities']}) if sum(e['name']['quote']==name for e in result['entities'])>1]
    for e in result['entities']:
        if e['usage']=='mentioned':e['mentioned_usage_support']=mentioned_usage_support(e)
    usage_gaps=[]
    for name in sorted({e['name']['quote'] for e in result['entities']}):
        if any(e['name']['quote']==name and e['usage']=='used' for e in result['entities']):continue
        for unit in doc['units']:
            if name not in unit['text'] or not affirmative_entity_use(name,unit['text']):continue
            context=resolve_span({'unit_id':unit['unit_id'],'quote':unit['text'].strip(),'occurrence':0},doc)
            if any(m['same_complete_literal'] for m in local_name_mentions(name,context,doc)):
                usage_gaps.append({'exact_name':name,'unit_id':unit['unit_id'],'start':unit['start'],'end':unit['end'],
                    'reason':'affirmative_source_occurrence_without_any_used_entity_record','model_usage_not_silently_overridden':True})
    result['affirmative_entity_usage_gaps']=usage_gaps
    for r in result['relations']:
        require(r['fluor_entity_id'] in entities and (r['target_entity_id'] is None or r['target_entity_id'] in entities),'RELATION_DANGLING_ENTITY')
        require(r['target_entity_id'] is not None or r['status'] in ['unknown','ambiguous'],'EXPLICIT_RELATION_REQUIRES_TARGET')
        f=entities[r['fluor_entity_id']];t=entities[r['target_entity_id']] if r['target_entity_id'] is not None else None
        mentions={'fluor':local_name_mentions(f['name']['quote'],r['evidence'],doc),
                  'target':local_name_mentions(t['name']['quote'],r['evidence'],doc) if t else []}
        r['relation_evidence_mentions']=mentions;r['primary_entity_spans_preserved']=True
        scope=relation_clause_support(f['name']['quote'],t['name']['quote'],r['evidence'],doc,result['entities']) if t else None
        r['relation_clause_scope_audit']=scope
        r['relation_local_mentions']=scope['selected_mentions'] if scope else mentions
        if t is None:ok,why=False,'unknown_target_endpoint_not_projected'
        elif not f['name_binding']['atomicity']['projection_eligible_provisional'] or not t['name_binding']['atomicity']['projection_eligible_provisional']:ok,why=False,'endpoint_name_atomicity_unresolved'
        elif f['kind'] not in ['fluorophore','fluorescent_protein']:ok,why=False,'label_endpoint_kind_unresolved'
        elif f['id']==t['id']:ok,why=False,'self_target_identity_not_supported'
        else:ok,why=scope['projection_supported'],scope['reason']
        r['projection_allowed']=r['status']=='explicit' and ok;r['mechanical_relation_state']=why
        r['entity_type_and_relation_role_distinct']=True
        r['unsupported_claim_retained_not_repaired']=r['status']=='explicit' and not r['projection_allowed']
    for record in result['intrinsic_signals']:
        require(record['entity_id'] in entities,'INTRINSIC_DANGLING_ENTITY')
        record['identity_policy']=intrinsic_policy(record,entities[record['entity_id']],result['relations'],doc,result['entities'])
    duration_spans=[]
    for o in result['operations']:
        op=o['operation']
        if o['duration']:
            d=o['duration'];op=o['operation']
            binding=record_binding(op,d,doc);o['duration_binding']=binding
            key=(d['start'],d['end']);require(key not in duration_spans,'REUSED_DURATION_DOUBLE_COUNT');duration_spans.append(key)
            literal=duration_value(d['quote']);o['raw_literal_parsed_duration']=literal
            nonadditive=next((r['kind'] for r in registry['records'] if r['kind'] in ['dimensional_expression_lead','recurrence_interval_lead'] and r['span']['start']==d['start'] and r['span']['end']==d['end']),None)
            o['parsed_duration']=literal if binding['valid'] and not nonadditive else {'state':nonadditive+'_not_operation_duration' if nonadditive else 'unresolved_operation_record_binding','bounds_hours':None,'unique_hours':None}
            o['legacy_overnight_comparison']=duration_value(d['quote'],8)
        else:o['parsed_duration']={'state':'missing','bounds_hours':None,'unique_hours':None}
        if o['phase']=='labeling_preparation':o['phase_support']=labeling_preparation_basis(o['operation'],doc)
        if o['repeat_evidence']:
            require(o['operation']['unit_id']==o['repeat_evidence']['unit_id'],'REPEAT_OUTSIDE_OPERATION_RECORD')
            o['repeat_source_binding']=repeat_source_binding(o['operation'],o['repeat_evidence'],doc,registry)
        if o['condition_evidence']:
            require(o['operation']['unit_id']==o['condition_evidence']['unit_id'],'CONDITION_OUTSIDE_OPERATION_RECORD')
        conditional_pattern=r'\bif\b|\bwhen needed\b|\bas needed\b|\bafter storage\b|\bre[- ]equilibrat\w*\b|\bagain\b|\brepeated\b|\bfuture\b|如需|如果|再次|再平衡|保存后'
        conditional_cue=re.search(conditional_pattern,o['operation']['context'],re.I)
        o['scope_gate']={'conditional_cue_detected':bool(conditional_cue),
            'conditional_scope_supported':bool(o['condition_evidence'] and re.search(conditional_pattern,o['condition_evidence']['quote'],re.I))}
        o['repeat_count']=repeat_count(o['repeat_evidence'])
        if o['repeat_evidence'] and not o['repeat_source_binding']['valid']:
            o['repeat_count']=None;o['repeat_uncertainty']='repeat_source_extent_binding_unresolved'
        if not o['repeat_evidence']:
            declarations=[r for r in registry['repeat_declarations'] if op['start']<=r['span']['start'] and r['span']['end']<=op['end']]
            if declarations:
                o['repeat_count']=None;o['repeat_uncertainty']='explicit_repetition_declaration_without_bound_P_reference'
                o['repeat_missing_reference_audit']={'source_declarations':copy.deepcopy(declarations),
                    'selected_operation_extent':{'start':op['start'],'end':op['end'],'unit_id':op['unit_id']},
                    'default_single_performance_withheld':True,'repeat_arithmetic_changed':False}
        repeat_context=o['operation']['context'] if o.get('duration_binding',{}).get('mode')=='same_source_record_unique_action_and_duration' else o['operation']['quote']
        if o['duration'] and re.search(r'\beach\b|每',repeat_context,re.I) and not o['repeat_evidence']:
            o['repeat_count']=None;o['repeat_uncertainty']='each_without_explicit_count'
    members=result['timeline']['operation_ids'];require(len(members)==len(set(members)) and set(members)<=set(ops),'TIMELINE_DUPLICATE_OR_DANGLING_OPERATION')
    result['timeline_proposal']=copy.deepcopy(result['timeline'])
    derived=[o['id'] for o in sorted(result['operations'],key=lambda x:x['operation']['start']) if o['phase'] in INCLUDE and o['execution_scope']=='initial']
    result['timeline']['operation_ids']=derived
    result['timeline_derivation']={'model_proposed_operation_ids':members,'program_initial_operation_ids':derived,
        'excluded_from_proposal':[i for i in members if i not in derived],'added_from_declared_initial_operations':[i for i in derived if i not in members],
        'same_members_and_order':members==derived,'raw_proposal_preserved':True,'phase_and_scope_semantics_verified':False}
    graph={k:[] for k in ops}
    for e in result['precedence_edges']:
        require(e['before_id'] in ops and e['after_id'] in ops,'EDGE_DANGLING_OPERATION');e['evidence']=resolved(e['evidence'])
        graph[e['before_id']].append(e['after_id'])
        e['direction_agrees_with_document_order']=ops[e['before_id']]['operation']['start']<ops[e['after_id']]['operation']['start']
        before,after=ops[e['before_id']]['operation'],ops[e['after_id']]['operation']
        same_unit=e['evidence']['unit_id']==before['unit_id']==after['unit_id']
        endpoints_covered=e['evidence']['start']<=before['start'] and before['end']<=e['evidence']['end'] and e['evidence']['start']<=after['start'] and after['end']<=e['evidence']['end']
        cue=bool(re.search(r'\bbefore\b|\bafter\b|\bthen\b|\bfollowed by\b|之后|之前|然后',e['evidence']['quote'],re.I))
        e['source_dependency_support']={'same_source_unit':same_unit,'both_operation_spans_covered':endpoints_covered,'explicit_dependency_cue':cue,
            'mechanically_supported':same_unit and endpoints_covered and cue,'adjacent_numbering_alone_sufficient':False}
        e['scientific_dependency_verified']=False;e['used_for_time_aggregation']=False
    done=set();active=set()
    def visit(node):
        require(node not in active,'CYCLIC_TIME_GRAPH')
        if node in done:return
        active.add(node)
        for child in graph[node]:visit(child)
        active.remove(node);done.add(node)
    cyclic=False
    try:
        for node in graph:visit(node)
    except ValueError as exc:
        require(str(exc)=='CYCLIC_TIME_GRAPH','UNEXPECTED_GRAPH_ERROR');cyclic=True
    result['precedence_audit']={'cyclic_model_proposal':cyclic,'backward_document_order_edges':sum(not e['direction_agrees_with_document_order'] for e in result['precedence_edges']),
        'unsupported_dependency_claims':sum(not e['source_dependency_support']['mechanically_supported'] for e in result['precedence_edges']),
        'model_edges_used_for_aggregation':False,'program_uses_declared_schedule_and_source_order_convention':True}
    inventory=copy.deepcopy(registry['records'])
    substantive=[s for o in result['operations'] for s in [o['duration']] if s]+[t['duration'] for t in result['total_time_claims']]
    unresolved=[r['evidence'] for r in result['coverage']['unresolved']]
    for r in inventory:
        s=r['span']
        cross_identity=exact_identity_mention_coverage(r,result['entities'],doc) if r['kind'] in ['numbered_name_lead','known_marker_name_lead'] else None
        if any(v['start']<=s['start'] and s['end']<=v['end'] for v in substantive if r['kind']=='duration'):state='covered_time_evidence'
        elif any(v['start']<=s['start'] and s['end']<=v['end'] for v in unresolved):state='explicitly_unresolved'
        elif r['kind'] in ['numbered_name_lead','known_marker_name_lead'] and any(v['name']['start']<=s['start'] and s['end']<=v['name']['end'] for v in result['entities']):
            matching=[v for v in result['entities'] if v['name']['start']<=s['start'] and s['end']<=v['name']['end']]
            eligible=[v for v in matching if v['name_binding']['atomicity']['projection_eligible_provisional']]
            state='entity_name_atomicity_unresolved' if not eligible else 'covered_entity_name' if any(v['usage']=='used' for v in eligible) else 'classified_entity_nonused_or_unknown'
        elif cross_identity and cross_identity['covered']:
            state='covered_repeated_exact_entity_identity';r['cross_mention_identity_coverage']=cross_identity
        elif r['kind']=='known_method_name_lead' and any(v['name']['start']<=s['start'] and s['end']<=v['name']['end'] for v in result['method_mentions']):state='classified_method_name'
        elif r['kind']=='dimensional_expression_lead':state='classified_non_duration_dimensional_expression'
        elif r['kind']=='recurrence_interval_lead':state='classified_non_additive_recurrence_interval'
        elif r['kind']=='action_section_heading_lead':state='source_section_heading_with_decimal_child_records'
        elif r['kind']=='operation_record_lead' and any(o['operation']['unit_id']==s['unit_id'] for o in result['operations']):state='covered_operation_record'
        elif r['kind'] not in ['duration','numbered_name_lead','known_marker_name_lead','known_method_name_lead'] and any(v['start']<=s['start'] and s['end']<=v['end'] for v in used_spans):state='covered_supplied_span'
        else:state='uncovered_candidate'
        r['coverage_state']=state
    return {'source_binding':{'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],'candidate_registry_sha256':registry['registry_sha256'],'enumerator_version':VERSION},'resolved':result,
            'score_evidence':score_evidence,'score_evidence_semantic_validity':'not_certified; source quotes do not establish correct rubric application',
            'inventory':inventory,'software_span_valid':True,'scientific_completeness_certified':False}

def compute_time(audit):
    g=audit['resolved'];ops=g['operations'];core=[o for o in ops if o['phase'] in INCLUDE]
    inc=[o for o in core if o['execution_scope']=='initial'];conditional=[o for o in core if o['execution_scope']=='conditional_or_future'];issues=[]
    if any(o['phase']=='unknown' for o in ops):issues.append('unresolved_phase_scope')
    if any(o['phase']=='labeling_preparation' and not o['phase_support']['supported'] for o in ops):issues.append('labeling_preparation_not_source_supported_or_possible_core_function')
    if any(o['execution_scope']=='unknown' for o in core):issues.append('unresolved_execution_scope')
    if any(o['scope_gate']['conditional_cue_detected'] for o in inc):issues.append('initial_operation_contains_conditional_scope_cue')
    if any(not o['scope_gate']['conditional_scope_supported'] for o in conditional):issues.append('conditional_scope_lacks_explicit_source_evidence')
    if conditional:issues.append('conditional_operations_require_endpoint_resolution')
    if set(g['timeline']['operation_ids'])!={o['id'] for o in inc}:issues.append('timeline_does_not_cover_exact_included_operations')
    if g['coverage']['core_time_operations']!='complete':issues.append('reported_core_operation_coverage_incomplete')
    if any(r['kind']=='duration' and r['coverage_state']!='covered_time_evidence' for r in audit['inventory']):issues.append('source_duration_candidates_not_all_classified')
    if any(r['kind']=='operation_record_lead' and r['coverage_state']!='covered_operation_record' for r in audit['inventory']):issues.append('source_action_records_not_all_classified')
    mode=g['timeline']['mode'];e=g['timeline']['relation_evidence'];evidence=e['quote'] if e else ''
    if mode=='parallel' and not re.search(r'simultaneous|in parallel|同时|并行',evidence,re.I):issues.append('parallel_relation_not_explicit')
    if mode=='alternative' and not re.search(r'\bor\b|either|任选|或者',evidence,re.I):issues.append('alternative_relation_not_explicit')
    if mode=='serial':
        # A deterministic textual-order convention is reported, never a claim of scientific necessity.
        starts=[next(o['operation']['start'] for o in inc if o['id']==i) for i in g['timeline']['operation_ids'] if i in {x['id'] for x in inc}]
        if starts!=sorted(starts):issues.append('serial_order_not_source_order')
        # Excluded staining/imaging schedules must not invalidate a serial
        # core-clearing calculation. Relevant operation spans and the explicit
        # supplied scheduling evidence are the only schedule-cue scope here.
        relevant_context='\n'.join(o['operation']['quote'] for o in inc)+'\n'+evidence
        if re.search(r'\b(?:parallel|simultaneous|either)\b|同时|并行|任选',relevant_context,re.I):issues.append('source_schedule_ambiguity')
    if mode=='unknown':issues.append('schedule_unknown')
    bounds=[];known_contributions=[];has_unknown=False
    for o in inc:
        b=o['parsed_duration']['bounds_hours'];repeat=o['repeat_count']
        if b is None or repeat is None:
            issues.append('unknown_included_duration_or_repeat:'+o['id']);has_unknown=True
            if b is not None:known_contributions.append({'operation_id':o['id'],'lower_hours':b[0],'upper_hours':None,'repeat_status':'unknown_at_least_one'})
        else:
            bounds.append([b[0]*repeat,b[1]*repeat]);known_contributions.append({'operation_id':o['id'],'lower_hours':b[0]*repeat,'upper_hours':b[1]*repeat,'repeat_status':'source_exact_or_single'})
    candidate=None
    if len(bounds)==len(inc) and inc:
        if mode=='serial':candidate=[sum(b[0] for b in bounds),sum(b[1] for b in bounds)]
        elif mode=='parallel':candidate=[max(b[0] for b in bounds),max(b[1] for b in bounds)]
        elif mode=='alternative':candidate=[min(b[0] for b in bounds),max(b[1] for b in bounds)]
        else:candidate=[max(b[0] for b in bounds),sum(b[1] for b in bounds)]
    else:
        issues.append('no_complete_numeric_operation_set')
        if known_contributions and mode=='serial':candidate=[sum(x['lower_hours'] for x in known_contributions),None]
    claims=[]
    for claim in g['total_time_claims']:
        value=duration_value(claim['duration']['quote']);claims.append({'id':claim['id'],'scope':claim['scope'],**value})
        if claim['scope']=='unknown':issues.append('unresolved_total_claim_scope')
        if not re.search(r'\btotal\b|\boverall\b|\bsum\b|总|合计',claim['duration']['context'],re.I):issues.append('total_claim_has_no_lexical_total_cue')
        if claim['scope']=='clearing_total' and candidate and value['bounds_hours'] and value['bounds_hours']!=candidate:issues.append('explicit_total_conflicts_with_operation_sum')
    unique=candidate[0] if candidate and candidate[1] is not None and candidate[0]==candidate[1] and not issues else None
    if candidate and candidate[0]!=candidate[1]:issues.append('nonunique_duration_range')
    conditional_contributions=[]
    for o in conditional:
        b=o['parsed_duration']['bounds_hours'];n=o['repeat_count']
        conditional_contributions.append({'operation_id':o['id'],'source_supported_condition':o['scope_gate']['conditional_scope_supported'],
            'condition_evidence':o['condition_evidence'],'bounds_hours':[b[0]*n,b[1]*n] if b is not None and n is not None else None})
    endpoint_envelope=None
    if conditional and candidate:
        upper=candidate[1]
        if upper is not None and all(x['bounds_hours'] is not None for x in conditional_contributions):upper+=sum(x['bounds_hours'][1] for x in conditional_contributions)
        else:upper=None
        endpoint_envelope=[candidate[0],upper]
    return {'total_hours':unique,'candidate_bounds_hours':candidate,'issues':sorted(set(issues)),
            'included_operation_ids':[o['id'] for o in inc],'excluded_operations':[{'id':o['id'],'phase':o['phase']} for o in ops if o['phase'] in EXCLUDE],
            'claims':claims,'mode':mode,'known_operation_contributions':known_contributions,
            'initial_scope_candidate_bounds_hours':candidate,'conditional_operations':conditional_contributions,
            'timeline_derivation':g.get('timeline_derivation'),'model_precedence_audit':g.get('precedence_audit'),
            'coverage_scopes':{'whole_protocol_operations':g['coverage']['time_operations'],'core_time_operations':g['coverage']['core_time_operations'],
                'model_timeline_completeness':g['timeline_proposal']['completeness'],'program_core_gate_independent_of_whole_protocol_completeness':True,
                'action_recall_is_not_exhaustive_semantic_gold':True},
            'initial_plus_at_most_one_conditional_execution_envelope_hours':endpoint_envelope,
            'endpoint_scope':'Initial scope is reported separately. Presence of conditional/future core operations prevents choosing an unqualified legacy total. The optional envelope assumes at most one listed conditional execution; repeated maintenance may have no finite upper bound.',
            'bounds_scope':'Conditional on supplied phase/schedule classification; null upper bound means no finite source-supported upper bound.',
            'serial_convention':'Document-order operations are provisionally summed only if no branch/overlap cue is detected; semantic schedule is not certified.',
            'overnight_policy':'No source-exact numeric duration inferred; original 8h convention retained only per-operation comparison.',
            'scientific_total_confirmed':False}

def doc_context(audit):return '\n'.join(o['operation']['context'] for o in audit['resolved']['operations'])

def project_legacy(audit):
    g=audit['resolved'];time=compute_time(audit);issues=[];mapping={};conversion=[]
    selected=[m for m in g['method_mentions'] if m['usage']=='selected'];names={m['name']['quote'] for m in selected if m['name_binding']['atomicity']['projection_eligible_provisional']}
    if any(not m['name_binding']['atomicity']['projection_eligible_provisional'] for m in selected):
        names=set();issues.append('method_name_atomicity_unresolved')
    method=next(iter(names)) if len(names)==1 else None
    # Usage is still a model judgment. Require a lexical selection cue before
    # projecting it to the old scalar, and retain rejected mentions for audit.
    method_checks=[]
    for m in selected:
        context=m['name']['context'];name=re.escape(m['name']['quote'])
        explicit=bool(re.search(r'(?:chosen\s+method|selected\s+method|method\s*[:：]|方法\s*[:：]|采用|选择|\buse\b|\busing\b)[^\n]*'+name,context,re.I))
        negated=bool(re.search(r'\b(?:not|without|either|alternative)\b|不采用|不选择|或者',context,re.I))
        method_checks.append({'id':m['id'],'explicit_selection_cue':explicit,'negation_or_alternative_cue':negated})
    if method and not any(x['explicit_selection_cue'] and not x['negation_or_alternative_cue'] for x in method_checks):
        method=None;issues.append('selected_method_not_explicitly_anchored')
    if method is None:issues.append('method_unreported_or_ambiguous')
    entities={e['id']:e for e in g['entities']}
    for e in g['entities']:
        if not e['name_binding']['atomicity']['projection_eligible_provisional']:issues.append('entity_name_atomicity_unresolved:'+e['id'])
    for name in sorted({e['name']['quote'] for e in g['entities'] if e['kind'] in ['fluorophore','fluorescent_protein'] and e['usage']=='used' and e['name_binding']['atomicity']['projection_eligible_provisional']}):
        same=[e for e in g['entities'] if e['name']['quote']==name and e['usage']=='used'];ids={e['id'] for e in same}
        proposals=[r for r in g['relations'] if r['fluor_entity_id'] in ids]
        targets={entities[r['target_entity_id']]['name']['quote'] for r in proposals if r['projection_allowed']}
        unresolved=any(not r['projection_allowed'] for r in proposals)
        value=next(iter(targets)) if len(targets)==1 and not unresolved else ''
        if len(targets)>1:issues.append('one_name_multiple_targets_not_losslessly_representable:'+name)
        if unresolved:issues.append('relationship_unresolved:'+name)
        mapping[name]=value
        conversion.append({'source_entity_ids':sorted(ids),'legacy_key':name,'legacy_value':value,'target_count':len(targets),
                            'relationship_unresolved':unresolved,'target_inferred':False})
    intrinsic_conversion=[]
    for record in g['intrinsic_signals']:
        entity=entities[record['entity_id']];name=entity['name']['quote'];policy=record['identity_policy']
        allowed=policy['projection_allowed'];related=[r['id'] for r in g['relations'] if entities[r['fluor_entity_id']]['name']['quote']==name]
        conflict=bool(related or (mapping.get(name) not in [None,'',name]))
        applied=allowed and not conflict
        before=mapping.get(name)
        if applied:mapping[name]=name
        else:issues.append('intrinsic_identity_unresolved:'+name)
        intrinsic_conversion.append({'intrinsic_record_id':record['id'],'entity_id':entity['id'],'exact_source_name':name,
            'predicate':'source_declared_intrinsic_identity','relation_not_self_binding':True,
            'legacy_value_before':before,'legacy_value_after':mapping.get(name),'legacy_same_name_projection_applied':applied,
            'existing_relation_claims_on_key':related,'projection_conflict':conflict,
            'source_policy':policy,'scientific_input_changed_by_typed_adapter':applied,
            'question_requirement_or_preserved_biological_signal_claimed':False})
    targetids={e['id'] for e in g['entities'] if e['kind'] in ['target','antibody'] and e['usage']=='used'}
    mappedtargets={r['target_entity_id'] for r in g['relations'] if r['projection_allowed']}
    if targetids-mappedtargets:issues.append('unmapped_reported_target_identities')
    if any(e['kind']=='unknown' and e['usage'] in ['used','unknown'] for e in g['entities']):issues.append('unresolved_entity_kind')
    if any(e['usage']=='unknown' for e in g['entities']):issues.append('unresolved_entity_usage')
    if any(e['usage']=='mentioned' and not e['mentioned_usage_support']['supported'] for e in g['entities']):issues.append('unverified_mentioned_entity_usage')
    if g['affirmative_entity_usage_gaps']:issues.append('affirmative_entity_usage_occurrences_not_preserved')
    if g['coverage']['entities']!='complete':issues.append('reported_entity_coverage_incomplete')
    if any(r['kind'] in ['numbered_name_lead','known_marker_name_lead'] and r['coverage_state']=='uncovered_candidate' for r in audit['inventory']):issues.append('uncovered_entity_name_candidates')
    values={};ri_audit=[]
    for role in ['reagent_final','sample_target']:
        candidates=[]
        for r in g['ri_mentions']:
            if r['role']==role:
                value,state=parse_ri_literal(r['value']['quote'])
                ri_audit.append({'id':r['id'],'role':role,'value_span':r['value'],'parsed_value':value,'state':state,'role_semantics_verified':False})
                if value is not None:candidates.append(value)
        values[role]=candidates[0] if len(set(candidates))==1 else None
    if g.get('precedence_audit',{}).get('cyclic_model_proposal'):issues.append('cyclic_model_precedence_proposal_not_used')
    if g.get('precedence_audit',{}).get('backward_document_order_edges'):issues.append('backward_model_precedence_proposal_not_used')
    extraction={'method_name':method,'marker_dict':mapping,'clearing_total_time_hours':time['total_hours'],
        'reagent_ri_value':values['reagent_final'],'sample_ri_value':values['sample_target'],'protocol_time_hours':None,
        'reasoning':'Program projection from exact source spans; consult source-bound sidecar. Unknown relationships were not inferred.'}
    integrity.validate_legacy_extraction(extraction)
    label_ready=not any('target' in s or 'relationship' in s or 'entity' in s or 'numbered_name' in s or 'intrinsic_identity_unresolved' in s for s in issues)
    return {'extraction':extraction,'time_calculation':time,'entity_conversion':conversion,'method_selection_checks':method_checks,'projection_issues':issues,
            'intrinsic_identity_conversion':intrinsic_conversion,'intrinsic_identity_is_separate_from_original_dye_pair_denominator':True,
            'ri_projection_audit':ri_audit,'rejected_relation_claims':[copy.deepcopy(r) for r in g['relations'] if not r['projection_allowed']],
            'component_input_state':{'s_method':'available_provisional' if method else 'NA_method',
                's_label':'available_provisional' if label_ready else 'partial_projection_requires_NA_gate',
                's_time':'available_provisional' if time['total_hours'] is not None else 'NA_time_not_unique',
                's_trans':'original_question_and_KB_path_unchanged'},
            'legacy_projection_lossless_for_reported_graph':label_ready,'scientific_confirmation':False,
            'policy':'Raw EGES function remains unchanged. A separate publication gate must not treat partial marker projection as fully known; preserve unaffected components and raw diagnostics.'}

# Appended after the preserved v7 source-binding and projection functions.
# This is authoring source, not a second converter entry point.
WIRE_MAPS={
 'method_mentions':{'i':'id','n':'literal_name','a':'name_occurrence','u':'supporting_evidence','s':'usage'},
 'entities':{'i':'id','n':'literal_name','a':'name_occurrence','u':'supporting_evidence','k':'kind','s':'usage'},
 'relations':{'i':'id','f':'fluor_entity_id','t':'target_entity_id','e':'evidence','s':'status'},
 'intrinsic_signals':{'i':'id','e':'entity_id','u':'evidence','s':'status'},
 'operations':{'i':'id','o':'operation','p':'phase','d':'duration','r':'repeat_evidence','s':'execution_scope','c':'condition_evidence'},
 'precedence_edges':{'b':'before_id','a':'after_id','e':'evidence'},
 'total_time_claims':{'i':'id','d':'duration','s':'scope'},
 'ri_mentions':{'i':'id','v':'value','r':'role'}}
REFERENCE_FIELDS={'supporting_evidence','evidence','operation','duration','repeat_evidence','condition_evidence','value','relation_evidence'}

def build_source_document(text,source_id):return document(text,source_id)
def build_registry(doc):return candidate_registry(doc)

def _wire_schema(doc=None):
    registry=candidate_registry(doc) if doc is not None else None
    ids={}
    if registry is not None:
        ids['L']=[u['unit_id'] for u in doc['units']]
        for prefix,rows,key in [('D',registry['records'],'candidate_id'),('R',registry['records'],'candidate_id'),
                                ('O',registry['operation_candidates'],'candidate_id'),('P',registry['repeat_candidates'],'candidate_id'),('Q',registry['clauses'],'clause_id')]:
            ids[prefix]=[r[key] for r in rows if r[key].startswith(prefix)]
        operation_units={r['span']['unit_id'] for r in registry['operation_candidates']}
        ids['OL']=ids['O']+[u for u in ids['L'] if u not in operation_units]
    def ref(prefix,nullable=False):
        if registry is None:base={'type':'string','pattern':'^['+prefix+'][0-9]+$'}
        else:
            legal=ids[prefix] if prefix in ids else sum([ids[p] for p in prefix],[])
            # A zero-member numerical inventory makes optional values null.
            # Required rows are disabled below rather than inventing a sentinel ID.
            base={'type':'string','enum':legal} if legal else {'type':'string','pattern':'(?!)'}
            if not legal and nullable:return {'type':'null'}
        return {'anyOf':[base,{'type':'null'}]} if nullable else base
    ordinal={'type':'integer','minimum':0};nullable_ordinal={'anyOf':[ordinal,{'type':'null'}]}
    relation_common={'i':ID,'f':ID,'e':ref('LQ')}
    relationships={'anyOf':[
        obj({**relation_common,'t':ID,'s':{'const':'explicit'},'fo':ordinal,'to':ordinal}),
        obj({**relation_common,'t':{'anyOf':[ID,{'type':'null'}]},'s':enum('ambiguous','unknown'),'fo':nullable_ordinal,'to':nullable_ordinal})]}
    ground=obj({'schema_version':{'const':VERSION},'source_id':{'const':doc['source_id']} if doc is not None else TEXT,
        'method_mentions':arr(obj({'i':ID,'n':{'type':'string','minLength':1},'a':ordinal,'u':ref('L'),'s':enum('selected','mentioned','alternative','negated','unknown')})),
        'entities':arr(obj({'i':ID,'n':{'type':'string','minLength':1},'a':ordinal,'u':ref('L'),'k':enum('fluorophore','fluorescent_protein','target','antibody','unknown'),'s':enum('used','mentioned','alternative','negated','unknown')})),
        'relations':arr(relationships),
        'intrinsic_signals':arr(obj({'i':ID,'e':ID,'u':ref('L'),'s':enum('source_declared','ambiguous','unknown')})),
        'operations':arr(obj({'i':ID,'o':ref('OL'),'p':enum(*(sorted(INCLUDE|EXCLUDE)+['unknown'])),'d':ref('D',True),'r':ref('P',True),
            's':enum('initial','conditional_or_future','unknown'),'c':ref('L',True)})),
        'timeline':obj({'m':enum('serial','parallel','alternative','unknown'),'o':arr(ID),'e':ref('L',True),'c':enum('complete','partial','unknown')}),
        'precedence_edges':arr(obj({'b':ID,'a':ID,'e':ref('L')})),
        'total_time_claims':arr(obj({'i':ID,'d':ref('D'),'s':enum('clearing_total','whole_protocol','unknown')})),
        'ri_mentions':arr(obj({'i':ID,'v':ref('R'),'r':enum('reagent_final','sample_target','unknown')})),
        'coverage':obj({'e':enum('complete','partial','unknown'),'t':enum('complete','partial','unknown'),'c':enum('complete','partial','unknown'),
            'u':arr(obj({'e':ref('L'),'r':{'type':'string','minLength':1}}))})})
    if registry is not None:
        for key,prefix in [('ri_mentions','R'),('total_time_claims','D')]:
            if not ids[prefix]:
                ground['properties'][key]['maxItems']=0
                field='v' if prefix=='R' else 'd'
                ground['properties'][key]['items']['properties'][field]={'type':'string','pattern':'^'+prefix+'[0-9]+$'}
    score_evidence=arr(obj({'m':enum(*DIRECT),'u':arr(ref('L')),'b':enum('observed','absence','insufficient','mixed'),'r':{'type':'string','minLength':1}}))
    return obj({'scores':_expanded_schema()['properties']['scores'],'score_evidence':score_evidence,'grounded_extraction':ground})

def schema():return _wire_schema()
def schema_for_document(doc):return _wire_schema(doc)

def _expand_ref(value):
    if value is None:return None
    if value.startswith('L'):return {'unit_id':value}
    if value.startswith('Q'):return {'clause_id':value}
    return {'candidate_id':value}

def expand_wire_payload(payload,doc):
    """Lossless field renaming, not a repair or evidence-completion path."""
    validate_shape(payload,schema_for_document(doc));integrity.validate_score_proposals(payload['scores'])
    wire=payload['grounded_extraction'];g={'schema_version':wire['schema_version'],'source_id':wire['source_id']}
    endpoints={}
    for group,mapping in WIRE_MAPS.items():
        g[group]=[]
        for row in wire[group]:
            expanded={long:(_expand_ref(row[short]) if long in REFERENCE_FIELDS else copy.deepcopy(row[short])) for short,long in mapping.items()}
            g[group].append(expanded)
            if group=='relations':endpoints[row['i']]={'fluor_occurrence':row['fo'],'target_occurrence':row['to']}
    timeline=wire['timeline'];g['timeline']={'mode':timeline['m'],'operation_ids':copy.deepcopy(timeline['o']),
        'relation_evidence':_expand_ref(timeline['e']),'completeness':timeline['c']}
    coverage=wire['coverage'];g['coverage']={'entities':coverage['e'],'time_operations':coverage['t'],'core_time_operations':coverage['c'],
        'unresolved':[{'evidence':_expand_ref(r['e']),'reason':r['r']} for r in coverage['u']]}
    evidence=[{'metric':r['m'],'answer_spans':[_expand_ref(v) for v in r['u']],'basis':r['b'],'rubric_basis':r['r']} for r in payload['score_evidence']]
    expanded={'scores':copy.deepcopy(payload['scores']),'score_evidence':evidence,'grounded_extraction':g}
    validate_shape(expanded,_expanded_schema())
    return expanded,endpoints

def _short_ref(ref):return None if ref is None else next(ref[k] for k in ['unit_id','candidate_id','clause_id'] if k in ref)

def compact_fixture_payload(expanded,doc):
    """Software-fixture serialization only. Never used to alter a model return."""
    full=copy.deepcopy(expanded);g=full['grounded_extraction'];g['schema_version']=VERSION
    compact={'schema_version':VERSION,'source_id':g['source_id']};registry=candidate_registry(doc)
    for group,mapping in WIRE_MAPS.items():
        compact[group]=[]
        for row in g[group]:
            c={short:(_short_ref(row[long]) if long in REFERENCE_FIELDS else copy.deepcopy(row[long])) for short,long in mapping.items()}
            if group=='operations' and c['o'].startswith('L'):
                matching=[r for r in registry['operation_candidates'] if r['span']['unit_id']==c['o']]
                if c['d'] is not None:matching=[r for r in matching if c['d'] in r['eligible_duration_candidate_ids']]
                require(len(matching)<=1,'FIXTURE_OPERATION_EXTENT_AMBIGUOUS')
                if matching:c['o']=matching[0]['candidate_id']
            if group=='relations':
                c['fo']=0 if row['status']=='explicit' else None
                c['to']=0 if row['target_entity_id'] is not None and row['status']=='explicit' else None
            compact[group].append(c)
    t=g['timeline'];compact['timeline']={'m':t['mode'],'o':copy.deepcopy(t['operation_ids']),'e':_short_ref(t['relation_evidence']),'c':t['completeness']}
    c=g['coverage'];compact['coverage']={'e':c['entities'],'t':c['time_operations'],'c':c['core_time_operations'],
        'u':[{'e':_short_ref(r['evidence']),'r':r['reason']} for r in c['unresolved']]}
    return {'scores':copy.deepcopy(full['scores']),
        'score_evidence':[{'m':r['metric'],'u':[_short_ref(s) for s in r['answer_spans']],'b':r['basis'],'r':r['rubric_basis']} for r in full['score_evidence']],
        'grounded_extraction':compact}

def _endpoint_occurrence_audit(entity,evidence,occurrence,doc):
    if entity is None or occurrence is None:return {'valid':False,'reason':'endpoint_or_occurrence_unspecified','occurrence':occurrence,'span':None}
    unit=next(u for u in doc['units'] if u['unit_id']==evidence['unit_id'])
    literal=entity['name']['quote'];hits=[m.start() for m in re.finditer('(?='+re.escape(literal)+')',unit['text'])]
    if occurrence>=len(hits):return {'valid':False,'reason':'complete_endpoint_occurrence_absent','occurrence':occurrence,'span':None,'exact_occurrence_count':len(hits)}
    try:
        span,binding=bind_literal_name(literal,resolve({'unit_id':unit['unit_id']},doc),doc,occurrence)
    except ValueError as exc:return {'valid':False,'reason':'endpoint_identity_boundary_rejected','detail':str(exc),'occurrence':occurrence,'span':None}
    inside=evidence['start']<=span['start'] and span['end']<=evidence['end']
    return {'valid':inside and binding['atomicity']['projection_eligible_provisional'],
        'reason':None if inside and binding['atomicity']['projection_eligible_provisional'] else 'endpoint_outside_selected_evidence_or_atomicity_unresolved',
        'occurrence':occurrence,'span':span,'name_binding':binding,'not_relationship_semantic_confirmation':True}

def _selected_clause_endpoint_audit(endpoint,role,scope):
    """Bind a declared occurrence to the SAME clause selected by the old policy."""
    span=endpoint.get('span');scope=scope or {};index=scope.get('selected_clause_index')
    clauses=scope.get('candidate_clauses',[])
    if not endpoint.get('valid') or type(index) is not int or not 0<=index<len(clauses):
        return {'valid':False,'reason':'endpoint_or_unique_selected_clause_unavailable','selected_clause_index':index}
    clause=clauses[index]['source_clause']
    matches=[m for m in scope.get('selected_mentions',{}).get(role,[]) if m.get('same_complete_literal')
        and all(m.get(k)==span.get(k) for k in ['start','end','quote','answer_sha256'])]
    inside=clause['start']<=span['start'] and span['end']<=clause['end']
    valid=inside and len(matches)==1
    return {'valid':valid,'reason':None if valid else 'declared_endpoint_is_not_in_the_policy_selected_pair_clause',
        'selected_clause_index':index,'selected_clause_start':clause['start'],'selected_clause_end':clause['end'],
        'exact_selected_mention_matches':len(matches),'inside_selected_clause':inside,
        'original_semantic_policy_still_required':True,'ordinal_not_corrected':True}

def candidate_accounting(audit,doc):
    registry=candidate_registry(doc);g=audit['resolved']
    names=[r['name'] for group in ['entities','method_mentions'] for r in g[group]]
    times=[o['duration'] for o in g['operations'] if o['duration']]+[r['duration'] for r in g['total_time_claims']]
    unresolved=[r['evidence'] for r in g['coverage']['unresolved']]
    other=[r['evidence'] for group in ['relations','intrinsic_signals'] for r in g[group]]+[r['value'] for r in g['ri_mentions']]
    operation_spans=[r['operation'] for r in g['operations']]
    def covers(a,b):return a['start']<=b['start'] and b['end']<=a['end']
    rows=[]
    for record in registry['records']+registry['operation_candidates']:
        span=record['span'];kind=record['kind']
        if kind=='duration':returned=any(covers(x,span) for x in times)
        elif kind in ['numbered_name_lead','known_marker_name_lead','known_method_name_lead']:
            returned=any(covers(x,span) for x in names)
            old=next((r for r in audit['inventory'] if r['candidate_id']==record['candidate_id']),{})
            returned=returned or bool(old.get('cross_mention_identity_coverage',{}).get('covered'))
        elif kind=='operation_record_lead':returned=any(x['unit_id']==span['unit_id'] for x in operation_spans)
        else:returned=any(covers(x,span) for x in names+times+operation_spans+other)
        unknown=any(covers(x,span) for x in unresolved)
        rows.append({'candidate_id':record['candidate_id'],'kind':kind,'unit_id':span['unit_id'],'start':span['start'],'end':span['end'],
            'returned':returned,'explicit_unresolved':unknown,'state':'both' if returned and unknown else 'returned' if returned else 'explicit_unresolved' if unknown else 'unaccounted'})
    from collections import Counter
    return {'rows':rows,'counts':dict(Counter(r['state'] for r in rows)),
        'warning_denominator_not_semantic_gold':True,'C_and_O_can_overlap_not_independent_facts':True,
        'no_automatic_completion_or_projection_change':True,'open_name_recall_not_certified':True}

def audit_payload(payload,doc):
    expanded,endpoints=expand_wire_payload(payload,doc)
    audit=_audit_expanded_payload(expanded,doc);entities={r['id']:r for r in audit['resolved']['entities']}
    for relation in audit['resolved']['relations']:
        claimed=endpoints[relation['id']]
        f=_endpoint_occurrence_audit(entities[relation['fluor_entity_id']],relation['evidence'],claimed['fluor_occurrence'],doc)
        t=_endpoint_occurrence_audit(entities.get(relation['target_entity_id']),relation['evidence'],claimed['target_occurrence'],doc)
        fc=_selected_clause_endpoint_audit(f,'fluor',relation.get('relation_clause_scope_audit'))
        tc=_selected_clause_endpoint_audit(t,'target',relation.get('relation_clause_scope_audit'))
        valid=f['valid'] and t['valid'] and fc['valid'] and tc['valid']
        relation['declared_local_endpoint_occurrences']={'fluor':f,'target':t,'both_valid':valid,
            'policy_selected_clause_binding':{'fluor':fc,'target':tc},
            'original_pair_policy_also_required':True,'model_claims_not_repaired':True}
        if not valid:
            relation['projection_allowed']=False
            relation['mechanical_relation_state']='declared_local_endpoint_occurrences_not_supported'
            relation['unsupported_claim_retained_not_repaired']=relation['status']=='explicit'
    registry=candidate_registry(doc);known_units={r['span']['unit_id'] for r in registry['operation_candidates']}
    audit['operation_catalog_gaps']=[{'operation_id':r['id'],'unit_id':r['operation']['unit_id'],
        'reason':'model_identified_operation_in_unit_without_pre_enumerated_O','phase_not_inferred':True}
        for r in audit['resolved']['operations'] if r['operation']['unit_id'] not in known_units]
    audit['candidate_accounting']=candidate_accounting(audit,doc)
    audit['compact_wire_version']=VERSION
    return audit

def convert(raw,doc):
    parsed=integrity.parse_judge_object(raw)
    expanded,endpoints=expand_wire_payload(parsed,doc)
    audit=audit_payload(parsed,doc);projection=project_legacy(audit)
    legacy={'scores':copy.deepcopy(parsed['scores']),'extraction':projection['extraction']}
    return {'raw_response_sha256':rawsha(raw),'raw_content_preserved':raw,'wire_payload':parsed,
        'wire_payload_sha256':rawsha(canonical(parsed)),'expanded_payload':expanded,
        'expanded_payload_sha256':rawsha(canonical(expanded)),'explicit_endpoint_selection':endpoints,
        'source_audit':audit,'legacy_projection':projection,'legacy_runner_payload':legacy,
        'legacy_runner_content':canonical(legacy),'transformation_is_explicit_not_raw_identity':True,
        'scores_preserved_exactly':legacy['scores']==parsed['scores'],'formal_eligible':False,'expert_confirmed':False}

INSTRUCTIONS='''[SOURCE-BOUND COMPACT CONTRACT v9]
Return exactly one JSON object, without prose or Markdown. The source-specific decoder schema is supplied. Keep the original scores subtree, scales and rubric; optional repeated maxima/descriptions need not be copied. Keep necessary uncertainty explanations. Do not omit difficult facts to shorten output.
The row keys below are a reversible wire encoding, not new scientific variables:
score_evidence: m=metric,u=array of Unit IDs,b=basis,r=short rubric basis. One row for each c_param/co_order/co_method/co_param/co_chem. observed/mixed needs source units; absence has u=[]; absence is not evidence quoted from a present fact.
method_mentions: i=record ID,n=complete literal name,a=occurrence,u=Unit,s=usage.
entities: i,n,a,u as above;k=kind,s=usage. Names stay OPEN; copy the complete literal, including prefixes, digits, parentheses and terminal charge/positive +. a is the zero-based index of ALL exact, possibly overlapping literal occurrences in that original Unit, before boundary checks. Never use IDs or the recall list to guess a name, and never merge an alternative list into one entity.
relations: i=record ID,f=fluor entity ID,t=target entity ID,e=Unit or Q-clause ID,s=status,fo/to=local complete-name occurrence indices in e's ORIGINAL FULL UNIT. For explicit relations, both indices must select complete endpoint names INSIDE e; a name merely declared elsewhere is not evidence for this relation. The local clause must actually pair those two identities. Co-occurrence, list order, shared color, capability or a guessed target is insufficient. Preserve unknown/ambiguous links rather than assert explicit. Preserve every alternative member separately. A selected occurrence does not override local negation, alternatives, or atomicity. No ordinary self-target mapping. Small-molecule key-only dye use does not require inventing an unknown/null-target relation.
RELATION OCCURRENCE COUNTING: fo and to are two INDEPENDENT zero-based counters, one for the complete fluor literal and one for the complete target literal, in the evidence reference's ORIGINAL FULL UNIT. If that literal appears exactly once in that Unit, its only possible index is 0. Do not use the entity ID, entity-array position, order of labels in a list, or the other endpoint's count. If evidence is a Q clause, still count within its parent full Unit, then select the occurrence inside the supported local pair. Fictional example: "Chosen Labeling: [SIGNAL_RED, TARGET_A + SIGNAL_BLUE, TARGET_B + SIGNAL_BLUE]". For the TARGET_A pair, SIGNAL_BLUE has fo=0 and TARGET_A has to=0. For the TARGET_B pair, SIGNAL_BLUE has fo=1 but TARGET_B still has to=0. The unrelated first list member SIGNAL_RED does not add to the SIGNAL_BLUE count. These are counting examples only, not source facts or a license to infer a relationship.
intrinsic_signals: i=record ID,e=entity ID,u=Unit,s=source_declared/ambiguous/unknown. Cite a chosen native declaration; capability, antibodies, negation and alternatives do not prove native use. A protein may be used natively without a staining operation. Keep the most specific source-supported kind: a fluorescent-protein reporter is fluorescent_protein, a nonprotein dye is fluorophore, unsupported identity is unknown. Source declaration does not prove biological preservation or task fit.
operations: i=record ID,o=O extent ID (or a permitted Unit ONLY where no O exists),p=phase,d=D duration or null,r=P repetition or null,s=execution_scope,c=condition Unit or null. List EVERY operation, including labeling, storage, unsupported-duration actions, and later conditional operations. For a merged line select each separate O, never one broad source line for several actions. Select D/P only from that O's eligible lists. Empty list means null with the operation preserved, not borrowing from a different O. A Unit fallback marks an O-catalog gap, not proof that the source lacks an operation. Repeat declarations without supported P remain unresolved; do not assume one. IDs give exact source spans, not phase/scope labels or correct pairing.
initial means the first pass of the PROPOSED protocol, not that a real experiment has been completed. conditional_or_future means an additional conditional/later/repeated pass. unknown is genuine ambiguity. Phase describes the concrete action, not its later purpose: repeat RI equilibration for later imaging is RI with later scope. labeling_preparation needs explicit source labeling context; generic preparation cannot automatically be excluded. Keep all source conditions.
timeline: m=mode,o=proposed operation IDs,e=relation Unit or null,c=completeness. Do not sum times: original code computes from source-bound evidence. precedence_edges: b=before ID,a=after ID,e=Unit; default [], since numbering alone is not an explicit dependency. An edge needs both operations and an explicit cue in the cited Unit.
total_time_claims: i,d=D,s=scope. These are source-stated totals, not sums you calculate. ri_mentions: i,v=R,r=role. R must be a source-stated RI expression with the correct role, never a dimension or a value from a reference/KB. Unsupported month/overnight expressions stay unresolved under the unchanged arithmetic.
coverage: e=entity coverage,t=whole-operation coverage,c=core-operation coverage,u=unresolved list [{e:Unit,r:reason}]. Whole and core coverage are INDEPENDENT: an unquantified excluded storage action does not alone make otherwise fully specified core actions incomplete; unknown core membership still does. Mark missing evidence honestly, including unrepresented numerical/name candidates. A returned record and unresolved evidence may both exist; do not drop the record to report uncertainty. IDs and self-reported complete do not certify recall.
Chosen/Selected Method is direct proposed-selection evidence unless its own context negates or makes it alternative. Merely describing capability/example remains mentioned. used/selected concerns the proposed protocol, not completed experimentation. Retain the raw distinction instead of turning every instruction into unknown.
No quote/start/end/free SourceRef objects, invented IDs, aliases, repair or extra keys. The full text and original scoring/reference context are unchanged. Typed references are strings: L units,O operation extents,D duration,P repetition,R RI,Q clauses. Short keys have the meanings above; semantic enums and explicit nulls retain their original meanings.
'''

def make_prompt(case,doc):
    import cce_grounded_extraction_v7 as previous
    old=previous.make_prompt(case,doc)
    require(old.count(previous.INSTRUCTIONS)==1,'V7_PROMPT_EXTRACTION_BOUNDARY')
    prefix,tail=old.split(previous.INSTRUCTIONS)
    # Reuse the exact original rubric, source text, reference suffix and registry
    # tables. Only the extraction contract wording and wire legend change.
    registry=candidate_registry(doc);covered={r['span']['unit_id'] for r in registry['operation_candidates']}
    fallback=[u['unit_id'] for u in doc['units'] if u['unit_id'] not in covered]
    return prefix+INSTRUCTIONS+'\n[V9 SOURCE-SCHEMA OPERATION RULE]\n'+canonical({'operation_extent_ids':[r['candidate_id'] for r in registry['operation_candidates']],
        'Unit_fallback_ids_only_where_no_O_extent_exists':fallback,'literal_name_catalog_is_open':True})+tail

def synthetic_fixture(first='2 hours',second='30 minutes',mode='serial',relation='explicit'):
    import cce_grounded_extraction_v7 as previous
    doc,full=previous.synthetic_fixture(first,second,mode,relation)
    return doc,compact_fixture_payload(full,doc)

def synthetic_record_fixture(null_target=False):
    import cce_grounded_extraction_v7 as previous
    doc,full=previous.synthetic_record_fixture(null_target)
    return doc,compact_fixture_payload(full,doc)

def self_check():
    import ast
    import cce_grounded_extraction_v7 as previous
    checks=[]
    def check(name,test,detail=None):
        require(bool(test),'V9_SOFTWARE_PROBE_FAILED:'+name);checks.append({'name':name,'status':'pass','detail':detail})
    def reject(name,func):
        try:func()
        except (ValueError,integrity.JudgeFormatError) as exc:check(name,True,str(exc));return
        raise ValueError('V9_UNEXPECTED_ACCEPTANCE:'+name)
    doc,payload=synthetic_fixture();result=convert(canonical(payload),doc)
    check('fictional_full_conversion',result['legacy_projection']['time_calculation']['total_hours']==2.5)
    check('fictional_pair_preserved',result['legacy_projection']['extraction']['marker_dict']=={'SYNTHETIC_FLUOR_101':'SYNTHETIC_TARGET'})
    check('wire_raw_exact',result['raw_content_preserved']==canonical(payload) and result['scores_preserved_exactly'])
    expanded,endpoints=expand_wire_payload(payload,doc)
    check('compact_expansion_roundtrip',compact_fixture_payload(expanded,doc)==payload)
    check('scores_original_subtree',schema()['properties']['scores']==previous.schema()['properties']['scores'])
    check('compact_fixture_serialization_smaller',len(canonical(payload))<len(canonical(expanded)),{'wire_chars':len(canonical(payload)),'expanded_chars':len(canonical(expanded))})
    reject('old_expanded_format_no_fallback',lambda:convert(canonical(expanded),doc))
    reject('duplicate_JSON',lambda:convert('{"scores":{},"scores":{}}',doc))
    for name,edit in [
        ('wrong_source',lambda p:p['grounded_extraction'].update(source_id='SRC_wrong')),
        ('unknown_Unit',lambda p:p['grounded_extraction']['entities'][0].update(u='L99999')),
        ('unknown_O',lambda p:p['grounded_extraction']['operations'][0].update(o='O99999')),
        ('wrong_D_role',lambda p:p['grounded_extraction']['operations'][0].update(d='R0001')),
        ('wrong_D_ID',lambda p:p['grounded_extraction']['operations'][0].update(d='D99999')),
        ('wrong_P_role',lambda p:p['grounded_extraction']['operations'][0].update(r='D0001')),
        ('name_boolean_ordinal',lambda p:p['grounded_extraction']['entities'][0].update(a=True)),
        ('explicit_null_endpoint_ordinal',lambda p:p['grounded_extraction']['relations'][0].update(to=None)),
        ('duplicate_record',lambda p:p['grounded_extraction']['entities'][1].update(i=p['grounded_extraction']['entities'][0]['i'])),
        ('absence_with_source',lambda p:p['score_evidence'][0].update(b='absence',u=['L0003']))]:
        mutated=copy.deepcopy(payload);edit(mutated);reject(name,lambda p=mutated:convert(canonical(p),doc))
    # Source-specific decoder and converter reject wide Units where O exists.
    mutated=copy.deepcopy(payload);op=mutated['grounded_extraction']['operations'][0]
    op['o']=next(r['span']['unit_id'] for r in candidate_registry(doc)['operation_candidates'] if r['candidate_id']==op['o'])
    reject('wide_Unit_cannot_bypass_existing_O',lambda:convert(canonical(mutated),doc))
    mutated=copy.deepcopy(payload);mutated['grounded_extraction']['relations'][0]['to']=99
    bad=convert(canonical(mutated),doc)
    check('wrong_local_endpoint_withheld_not_repaired',not bad['source_audit']['resolved']['relations'][0]['projection_allowed'] and bad['source_audit']['resolved']['relations'][0]['unsupported_claim_retained_not_repaired'])
    check('unaffected_time_preserved_after_endpoint_rejection',bad['legacy_projection']['time_calculation']['total_hours']==2.5)
    # A broad Unit may contain the same literal again outside the actual pair.
    # The wire ordinal must identify the old policy's supported local clause.
    text='Chosen Labeling: TARGET_A+FLUOR_101; FLUOR_101 is mentioned.\n'
    d=document(text,'SRC_virtual_local_pair');f=copy.deepcopy(payload);g=f['grounded_extraction']
    g.update(source_id=d['source_id'],method_mentions=[],intrinsic_signals=[],operations=[],precedence_edges=[],total_time_claims=[],ri_mentions=[])
    g['entities']=[{'i':'f','n':'FLUOR_101','a':0,'u':'L0001','k':'fluorophore','s':'used'},
        {'i':'t','n':'TARGET_A','a':0,'u':'L0001','k':'target','s':'used'}]
    g['relations']=[{'i':'pair','f':'f','t':'t','e':'L0001','s':'explicit','fo':0,'to':0}]
    g['timeline']={'m':'unknown','o':[],'e':None,'c':'unknown'}
    g['coverage']={'e':'unknown','t':'unknown','c':'unknown','u':[]}
    f['score_evidence']=[{'m':m,'u':[],'b':'absence','r':'Fictional software fixture.'} for m in DIRECT]
    good=convert(canonical(f),d)
    check('same_local_pair_declared_occurrences_preserved',good['source_audit']['resolved']['relations'][0]['projection_allowed'])
    f['grounded_extraction']['relations'][0]['fo']=1;badlocal=convert(canonical(f),d)
    r=badlocal['source_audit']['resolved']['relations'][0]
    check('other_clause_occurrence_withheld',not r['projection_allowed'] and not r['declared_local_endpoint_occurrences']['policy_selected_clause_binding']['fluor']['valid'])
    check('other_clause_raw_claim_not_repaired',badlocal['wire_payload']['grounded_extraction']['relations'][0]['fo']==1 and r['unsupported_claim_retained_not_repaired'])
    check('endpoint_guard_does_not_change_direct_scores',good['legacy_runner_payload']['scores']==badlocal['legacy_runner_payload']['scores']==f['scores'])
    # Null-duration operations must inspect their OWN repeat declaration.
    text='Chosen method: VITRUM_Z\nSignal: LUMEN_Q\n1. Wash for 2 hours.\n2. Store; repeat several times.\n'
    d=document(text,'SRC_virtual_repeat');reg=candidate_registry(d)
    f=copy.deepcopy(expanded);g=f['grounded_extraction'];g['source_id']=d['source_id'];g['method_mentions']=[];g['entities']=[];g['relations']=[];g['intrinsic_signals']=[]
    g['operations']=[{'id':'op1','operation':{'candidate_id':reg['operation_candidates'][0]['candidate_id']},'phase':'clearing_treatment','duration':{'candidate_id':next(r['candidate_id'] for r in reg['records'] if r['kind']=='duration')},'repeat_evidence':None,'execution_scope':'initial','condition_evidence':None},
        {'id':'op2','operation':{'candidate_id':reg['operation_candidates'][1]['candidate_id']},'phase':'storage','duration':None,'repeat_evidence':None,'execution_scope':'initial','condition_evidence':None}]
    g['timeline']={'mode':'serial','operation_ids':['op1'],'relation_evidence':None,'completeness':'complete'};g['precedence_edges']=[];g['total_time_claims']=[];g['ri_mentions']=[]
    g['coverage']={'entities':'unknown','time_operations':'partial','core_time_operations':'complete','unresolved':[]}
    f['score_evidence']=[{'metric':m,'answer_spans':[{'unit_id':'L0003'}],'basis':'observed','rubric_basis':'Fictional software basis.'} for m in DIRECT]
    nullcase=convert(canonical(compact_fixture_payload(f,d)),d)
    check('duration_null_current_operation_repeat_guard',nullcase['source_audit']['resolved']['operations'][1]['repeat_count'] is None)
    check('other_operation_repeat_does_not_pollute_first',nullcase['source_audit']['resolved']['operations'][0]['repeat_count']==1)
    # Original arithmetic, phase and relation policies are preserved as source AST.
    def asts(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(Path(path).read_text(encoding='utf8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    old,new=asts(previous.__file__),asts(__file__)
    for name in ['document','resolve_span','duration_value','duration_role','evidence_inventory','operation_inventory','repeat_inventory','repeat_count','record_binding','repeat_source_binding','compute_time','parse_ri_literal','intrinsic_policy','relation_policy','relation_clause_support','bind_literal_name','project_legacy']:
        check('original_function_AST_'+name,old[name]==new[name])
    check('no_quote_reference_in_wire_schema','"quote"' not in canonical(schema()))
    save(OUT/'software_probes.json',{'status':'pass','checks':checks,'count':len(checks),'script_sha256':sha(__file__),'schema_sha256':rawsha(canonical(schema())),
        'no_scientific_accuracy_claim':True,'new_model_requests':0,'actual_command':[sys.executable,*sys.argv]})
    print(canonical({'status':'software_pass','checks':len(checks),'script_sha256':sha(__file__)}))

def draft():
    import collections
    import cce_grounded_extraction_v7 as previous
    global OUT
    OUT=OUT/'draft';OUT.mkdir(parents=True,exist_ok=True)
    cases_path=baseline.OUT/'cases.json';cases=read(cases_path)['cases']
    control_path=ROOT/'artifacts/cce_validation/judges/controls_contract_v2/cases.json';controls=read(control_path)['cases']
    require([c['anonymous_answer_id'] for c in cases]==['A01','A02','A03','A04','A05'] and len(controls)==21,'ONLY_FIXED_PUBLIC_5_PLUS_21')
    save(OUT/'schema.json',schema());(OUT/'extraction_instructions.txt').write_text(INSTRUCTIONS,encoding='utf8')
    save(OUT/'wire_field_map.json',WIRE_MAPS)
    matrix=[];coverage=[]
    for cohort,rows in [('development',cases),('controls',controls)]:
        for case in rows:
            key=case['anonymous_answer_id'] if cohort=='development' else case['case_id']
            doc=document(case['model_response'],source_id_for_case(case));reg=candidate_registry(doc);old=previous.candidate_registry(doc)
            for group in ['records','clauses','operation_candidates','repeat_candidates','repeat_declarations']:require(reg[group]==old[group],'V7_SOURCE_REGISTRY_CHANGED:'+group)
            require(doc['answer_sha256']==case['answer_sha256'] and rawsha(case['specific_question'])==case['question_sha256'],'ORIGINAL_SOURCE_HASH_CHANGED')
            prompt=make_prompt(case,doc);specific=schema_for_document(doc)
            require(prompt.split(INSTRUCTIONS)[0]==previous.make_prompt(case,doc).split(previous.INSTRUCTIONS)[0],'ORIGINAL_SCORING_PREFIX_CHANGED')
            require(''.join(u['text'] for u in doc['units'])==case['model_response'],'SOURCE_NOT_LOSSLESS')
            # Bytes are a deliberately conservative bound, not a tokenizer count.
            bound=len(prompt.encode('utf8'))+8192+256
            require(bound<=CONFIGURED_NUM_CTX,'CONTEXT_EXCEEDED_NO_TRUNCATION')
            record={'cohort':cohort,'case_id':key,'question_id':case['question_id'],'answer_sha256':doc['answer_sha256'],'question_sha256':case['question_sha256'],
                'opaque_source_id':doc['source_id'],'registry_sha256':reg['registry_sha256'],'schema_canonical_sha256':rawsha(canonical(specific)),
                'prompt_text_sha256':rawsha(prompt),'conservative_context_bound':bound,'configured_num_ctx':CONFIGURED_NUM_CTX,
                'fits_configured_context':True,'fits_40960':bound<=40960,'full_source_bytes_and_original_score_reference_context_preserved':True,
                'registry_equals_v7_except_version_hash':True}
            matrix.append(record)
            operation_units={r['span']['unit_id'] for r in reg['operation_candidates']}
            duration_gaps=[{'candidate_id':r['candidate_id'],'unit_id':r['span']['unit_id'],'fallback_Unit_allowed':True,'core_phase_not_inferred':True}
                for r in reg['records'] if r['kind']=='duration' and r['span']['unit_id'] not in operation_units]
            coverage.append({'case_id':key,'cohort':cohort,'record_counts':dict(collections.Counter(r['kind'] for r in reg['records'])),
                'O_count':len(reg['operation_candidates']),'duration_candidates_in_units_without_O':duration_gaps,'catalog_not_semantic_gold':True})
            if cohort=='development':
                save(OUT/'source_documents'/f'{key}.json',doc);save(OUT/'source_registries'/f'{key}.json',reg)
                save(OUT/'schemas'/f'{key}.json',specific);p=OUT/'prompts'/f'{key}.txt';p.parent.mkdir(exist_ok=True);p.write_text(prompt,encoding='utf8')
    save(OUT/'context_and_registry_checks.json',{'status':'pass_26_public_inputs_only','records':matrix,'registry_coverage':coverage,'new_model_requests':0,'sealed_or_human_inputs_read':False})
    inputs=[Path(__file__),Path(previous.__file__),cases_path,control_path,OUT.parent/'prospective_scope.json',baseline.OUT/'final_output_schema.json',ROOT/'evaluator_integrity.py',
        ROOT/'OEQ_run_grading_new.py',ROOT/'KnowledgeBase/method_fluro_compati.json',ROOT/'artifacts/cce_validation/optimizer_20261010/validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json']
    save(OUT/'draft_manifest.json',{'status':'draft_not_prepared_or_frozen','version':VERSION,'matrix':matrix[:5],'control_context_rows':matrix[5:],
        'configured_num_ctx':CONFIGURED_NUM_CTX,'max_output_tokens':8192,'temperature':0,'fixed_fact_denominators':{'complete_names':16,'initial_durations':31,'explicit_pairs':3,'ambiguity_groups':2},
        'input_sha256':{str(p.resolve()):sha(p) for p in inputs},'new_model_requests':0,'actual_command':[sys.executable,*sys.argv]})
    self_check()
    print(canonical({'status':'draft_ready_for_independent_review_not_generation','development_context_bounds':[r['conservative_context_bound'] for r in matrix[:5]],
        'all_26_max_context':max(r['conservative_context_bound'] for r in matrix),'script_sha256':sha(__file__),'new_model_requests':0}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['draft','self-check','convert']);p.add_argument('--source-document',type=Path);p.add_argument('--raw-response',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.action=='draft':draft()
    elif a.action=='self-check':
        global OUT
        OUT=OUT/'draft';OUT.mkdir(parents=True,exist_ok=True);self_check()
    else:
        require(a.source_document and a.raw_response and a.out,'CONVERT_PATHS_REQUIRED')
        save(a.out,convert(a.raw_response.read_bytes().decode('utf8'),read(a.source_document)))

if __name__=='__main__':main()
