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
OUT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_extraction_v2'
VERSION='source_bound_extraction_v2'
SECTION3='3. 荧光兼容性与实验数据提取 Prompt (Data Extraction for Fluorescence Compatibility)'
INCLUDE={'delipidation','decalcification','decolorization','ri_matching','clearing_treatment','reagent_transition_wash'}
EXCLUDE={'fixation','antibody_incubation','staining','imaging','routine_wash','storage'}
SPAN={'type':'object','additionalProperties':False,'required':['unit_id','quote','occurrence'],
      'properties':{'unit_id':{'type':'string'},'quote':{'type':'string','minLength':1},'occurrence':{'type':'integer','minimum':0}}}
NULLSPAN={'anyOf':[SPAN,{'type':'null'}]}
def obj(properties):return {'type':'object','additionalProperties':False,'required':list(properties),'properties':properties}
def arr(items):return {'type':'array','items':items}
def enum(*values):return {'type':'string','enum':list(values)}
TEXT={'type':'string'}
ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]*$'}
DIRECT=('c_param','co_order','co_method','co_param','co_chem')

def schema():
    old=json.loads((baseline.OUT/'final_output_schema.json').read_text(encoding='utf8'))
    ground=obj({'schema_version':{'const':VERSION},'source_id':TEXT,
        'method_mentions':arr(obj({'id':ID,'name':SPAN,'usage':enum('selected','mentioned','alternative','negated','unknown')})),
        'entities':arr(obj({'id':ID,'name':SPAN,'kind':enum('fluorophore','fluorescent_protein','target','antibody','unknown'),
                            'usage':enum('used','alternative','negated','unknown')})),
        'relations':arr(obj({'id':ID,'fluor_entity_id':ID,'target_entity_id':{'anyOf':[ID,{'type':'null'}]},'evidence':SPAN,
                            'status':enum('explicit','ambiguous','unknown')})),
        'operations':arr(obj({'id':ID,'operation':SPAN,'phase':enum(*(sorted(INCLUDE|EXCLUDE)+['unknown'])),
                              'duration':NULLSPAN,'repeat_evidence':NULLSPAN,
                              'execution_scope':enum('initial','conditional_or_future','unknown'),
                              'condition_evidence':NULLSPAN})),
        'timeline':obj({'mode':enum('serial','parallel','alternative','unknown'),'operation_ids':arr(ID),
                        'relation_evidence':NULLSPAN,'completeness':enum('complete','partial','unknown')}),
        'precedence_edges':arr(obj({'before_id':ID,'after_id':ID,'evidence':SPAN})),
        'total_time_claims':arr(obj({'id':ID,'duration':SPAN,'scope':enum('clearing_total','whole_protocol','unknown')})),
        'ri_mentions':arr(obj({'id':ID,'value':SPAN,'role':enum('reagent_final','sample_target','unknown')})),
        'coverage':obj({'entities':enum('complete','partial','unknown'),'time_operations':enum('complete','partial','unknown'),
                        'unresolved':arr(obj({'evidence':SPAN,'reason':TEXT}))})})
    evidence=arr(obj({'metric':enum(*DIRECT),'answer_spans':arr(SPAN),
        'basis':enum('observed','absence','insufficient','mixed'),
        'rubric_basis':{'type':'string','minLength':1}}))
    return obj({'scores':old['properties']['scores'],'score_evidence':evidence,'grounded_extraction':ground})

def schema_catalog(spec):
    """Compact shape documentation; the full schema travels in Ollama format.

    This is generated from the actual decoder schema, not a populated example.
    Required keys, enums and nullability survive the compact representation.
    """
    if spec==SPAN:return 'Span'
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

def resolve(ref,doc):
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
            records.append({'candidate_id':f'C{len(records)+1:04d}','kind':category,
                'span':resolve({'unit_id':unit['unit_id'],'quote':quote,'occurrence':occ},doc),
                'role':'recall_candidate_not_scientific_gold'})
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

def local_name_mentions(name,evidence,doc):
    results=[]
    for match in re.finditer(re.escape(name),evidence['quote']):
        a=evidence['start']+match.start();b=evidence['start']+match.end()
        left=a>0 and bool(re.match(r'\w',doc['text'][a-1])) and bool(re.match(r'\w',name[0]))
        right=b<len(doc['text']) and bool(re.match(r'\w',doc['text'][b])) and bool(re.match(r'\w',name[-1]))
        anti=bool(re.search(r'anti[- ]$',doc['text'][max(0,a-8):a],re.I)) and not name.lower().startswith('anti')
        suffix=bool(re.match(r'^\s+\d{2,4}\b(?!\s*[%％])',doc['text'][b:evidence['context_end']]))
        results.append({'start':a,'end':b,'quote':doc['text'][a:b],'answer_sha256':doc['answer_sha256'],
            'same_complete_literal':not(left or right or anti or suffix),
            'clipped_boundary':left or right,'additional_anti_qualifier':anti,'additional_numeric_suffix':suffix})
    return results

def relation_policy(f,t,evidence,entities):
    # Identity binding and semantic relationship evidence are different gates.
    ok,why=lexical_relation(f,t,evidence,entities)
    if ok:return ok,why
    if why=='negation_or_alternative_or_inferred_assignment':return False,why
    text=evidence['quote'].strip();ff,tt=re.escape(f),re.escape(t)
    summary=bool(re.search(r'Fluorescen(?:t|ce)\s+(?:Label|Marker)|荧光标记',evidence['context'],re.I))
    pair=bool(re.fullmatch(r'(?:'+tt+r'(?:\s*\([^)]*\))?\s*\+\s*'+ff+r'|'+ff+r'\s*\+\s*'+tt+r')',text))
    if summary and pair:return True,'explicit_single_pair_in_label_summary_not_expert_confirmed'
    # A use/purpose clause can explicitly name an anatomical target without
    # asserting a chemical conjugation. Do not infer a target from cooccurrence.
    purpose=bool(re.search(ff+r'[^.;]*\b(?:for|to label|labels)\s+'+tt+r'(?:\b|$)',text,re.I))
    if purpose:return True,'explicit_named_use_or_label_purpose_not_expert_confirmed'
    return False,'relationship_not_mechanically_explicit'

def record_action_heads(text):
    # Direct/nominal action heads only; a purpose phrase is not another order.
    actions=[]
    pattern=re.compile(r'(?:^|[;.]\s+|\b(?:and|then)\s+)(?:\d+(?:\.\d+)*[.)]?\s*)?(incubat(?:ion|e|ing)|stor(?:age|e|ing)|wash(?:ing)?|rins(?:e|ing)|transfer(?:ring)?|immers(?:ion|e)|soak(?:ing)?|mount(?:ing)?|equilibrat(?:ion|e|ing)|dehydrat(?:ion|e|ing)|clear(?:ing)?)\b',re.I)
    for match in pattern.finditer(text):
        prefix=text[:match.start()]
        if match[1].lower().endswith('ing') and re.search(r'\bfor\b[^.;]*$',prefix,re.I):continue
        actions.append(match[1])
    return actions

def record_binding(operation,value,doc):
    """A lexical binding guard, never semantic operation-assignment proof."""
    unit=next(u for u in doc['units'] if u['unit_id']==operation['unit_id'])
    envelope={'unit_id':unit['unit_id'],'start':unit['start'],'end':unit['end'],'text_sha256':rawsha(unit['text'])}
    contained=operation['start']<=value['start'] and value['end']<=operation['end']
    if contained:
        durations=list(DURATION.finditer(operation['quote']));actions=record_action_heads(operation['quote'])
        valid=len(durations)==1 and len(actions)<=1
        return {'valid':valid,'mode':'inside_operation_quote' if valid else 'ambiguous_multioperation_or_multiduration_quote',
            'record_envelope':envelope,'quoted_duration_count':len(durations),'quoted_action_heads':actions,
            'semantic_assignment_verified':False,'guard_scope':'literal duration count and narrow action-head enumeration, not exhaustive NLP'}
    if value['unit_id']!=operation['unit_id']:return {'valid':False,'mode':'different_source_units','record_envelope':envelope}
    durations=list(DURATION.finditer(unit['text']));actions=record_action_heads(unit['text'])
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

def audit_payload(payload,doc):
    require(rawsha(doc['text'])==doc['answer_sha256'] and document(doc['text'],doc['source_id'])['units']==doc['units'],'DOCUMENT_HASH_OR_UNIT_BINDING')
    validate_shape(payload,schema());integrity.validate_score_proposals(payload['scores'])
    g=payload['grounded_extraction'];require(g['source_id']==doc['source_id'],'SOURCE_ID_MISMATCH')
    score_evidence=copy.deepcopy(payload['score_evidence'])
    require(len(score_evidence)==len(DIRECT) and {e['metric'] for e in score_evidence}==set(DIRECT),'SCORE_EVIDENCE_EXACT_FIVE_UNIQUE')
    for e in score_evidence:
        e['answer_spans']=[resolve(s,doc) for s in e['answer_spans']]
        if e['basis'] in ['observed','mixed']:require(bool(e['answer_spans']),'OBSERVED_SCORE_EVIDENCE_REQUIRES_SPAN')
        if e['basis']=='absence':require(not e['answer_spans'],'ABSENCE_EVIDENCE_IS_NOT_A_QUOTED_PRESENT_FACT')
        require(bool(e['rubric_basis'].strip()),'EMPTY_SCORE_RUBRIC_BASIS')
    result=copy.deepcopy(g);allids=set();used_spans=[]
    def resolved(ref):
        value=resolve(ref,doc);used_spans.append(value);return value
    for group,fields in [('method_mentions',['name']),('entities',['name']),('relations',['evidence']),
        ('operations',['operation','duration','repeat_evidence','condition_evidence']),('total_time_claims',['duration']),('ri_mentions',['value'])]:
        for r in result[group]:
            require(r['id'] not in allids,'DUPLICATE_RECORD_ID');allids.add(r['id'])
            for field in fields:
                if r[field] is not None:r[field]=resolved(r[field])
            if 'name' in r:
                name=r['name'];require(name['quote']==name['quote'].strip(),'NAME_WHITESPACE_NOT_IDENTITY')
                require(not (name['start']>0 and re.match(r'\w',doc['text'][name['start']-1]) and re.match(r'\w',name['quote'][0])),'CLIPPED_NAME_START')
                require(not (name['end']<len(doc['text']) and re.match(r'\w',doc['text'][name['end']]) and re.match(r'\w',name['quote'][-1])),'CLIPPED_NAME_END')
                trailing=doc['text'][name['end']:name['context_end']]
                require(not re.match(r'^\s+\d{2,4}\b(?!\s*[%％])',trailing),'OMITTED_DISTINGUISHING_NUMERIC_SUFFIX')
    if result['timeline']['relation_evidence'] is not None:result['timeline']['relation_evidence']=resolved(result['timeline']['relation_evidence'])
    for r in result['coverage']['unresolved']:r['evidence']=resolved(r['evidence'])
    entities={e['id']:e for e in result['entities']};ops={o['id']:o for o in result['operations']}
    for r in result['relations']:
        require(r['fluor_entity_id'] in entities and (r['target_entity_id'] is None or r['target_entity_id'] in entities),'RELATION_DANGLING_ENTITY')
        require(r['target_entity_id'] is not None or r['status'] in ['unknown','ambiguous'],'EXPLICIT_RELATION_REQUIRES_TARGET')
        f=entities[r['fluor_entity_id']];t=entities[r['target_entity_id']] if r['target_entity_id'] is not None else None
        mentions={'fluor':local_name_mentions(f['name']['quote'],r['evidence'],doc),
                  'target':local_name_mentions(t['name']['quote'],r['evidence'],doc) if t else []}
        r['relation_local_mentions']=mentions;r['primary_entity_spans_preserved']=True
        unique=all(sum(v['same_complete_literal'] for v in mentions[k])==1 for k in ['fluor','target'])
        if t is None:ok,why=False,'unknown_target_endpoint_not_projected'
        elif not unique:ok,why=False,'complete_endpoint_identity_absent_or_ambiguous_in_relation_evidence'
        elif f['kind'] not in ['fluorophore','fluorescent_protein']:ok,why=False,'label_endpoint_kind_unresolved'
        elif f['id']==t['id']:ok,why=False,'self_target_identity_not_supported'
        else:ok,why=relation_policy(f['name']['quote'],t['name']['quote'],r['evidence'],result['entities'])
        r['projection_allowed']=r['status']=='explicit' and ok;r['mechanical_relation_state']=why
        r['entity_type_and_relation_role_distinct']=True
        r['unsupported_claim_retained_not_repaired']=r['status']=='explicit' and not r['projection_allowed']
    duration_spans=[]
    for o in result['operations']:
        if o['duration']:
            d=o['duration'];op=o['operation']
            binding=record_binding(op,d,doc);o['duration_binding']=binding
            key=(d['start'],d['end']);require(key not in duration_spans,'REUSED_DURATION_DOUBLE_COUNT');duration_spans.append(key)
            literal=duration_value(d['quote']);o['raw_literal_parsed_duration']=literal
            o['parsed_duration']=literal if binding['valid'] else {'state':'unresolved_operation_record_binding','bounds_hours':None,'unique_hours':None}
            o['legacy_overnight_comparison']=duration_value(d['quote'],8)
        else:o['parsed_duration']={'state':'missing','bounds_hours':None,'unique_hours':None}
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
        'model_edges_used_for_aggregation':False,'program_uses_declared_schedule_and_source_order_convention':True}
    inventory=evidence_inventory(doc)
    substantive=[s for o in result['operations'] for s in [o['duration']] if s]+[t['duration'] for t in result['total_time_claims']]
    unresolved=[r['evidence'] for r in result['coverage']['unresolved']]
    for r in inventory:
        s=r['span']
        cross_identity=exact_identity_mention_coverage(r,result['entities'],doc) if r['kind'] in ['numbered_name_lead','known_marker_name_lead'] else None
        if any(v['start']<=s['start'] and s['end']<=v['end'] for v in substantive if r['kind']=='duration'):state='covered_time_evidence'
        elif any(v['start']<=s['start'] and s['end']<=v['end'] for v in unresolved):state='explicitly_unresolved'
        elif r['kind'] in ['numbered_name_lead','known_marker_name_lead'] and any(v['name']['start']<=s['start'] and s['end']<=v['name']['end'] for v in result['entities']):
            matching=[v for v in result['entities'] if v['name']['start']<=s['start'] and s['end']<=v['name']['end']]
            state='covered_entity_name' if any(v['usage']=='used' for v in matching) else 'classified_entity_nonused_or_unknown'
        elif cross_identity and cross_identity['covered']:
            state='covered_repeated_exact_entity_identity';r['cross_mention_identity_coverage']=cross_identity
        elif r['kind']=='known_method_name_lead' and any(v['name']['start']<=s['start'] and s['end']<=v['name']['end'] for v in result['method_mentions']):state='classified_method_name'
        elif r['kind'] not in ['duration','numbered_name_lead','known_marker_name_lead','known_method_name_lead'] and any(v['start']<=s['start'] and s['end']<=v['end'] for v in used_spans):state='covered_supplied_span'
        else:state='uncovered_candidate'
        r['coverage_state']=state
    return {'source_binding':{'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256']},'resolved':result,
            'score_evidence':score_evidence,'score_evidence_semantic_validity':'not_certified; source quotes do not establish correct rubric application',
            'inventory':inventory,'software_span_valid':True,'scientific_completeness_certified':False}

def compute_time(audit):
    g=audit['resolved'];ops=g['operations'];core=[o for o in ops if o['phase'] in INCLUDE]
    inc=[o for o in core if o['execution_scope']=='initial'];conditional=[o for o in core if o['execution_scope']=='conditional_or_future'];issues=[]
    if any(o['phase']=='unknown' for o in ops):issues.append('unresolved_phase_scope')
    if any(o['execution_scope']=='unknown' for o in core):issues.append('unresolved_execution_scope')
    if any(o['scope_gate']['conditional_cue_detected'] for o in inc):issues.append('initial_operation_contains_conditional_scope_cue')
    if any(not o['scope_gate']['conditional_scope_supported'] for o in conditional):issues.append('conditional_scope_lacks_explicit_source_evidence')
    if conditional:issues.append('conditional_operations_require_endpoint_resolution')
    if set(g['timeline']['operation_ids'])!={o['id'] for o in inc}:issues.append('timeline_does_not_cover_exact_included_operations')
    if g['coverage']['time_operations']!='complete' or g['timeline']['completeness']!='complete':issues.append('reported_operation_coverage_incomplete')
    if any(r['kind']=='duration' and r['coverage_state']!='covered_time_evidence' for r in audit['inventory']):issues.append('source_duration_candidates_not_all_classified')
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
            'initial_plus_at_most_one_conditional_execution_envelope_hours':endpoint_envelope,
            'endpoint_scope':'Initial scope is reported separately. Presence of conditional/future core operations prevents choosing an unqualified legacy total. The optional envelope assumes at most one listed conditional execution; repeated maintenance may have no finite upper bound.',
            'bounds_scope':'Conditional on supplied phase/schedule classification; null upper bound means no finite source-supported upper bound.',
            'serial_convention':'Document-order operations are provisionally summed only if no branch/overlap cue is detected; semantic schedule is not certified.',
            'overnight_policy':'No source-exact numeric duration inferred; original 8h convention retained only per-operation comparison.',
            'scientific_total_confirmed':False}

def doc_context(audit):return '\n'.join(o['operation']['context'] for o in audit['resolved']['operations'])

def project_legacy(audit):
    g=audit['resolved'];time=compute_time(audit);issues=[];mapping={};conversion=[]
    selected=[m for m in g['method_mentions'] if m['usage']=='selected'];names={m['name']['quote'] for m in selected}
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
    for name in sorted({e['name']['quote'] for e in g['entities'] if e['kind'] in ['fluorophore','fluorescent_protein'] and e['usage']=='used'}):
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
    targetids={e['id'] for e in g['entities'] if e['kind'] in ['target','antibody'] and e['usage']=='used'}
    mappedtargets={r['target_entity_id'] for r in g['relations'] if r['projection_allowed']}
    if targetids-mappedtargets:issues.append('unmapped_reported_target_identities')
    if any(e['kind']=='unknown' and e['usage'] in ['used','unknown'] for e in g['entities']):issues.append('unresolved_entity_kind')
    if any(e['usage']=='unknown' for e in g['entities']):issues.append('unresolved_entity_usage')
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
    label_ready=not any('target' in s or 'relationship' in s or 'entity' in s or 'numbered_name' in s for s in issues)
    return {'extraction':extraction,'time_calculation':time,'entity_conversion':conversion,'method_selection_checks':method_checks,'projection_issues':issues,
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
       'method_mentions':[{'id':'method1','name':sp('SYNTHETIC_METHOD'),'usage':'selected'}],
       'entities':[{'id':'fluor1','name':sp('SYNTHETIC_FLUOR_101'),'kind':'fluorophore','usage':'used'},
                   {'id':'target1','name':sp('SYNTHETIC_TARGET'),'kind':'target','usage':'used'}],
       'relations':[{'id':'relation1','fluor_entity_id':'fluor1','target_entity_id':'target1','evidence':sp(relation_text),'status':relation}],
       'operations':operations,'timeline':{'mode':mode,'operation_ids':['op1','op2'],'relation_evidence':sp(cue),'completeness':'complete'},
       'precedence_edges':[],'total_time_claims':[],'ri_mentions':[],
       'coverage':{'entities':'complete','time_operations':'complete','unresolved':[]}}
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
    """Meaningful isolated contract checks; no network or natural labels."""
    import collections
    checks=[]
    def check(name,condition=True):
        require(bool(condition),'SOFTWARE_PROBE_FAILED:'+name)
        checks.append({'fixture':name,'status':'pass','synthetic_only':True})
    def run(doc,payload):return convert(canonical(payload),doc)
    def reject(name,mutate,code):
        doc,payload=synthetic_fixture();mutate(doc,payload)
        try:run(doc,payload)
        except (ValueError,integrity.JudgeFormatError) as exc:
            require(code in str(exc),'WRONG_FAILURE:'+name+':'+str(exc))
            checks.append({'fixture':name,'status':'rejected_as_expected','code':str(exc),'synthetic_only':True})
        else:raise ValueError('UNEXPECTED_ACCEPTANCE:'+name)
    def append(doc,line):return document(doc['text']+line+'\n',doc['source_id'])
    def ref(doc,quote,unit=None):
        candidates=[u for u in doc['units'] if quote in u['text'] and (unit is None or unit==u['unit_id'])]
        require(len(candidates)==1,'PROBE_QUOTE_NOT_UNIQUE')
        return {'unit_id':candidates[0]['unit_id'],'quote':quote,'occurrence':0}
    def g(payload):return payload['grounded_extraction']
    doc,payload=synthetic_fixture();converted=run(doc,payload)
    check('original_scores_subtree_unchanged',converted['legacy_runner_payload']['scores']==payload['scores'])
    check('raw_source_payload_preserved_exactly',converted['raw_content_preserved']==canonical(payload))
    check('strict_synthetic_sum',converted['legacy_projection']['time_calculation']['total_hours']==2.5)
    check('original_known_relation_projected',converted['legacy_projection']['extraction']['marker_dict']=={'SYNTHETIC_FLUOR_101':'SYNTHETIC_TARGET'})
    check('scores_schema_unchanged',schema()['properties']['scores']==read(baseline.OUT/'final_output_schema.json')['properties']['scores'])
    case={'specific_question':'SYNTHETIC QUESTION','model_response':doc['text'],'case_id':'MODEL_AND_PARAMETER_DELETION'}
    sid=source_id_for_case(case);changed=copy.deepcopy(case);changed['case_id']='OTHER_MODEL_BASELINE'
    check('opaque_source_identity_cross_batch_invariant',sid==source_id_for_case(changed) and re.fullmatch(r'SRC_[0-9a-f]{24}',sid))
    changed['model_response']+='Changed.'
    check('opaque_source_identity_changes_with_fulltext',sid!=source_id_for_case(changed))
    reject('fake_source_span_hard_failure',lambda d,p:g(p)['entities'][0]['name'].update(quote='ABSENT_SYNTHETIC_NAME'),'SPAN_QUOTE_NOT_FOUND')
    reject('dangling_nonnull_endpoint_hard_failure',lambda d,p:g(p)['relations'][0].update(target_entity_id='undeclared'),'RELATION_DANGLING_ENTITY')
    reject('explicit_null_endpoint_hard_failure',lambda d,p:g(p)['relations'][0].update(target_entity_id=None),'EXPLICIT_RELATION_REQUIRES_TARGET')
    reject('reused_duration_hard_failure',lambda d,p:g(p)['operations'][1].update(duration=copy.deepcopy(g(p)['operations'][0]['duration'])),'REUSED_DURATION_DOUBLE_COUNT')
    reject('score_evidence_missing_metric',lambda d,p:p['score_evidence'].pop(),'SCORE_EVIDENCE_EXACT_FIVE_UNIQUE')
    reject('duplicate_record_id',lambda d,p:g(p)['entities'][1].update(id='fluor1'),'DUPLICATE_RECORD_ID')
    try:convert('{"scores":{},"scores":{}}',doc)
    except integrity.JudgeFormatError as exc:check('duplicate_json_keys_remain_hard_failure','duplicate' in str(exc).lower())
    else:raise ValueError('DUPLICATE_JSON_ACCEPTED')
    doc,payload=synthetic_record_fixture(null_target=True);r=run(doc,payload)
    check('null_unknown_endpoint_honest_partial_projection',r['source_audit']['resolved']['relations'][0]['projection_allowed'] is False and r['legacy_projection']['extraction']['marker_dict']['SYNTHETIC_FLUOR_101']=='')
    check('semantic_partial_preserves_unrelated_scores_method_time',r['legacy_runner_payload']['scores']==payload['scores'] and r['legacy_projection']['extraction']['method_name']=='SYNTHETIC_METHOD' and r['legacy_projection']['time_calculation']['total_hours']==2.5)
    check('short_action_adjacent_time_same_unique_record',r['source_audit']['resolved']['operations'][0]['duration_binding']['valid'])
    for suffix,expected in [(' Wash SYNTHETIC_SECOND for 3 hours.',False),(' Wash SYNTHETIC_SECOND.',False)]:
        d,p=synthetic_record_fixture();text=d['text'].replace('Time: 2 hours.','Time: 2 hours.'+suffix);d=document(text,d['source_id'])
        q=run(d,p);check('adjacent_record_rejects_'+('two_durations' if '3 hours' in suffix else 'two_actions'),q['source_audit']['resolved']['operations'][0]['duration_binding']['valid'] is expected)
    d,p=synthetic_record_fixture();line='1. Incubate ALPHA for 2 hours; wash BETA for 3 hours.'
    d=document(d['text'].replace(d['units'][2]['text'].strip(),line),d['source_id'])
    g(p)['operations'][0]['operation']=ref(d,line);g(p)['operations'][0]['duration']=ref(d,'3 hours')
    q=run(d,p);check('contained_whole_multioperation_quote_not_unique_assignment',not q['source_audit']['resolved']['operations'][0]['duration_binding']['valid'])
    d,p=synthetic_fixture();g(p)['operations'][0]['duration']=copy.deepcopy(g(p)['operations'][1]['duration']);g(p)['operations'][1]['duration']=None
    q=run(d,p);check('different_record_duration_not_aggregated',q['source_audit']['resolved']['operations'][0]['duration_binding']['mode']=='different_source_units' and q['legacy_projection']['time_calculation']['total_hours'] is None)
    d,p=synthetic_fixture();line='SYNTHETIC_FLUOR_101-labeled SYNTHETIC_TARGET';d=append(d,line)
    original_primary=copy.deepcopy(g(p)['entities'][0]['name']);g(p)['relations'][0]['evidence']=ref(d,line,d['units'][-1]['unit_id'])
    q=run(d,p);rr=q['source_audit']['resolved']['relations'][0]
    check('complete_identity_cross_mention_binding_preserves_primary',rr['projection_allowed'] and q['source_audit']['resolved']['entities'][0]['name']['unit_id']==original_primary['unit_id'] and rr['relation_local_mentions']['fluor'][0]['start']!=q['source_audit']['resolved']['entities'][0]['name']['start'])
    d,p=synthetic_fixture();d=append(d,'GENERIC_FLUOR-labeled SYNTHETIC_TARGET');g(p)['relations'][0]['evidence']=ref(d,'GENERIC_FLUOR-labeled SYNTHETIC_TARGET')
    q=run(d,p);check('generic_to_specific_claim_retained_but_not_projected',not q['source_audit']['resolved']['relations'][0]['projection_allowed'] and q['source_audit']['resolved']['relations'][0]['unsupported_claim_retained_not_repaired'])
    d,p=synthetic_fixture();d=append(d,'SYNTHETIC_FLUOR_101-labeled anti-SYNTHETIC_TARGET');g(p)['relations'][0]['evidence']=ref(d,'SYNTHETIC_FLUOR_101-labeled anti-SYNTHETIC_TARGET')
    check('different_anti_qualifier_not_merged',not run(d,p)['source_audit']['resolved']['relations'][0]['projection_allowed'])
    d,p=synthetic_fixture();g(p)['entities'][1]['kind']='fluorescent_protein'
    check('entity_type_separate_from_target_role',run(d,p)['source_audit']['resolved']['relations'][0]['projection_allowed'])
    d,p=synthetic_fixture();d=append(d,'SYNTHETIC_FLUOR_101 and SYNTHETIC_TARGET');g(p)['relations'][0]['evidence']=ref(d,'SYNTHETIC_FLUOR_101 and SYNTHETIC_TARGET')
    check('cooccurrence_never_sufficient_relation',not run(d,p)['source_audit']['resolved']['relations'][0]['projection_allowed'])
    for text,expected in [('GFP appears again.',True),('GFP is not used.',False),('Either GFP or another label is used.',False),('anti-GFP appears.',False),('GFP 488 appears.',False)]:
        d=document('GFP is used.\n'+text+'\n','SYNTHETIC_IDENTITY_COVERAGE');primary=resolve({'unit_id':'L0001','quote':'GFP','occurrence':0},d)
        span=resolve({'unit_id':'L0002','quote':'GFP','occurrence':0},d)
        cov=exact_identity_mention_coverage({'span':span},[{'id':'e1','name':primary,'usage':'used'}],d)
        check('repeat_identity_'+text.replace(' ','_'),cov['covered']==expected)
    d,p=synthetic_fixture();line='3. Stain SYNTHETIC_OTHER in parallel for 1 hour.';d=append(d,line)
    g(p)['operations'].append({'id':'excluded','operation':ref(d,line),'phase':'staining','duration':ref(d,'1 hour'),'repeat_evidence':None,'execution_scope':'initial','condition_evidence':None})
    g(p)['timeline']['operation_ids'].append('excluded');q=run(d,p);t=q['legacy_projection']['time_calculation']
    check('program_timeline_filters_excluded_and_keeps_proposal',t['total_hours']==2.5 and t['timeline_derivation']['excluded_from_proposal']==['excluded'] and q['source_audit']['resolved']['timeline_proposal']['operation_ids'][-1]=='excluded')
    g(p)['operations'][-1]['phase']='unknown';q=run(d,p)
    check('unknown_phase_not_filtered_to_finite_total',q['legacy_projection']['time_calculation']['total_hours'] is None and 'unresolved_phase_scope' in q['legacy_projection']['time_calculation']['issues'])
    d,p=synthetic_fixture();g(p)['operations'][0]['execution_scope']='unknown';q=run(d,p)
    check('unknown_scope_not_filtered_to_finite_total',q['legacy_projection']['time_calculation']['total_hours'] is None)
    d,p=synthetic_record_fixture();d=document(d['text'].replace('Time: 2 hours.','Time: 2 hours each.'),d['source_id']);q=run(d,p)
    check('each_in_adjacent_duration_record_not_assumed_once',q['source_audit']['resolved']['operations'][0]['repeat_count'] is None and q['legacy_projection']['time_calculation']['total_hours'] is None)
    d,p=synthetic_record_fixture();d=document(d['text'].replace('Time: 2 hours.','Time: 2 hours each, twice.'),d['source_id']);g(p)['operations'][0]['repeat_evidence']=ref(d,'twice');q=run(d,p)
    check('explicit_same_record_repeat_arithmetic',q['legacy_projection']['time_calculation']['total_hours']==4.5)
    d,p=synthetic_fixture();g(p)['operations']=g(p)['operations'][:1];g(p)['timeline']['operation_ids']=['op1'];q=run(d,p)
    check('self_report_complete_cannot_hide_missing_source_duration',q['legacy_projection']['time_calculation']['total_hours'] is None and 'source_duration_candidates_not_all_classified' in q['legacy_projection']['time_calculation']['issues'])
    d,p=synthetic_fixture();d=append(d,'Total: 9 hours.');g(p)['total_time_claims']=[{'id':'total1','duration':ref(d,'9 hours'),'scope':'clearing_total'}];q=run(d,p)
    check('conflicting_source_total_preserves_sum_and_claim',q['legacy_projection']['time_calculation']['total_hours'] is None and q['legacy_projection']['time_calculation']['candidate_bounds_hours']==[2.5,2.5] and 'explicit_total_conflicts_with_operation_sum' in q['legacy_projection']['time_calculation']['issues'])
    d,p=synthetic_fixture();edge=copy.deepcopy(g(p)['timeline']['relation_evidence']);g(p)['precedence_edges']=[{'before_id':'op2','after_id':'op1','evidence':edge},{'before_id':'op1','after_id':'op2','evidence':edge}]
    q=run(d,p);pa=q['source_audit']['resolved']['precedence_audit']
    check('backward_cycle_claim_preserved_not_used_as_schedule',pa['cyclic_model_proposal'] and pa['backward_document_order_edges']==1 and not pa['model_edges_used_for_aggregation'] and q['legacy_projection']['time_calculation']['total_hours']==2.5)
    d,p=synthetic_fixture();line='If needed after storage, re-equilibrate SYNTHETIC_MEDIUM for 1 hour.';d=append(d,line)
    g(p)['operations'].append({'id':'future','operation':ref(d,line),'phase':'ri_matching','duration':ref(d,'1 hour'),'repeat_evidence':None,'execution_scope':'conditional_or_future','condition_evidence':ref(d,'If needed after storage')})
    q=run(d,p);t=q['legacy_projection']['time_calculation']
    check('initial_and_future_bounds_distinct_without_forced_total',t['total_hours'] is None and t['initial_scope_candidate_bounds_hours']==[2.5,2.5] and t['initial_plus_at_most_one_conditional_execution_envelope_hours']==[2.5,3.5])
    for text,expected in [('RI = 1.5',1.5),('Refractive Index = 1.5',1.5),('1.5',1.5),('50%',None),('RI = 1.4 or 1.5',None),('concentration = 1.5',None),('medium SYNTHETIC 1.5',None)]:
        check('RI_literal_'+text,parse_ri_literal(text)[0]==expected)
    check('unobserved_duration_prefix_not_silently_repaired',duration_value('Time: 2 hours')['unique_hours'] is None)
    for value,expected in [('overnight',None),('2-4 hours',None),('30 minutes',0.5)]:
        check('duration_arithmetic_'+value,duration_value(value)['unique_hours']==expected)
    # Full actual format schema through existing transport, with the client
    # replaced before any socket operation. No provider traffic or ledger entry.
    from models.Ollama_LLM import OllamaLLM
    captured=[];d,p=synthetic_record_fixture(null_target=True)
    class NoNetwork:
        def generate(self,**kwargs):
            captured.append(copy.deepcopy(kwargs));return {'done':True,'done_reason':'stop','response':canonical(p),'eval_count':1,'prompt_eval_count':1,'model':'SYNTHETIC_ONLY_MODEL'}
    adapter=OllamaLLM('SYNTHETIC_ONLY_MODEL',format=schema(),max_length=8192,temperature=0,enable_thinking=False);adapter.client=NoNetwork()
    response=adapter._generate('SYNTHETIC_ONLY source prompt')
    check('full_schema_transport_no_network',captured[0]['format']==schema() and response['content']==canonical(p))
    save(OUT/'synthetic_only/source_document.json',d);save(OUT/'synthetic_only/payload.json',p)
    save(OUT/'synthetic_only/conversion.json',run(d,p));save(OUT/'synthetic_only/transmitted_payload.json',captured[0])
    (OUT/'synthetic_only/raw_response.txt').write_text(canonical(p),encoding='utf8')
    actual=[]
    for case in read(baseline.OUT/'cases.json')['cases']:
        aid=case['anonymous_answer_id'];d=read(OUT/'source_documents'/f'{aid}.json')
        require(d['source_id']==source_id_for_case(case) and d['text']==case['model_response'] and d['answer_sha256']==case['answer_sha256'],'ACTUAL_SOURCE_IDENTITY')
        candidates=evidence_inventory(d)
        for c in candidates:require(resolve({k:c['span'][k] for k in ['unit_id','quote','occurrence']},d)==c['span'],'ACTUAL_CANDIDATE_SPAN')
        actual.append({'anonymous_answer_id':aid,'answer_sha256':d['answer_sha256'],'source_id':d['source_id'],
            'all_units_reconstruct_original':True,'candidate_span_checks':len(candidates),'labels_created':0,'semantic_correctness_inferred':False})
    report={'status':'pass','synthetic_only_checks':checks,'synthetic_fixture_count':len(checks),'actual_source_identity_checks':actual,
        'new_model_requests':0,'network_calls':0,'scientific_or_expert_labels_created':0,'script_sha256':sha(__file__),
        'schema_sha256':sha(OUT/'schema.json'),'plan_sha256':sha(OUT/'plan.json'),'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'software_probes.json',report)
    print(canonical({'status':'offline_checks_pass','synthetic_checks':len(checks),'actual_source_identity_checks':len(actual),'new_requests':0}))

INSTRUCTIONS='''[SOURCE-BOUND EXTRACTION CONTRACT v2]
Return one joint JSON: unchanged scores, score_evidence, grounded_extraction. The complete schema is in decoder format; the catalog below describes shape, not example values.
Every fact cites the submitted answer, never QUESTION/reference/prior knowledge. Span={unit_id,quote,occurrence}; quote is exact original text, occurrence zero-based within that line. Preserve full names, qualifiers and numeric suffixes; no fuzzy repair or aliases.
score_evidence has exactly one c_param/co_order/co_method/co_param/co_chem record. observed/mixed requires answer spans; absence has an empty span list and a short rubric basis. Quotes do not prove score correctness. Keep original scales and c_step unchanged.
Entities retain their primary name spans. Entity kind describes identity, whereas being a relation target is a separate role: a protein can itself be a target. A relation refers to declared IDs. target_entity_id=null is allowed only for unknown/ambiguous status; never invent an ID named unknown. Exact complete names must occur inside relation evidence to support a specific edge. The program records relation-local mentions without moving primary spans. Co-occurrence, generic family names, numbered names appearing elsewhere, list order, or common knowledge cannot establish a specific mapping. Unsupported explicit claims stay rejected in the sidecar; do not hide them with guessed targets.
Enumerate source operations and all duration mentions, including exclusions and conditional later actions. Operation and duration may be separate exact spans in one original record, but do not link different records. Ambiguous multi-operation/multi-duration records remain unresolved. Repeat and condition evidence must be local to the same record. Preserve all raw spans; never count one duration twice.
Time includes delipidation/decalcification/decolorization/RI matching/clearing treatment/reagent-transition wash; excludes fixation/antibody incubation/staining/imaging/routine wash/continuing storage. Phase/scope are provisional classifications. Record execution_scope as initial/conditional_or_future/unknown with actual condition evidence. Do not sum times. The program derives initial timeline membership from declared phase/scope, saves your proposal/differences, and converts units. Ranges, unknowns, missing durations, endpoint ambiguity and unspecified overnight remain nullable with known components retained; old overnight=8h is comparison only. Model precedence claims are audited separately and are not scientific dependencies.
Keep method mentions and RI roles distinct. RI may quote a unique explicit number or an explicit RI-labelled numeric expression; a medium name supplies no number. Sample RI is not sample type/scale. Never invent reference protocol_time_hours. Report coverage honestly; empty or all-unknown output does not establish fact preservation. Exact spans and structural success are not semantic or expert validation.
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
    pointers=[[r['candidate_id'],r['kind'],r['unit_id'],r['quote'],r['occurrence']] for r in inventory]
    catalog=schema_catalog(schema())
    return prefix+INSTRUCTIONS+'\n[SOURCE_ID]\n'+doc['source_id']+'\n[RECALL POINTERS: candidate_id,kind,unit_id,exact_quote,occurrence; NOT GOLD]\n'+canonical(pointers)+'\n[OUTPUT TYPE CATALOG: required keys; all objects disallow extra keys; full schema also supplied in decoder format]\n'+canonical(catalog)+baseline.parent.v2.reference_suffix(case)

def prepare():
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
        (OUT/'prompts'/f'{aid}_from_identity_v2.diff').write_text(''.join(difflib.unified_diff(old.splitlines(keepends=True),prompt.splitlines(keepends=True),fromfile=aid+'/identity_v2',tofile=aid+'/grounded_extraction_v2')),encoding='utf8')
        bound=len(prompt.encode('utf8'))+8192+256
        matrices.append({'anonymous_answer_id':aid,'question_id':c['question_id'],'case_id':c['case_id'],
            'opaque_source_id':doc['source_id'],'case_id_not_in_prompt':True,
            'question_sha256':c['question_sha256'],'answer_sha256':c['answer_sha256'],'source_document_sha256':sha(OUT/'source_documents'/f'{aid}.json'),
            'prompt_sha256':sha(p),'conservative_context_bound':bound,'fits_40960':bound<=40960,
            'full_answer_reconstruction_equal':True,'original_score_rubric_equal_after_format_header_and_lossless_source_projection':True,
            'reference_context_unchanged':True,'reference_context_sha256':rawsha(baseline.parent.v2.reference_suffix(c)),
            'inventory_counts':dict(__import__('collections').Counter(x['kind'] for x in evidence_inventory(doc))),
            'scientific_labels_created':0})
    sourcepaths=[Path(__file__),baseline.OUT/'cases.json',baseline.OUT/'final_output_schema.json',baseline.OUT/'rubric_identity_preserved.txt',
        ROOT/'OEQ_run_grading_new.py',ROOT/'evaluator_integrity.py',ROOT/'models/Ollama_LLM.py',ROOT/'KnowledgeBase/method_fluro_compati.json',
        ROOT/'artifacts/cce_validation/judges/identity_stability_dev_v1/A01_variation_trace.json',
        ROOT/'artifacts/cce_validation/judges/identity_stability_dev_v1/A04_repeat_trace.json']
    sourcepaths += [ROOT/'scripts/cce_grounded_extraction_v1.py',OUT.parent/'grounded_extraction_v1/plan.json',
        OUT.parent/'grounded_development_v1/completion_summary.json',OUT.parent/'grounded_development_v1/independent_fact_audit_v1/summary.json',
        OUT.parent/'grounded_failure_diagnostics_v1/summary_5of5.json',
        OUT.parent/'validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json']
    plan={'status':'candidate_offline_contract_pending_root_review','version':VERSION,'matrix':matrices,
        'planned_call_shape':'one_joint_payload_per_answer; no separate extraction/judge call','planned_development_answers':5,
        'new_judge_requests':0,'old_scores_and_human_package_modified':False,'no_heldout_scientific_records_read':True,
        'scores_schema_byte_equivalent_to_original_subtree':schema_value['properties']['scores']==read(baseline.OUT/'final_output_schema.json')['properties']['scores'],
        'EGES_function_and_knowledge_base_changed':False,'proposed_model':'Same local 27B/Q8 model as model_probe_v1 and grounded_development_v1; actual model identity/settings are frozen by the separate v2 development runner before calls',
        'ollama_format_schema_supported_by_existing_transport':True,'schema_decoder_is_not_a_semantic_or_duplicate_key_guarantee':True,
        'schema_transport':'Complete schema object supplied via Ollama format; prompt contains a compact program-generated type catalog. No completed output examples.',
        'source_id_policy':'SRC_ + SHA256(question + NUL + full answer)[:24]; no model name or condition label. Real case identity remains in external matrix. Equal question/fulltext across batches has equal source ID.',
        'score_evidence_contract':'Exactly five distinct direct metrics. Answer spans resolved against the original answer; observed/mixed require a span, absence requires no span. Rubric correctness remains unverified.',
        'time_policy_delta':'Source-exact unique arithmetic; unknown overnight stays NA. The old 8-hour convention is a separate comparison. Conditional/future operations retain separate initial-scope bounds and an explicitly conditional envelope; no unqualified endpoint is silently selected. Excluded non-clearing schedule cues do not invalidate core time.',
        'target_policy_delta':'Nullable unknown targets; entity type distinct from relationship role; exact relation-local mention links preserve primary/raw spans. Unsupported semantic claims become rejected projection/component warnings rather than losing unrelated direct/method/time components. JSON, false spans and dangling nonnull IDs remain hard errors.',
        'coverage_policy_delta':'Repeated exact full-name mentions can link to an existing used entity as identity-only coverage. Alternative/negated/differently qualified mentions require separate classification or unresolved evidence; no target/new usage is inferred.',
        'time_binding_policy_delta':'A unique same-source-record action/duration may bind adjacent fields. Ambiguous records retain literal numbers but are not aggregated. Initial timeline is derived from declared phase/scope with original proposal/diff retained. Unverified precedence claims are not dependencies.',
        'RI_policy_delta':'An explicitly RI-labelled unique number is parsed with source trace; percentages, multiple values and unlabelled prose are not accepted. No duration-prefix repair was added.',
        'known_limits':['Lexical candidate inventory is not a completeness gold standard.','Phase assignment and source-order serial schedule are declared provisional conventions.','Nested parallel subgroups are not supported; keep unknown rather than flatten.','The model may still omit or misclassify valid spans; this contract makes evidence auditable, not scientifically true.','Legacy marker_dict cannot represent all entity graphs; do not treat partial projection as complete EGES.'],
        'input_sha256':{str(p.resolve()):sha(p) for p in sourcepaths},'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'plan.json',plan)
    require(all(r['fits_40960'] for r in matrices),'CONSERVATIVE_CONTEXT_BOUND_EXCEEDED')
    text='''# Source-bound extraction v2: offline candidate

This package contains **no model generation and no expert labels**. It uses the unchanged five original development answers. No sealed confirmation or holdout scientific output was used.

One joint response preserves the original scores schema and adds five score-evidence records plus entity, relationship, operation and time evidence arrays. Every quoted span resolves to the lossless original-answer index. The source text, question, reference suffix, old score rubric and fixed evidence files are hash-bound. The old EGES functions and lookup tables remain untouched.

`convert(raw, document(answer, source_id_for_case(case)))` uses the original strict duplicate-key parser, checks the new contract, and returns `legacy_runner_content` plus an explicit source-audit/conversion sidecar. The opaque ID hashes the exact question, a NUL separator and full answer; it exposes no case/model/condition name. The original provider raw content is retained separately; this conversion must never be represented as raw identity. `legacy_runner_payload.scores` is exactly the returned scores subtree. The downstream runner must save both raw EGES and any distinct component-availability gate.

Entity identity and relation confidence differ: valid full names do not imply a target assignment. Co-occurrence alone is not projected. A relation-local exact complete name may bind the same identity as a header mention while preserving both original offsets. Unknown targets can be null. Entity kind and relation role are separate. A rejected semantic relationship is retained with `projection_allowed=false`; it no longer makes unrelated valid fields a whole-case structural failure. A fake span, invalid JSON or dangling non-null ID still fails. Missing relationships leave the old empty-target representation plus an explicit partial-projection flag. That flag is an audit warning, not a command to erase every partial EGES result: a source-supported valid known zero can still determine the old nullable-min label component. Unknown components must not erase unaffected known components.

Durations are parsed and aggregated by code, conditional on the supplied phase and scheduling classifications. A short action quote can bind an adjacent duration only in a single source record passing the unique action/duration guard. A quoted whole line containing multiple actions or durations is not proof of unique assignment. These are narrow lexical guards, not full semantic parsing. The program derives initial timeline membership from declared phase/scope and preserves the model proposal/differences; unknown classifications cannot be discarded to produce a finite complete total. Backward/cyclic model precedence proposals are retained as diagnostics and do not control aggregation. Ranges, missing durations, unspecified overnight, ambiguity and total/sum conflicts remain nullable with known values and causes. The old overnight=8 h convention is retained only in a separate comparison. Nested parallel groups are not flattened. Source-order summation is a declared provisional convention, not a scientific gold schedule. RI-labelled unique numbers are source-parsed; no duration prefix repair is added.

Coverage candidates enumerate durations, numeric/name leads, and existing knowledge-base names. They are recall prompts and auditable omission checks, not scientific labels or a proof of completeness. Alternative/negated names must be retained with their actual status rather than treated as all simultaneously required. Exact spans do not establish correct entity type, phase, RI role, scoring judgment or complete scientific validity.

The complete JSON Schema belongs in the actual Ollama `format` object. The prompt contains compact shape documentation, not a populated example. The isolated synthetic transport probe replaces HTTP with an in-memory stub and verifies the full schema is serialized. It does not validate real generation behavior.

Reproduce offline from repository root:

```powershell
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_grounded_extraction_v2.py prepare
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_grounded_extraction_v2.py self-check
```

The `synthetic_only/` payload/source pair is for runner integration tests only. It is unrelated to any natural answer or expert review. `plan.json` remains a candidate pending the root's model/settings freeze; the actual generation wrapper is separate.
'''
    (OUT/'README.md').write_text(text,encoding='utf8')
    print(canonical({'status':plan['status'],'new_requests':0,'context_bounds':[r['conservative_context_bound'] for r in matrices],'all_fit':all(r['fits_40960'] for r in matrices)}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','self-check','convert']);p.add_argument('--source-document',type=Path);p.add_argument('--raw-response',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='self-check':self_check()
    else:
        require(a.source_document and a.raw_response and a.out,'CONVERT_REQUIRES_EXPLICIT_FILES');save(a.out,convert(a.raw_response.read_text(encoding='utf8'),read(a.source_document)))
if __name__=='__main__':main()
