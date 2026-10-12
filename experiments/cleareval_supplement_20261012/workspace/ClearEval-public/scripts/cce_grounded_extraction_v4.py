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
OUT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_extraction_v4'
VERSION='source_bound_extraction_v4'
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
PRECISE_REF={'anyOf':[SPAN,CANDIDATE_REF]}
REF={'anyOf':[SPAN,CANDIDATE_REF,UNIT_REF]}
NULLSPAN={'anyOf':[SPAN,CANDIDATE_REF,UNIT_REF,{'type':'null'}]}
NULL_PRECISE_REF={'anyOf':[SPAN,CANDIDATE_REF,{'type':'null'}]}
def obj(properties):return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}
def arr(items):return {'type':'array','items':items}
def enum(*values):return {'type':'string','enum':list(values)}
TEXT={'type':'string'}
ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]*$'}
DIRECT=('c_param','co_order','co_method','co_param','co_chem')

def schema():
    old=json.loads((baseline.OUT/'final_output_schema.json').read_text(encoding='utf8'))
    common={'id':ID,'fluor_entity_id':ID,'evidence':REF}
    relationship={'anyOf':[
        obj({**common,'target_entity_id':ID,'status':{'const':'explicit'}}),
        obj({**common,'target_entity_id':{'anyOf':[ID,{'type':'null'}]},'status':enum('ambiguous','unknown')})]}
    ground=obj({'schema_version':{'const':VERSION},'source_id':TEXT,
        'method_mentions':arr(obj({'id':ID,'literal_name':{'type':'string','minLength':1},'supporting_evidence':REF,'usage':enum('selected','mentioned','alternative','negated','unknown')})),
        'entities':arr(obj({'id':ID,'literal_name':{'type':'string','minLength':1},'supporting_evidence':REF,'kind':enum('fluorophore','fluorescent_protein','target','antibody','unknown'),
                            'usage':enum('used','mentioned','alternative','negated','unknown')})),
        'relations':arr(relationship),
        'intrinsic_signals':arr(obj({'id':ID,'entity_id':ID,'evidence':REF,'status':enum('source_declared','ambiguous','unknown')})),
        'operations':arr(obj({'id':ID,'operation':REF,'phase':enum(*(sorted(INCLUDE|EXCLUDE)+['unknown'])),
                              'duration':NULL_PRECISE_REF,'repeat_evidence':NULLSPAN,
                              'execution_scope':enum('initial','conditional_or_future','unknown'),
                              'condition_evidence':NULLSPAN})),
        'timeline':obj({'mode':enum('serial','parallel','alternative','unknown'),'operation_ids':arr(ID),
                        'relation_evidence':NULLSPAN,'completeness':enum('complete','partial','unknown')}),
        'precedence_edges':arr(obj({'before_id':ID,'after_id':ID,'evidence':REF})),
        'total_time_claims':arr(obj({'id':ID,'duration':PRECISE_REF,'scope':enum('clearing_total','whole_protocol','unknown')})),
        'ri_mentions':arr(obj({'id':ID,'value':PRECISE_REF,'role':enum('reagent_final','sample_target','unknown')})),
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
    if spec==SPAN:return 'RawSpan'
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

def candidate_registry(doc):
    rows=evidence_inventory(doc)
    require(len({r['candidate_id'] for r in rows})==len(rows),'DUPLICATE_SOURCE_CANDIDATE_ID')
    return {'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],'enumerator_version':VERSION,
        'records':rows,'registry_sha256':rawsha(canonical({'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],'version':VERSION,'records':rows}))}

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
        require(isinstance(ref['candidate_id'],str) and re.fullmatch(r'C[0-9]+',ref['candidate_id']),'CANDIDATE_ID_SHAPE')
        expected=candidate_registry(doc) if registry is None else registry
        require(expected['source_id']==doc['source_id'] and expected['answer_sha256']==rawsha(doc['text']),'CANDIDATE_REGISTRY_SOURCE_MISMATCH')
        rows=[r for r in expected['records'] if r['candidate_id']==ref['candidate_id']]
        require(len(rows)==1,'CANDIDATE_ID_NOT_IN_CURRENT_SOURCE')
        item=rows[0];span=item['span']
        original=resolve_span({k:span[k] for k in ['unit_id','quote','occurrence']},doc)
        require(original==span,'REGISTERED_CANDIDATE_SOURCE_SPAN_DRIFT')
        return {**span,'candidate_reference':{'candidate_id':item['candidate_id'],'kind':item['kind'],
            'registry_sha256':expected['registry_sha256'],'enumerator_version':expected['enumerator_version'],
            'selection_is_not_semantic_confirmation':True}}
    return resolve_span(ref,doc)

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

def local_name_mentions(name,evidence,doc):
    results=[]
    for match in re.finditer(re.escape(name),evidence['quote']):
        a=evidence['start']+match.start();b=evidence['start']+match.end()
        left=a>0 and bool(re.match(r'\w',doc['text'][a-1])) and bool(re.match(r'\w',name[0]))
        right=b<len(doc['text']) and bool(re.match(r'\w',doc['text'][b])) and bool(re.match(r'\w',name[-1]))
        anti=bool(re.search(r'anti[- ]$',doc['text'][max(0,a-8):a],re.I)) and not name.lower().startswith('anti')
        suffix=omitted_numeric_name_suffix(doc['text'][b:evidence['context_end']])
        punctuation=doc['text'][b:evidence['context_end']].startswith('+') and not re.match(r'^\+\s+\S',doc['text'][b:evidence['context_end']])
        results.append({'start':a,'end':b,'quote':doc['text'][a:b],'answer_sha256':doc['answer_sha256'],
            'same_complete_literal':not(left or right or anti or suffix or punctuation),
            'clipped_boundary':left or right,'additional_anti_qualifier':anti,'additional_numeric_suffix':suffix,'additional_punctuation_suffix':punctuation})
    return results

def relation_policy(f,t,evidence,entities):
    # Identity binding and semantic relationship evidence are different gates.
    ok,why=lexical_relation(f,t,evidence,entities)
    if ok:return ok,why
    if why=='negation_or_alternative_or_inferred_assignment':return False,why
    text=evidence['quote'].strip();ff,tt=re.escape(f),re.escape(t)
    label_header=r'(?:Fluorescen(?:t|ce)\s+(?:Label|Marker)s?|(?:Chosen|Selected)\s+(?:Label(?:l?ing)?|Marker)s?|荧光标记|选用标记)\s*[:：]'
    summary=bool(re.search(label_header,evidence['context'],re.I))
    # A full field quote and its bare pair are equivalent representations.
    # Match only a recognized optional field head and one terminal punctuation;
    # never rewrite the stored quote, offsets, identity, or relationship claim.
    pair=bool(re.fullmatch(r'(?:(?i:'+label_header+r')\s*)?(?:'+tt+r'(?:\s*\([^)]*\))?\s*\+\s*'+ff+r'|'+ff+r'\s*\+\s*'+tt+r')\s*[.!?。！？]?',text))
    if summary and pair:return True,'explicit_single_pair_in_label_summary_not_expert_confirmed'
    # A use/purpose clause can explicitly name an anatomical target without
    # asserting a chemical conjugation. Do not infer a target from cooccurrence.
    purpose=bool(re.search(ff+r'[^.;]*\b(?:for|to label|labels)\s+'+tt+r'(?:\b|$)',text,re.I))
    if purpose:return True,'explicit_named_use_or_label_purpose_not_expert_confirmed'
    return False,'relationship_not_mechanically_explicit'

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
    """A narrow section-heading gate, not a universal permeabilization rule."""
    headings=[]
    for unit in doc['units']:
        if unit['start']>=operation['start']:break
        text=unit['text'].strip()
        if re.match(r'^\d+(?:[.)]\s+|\s+)\D',text) or re.match(r'^#{1,6}\s+',text):headings.append(unit)
    latest=headings[-1] if headings else None
    source_supported=bool(latest and re.search(r'immunostain|immunolabel|(?:pre[- ]clearing\s+)?stain|label(?:l?ing)?\s+prepar|免疫染色|标记预处理',latest['text'],re.I))
    mixed=bool(re.search(r'delipid|decalcif|decolor|RI\s+match|refractive\s+index\s+match|clearing\s+reagent|脱脂|脱钙|脱色|折射率',operation['quote'],re.I))
    return {'supported':source_supported and not mixed,'source_heading':resolve_span({'unit_id':latest['unit_id'],'quote':latest['text'].strip(),'occurrence':0},doc) if latest else None,
        'possible_core_function':mixed,'unknown_or_multifunction_not_automatically_excluded':True,'scientific_phase_confirmed':False}

def intrinsic_policy(record,entity,relations,doc,all_entities=None):
    evidence=record['evidence'];name=entity['name']['quote'];mentions=local_name_mentions(name,evidence,doc)
    native=r'\b(?:native|endogenous|intrinsic)\b|内源|原生|自发报告信号'
    bad=r'\b(?:not|without|either|or|alternative|may|can|lost|quenched|absent|instead|like)\b|\boptimi[sz]ed\s+to\b|e\.g\.|不|备选|替代|例如|比如'
    affirmative=r'\b(?:selected|chosen|used|retain(?:ed)?|preserv(?:ed)?)\b|选用|选择|采用|保留'
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

def bind_literal_name(literal,support,doc):
    """Exact, unique complete literal inside supplied support; never infer a name.

    These public lexical guards reject field/list representations. A surviving
    unknown name remains a literal identity proposal, not a semantic gold label.
    """
    require(isinstance(literal,str) and bool(literal) and literal==literal.strip(),'NAME_WHITESPACE_NOT_IDENTITY')
    require(not re.search(r'[\r\n]|^\s*(?:\*\*|#{1,6}\s)|(?:chosen|selected)\s+(?:method|label(?:l?ing)?s?|markers?|signals?)\s*[:：]|^(?:method|labels?|markers?|方法|标记)\s*[:：]',literal,re.I),'NONATOMIC_NAME_FIELD_HEADER')
    require(not re.search(r'\b(?:is selected|is used|can preserve|optimized to|optimi[sz]ed for)\b',literal,re.I),'NONATOMIC_NAME_ASSERTION')
    hits=[];rejections=[]
    for m in re.finditer('(?='+re.escape(literal)+')',support['quote']):
        start=support['start']+m.start();end=start+len(literal)
        before=doc['text'][max(0,start-32):start];after=doc['text'][end:support['context_end']]
        why=[]
        if start>0 and re.match(r'\w',doc['text'][start-1]) and re.match(r'\w',literal[0]):why.append('CLIPPED_NAME_START')
        if re.search(r'\banti[-\s]+$',before,re.I):why.append('OMITTED_ANTIBODY_IDENTITY_PREFIX')
        if end<len(doc['text']) and re.match(r'\w',doc['text'][end]) and re.match(r'\w',literal[-1]):why.append('CLIPPED_NAME_END')
        if after.startswith('+') and not re.match(r'^\+\s+\S',after):why.append('OMITTED_PUNCTUATION_IDENTITY_SUFFIX')
        if omitted_numeric_name_suffix(after):why.append('OMITTED_DISTINGUISHING_NUMERIC_SUFFIX')
        if why:rejections.append({'start':start,'end':end,'reasons':why});continue
        hits.append((start,end))
    require(bool(hits),rejections[0]['reasons'][0] if rejections else 'LITERAL_NAME_NOT_IN_SUPPORT')
    require(len(hits)==1,'LITERAL_NAME_AMBIGUOUS_WITHIN_SUPPORT_REQUIRE_NARROW_REF')
    start,end=hits[0];unit=next(u for u in doc['units'] if u['unit_id']==support['unit_id'])
    occurrences=[m.start() for m in re.finditer('(?='+re.escape(literal)+')',unit['text'])]
    narrow=resolve_span({'unit_id':unit['unit_id'],'quote':literal,'occurrence':occurrences.index(start-unit['start'])},doc)
    return narrow,{'literal_name':literal,'supporting_evidence':copy.deepcopy(support),'derived_name_span':copy.deepcopy(narrow),
        'atomicity':name_atomicity(literal,support),
        'complete_occurrences_in_support':1,'rejected_substring_occurrences':rejections,'record_id_or_KB_used_to_infer_name':False,
        'atomicity_guard':'hard field/assertion guard plus separate nonfatal composite syntax audit; exact literal binding is independent of atomicity',
        'semantic_identity_confirmed':False,'original_support_preserved':True}

def audit_payload(payload,doc):
    require(rawsha(doc['text'])==doc['answer_sha256'] and document(doc['text'],doc['source_id'])['units']==doc['units'],'DOCUMENT_HASH_OR_UNIT_BINDING')
    validate_shape(payload,schema());integrity.validate_score_proposals(payload['scores'])
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
                    if candidate and field=='duration':require(candidate['kind']=='duration','CANDIDATE_KIND_NOT_DURATION_EVIDENCE')
            if 'literal_name' in r:
                r['name'],r['name_binding']=bind_literal_name(r['literal_name'],r['supporting_evidence'],doc)
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
        r['relation_local_mentions']=mentions;r['primary_entity_spans_preserved']=True
        unique=all(sum(v['same_complete_literal'] for v in mentions[k])==1 for k in ['fluor','target'])
        if t is None:ok,why=False,'unknown_target_endpoint_not_projected'
        elif not f['name_binding']['atomicity']['projection_eligible_provisional'] or not t['name_binding']['atomicity']['projection_eligible_provisional']:ok,why=False,'endpoint_name_atomicity_unresolved'
        elif not unique:ok,why=False,'complete_endpoint_identity_absent_or_ambiguous_in_relation_evidence'
        elif f['kind'] not in ['fluorophore','fluorescent_protein']:ok,why=False,'label_endpoint_kind_unresolved'
        elif f['id']==t['id']:ok,why=False,'self_target_identity_not_supported'
        else:ok,why=relation_policy(f['name']['quote'],t['name']['quote'],r['evidence'],result['entities'])
        r['projection_allowed']=r['status']=='explicit' and ok;r['mechanical_relation_state']=why
        r['entity_type_and_relation_role_distinct']=True
        r['unsupported_claim_retained_not_repaired']=r['status']=='explicit' and not r['projection_allowed']
    for record in result['intrinsic_signals']:
        require(record['entity_id'] in entities,'INTRINSIC_DANGLING_ENTITY')
        record['identity_policy']=intrinsic_policy(record,entities[record['entity_id']],result['relations'],doc,result['entities'])
    duration_spans=[]
    for o in result['operations']:
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
        if o['condition_evidence']:
            require(o['operation']['unit_id']==o['condition_evidence']['unit_id'],'CONDITION_OUTSIDE_OPERATION_RECORD')
        conditional_pattern=r'\bif\b|\bwhen needed\b|\bas needed\b|\bafter storage\b|\bre[- ]equilibrat\w*\b|\bagain\b|\brepeated\b|\bfuture\b|如需|如果|再次|再平衡|保存后'
        conditional_cue=re.search(conditional_pattern,o['operation']['context'],re.I)
        o['scope_gate']={'conditional_cue_detected':bool(conditional_cue),
            'conditional_scope_supported':bool(o['condition_evidence'] and re.search(conditional_pattern,o['condition_evidence']['quote'],re.I))}
        o['repeat_count']=repeat_count(o['repeat_evidence'])
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

def convert(raw,doc):
    parsed=integrity.parse_judge_object(raw);audit=audit_payload(parsed,doc);projection=project_legacy(audit)
    legacy={'scores':copy.deepcopy(parsed['scores']),'extraction':projection['extraction']}
    return {'raw_response_sha256':rawsha(raw),'raw_content_preserved':raw,'source_audit':audit,
        'legacy_projection':projection,'legacy_runner_payload':legacy,'legacy_runner_content':canonical(legacy),
        'transformation_is_explicit_not_raw_identity':True,'scores_preserved_exactly':legacy['scores']==parsed['scores'],
        'formal_eligible':False,'expert_confirmed':False}

def synthetic_fixture(first='2 hours',second='30 minutes',mode='serial',relation='explicit'):
    """Software-only, intentionally fictional names; never a natural-answer label."""
    relation_text=('SYNTHETIC_FLUOR_101-labeled SYNTHETIC_TARGET' if relation=='explicit' else
        'SYNTHETIC_FLUOR_101 and SYNTHETIC_TARGET')
    cue={'serial':'Sequential schedule.','parallel':'Run in parallel.','alternative':'Choose either operation or the other.','unknown':'Schedule is unspecified.'}[mode]
    text=('Chosen Method: SYNTHETIC_METHOD\n'+relation_text+'\n'+
        '1. Synthetic clearing treatment for '+first+'.\n'+
        '2. Synthetic RI matching for '+second+'.\n'+cue+'\n')
    doc=document(text,'SYNTHETIC_ONLY_SOURCE')
    def sp(quote):
        units=[u for u in doc['units'] if quote in u['text']];require(len(units)==1,'FIXTURE_QUOTE_NOT_UNIQUE')
        return {'unit_id':units[0]['unit_id'],'quote':quote,'occurrence':0}
    scores={'completeness':{k:{'score':0,'reasoning':'SYNTHETIC_ONLY software fixture, not a scientific judgment.'} for k in ['c_step','c_param']},
            'correctness':{k:{'score':0,'reasoning':'SYNTHETIC_ONLY software fixture, not a scientific judgment.'} for k in ['co_order','co_method','co_param','co_chem']}}
    operations=[{'id':'op1','operation':sp(doc['units'][2]['text'].strip()),'phase':'clearing_treatment','duration':sp(first),'repeat_evidence':None,'execution_scope':'initial','condition_evidence':None},
                {'id':'op2','operation':sp(doc['units'][3]['text'].strip()),'phase':'ri_matching','duration':sp(second),'repeat_evidence':None,'execution_scope':'initial','condition_evidence':None}]
    g={'schema_version':VERSION,'source_id':doc['source_id'],
       'method_mentions':[{'id':'method1','literal_name':'SYNTHETIC_METHOD','supporting_evidence':sp('SYNTHETIC_METHOD'),'usage':'selected'}],
       'entities':[{'id':'fluor1','literal_name':'SYNTHETIC_FLUOR_101','supporting_evidence':sp('SYNTHETIC_FLUOR_101'),'kind':'fluorophore','usage':'used'},
                   {'id':'target1','literal_name':'SYNTHETIC_TARGET','supporting_evidence':sp('SYNTHETIC_TARGET'),'kind':'target','usage':'used'}],
       'relations':[{'id':'relation1','fluor_entity_id':'fluor1','target_entity_id':'target1','evidence':sp(relation_text),'status':relation}],
       'intrinsic_signals':[],
       'operations':operations,'timeline':{'mode':mode,'operation_ids':['op1','op2'],'relation_evidence':sp(cue),'completeness':'complete'},
       'precedence_edges':[],'total_time_claims':[],'ri_mentions':[],
       'coverage':{'entities':'complete','time_operations':'complete','core_time_operations':'complete','unresolved':[]}}
    payload={'scores':scores,'score_evidence':[{'metric':m,'answer_spans':[],
        'basis':'absence','rubric_basis':'SYNTHETIC_ONLY rubric coverage fixture; no scientific score claim.'} for m in DIRECT],
        'grounded_extraction':g}
    return doc,payload

def synthetic_record_fixture(null_target=False):
    """Fictional short action plus adjacent time; no natural-answer labels."""
    doc,payload=synthetic_fixture()
    text=doc['text'].replace('1. Synthetic clearing treatment for 2 hours.',
        '1. Incubation in SYNTHETIC_MEDIUM. Time: 2 hours.')
    doc=document(text,doc['source_id'])
    op=payload['grounded_extraction']['operations'][0]
    op['operation']={'unit_id':'L0003','quote':'Incubation in SYNTHETIC_MEDIUM','occurrence':0}
    if null_target:
        payload['grounded_extraction']['entities']=payload['grounded_extraction']['entities'][:1]
        payload['grounded_extraction']['relations'][0]['target_entity_id']=None
        payload['grounded_extraction']['relations'][0]['status']='unknown'
    return doc,payload

def self_check():
    """Isolated v4 software probes; no provider or natural-answer gold labels."""
    checks=[]
    def check(name,condition=True,detail=None):
        require(bool(condition),'SOFTWARE_PROBE_FAILED:'+name)
        checks.append({'fixture':name,'status':'pass','synthetic_only':True,'detail':detail})
    def rejected(name,call,code):
        try:call()
        except (ValueError,integrity.JudgeFormatError) as exc:
            check(name,code.casefold() in str(exc).casefold(),{'expected_failure':str(exc)});return
        raise ValueError('UNEXPECTED_ACCEPTANCE:'+name)
    def run(d,p):return convert(canonical(p),d)
    def g(p):return p['grounded_extraction']
    def ref(d,quote,unit=None):
        units=[u for u in d['units'] if quote in u['text'] and (not unit or unit==u['unit_id'])]
        require(len(units)==1,'PROBE_QUOTE_NOT_UNIQUE')
        return {'unit_id':units[0]['unit_id'],'quote':quote,'occurrence':0}
    def append(d,line):return document(d['text']+line+'\n',d['source_id'])
    def entity(d,name,id='extra',kind='fluorescent_protein',usage='used',unit=None):
        return {'id':id,'literal_name':name,'supporting_evidence':ref(d,name,unit),'kind':kind,'usage':usage}
    d,p=synthetic_fixture();q=run(d,p)
    check('unchanged_scores_and_strict_sum',q['legacy_runner_payload']['scores']==p['scores'] and q['legacy_projection']['time_calculation']['total_hours']==2.5)
    check('strict_relation_projection',q['legacy_projection']['extraction']['marker_dict']=={'SYNTHETIC_FLUOR_101':'SYNTHETIC_TARGET'})
    check('raw_response_identity',q['raw_content_preserved']==canonical(p))
    check('original_score_schema',schema()['properties']['scores']==read(baseline.OUT/'final_output_schema.json')['properties']['scores'])
    rejected('strict_duplicate_keys',lambda:convert('{"scores":{},"scores":{}}',d),'duplicate')
    for name,mutate,code in [
        ('explicit_null',lambda x:g(x)['relations'][0].update(target_entity_id=None),'SCHEMA_ANYOF'),
        ('dangling_target',lambda x:g(x)['relations'][0].update(target_entity_id='absent'),'RELATION_DANGLING_ENTITY'),
        ('duplicate_id',lambda x:g(x)['entities'][1].update(id='fluor1'),'DUPLICATE_RECORD_ID'),
        ('missing_score_evidence',lambda x:x['score_evidence'].pop(),'SCORE_EVIDENCE_EXACT_FIVE_UNIQUE'),
        ('fake_quote',lambda x:g(x)['entities'][0]['supporting_evidence'].update(quote='ABSENT_NAME'),'SPAN_QUOTE_NOT_FOUND'),
        ('unit_duration',lambda x:g(x)['operations'][0].update(duration={'unit_id':'L0003'}),'SCHEMA_ANYOF'),
        ('reused_duration',lambda x:g(x)['operations'][1].update(duration=copy.deepcopy(g(x)['operations'][0]['duration'])),'REUSED_DURATION_DOUBLE_COUNT')]:
        d,p=synthetic_fixture();mutate(p);rejected(name,lambda:run(d,p),code)
    d,p=synthetic_record_fixture(True);q=run(d,p)
    check('unknown_nullable_target_keeps_unrelated_components',q['legacy_projection']['time_calculation']['total_hours']==2.5 and not q['source_audit']['resolved']['relations'][0]['projection_allowed'])
    check('same_record_adjacent_duration',q['source_audit']['resolved']['operations'][0]['duration_binding']['valid'])
    # Execute all 24 independently specified name cases with the public binder.
    specpath=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_v4_design_v1/name_contract_review/name_counterexample_spec.json'
    expected_reject={'N03':'NONATOMIC_NAME_FIELD_HEADER','N05':'LITERAL_NAME_AMBIGUOUS','N07':'CLIPPED_NAME_START','N09':'OMITTED_ANTIBODY','N11':'OMITTED_DISTINGUISHING','N16':'OMITTED_PUNCTUATION','N18':'LITERAL_NAME_NOT_IN_SUPPORT','N20':'LITERAL_NAME_NOT_IN_SUPPORT'}
    for row in read(specpath)['cases']:
        units=row.get('units',[row.get('evidence','')]);nd=document('\n'.join(units)+'\n','SYNTHETIC_NAME_SPEC_'+row['id'])
        idx=row.get('selected_unit',1 if row['id']=='N19' else 0);support=resolve({'unit_id':nd['units'][idx]['unit_id']},nd)
        literals=[r['literal'] for r in row['records']] if 'records' in row else [row['literal']]
        if row['id'] in expected_reject:
            rejected('name_spec_'+row['id'],lambda:bind_literal_name(literals[0],support,nd),expected_reject[row['id']]);continue
        bound=[bind_literal_name(l,support,nd) for l in literals]
        check('name_spec_'+row['id'],all(nd['text'][s['start']:s['end']]==l and s['quote']==l for l,(s,b) in zip(literals,bound)),{'binding_only_not_semantics':True})
        if row['id']=='N04':check('N04_prespecified_unresolved_atomicity_branch',not bound[0][1]['atomicity']['projection_eligible_provisional'])
    nd=document('Marker: GFP then GFP.\r\n','SYNTHETIC_REPEAT')
    narrow=resolve({'unit_id':'L0001','quote':'GFP','occurrence':1},nd);s,b=bind_literal_name('GFP',narrow,nd)
    check('explicit_narrow_support_disambiguates_repeated_name',s['occurrence']==1 and s['start']==nd['text'].rfind('GFP'))
    wide=resolve({'unit_id':'L0001'},nd)
    check('UnitRef_CRLF_exact',wide['quote']==nd['text'] and wide['unit_reference']['source_unit_sha256']==rawsha(nd['text']))
    for literal in ['Unknown[3H]-Q','Protein(A/B)','2,2′-Thiodiethanol','Novel:Marker-Q']:
        pd=document(literal+'\n','SYNTHETIC_PUNCTUATION');ns,b=bind_literal_name(literal,resolve({'unit_id':'L0001'},pd),pd)
        check('unknown_punctuation_'+literal,ns['quote']==literal)
    for literal,eligible in [('SYNTHETIC, Ester',True),('SYNTHETIC_A/SYNTHETIC_B',False),('SYNTHETIC_A / SYNTHETIC_B',False),('SYNTHETIC_A;SYNTHETIC_B',False),('SYNTHETIC_A + SYNTHETIC_B',False),('SYNTHETIC_A, SYNTHETIC_B',False),('2,2′-Thiodiethanol',True),('Unknown Multiword Marker',True),('iDISCO+',True)]:
        nd=document(literal+'\n','SYNTHETIC_ATOMICITY');ns,nb=bind_literal_name(literal,resolve({'unit_id':'L0001'},nd),nd)
        check('atomicity_boundary_'+literal,ns['quote']==literal and nb['atomicity']['projection_eligible_provisional']==eligible)
    d,p=synthetic_fixture();line='Chosen marker: SYNTHETIC_A/SYNTHETIC_B (native).';d=append(d,line)
    g(p)['entities'].append(entity(d,'SYNTHETIC_A/SYNTHETIC_B','composite'))
    g(p)['intrinsic_signals'].append({'id':'composite_native','entity_id':'composite','evidence':ref(d,line),'status':'source_declared'})
    q=run(d,p)
    check('composite_entity_and_intrinsic_not_projected',q['source_audit']['resolved']['entities'][-1]['name']['quote']=='SYNTHETIC_A/SYNTHETIC_B' and 'SYNTHETIC_A/SYNTHETIC_B' not in q['legacy_projection']['extraction']['marker_dict'] and not q['legacy_projection']['intrinsic_identity_conversion'][-1]['legacy_same_name_projection_applied'])
    check('composite_unresolved_keeps_unrelated_components',q['legacy_runner_payload']['scores']==p['scores'] and q['legacy_projection']['extraction']['method_name']=='SYNTHETIC_METHOD' and q['legacy_projection']['time_calculation']['total_hours']==2.5 and q['legacy_projection']['component_input_state']['s_label']=='partial_projection_requires_NA_gate')
    line='SYNTHETIC_A/SYNTHETIC_B-labeled SYNTHETIC_TARGET';d=append(d,line);g(p)['relations'].append({'id':'composite_relation','fluor_entity_id':'composite','target_entity_id':'target1','evidence':ref(d,line),'status':'explicit'});q=run(d,p)
    check('composite_relation_endpoint_not_projected',not q['source_audit']['resolved']['relations'][-1]['projection_allowed'] and q['source_audit']['resolved']['relations'][-1]['mechanical_relation_state']=='endpoint_name_atomicity_unresolved')
    d,p=synthetic_fixture();line='Chosen Method: METHOD_A / METHOD_B';d=append(d,line);g(p)['method_mentions']=[{'id':'composite_method','literal_name':'METHOD_A / METHOD_B','supporting_evidence':{'unit_id':d['units'][-1]['unit_id']},'usage':'selected'}];q=run(d,p)
    check('composite_method_not_projected',q['legacy_projection']['extraction']['method_name'] is None and q['legacy_projection']['time_calculation']['total_hours']==2.5)
    choice='Chosen Labeling: [REPORTER (native), DYE_A / DYE_B / DYE_C]'
    check('alternative_group_header_does_not_mark_all_used',affirmative_entity_use('REPORTER',choice) and not any(affirmative_entity_use(n,choice) for n in ['DYE_A','DYE_B','DYE_C']))
    check('later_operation_selects_only_literal_member',affirmative_entity_use('DYE_A','Incubate in DYE_A.') and not affirmative_entity_use('DYE_B','Incubate in DYE_A.'))
    for text,literal,expected in [('Hoechst 33342','Hoechst',False),('DAPI 10 micromolar','DAPI',True),('iDISCO+','iDISCO',False),('iDISCO+','iDISCO+',True)]:
        pd=document(text+'\n','SYNTHETIC_SUFFIX');support=resolve({'unit_id':'L0001'},pd)
        check('relation_local_suffix_consistency_'+text+'_'+literal,local_name_mentions(literal,support,pd)[0]['same_complete_literal']==expected)
    rejected('foreign_unit',lambda:resolve({'unit_id':'L0999'},nd),'UNIT_REFERENCE_NOT_IN_CURRENT_SOURCE')
    d,p=synthetic_fixture();g(p)['method_mentions'][0]['supporting_evidence']={'unit_id':'L0001'};p['score_evidence'][0].update(basis='observed',answer_spans=[{'unit_id':'L0001'}]);q=run(d,p)
    check('unit_support_derives_narrow_name_and_keeps_wide',q['source_audit']['resolved']['method_mentions'][0]['name']['quote']=='SYNTHETIC_METHOD' and q['source_audit']['resolved']['method_mentions'][0]['supporting_evidence']['quote']==d['units'][0]['text'])
    check('unit_score_evidence_exact',q['source_audit']['score_evidence'][0]['answer_spans'][0]['quote']==d['units'][0]['text'])
    registry=candidate_registry(d);duration=next(r for r in registry['records'] if r['kind']=='duration')
    check('candidate_exact_current_document',resolve({'candidate_id':duration['candidate_id']},d)['quote']==duration['span']['quote'])
    rejected('unknown_candidate',lambda:resolve({'candidate_id':'C999999'},d),'CANDIDATE_ID_NOT_IN_CURRENT_SOURCE')
    # Source units are not name/phase truth; duplicate identities stay visible.
    d,p=synthetic_fixture();duplicate=copy.deepcopy(g(p)['entities'][0]);duplicate['id']='second_fluor';g(p)['entities'].append(duplicate);q=run(d,p)
    check('duplicate_literal_records_audited_not_erased',len(q['source_audit']['resolved']['entities'])==3 and q['source_audit']['resolved']['duplicate_literal_identity_audit'][0]['entity_ids']==['fluor1','second_fluor'])
    for ending in ['imaging','morphological mapping','anatomical context','light-sheet or confocal imaging','high-resolution volumetric reconstruction']:
        d,p=synthetic_fixture();d=append(d,'This supports 3D '+ending+'.');q=run(d,p)
        check('spatial_'+ending,q['legacy_projection']['time_calculation']['total_hours']==2.5 and any(x['kind']=='dimensional_expression_lead' for x in q['source_audit']['inventory']))
    for literal in ['3d','3D','3 days']:
        check('actual_day_'+literal,duration_role(literal,'Incubate for ',' before proceeding.')[0]=='duration' and duration_value(literal)['unique_hours']==72)
    check('nominal_clearing_process_not_action',record_action_heads('Justification: protect labels throughout dehydration and clearing process.')==[])
    check('imperative_clear_preserved',record_action_heads('Incubate ALPHA and clear BETA.').count('clear')==1)
    check('nominal_instruction_clearing_object_preserved','clearing' in record_action_heads('Wash ALPHA and clearing BETA for 1 hour.'))
    for text,supported in [('The method is optimized to preserve reporters like REPORTER.',True),('Chosen marker: REPORTER, like other labels.',False)]:
        nd=document(text+'\n','SYNTHETIC_USAGE');ns,_=bind_literal_name('REPORTER',resolve({'unit_id':'L0001'},nd),nd)
        check('mentioned_'+str(supported),mentioned_usage_support({'name':ns})['supported']==supported)
    # Incoming targets and outgoing legacy keys have different roles. These
    # nine cases are the independently proposed graph specs, not biology gold.
    def intrinsic_case(line='Chosen signal: REPORTER (native).'):
        d,p=synthetic_fixture();d=append(d,line);g(p)['entities'].append(entity(d,'REPORTER','reporter'))
        g(p)['intrinsic_signals']=[{'id':'native','entity_id':'reporter','evidence':ref(d,line),'status':'source_declared'}]
        return d,p
    def add_incoming(d,p,line='SYNTHETIC_FLUOR_101-labeled REPORTER.'):
        d=append(d,line);g(p)['relations']=[{'id':'incoming','fluor_entity_id':'fluor1','target_entity_id':'reporter','evidence':ref(d,line),'status':'explicit'}];return d,p
    graph_results=[]
    for code in ['G01','G02','G03','G04','G05','G06','G07','G08','G09']:
        text={'G02':'REPORTER is detected by antibody only; native signal is not used.','G03':'Chosen signal: REPORTER.','G04':'Native REPORTER is absent; antibody detection is used.','G05':'This method is optimized to preserve endogenous fluorescence like REPORTER.','G09':'If condition A applies, chosen signal: REPORTER (native).'}.get(code,'Chosen signal: REPORTER (native).')
        d,p=intrinsic_case(text)
        if code in ['G01','G02','G03','G04','G09']:d,p=add_incoming(d,p)
        if code=='G06':g(p)['relations'].append({'id':'outgoing','fluor_entity_id':'reporter','target_entity_id':'target1','evidence':ref(d,text),'status':'unknown'})
        if code=='G07':d,p=add_incoming(d,p,'SYNTHETIC_FLUOR_101 and REPORTER are separately listed.')
        if code=='G08':g(p)['entities'].append(entity(d,'REPORTER','collision',kind='target',usage='unknown'))
        q=run(d,p);ic=q['legacy_projection']['intrinsic_identity_conversion'][0];expected=code in ['G01','G07']
        check('graph_spec_'+code,ic['legacy_same_name_projection_applied']==expected)
        if not expected:check('graph_unresolved_component_'+code,q['legacy_projection']['component_input_state']['s_label']=='partial_projection_requires_NA_gate')
        graph_results.append({'id':code,'applied':ic['legacy_same_name_projection_applied'],'expected':expected})
    # Same-record chosen usage is preserved even alongside a separate example.
    d,p=synthetic_fixture();d=append(d,'This method can preserve reporters like REPORTER.');example=d['units'][-1]['unit_id'];d=append(d,'Chosen marker: REPORTER.')
    g(p)['entities'].append(entity(d,'REPORTER','example','fluorescent_protein','mentioned',example));q=run(d,p)
    check('mentioned_does_not_erase_separate_selection',bool(q['source_audit']['resolved']['affirmative_entity_usage_gaps']))
    g(p)['entities'].append(entity(d,'REPORTER','chosen','fluorescent_protein','used',d['units'][-1]['unit_id']));q=run(d,p)
    check('separate_used_record_resolves_usage_gap',not q['source_audit']['resolved']['affirmative_entity_usage_gaps'])
    for change,expected in [('whole_partial',2.5),('core_partial',None),('unknown_phase',None),('missing_duration',None)]:
        d,p=synthetic_fixture()
        if change=='whole_partial':g(p)['coverage']['time_operations']='partial';g(p)['timeline']['completeness']='partial'
        elif change=='core_partial':g(p)['coverage']['core_time_operations']='partial'
        elif change=='unknown_phase':g(p)['operations'][0]['phase']='unknown'
        else:g(p)['operations'][0]['duration']=None
        check('time_'+change,run(d,p)['legacy_projection']['time_calculation']['total_hours']==expected)
    d,p=synthetic_fixture();d=append(d,'3. Incubate OMITTED_CORE_ACTION.');q=run(d,p)
    check('core_missing_action_still_NA','source_action_records_not_all_classified' in q['legacy_projection']['time_calculation']['issues'])
    d,p=synthetic_fixture('2-4 hours');q=run(d,p)
    check('range_retains_bounds_not_scalar',q['legacy_projection']['time_calculation']['total_hours'] is None and q['legacy_projection']['time_calculation']['candidate_bounds_hours']==[2.5,4.5])
    d,p=synthetic_fixture();line='Before repeated imaging, equilibrate ALPHA for 1 hour.';d=append(d,line)
    g(p)['operations'].append({'id':'future','operation':ref(d,'equilibrate ALPHA'),'phase':'ri_matching','duration':ref(d,'1 hour'),'repeat_evidence':None,'execution_scope':'conditional_or_future','condition_evidence':ref(d,'Before repeated imaging')});q=run(d,p)
    check('conditional_endpoint_keeps_initial_and_unknown_total',q['legacy_projection']['time_calculation']['total_hours'] is None and q['legacy_projection']['time_calculation']['initial_scope_candidate_bounds_hours']==[2.5,2.5])
    d,p=synthetic_fixture();g(p)['precedence_edges']=[{'before_id':'op1','after_id':'op2','evidence':{'unit_id':'L0003'}}];q=run(d,p)
    check('adjacent_numbering_not_dependency',q['source_audit']['resolved']['precedence_audit']['unsupported_dependency_claims']==1)
    g(p)['precedence_edges'].append({'before_id':'op2','after_id':'op1','evidence':{'unit_id':'L0004'}});q=run(d,p)
    check('cycle_preserved_invalid_unused',q['source_audit']['resolved']['precedence_audit']['cyclic_model_proposal'] and not q['source_audit']['resolved']['precedence_audit']['model_edges_used_for_aggregation'])
    # Explicit shared record support can be diagnosed without claiming a true
    # dependency or using the edge for arithmetic.
    d,p=synthetic_fixture();line='Incubate ALPHA before rinse BETA.';d=append(d,line)
    for oid,verb in [('depA','Incubate ALPHA'),('depB','rinse BETA')]:g(p)['operations'].append({'id':oid,'operation':ref(d,verb),'phase':'routine_wash','duration':None,'repeat_evidence':None,'execution_scope':'initial','condition_evidence':None})
    g(p)['precedence_edges']=[{'before_id':'depA','after_id':'depB','evidence':{'unit_id':d['units'][-1]['unit_id']}}];q=run(d,p)
    check('explicit_shared_unit_dependency_support_retained',q['source_audit']['resolved']['precedence_edges'][0]['source_dependency_support']['mechanically_supported'])
    # Transport probe swaps the client before socket access.
    from models.Ollama_LLM import OllamaLLM
    captured=[];d,p=synthetic_record_fixture(True)
    class NoNetwork:
        def generate(self,**kwargs):
            captured.append(copy.deepcopy(kwargs));return {'done':True,'done_reason':'stop','response':canonical(p),'eval_count':1,'prompt_eval_count':1,'model':'SYNTHETIC_ONLY_MODEL'}
    adapter=OllamaLLM('SYNTHETIC_ONLY_MODEL',format=schema(),max_length=8192,temperature=0,enable_thinking=False);adapter.client=NoNetwork()
    response=adapter._generate('SYNTHETIC_ONLY source prompt');check('full_decoder_schema_no_network',captured[0]['format']==schema() and response['content']==canonical(p))
    save(OUT/'synthetic_only/source_document.json',d);save(OUT/'synthetic_only/payload.json',p);save(OUT/'synthetic_only/conversion.json',run(d,p));save(OUT/'synthetic_only/transmitted_payload.json',captured[0])
    (OUT/'synthetic_only/raw_response.txt').write_bytes(canonical(p).encode('utf8'))
    import subprocess
    crlf=json.dumps(p,ensure_ascii=False,indent=2).replace('\n','\r\n');rp=OUT/'synthetic_only/raw_response_CRLF.txt';rp.write_bytes(crlf.encode('utf8'));cp=OUT/'synthetic_only/CLI_CRLF_conversion.json'
    argv=[sys.executable,str(Path(__file__).resolve()),'convert','--source-document',str(OUT/'synthetic_only/source_document.json'),'--raw-response',str(rp),'--out',str(cp)]
    result=subprocess.run(argv,capture_output=True,text=True,encoding='utf8');require(result.returncode==0,'CLI_CRLF_REPLAY_FAILED:'+result.stderr);cq=read(cp)
    check('actual_CLI_preserves_raw_CRLF',cq['raw_content_preserved']==crlf and cq['raw_response_sha256']==sha(rp))
    save(OUT/'synthetic_only/CLI_CRLF_execution.json',{'argv':argv,'exit_code':result.returncode,'new_model_requests':0,'synthetic_only':True})
    actual=[]
    for case in read(baseline.OUT/'cases.json')['cases']:
        aid=case['anonymous_answer_id'];doc=read(OUT/'source_documents'/f'{aid}.json')
        require(doc['source_id']==source_id_for_case(case) and doc['text']==case['model_response'] and doc['answer_sha256']==case['answer_sha256'],'ACTUAL_SOURCE_IDENTITY')
        candidates=evidence_inventory(doc)
        for item in candidates:require(resolve_span({k:item['span'][k] for k in ['unit_id','quote','occurrence']},doc)==item['span'],'ACTUAL_CANDIDATE_SPAN')
        for unit in doc['units']:require(resolve({'unit_id':unit['unit_id']},doc)['quote']==unit['text'],'ACTUAL_UNIT_BYTES')
        actual.append({'anonymous_answer_id':aid,'answer_sha256':doc['answer_sha256'],'source_id':doc['source_id'],'all_units_reconstruct_original':True,'candidate_span_checks':len(candidates),'labels_created':0})
    mf=OUT/'plan.json' if (OUT/'plan.json').exists() else OUT/'draft_manifest.json'
    report={'status':'pass','synthetic_only_checks':checks,'synthetic_fixture_count':len(checks),'actual_source_identity_checks':actual,'independent_name_spec_count':24,'independent_graph_spec_count':9,'graph_results':graph_results,'new_model_requests':0,'network_calls':0,'scientific_or_expert_labels_created':0,'script_sha256':sha(__file__),'schema_sha256':sha(OUT/'schema.json'),'actual_command':[sys.executable,*sys.argv]}
    report['plan_sha256' if mf.name=='plan.json' else 'draft_manifest_sha256']=sha(mf);save(OUT/'software_probes.json',report)
    print(canonical({'status':'offline_checks_pass','synthetic_checks':len(checks),'actual_source_identity_checks':len(actual),'new_requests':0}))


INSTRUCTIONS='''[SOURCE-BOUND EXTRACTION CONTRACT v4]
Return one JSON with unchanged scores, five score_evidence records and grounded_extraction. Full decoder schema is supplied separately. Extracted answer facts/source spans cite MODEL_PROTOCOL only; direct scoring still uses the unchanged QUESTION/rubric/reference evidence.
SourceRef: prefer {candidate_id} from this source catalog, or {unit_id} for an unchanged full indexed unit, or exact RawSpan={unit_id,quote,occurrence} (zero-based). Unknown names still use RawSpan; never omit them. Method/entity literal_name is the complete name only, not its field header/list. supporting_evidence may be wider; its unique complete literal occurrence produces a narrow name span. Repeated names in a unit require an explicit narrow Ref. Preserve qualifiers/suffixes and exact punctuation; never derive names from IDs or aliases. Duration/RI values require a precise CandidateRef or RawSpan, not UnitRef. Catalog leads are not semantic truth.
Preserve every member of an explicitly alternative source list as a separate name. Later actual operations can select only the corresponding member; retain other members as alternative/unknown and cite list ambiguity in coverage.unresolved. A Chosen heading or slash alone proves neither simultaneous use nor mutual exclusivity. Never use a combined list string as one atomic entity.
score_evidence covers c_param/co_order/co_method/co_param/co_chem once each: observed/mixed requires answer references; absence has none and a short rubric basis. Preserve all original scales including c_step.
Relation has id,fluor_entity_id,target_entity_id,evidence,status. explicit requires a nonnull declared target ID; ambiguous/unknown may use null. Complete endpoint names must occur locally in relationship evidence. Entity type differs from target role. Co-occurrence, arbitrary lists, generic family names and numbered names elsewhere cannot prove a mapping. Ordinary self-target relations remain unsupported. For small-molecule dyes, the original legacy interface is key-only: do not invent a target or a null-target relation merely to fill a field. Actual ambiguous external-label claims must remain explicit uncertainties.
Entity usage mentioned is only for source capability/example cues (including like/optimized-to) without affirmative use in that record; preserve separate chosen/used occurrences of the same name. Never use mentioned to erase selected identities. intrinsic_signals records id,entity_id,evidence,status(source_declared/ambiguous/unknown). Only an affirmatively selected/used fluorescent protein with its complete name and explicit native/endogenous declaration may support source_declared_intrinsic_identity. Antibody-only detection, capabilities/examples, alternatives, negation or conflicting outgoing claims using the same literal legacy key do not. An incoming dye-to-protein target relation is distinct and cannot itself establish or negate native usage. This is not self-binding or proof of preservation/task suitability; the adapter records same-name legacy serialization separately.
Enumerate operations, durations, exclusions and later conditions. SourceRef operation and duration can be adjacent fields of one unambiguous record. Never reuse one duration twice. Classify phase/scope from source; labeling_preparation needs a preceding labeling/immunostaining heading and no conflicting core function. Generic or multifunctional permeabilization stays unknown. Classify coverage.time_operations for the whole protocol independently from coverage.core_time_operations. Undetailed upstream labeling can make only whole coverage partial when all actual core actions and durations are present; do not copy whole partial into core. Missing core actions/durations or uncertain core membership still makes core partial/unknown. Never claim complete just because all numeric leads are cited.
Do not sum times. The program derives core initial membership, preserves your timeline proposal/differences, converts units, and retains known bounds. Ranges, missing values, phase/scope ambiguity, unspecified overnight and conditional endpoints remain nullable. Default precedence_edges=[]: adjacent numbering is not an explicit dependency. Add an edge only with exact same-unit evidence containing both operations and an explicit dependency cue; never paraphrase several source lines into one quote. Edges are audited, not used for time aggregation. Core includes delipidation/decalcification/decolorization/RI/clearing treatment/transition washes; excludes fixation/labeling/antibody/imaging/routine wash/continuing storage. Strong spatial phrases such as dimensional imaging are not durations; actual day units remain valid.
Keep method/RI roles distinct. RI may be a unique explicit number or RI-labelled number; a medium name gives no number. Never invent protocol_time_hours. Coverage is not certified by self-report. Structural success and source-exact spans do not establish semantic, rubric or expert correctness.
'''

def make_prompt(case,doc):
    import contextlib,io
    require(doc['source_id']==source_id_for_case(case),'PROMPT_SOURCE_ID_NOT_OPAQUE_CONTENT_BOUND')
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):old=baseline.transform(helper.exact_runner_prompt(case))
    require(old.count(SECTION3)==1,'EXTRACTION_SECTION_ANCHOR')
    prefix=old.split(SECTION3)[0]
    prefix=prefix.replace('- extraction.marker_dict, extraction.clearing_total_time_hours','- grounded_extraction source evidence records')
    prefix=prefix.replace('scores and extraction groups','scores and grounded_extraction groups')
    prefix=prefix.replace("and 'extraction'.","and 'grounded_extraction'.")
    units=[{'unit_id':u['unit_id'],'text':u['text']} for u in doc['units']]
    require(''.join(u['text'] for u in units)==case['model_response'],'INDEXED_SOURCE_NOT_EXACTLY_RECONSTRUCTABLE')
    require(prefix.count(case['model_response'])==1,'ORIGINAL_MODEL_PROTOCOL_BLOCK_NOT_UNIQUE')
    prefix=prefix.replace(case['model_response'],'[LOSSLESS INDEXED MODEL_PROTOCOL; concatenate text fields in order]\n'+canonical(units),1)
    inventory=[{'candidate_id':r['candidate_id'],'kind':r['kind'],'unit_id':r['span']['unit_id'],
                'quote':r['span']['quote'],'occurrence':r['span']['occurrence']} for r in evidence_inventory(doc) if r['kind']!='number']
    # Compact candidate pointers avoid another copy of the source text. No scientific content is dropped.
    codes={'duration':'D','numbered_name_lead':'N','known_marker_name_lead':'F','known_method_name_lead':'M',
        'declared_field_lead':'H','metadata_word_lead':'W','operation_record_lead':'O','dimensional_expression_lead':'X',
        'recurrence_interval_lead':'I','action_section_heading_lead':'S'}
    pointers=[[r['candidate_id'],codes[r['kind']],r['unit_id']] if r['kind'] in ['operation_record_lead','action_section_heading_lead'] else
        [r['candidate_id'],codes[r['kind']],r['unit_id'],r['quote'],r['occurrence']] for r in inventory]
    legend='D duration; N numbered-name; F known-marker; M method; H field; W metadata-word; O operation line; S section heading; X spatial; I interval. O/S are full trimmed indexed lines. Recall only, NOT GOLD.'
    return prefix+INSTRUCTIONS+'\n[SOURCE_ID]\n'+doc['source_id']+'\n[RECALL POINTERS: candidate_id,kind,unit_id,exact_quote,occurrence; O omits quote because it is the entire trimmed indexed line]\n'+legend+'\n'+canonical(pointers)+baseline.parent.v2.reference_suffix(case)

def _build_draft():
    OUT.mkdir(parents=True,exist_ok=True);cases=read(baseline.OUT/'cases.json')['cases'];require([c['anonymous_answer_id'] for c in cases]==['A01','A02','A03','A04','A05'],'FIXED_DEVELOPMENT_SELECTION')
    schema_value=schema();save(OUT/'schema.json',schema_value);save(OUT/'type_catalog.json',schema_catalog(schema_value));(OUT/'extraction_instructions.txt').write_text(INSTRUCTIONS,encoding='utf8')
    matrices=[]
    for c in cases:
        aid=c['anonymous_answer_id'];doc=document(c['model_response'],source_id_for_case(c))
        require(doc['answer_sha256']==c['answer_sha256'] and rawsha(c['specific_question'])==c['question_sha256'],'ORIGINAL_DEVELOPMENT_IDENTITY')
        save(OUT/'source_documents'/f'{aid}.json',doc);save(OUT/'candidate_inventories'/f'{aid}.json',evidence_inventory(doc))
        prompt=make_prompt(c,doc);p=OUT/'prompts'/f'{aid}.txt';p.parent.mkdir(exist_ok=True);p.write_text(prompt,encoding='utf8')
        require(c['case_id'] not in prompt,'CASE_METADATA_LEAK_IN_PROMPT')
        old=(baseline.OUT/'prompts'/f'{aid}_prompt.txt').read_text(encoding='utf8')
        # De-indexing the new prefix must reproduce the retained score rubric
        # exactly, apart from the named output-group header which has changed.
        units=[{'unit_id':u['unit_id'],'text':u['text']} for u in doc['units']]
        newprefix=prompt.split(INSTRUCTIONS)[0].replace('[LOSSLESS INDEXED MODEL_PROTOCOL; concatenate text fields in order]\n'+canonical(units),c['model_response'],1)
        oldprefix=old.split(SECTION3)[0].replace('- extraction.marker_dict, extraction.clearing_total_time_hours','- grounded_extraction source evidence records').replace('scores and extraction groups','scores and grounded_extraction groups').replace("and 'extraction'.","and 'grounded_extraction'.")
        require(newprefix==oldprefix,'ORIGINAL_SCORE_RUBRIC_CHANGED')
        require(prompt.endswith(baseline.parent.v2.reference_suffix(c)),'REFERENCE_SUFFIX_CHANGED')
        (OUT/'prompts'/f'{aid}_from_identity_v2.diff').write_text(''.join(difflib.unified_diff(old.splitlines(keepends=True),prompt.splitlines(keepends=True),fromfile=aid+'/identity_v2',tofile=aid+'/grounded_extraction_v4')),encoding='utf8')
        bound=len(prompt.encode('utf8'))+8192+256
        matrices.append({'anonymous_answer_id':aid,'question_id':c['question_id'],'case_id':c['case_id'],
            'opaque_source_id':doc['source_id'],'case_id_not_in_prompt':True,
            'question_sha256':c['question_sha256'],'answer_sha256':c['answer_sha256'],'source_document_sha256':sha(OUT/'source_documents'/f'{aid}.json'),
            'prompt_sha256':sha(p),'conservative_context_bound':bound,'fits_40960':bound<=40960,
            'configured_num_ctx':CONFIGURED_NUM_CTX,'fits_configured_context':bound<=CONFIGURED_NUM_CTX,
            'full_answer_reconstruction_equal':True,'original_score_rubric_equal_after_format_header_and_lossless_source_projection':True,
            'reference_context_unchanged':True,'reference_context_sha256':rawsha(baseline.parent.v2.reference_suffix(c)),
            'inventory_counts':dict(__import__('collections').Counter(x['kind'] for x in evidence_inventory(doc))),
            'scientific_labels_created':0})
    sourcepaths=[Path(__file__),baseline.OUT/'cases.json',baseline.OUT/'final_output_schema.json',baseline.OUT/'rubric_identity_preserved.txt',
        ROOT/'OEQ_run_grading_new.py',ROOT/'evaluator_integrity.py',ROOT/'models/Ollama_LLM.py',ROOT/'KnowledgeBase/method_fluro_compati.json',
        ROOT/'artifacts/cce_validation/judges/identity_stability_dev_v1/A01_variation_trace.json',
        ROOT/'artifacts/cce_validation/judges/identity_stability_dev_v1/A04_repeat_trace.json']
    optimization=ROOT/'artifacts/cce_validation/optimizer_20261010'
    sourcepaths += [ROOT/'scripts/cce_grounded_extraction_v2.py',optimization/'grounded_extraction_v2/plan.json',
        optimization/'grounded_development_v2/completion_summary.json',
        optimization/'grounded_v2_failure_diagnostics_v1/summary_5of5.json',
        optimization/'grounded_v2_failure_diagnostics_v1/intrinsic_identity_design.json',
        optimization/'grounded_v3_design_v1/input_audit.json',optimization/'grounded_v3_design_v1/counterexamples.json',
        optimization/'validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json']
    sourcepaths += sorted((optimization/'grounded_v2_failure_diagnostics_v1').glob('*addendum*.json'))
    sourcepaths += [ROOT/'scripts/cce_grounded_extraction_v3.py',optimization/'grounded_extraction_v3/plan.json',
        optimization/'grounded_development_v3/completion_summary.json',
        optimization/'grounded_v3_failure_diagnostics_v1/summary_5of5.json',
        optimization/'grounded_v3_failure_diagnostics_v1/source_ref_usage_5of5.json',
        optimization/'grounded_v3_failure_diagnostics_v1/methodological_addendum_v1/addendum.json',
        optimization/'grounded_v4_design_v1/name_contract_review/review_summary.json',
        optimization/'grounded_v4_design_v1/name_contract_review/name_counterexample_spec.json',
        optimization/'grounded_v4_design_v1/name_contract_review/graph_counterexample_spec.json',
        optimization/'grounded_v4_design_v1/name_contract_review/GRAPH_DIRECTION_REVIEW.md',
        optimization/'grounded_v4_fact_review_design_v1/name_boundary_followup.json']
    # Only the already exposed controls: no sealed confirmation or holdout.
    controls_path=ROOT/'artifacts/cce_validation/judges/controls_contract_v2/cases.json'
    controls=read(controls_path)['cases'];require(len(controls)==21,'FIXED_CONTROL_FULLTEXT_COUNT')
    controls_context=[]
    for c in controls:
        doc=document(c['model_response'],source_id_for_case(c));prompt=make_prompt(c,doc)
        require(doc['text']==c['model_response'] and ''.join(u['text'] for u in doc['units'])==c['model_response'],'CONTROL_SOURCE_RECONSTRUCTION')
        require(prompt.endswith(baseline.parent.v2.reference_suffix(c)),'CONTROL_REFERENCE_SUFFIX_CHANGED')
        require(c['case_id'] not in prompt,'CONTROL_METADATA_LEAK')
        bound=len(prompt.encode('utf8'))+8192+256
        controls_context.append({'case_id':c['case_id'],'question_id':c['question_id'],
            'answer_sha256':rawsha(c['model_response']),'question_sha256':rawsha(c['specific_question']),
            'prompt_text_sha256':rawsha(prompt),'conservative_context_bound':bound,'fits_40960':bound<=40960,
            'configured_num_ctx':CONFIGURED_NUM_CTX,'fits_configured_context':bound<=CONFIGURED_NUM_CTX,
            'full_original_text_and_reference_suffix_preserved':True})
    save(OUT/'control_context_audit.json',{'status':'draft_offline','records':controls_context,
        'count':21,'all_fit':all(x['fits_configured_context'] for x in controls_context),'all_fit_40960_diagnostic':all(x['fits_40960'] for x in controls_context),'new_model_requests':0,
        'cases_sha256':sha(controls_path),'original_scoring_or_control_results_modified':False})
    sourcepaths.append(controls_path)
    plan={'status':'draft_implementation_not_frozen_not_ready_for_generation','version':VERSION,'matrix':matrices,
        'configured_num_ctx':CONFIGURED_NUM_CTX,'previous_num_ctx':40960,'max_output_tokens':8192,
        'context_setting_change':'Root-authorized before v4 freeze/generation: shared 98304 context for dev/E2/E4/automatic confirmation so the frozen full same-method reference pool and scientific conditions fit. Original 40960 diagnostics remain; no source text is trimmed. Model native capacity/configuration evidence is bound by the separate runner.',
        'planned_call_shape':'one_joint_payload_per_answer; no separate extraction/judge call','planned_development_answers':5,
        'new_judge_requests':0,'old_scores_and_human_package_modified':False,'no_heldout_scientific_records_read':True,
        'scores_schema_byte_equivalent_to_original_subtree':schema_value['properties']['scores']==read(baseline.OUT/'final_output_schema.json')['properties']['scores'],
        'EGES_function_and_knowledge_base_changed':False,'proposed_model':'Same local 27B/Q8 model as model_probe_v1 and grounded_development_v2; actual model identity/settings must be frozen by the separate v4 development runner before calls',
        'ollama_format_schema_supported_by_existing_transport':True,'schema_decoder_is_not_a_semantic_or_duplicate_key_guarantee':True,
        'schema_transport':'Complete schema object supplied via Ollama format; prompt omits the redundant type catalog; complete schema is unchanged in transport. No completed output examples.',
        'source_id_policy':'SRC_ + SHA256(question + NUL + full answer)[:24]; no model name or condition label. Real case identity remains in external matrix. Equal question/fulltext across batches has equal source ID.',
        'score_evidence_contract':'Exactly five distinct direct metrics. Answer spans resolved against the original answer; observed/mixed require a span, absence requires no span. Rubric correctness remains unverified.',
        'time_policy_delta':'Source-exact unique arithmetic; unknown overnight stays NA. The old 8-hour convention is a separate comparison. Conditional/future operations retain separate initial-scope bounds and an explicitly conditional envelope; no unqualified endpoint is silently selected. Excluded non-clearing schedule cues do not invalidate core time.',
        'target_policy_delta':'Nullable unknown targets; entity type distinct from relationship role; exact relation-local mention links preserve primary/raw spans. Unsupported semantic claims become rejected projection/component warnings rather than losing unrelated direct/method/time components. JSON, false spans and dangling nonnull IDs remain hard errors.',
        'coverage_policy_delta':'Repeated exact full-name mentions can link to an existing used entity as identity-only coverage. Alternative/negated/differently qualified mentions require separate classification or unresolved evidence; no target/new usage is inferred.',
        'time_binding_policy_delta':'A unique same-source-record action/duration may bind adjacent fields. Ambiguous records retain literal numbers but are not aggregated. Initial timeline is derived from declared phase/scope with original proposal/diff retained. Unverified precedence claims are not dependencies.',
        'RI_policy_delta':'An explicitly RI-labelled unique number is parsed with source trace; percentages, multiple values and unlabelled prose are not accepted. No duration-prefix repair was added.',
        'v3_bundle':['Shared SourceRef schema: exact raw span or current-source candidate ID; no per-document enum.',
            'Complete relation-object anyOf rejects explicit/null combinations in the schema as well as the application.',
            'Generic source metadata word leads, not a closed biological name list.',
            'Strong dimensional contexts and explicit recurrence intervals remain audited non-additive source records.',
            'Core time coverage is separate from whole-protocol coverage; source action recall and all missing-core gates remain.',
            'Labeling-preparation phase requires a source heading and no literal core-function conflict.',
            'Mentioned usage requires source capability/example cues and cannot erase a separate affirmative chosen/used identity.',
            'Typed source-declared intrinsic identity can explicitly change legacy input via same-name serialization; old functions and KB are unchanged.'],
        'v4_bundle':['Literal method/entity names are separate from supporting evidence. The adapter derives a unique exact narrow span and preserves the wider raw support.',
            'UnitRef binds full source-unit text without CRLF or Markdown normalization; precise numerical references remain mandatory for durations and RI values.',
            'Field/assertion and qualifier/suffix guards remain hard checks. Exact binding is separate from name atomicity: composite-list syntax is retained unresolved and excluded from method/entity/relation/intrinsic projection, while unknown punctuation names are not rejected solely for punctuation.',
            'Spatial ND adjective/compound contexts and rationale clearing-process nouns are audited without changing the source text or true day durations.',
            'Incoming target edges are not outgoing legacy-key conflicts. Native source declarations, capability/negative/conditional limits and literal-key collisions remain separate gates.',
            'Mentioned capability/example usage includes like/optimized-to but cannot erase affirmative selected occurrences.',
            'Core coverage remains independent of whole coverage, with no automatic partial-to-complete overwrite.',
            'Explicit precedence requires shared-unit evidence; adjacency is insufficient and model graphs remain unused for arithmetic.',
            'Duplicate output-type catalog removed only from prompt; full schema still sent in decoder format.'],
        'control_context_audit_sha256':sha(OUT/'control_context_audit.json'),
        'not_pure_format_ablation':True,'prepare_or_final_freeze_executed':False,
        'known_limits':['Lexical candidate inventory is not a completeness gold standard.','Phase assignment and source-order serial schedule are declared provisional conventions.','Nested parallel subgroups are not supported; keep unknown rather than flatten.','The model may still omit or misclassify valid spans; this contract makes evidence auditable, not scientifically true.','Legacy marker_dict cannot represent all entity graphs; do not treat partial projection as complete EGES.'],
        'input_sha256':{str(p.resolve()):sha(p) for p in sourcepaths},'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'draft_manifest.json',plan)
    require(all(r['fits_configured_context'] for r in matrices),'CONSERVATIVE_CONTEXT_BOUND_EXCEEDED')
    require(all(r['fits_configured_context'] for r in controls_context),'CONTROL_CONTEXT_BOUND_EXCEEDED')
    text='''# Source-bound extraction v4: DRAFT implementation

This draft contains **no model generation, final freeze, or expert labels**. It uses the unchanged five original development answers. No sealed confirmation or holdout scientific output was used. It is a bundled policy proposal; typed intrinsic identity can change the legacy extraction input even though the old numeric functions and KB remain unchanged.

The inherited v3 bundle adds exact RawSpan-or-CandidateRef references, schema-level explicit/non-null relationship branches, generic metadata-word leads, additional recognized label fields, preserved dimensional/interval roles, a source-supported labeling-preparation phase, and independent core time coverage. Unknown core phase/scope and omitted action/duration evidence remain unresolved. The typed intrinsic signal is not a self-binding edge or proof of experimental preservation; external relations and negated/capability/alternative statements cannot be silently overwritten. Original small-molecule key-only serialization remains valid and does not require an invented null-target relationship. This is not a pure formatting ablation.

V4 separates `literal_name` from `supporting_evidence`. The latter accepts an exact RawSpan, a current-source CandidateRef, or a full UnitRef. The former must have a unique complete literal occurrence inside the supplied support. The adapter retains both the wider support and the derived narrow `resolved.name` span. Field/assertion and qualifier guards remain hard checks, but literal binding is distinct from `name_binding.atomicity`: slash/semicolon/separated-plus or comma with list context/parallel uppercase identities remains a retained unresolved composite, not a projected method/marker/relationship endpoint/native identity. A comma by itself never hard-rejects an unknown name; ordinary unknown multiword and chemical punctuation names remain provisional. These syntax checks cannot certify name semantics. Numerical duration and RI references cannot use UnitRef. Source bytes and provider bytes are never repaired.

Root additionally authorized `num_ctx=98304` before v4 freeze or generation, shared across development, E2/E4 and automatic confirmation, to accommodate the complete pre-unsealing reference catalog and scientific conditions. This is a declared configuration change in the bundle, not output-dependent tuning. The original 40960-byte conservative diagnostics remain alongside `fits_configured_context`; the model, temperature and 8192 output limit remain separately frozen by the runner. None of these offline checks validates model performance.

Incoming dye-to-target edges no longer automatically conflict with typed native identity; outgoing claims on the same literal legacy key, conflicting identity records, conditions, negation and capability evidence remain distinct blockers. The recognized `like`/`optimized-to` capability scope cannot establish native use or erase separately selected names. Whole and core coverage remain independent model claims, and the adapter never changes core partial into complete. Spatial adjective phrases and a rationale noun phrase such as “and clearing process” have explicit bounded lexical handling. Adjacent numbered steps need no precedence edge; only explicit same-unit evidence is diagnosed, and no model edge drives arithmetic.

One joint response preserves the original scores schema and adds five score-evidence records plus entity, relationship, operation and time evidence arrays. Every quoted span resolves to the lossless original-answer index. The source text, question, reference suffix, old score rubric and fixed evidence files are hash-bound. The old EGES functions and lookup tables remain untouched.

`convert(raw, document(answer, source_id_for_case(case)))` uses the original strict duplicate-key parser, checks the new contract, and returns `legacy_runner_content` plus an explicit source-audit/conversion sidecar. The opaque ID hashes the exact question, a NUL separator and full answer; it exposes no case/model/condition name. The original provider raw content is retained separately; this conversion must never be represented as raw identity. `legacy_runner_payload.scores` is exactly the returned scores subtree. The downstream runner must save both raw EGES and any distinct component-availability gate.

Entity identity and relation confidence differ: valid full names do not imply a target assignment. Co-occurrence alone is not projected. A relation-local exact complete name may bind the same identity as a header mention while preserving both original offsets. Unknown targets can be null. Entity kind and relation role are separate. A rejected semantic relationship is retained with `projection_allowed=false`; it no longer makes unrelated valid fields a whole-case structural failure. A fake span, invalid JSON or dangling non-null ID still fails. Missing relationships leave the old empty-target representation plus an explicit partial-projection flag. That flag is an audit warning, not a command to erase every partial EGES result: a source-supported valid known zero can still determine the old nullable-min label component. Unknown components must not erase unaffected known components.

Durations are parsed and aggregated by code, conditional on the supplied phase and scheduling classifications. A short action quote can bind an adjacent duration only in a single source record passing the unique action/duration guard. A quoted whole line containing multiple actions or durations is not proof of unique assignment. These are narrow lexical guards, not full semantic parsing. The program derives initial timeline membership from declared phase/scope and preserves the model proposal/differences; unknown classifications cannot be discarded to produce a finite complete total. Backward/cyclic model precedence proposals are retained as diagnostics and do not control aggregation. Ranges, missing durations, unspecified overnight, ambiguity and total/sum conflicts remain nullable with known values and causes. The old overnight=8 h convention is retained only in a separate comparison. Nested parallel groups are not flattened. Source-order summation is a declared provisional convention, not a scientific gold schedule. RI-labelled unique numbers are source-parsed; no duration prefix repair is added.

Coverage candidates enumerate durations, numeric/name leads, and existing knowledge-base names. They are recall prompts and auditable omission checks, not scientific labels or a proof of completeness. Alternative/negated names must be retained with their actual status rather than treated as all simultaneously required. Exact spans do not establish correct entity type, phase, RI role, scoring judgment or complete scientific validity.

The complete JSON Schema belongs in the actual Ollama `format` object. The prompt omits the duplicated shape catalog; the complete decoder schema still defines every output field. The isolated synthetic transport probe replaces HTTP with an in-memory stub and verifies the full schema is serialized. It does not validate real generation behavior.

Reproduce offline from repository root:

```powershell
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_grounded_extraction_v4.py draft
```

The `synthetic_only/` payload/source pair is for runner integration tests only. It is unrelated to any natural answer or expert review. `draft_manifest.json` is not a generation plan. The actual generation wrapper is separate; root review and independent checks must precede final freeze and new calls.

After root review, the offline `prepare` action validates the inspected draft and writes `plan.json`, `schema.json`, source/prompt artifacts and fresh `software_probes.json` to the parent v4 directory. It performs no provider requests. `self-check` may then replay the isolated probes against that prepared directory. The separate development runner must still pass its own independent review and generation gate.
'''
    (OUT/'README.md').write_text(text,encoding='utf8')
    print(canonical({'status':plan['status'],'new_requests':0,'context_bounds':[r['conservative_context_bound'] for r in matrices],'all_fit':all(r['fits_40960'] for r in matrices)}))

def draft():
    global OUT
    OUT=OUT/'draft';_build_draft();self_check()

def prepare():
    """Offline promotion of an already inspected draft; never calls a provider."""
    if (OUT/'plan.json').exists():
        plan=read(OUT/'plan.json')
        for path,expected in plan['input_sha256'].items():require(sha(path)==expected,'FROZEN_PLAN_INPUT_CHANGED:'+path)
        for relative,expected in plan['frozen_artifact_sha256'].items():require(sha(OUT/relative)==expected,'FROZEN_ARTIFACT_CHANGED:'+relative)
        check=read(OUT/'software_probes.json')
        require(check['status']=='pass' and check['script_sha256']==sha(__file__) and check['plan_sha256']==sha(OUT/'plan.json'),'FROZEN_PROBES_STALE')
        print(canonical({'status':'frozen_plan_reused','new_requests':0}));return
    source=OUT/'draft';manifest=read(source/'draft_manifest.json');probes=read(source/'software_probes.json')
    require(manifest['status']=='draft_implementation_not_frozen_not_ready_for_generation','NOT_AN_INSPECTABLE_DRAFT')
    for path,expected in manifest['input_sha256'].items():require(sha(path)==expected,'DRAFT_INPUT_CHANGED:'+path)
    require(probes['status']=='pass' and probes['script_sha256']==sha(__file__) and probes['schema_sha256']==sha(source/'schema.json') and probes['draft_manifest_sha256']==sha(source/'draft_manifest.json'),'DRAFT_PROBES_STALE')
    require(manifest['configured_num_ctx']==CONFIGURED_NUM_CTX and all(r['fits_configured_context'] for r in manifest['matrix']),'DRAFT_CONTEXT_EXCEEDED')
    copied={}
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.name in ['draft_manifest.json','software_probes.json']:continue
        # Synthetic output paths contain draft provenance and remain there. A
        # fresh isolated self-check below produces the frozen-directory copies.
        relative=path.relative_to(source)
        if relative.parts[0]=='synthetic_only':continue
        destination=OUT/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        contents=path.read_bytes()
        if relative==Path('README.md'):
            contents=(b'# Offline prepared contract; generation remains separately gated\n\n'
                b'Preparation status and exact artifact hashes are in plan.json. The preserved draft description follows; no model request or scientific acceptance is implied.\n\n'+contents)
        require(not destination.exists() or destination.read_bytes()==contents,'EXISTING_FREEZE_DESTINATION_CONFLICT:'+str(destination))
        destination.write_bytes(contents);copied[str(relative)]=sha(destination)
    plan=copy.deepcopy(manifest);plan.update({'status':'frozen_offline_contract_pending_independent_runner_gate',
        'prepare_or_final_freeze_executed':True,'draft_manifest_sha256':sha(source/'draft_manifest.json'),
        'draft_probes_sha256':sha(source/'software_probes.json'),'draft_actual_command':manifest['actual_command'],
        'actual_command':[sys.executable,*sys.argv],'frozen_artifact_sha256':copied,
        'root_generation_approval_or_scientific_acceptance_implied':False})
    save(OUT/'plan.json',plan);self_check()
    save(OUT/'preparation.json',{'actual_command':[sys.executable,*sys.argv],'status':'prepared_offline',
        'plan_sha256':sha(OUT/'plan.json'),'script_sha256':sha(__file__),'new_model_requests':0,
        'root_runner_generation_gate_still_required':True})
    print(canonical({'status':plan['status'],'plan_sha256':sha(OUT/'plan.json'),'new_requests':0}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['draft','prepare','self-check','convert']);p.add_argument('--source-document',type=Path);p.add_argument('--raw-response',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.action=='draft':draft()
    elif a.action=='prepare':prepare()
    elif a.action=='self-check':
        require((OUT/'plan.json').exists(),'SELF_CHECK_REQUIRES_OFFLINE_PREPARE');self_check()
    else:
        require(a.source_document and a.raw_response and a.out,'CONVERT_REQUIRES_EXPLICIT_FILES');save(a.out,convert(a.raw_response.read_bytes().decode('utf8'),read(a.source_document)))
if __name__=='__main__':main()
