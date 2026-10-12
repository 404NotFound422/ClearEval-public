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
OUT=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_extraction_v1'
VERSION='source_bound_extraction_v1'
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
        'relations':arr(obj({'id':ID,'fluor_entity_id':ID,'target_entity_id':ID,'evidence':SPAN,
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
    if spec==SPAN:return 'Span{unit_id:string,quote:exact-nonempty-string,occurrence:integer>=0}'
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
    others=[e['name']['quote'] for e in entities if e['kind'] in ['target','antibody'] and e['name']['quote']!=target]
    if any(name in context for name in others):return False,'multiple_targets_in_relation_context'
    return True,'explicit_lexical_relation_only_not_scientific_confirmation'

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
        require(r['fluor_entity_id'] in entities and r['target_entity_id'] in entities,'RELATION_DANGLING_ENTITY')
        f,t=entities[r['fluor_entity_id']],entities[r['target_entity_id']]
        require(f['kind'] in ['fluorophore','fluorescent_protein'] and t['kind'] in ['target','antibody'],'RELATION_ENTITY_KIND')
        require(f['name']['quote'] in r['evidence']['quote'] and t['name']['quote'] in r['evidence']['quote'],'RELATION_NAMES_NOT_IN_QUOTED_EVIDENCE')
        require(all(r['evidence']['start']<=x['name']['start'] and x['name']['end']<=r['evidence']['end'] for x in [f,t]),'RELATION_ENTITY_OCCURRENCE_NOT_BOUND')
        ok,why=lexical_relation(f['name']['quote'],t['name']['quote'],r['evidence'],result['entities'])
        r['projection_allowed']=r['status']=='explicit' and ok;r['mechanical_relation_state']=why
    duration_spans=[]
    for o in result['operations']:
        if o['duration']:
            d=o['duration'];op=o['operation']
            require(op['start']<=d['start']<d['end']<=op['end'],'DURATION_OUTSIDE_OPERATION')
            key=(d['start'],d['end']);require(key not in duration_spans,'REUSED_DURATION_DOUBLE_COUNT');duration_spans.append(key)
            o['parsed_duration']=duration_value(d['quote']);o['legacy_overnight_comparison']=duration_value(d['quote'],8)
        else:o['parsed_duration']={'state':'missing','bounds_hours':None,'unique_hours':None}
        if o['repeat_evidence']:
            require(o['operation']['start']<=o['repeat_evidence']['start'] and o['repeat_evidence']['end']<=o['operation']['end'],'REPEAT_OUTSIDE_OPERATION')
        if o['condition_evidence']:
            require(o['operation']['start']<=o['condition_evidence']['start'] and o['condition_evidence']['end']<=o['operation']['end'],'CONDITION_OUTSIDE_OPERATION')
        conditional_cue=re.search(r'\bif\b|\bwhen needed\b|\bas needed\b|\bafter storage\b|\bre[- ]equilibrat\w*\b|\bagain\b|如需|如果|再次|再平衡|保存后',o['operation']['quote'],re.I)
        o['scope_gate']={'conditional_cue_detected':bool(conditional_cue),
            'conditional_scope_supported':bool(o['condition_evidence'] and re.search(r'\bif\b|\bwhen needed\b|\bas needed\b|\bafter storage\b|\bre[- ]equilibrat\w*\b|\bagain\b|如需|如果|再次|再平衡|保存后',o['condition_evidence']['quote'],re.I))}
        o['repeat_count']=repeat_count(o['repeat_evidence'])
        if o['duration'] and re.search(r'\beach\b|每',o['operation']['quote'],re.I) and not o['repeat_evidence']:
            o['repeat_count']=None;o['repeat_uncertainty']='each_without_explicit_count'
    members=result['timeline']['operation_ids'];require(len(members)==len(set(members)) and set(members)<=set(ops),'TIMELINE_DUPLICATE_OR_DANGLING_OPERATION')
    graph={k:[] for k in ops}
    for e in result['precedence_edges']:
        require(e['before_id'] in ops and e['after_id'] in ops,'EDGE_DANGLING_OPERATION');e['evidence']=resolved(e['evidence'])
        graph[e['before_id']].append(e['after_id'])
    done=set();active=set()
    def visit(node):
        require(node not in active,'CYCLIC_TIME_GRAPH')
        if node in done:return
        active.add(node)
        for child in graph[node]:visit(child)
        active.remove(node);done.add(node)
    for node in graph:visit(node)
    inventory=evidence_inventory(doc)
    substantive=[s for o in result['operations'] for s in [o['duration']] if s]+[t['duration'] for t in result['total_time_claims']]
    unresolved=[r['evidence'] for r in result['coverage']['unresolved']]
    for r in inventory:
        s=r['span']
        if any(v['start']<=s['start'] and s['end']<=v['end'] for v in substantive if r['kind']=='duration'):state='covered_time_evidence'
        elif any(v['start']<=s['start'] and s['end']<=v['end'] for v in unresolved):state='explicitly_unresolved'
        elif r['kind'] in ['numbered_name_lead','known_marker_name_lead'] and any(v['name']['start']<=s['start'] and s['end']<=v['name']['end'] for v in result['entities']):
            matching=[v for v in result['entities'] if v['name']['start']<=s['start'] and s['end']<=v['name']['end']]
            state='covered_entity_name' if any(v['usage']=='used' for v in matching) else 'classified_entity_nonused_or_unknown'
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
    values={}
    for role in ['reagent_final','sample_target']:
        candidates=[]
        for r in g['ri_mentions']:
            if r['role']==role and re.fullmatch(NUMBER,r['value']['quote'].strip()):candidates.append(float(r['value']['quote']))
        values[role]=candidates[0] if len(set(candidates))==1 else None
    extraction={'method_name':method,'marker_dict':mapping,'clearing_total_time_hours':time['total_hours'],
        'reagent_ri_value':values['reagent_final'],'sample_ri_value':values['sample_target'],'protocol_time_hours':None,
        'reasoning':'Program projection from exact source spans; consult source-bound sidecar. Unknown relationships were not inferred.'}
    integrity.validate_legacy_extraction(extraction)
    label_ready=not any('target' in s or 'relationship' in s or 'entity' in s or 'numbered_name' in s for s in issues)
    return {'extraction':extraction,'time_calculation':time,'entity_conversion':conversion,'method_selection_checks':method_checks,'projection_issues':issues,
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

def self_check():
    """No service invocation. Test actual validator and old transport serialization."""
    import collections
    checks=[]
    def check(name,fn):
        fn();checks.append({'fixture':name,'status':'pass','synthetic_only':True})
    def rejected(name,mutation,code=None):
        doc,payload=synthetic_fixture();mutation(doc,payload)
        try:convert(canonical(payload),doc)
        except (ValueError,integrity.JudgeFormatError) as exc:
            require(code is None or code in str(exc),'WRONG_REJECTION:'+name+':'+str(exc))
            checks.append({'fixture':name,'status':'rejected_as_expected','failure_code':str(exc),'synthetic_only':True})
        else:raise ValueError('FIXTURE_UNEXPECTED_ACCEPTANCE:'+name)
    doc,payload=synthetic_fixture();converted=convert(canonical(payload),doc)
    require(converted['legacy_projection']['time_calculation']['total_hours']==2.5,'SYNTHETIC_TIME_SUM')
    require(converted['legacy_projection']['extraction']['marker_dict']=={'SYNTHETIC_FLUOR_101':'SYNTHETIC_TARGET'},'SYNTHETIC_EXPLICIT_RELATION')
    require(converted['legacy_runner_payload']['scores']==payload['scores'],'SYNTHETIC_SCORE_IDENTITY')
    check('exact_source_serial_arithmetic_legacy_projection_and_scores',lambda:None)
    save(OUT/'synthetic_only/source_document.json',doc);save(OUT/'synthetic_only/payload.json',payload)
    save(OUT/'synthetic_only/conversion.json',converted)
    (OUT/'synthetic_only/raw_response.json').write_text(canonical(payload),encoding='utf8')
    for duplicate in ['{"same":1,"same":1}','{"same":1,"same":2}']:
        try:integrity.parse_judge_object(duplicate)
        except integrity.JudgeFormatError:check('strict_duplicate_keys_'+('identical' if duplicate.endswith(':1}') else 'conflicting'),lambda:None)
        else:raise ValueError('DUPLICATE_KEY_ACCEPTED')
    rejected('edited_raw_document',lambda d,p:d.update(text=d['text']+'changed'),'DOCUMENT_HASH_OR_UNIT_BINDING')
    rejected('edited_unit_offsets',lambda d,p:d['units'][0].update(start=2),'DOCUMENT_HASH_OR_UNIT_BINDING')
    rejected('wrong_source_id',lambda d,p:p['grounded_extraction'].update(source_id='OTHER'),'SOURCE_ID_MISMATCH')
    rejected('nonexistent_quote',lambda d,p:p['grounded_extraction']['entities'][0]['name'].update(quote='NOT_PRESENT'),'SPAN_QUOTE_NOT_FOUND')
    rejected('wrong_occurrence',lambda d,p:p['grounded_extraction']['entities'][0]['name'].update(occurrence=9),'SPAN_QUOTE_NOT_FOUND')
    rejected('duplicate_record_id',lambda d,p:p['grounded_extraction']['entities'][1].update(id='fluor1'),'DUPLICATE_RECORD_ID')
    rejected('clipped_name',lambda d,p:p['grounded_extraction']['entities'][0]['name'].update(quote='SYNTHETIC_FLUOR'),'CLIPPED_NAME_END')
    rejected('dangling_relation',lambda d,p:p['grounded_extraction']['relations'][0].update(target_entity_id='missing'),'RELATION_DANGLING_ENTITY')
    rejected('wrong_relation_occurrence',lambda d,p:p['grounded_extraction']['relations'][0]['evidence'].update(quote='SYNTHETIC_TARGET'),'RELATION_NAMES_NOT_IN_QUOTED_EVIDENCE')
    rejected('duration_outside_operation',lambda d,p:p['grounded_extraction']['operations'][0].update(duration=copy.deepcopy(p['grounded_extraction']['operations'][1]['duration'])),'DURATION_OUTSIDE_OPERATION')
    def double(d,p):
        o=copy.deepcopy(p['grounded_extraction']['operations'][0]);o['id']='op3';p['grounded_extraction']['operations'].append(o)
    rejected('same_source_duration_double_count',double,'REUSED_DURATION_DOUBLE_COUNT')
    def cycle(d,p):
        evidence=p['grounded_extraction']['timeline']['relation_evidence'];p['grounded_extraction']['precedence_edges']=[
            {'before_id':'op1','after_id':'op2','evidence':evidence},{'before_id':'op2','after_id':'op1','evidence':evidence}]
    rejected('cyclic_time_graph',cycle,'CYCLIC_TIME_GRAPH')
    rejected('duplicate_timeline_operation',lambda d,p:p['grounded_extraction']['timeline']['operation_ids'].append('op1'),'TIMELINE_DUPLICATE_OR_DANGLING_OPERATION')
    rejected('missing_direct_score_evidence',lambda d,p:p['score_evidence'].pop(),'SCORE_EVIDENCE_EXACT_FIVE_UNIQUE')
    rejected('duplicate_direct_score_evidence',lambda d,p:p['score_evidence'][0].update(metric='co_order'),'SCORE_EVIDENCE_EXACT_FIVE_UNIQUE')
    rejected('observed_score_without_span',lambda d,p:p['score_evidence'][0].update(basis='observed'),'OBSERVED_SCORE_EVIDENCE_REQUIRES_SPAN')
    rejected('mixed_score_casing',lambda d,p:p['scores']['correctness'].update(CO_ORDER=p['scores']['correctness'].pop('co_order')),'SCHEMA_REQUIRED')
    for name,kwargs,bounds,total in [
        ('explicit_range_preserved',{'first':'2–3 hours'},[2.5,3.5],None),
        ('overnight_unknown_not_eight',{'first':'overnight'},[.5,None],None),
        ('explicit_parallel_maximum',{'mode':'parallel'},[2,2],2),
        ('explicit_alternative_range',{'mode':'alternative'},[.5,2],None),
        ('unknown_schedule_range',{'mode':'unknown'},[2,2.5],None)]:
        d,p=synthetic_fixture(**kwargs);r=convert(canonical(p),d)['legacy_projection']['time_calculation']
        require(r['candidate_bounds_hours']==bounds and r['total_hours']==total,'TIME_FIXTURE:'+name)
        if name=='overnight_unknown_not_eight':require(convert(canonical(p),d)['source_audit']['resolved']['operations'][0]['legacy_overnight_comparison']['unique_hours']==8,'LEGACY_OVERNIGHT_COMPARISON_MISSING')
        check(name,lambda:None)
    d,p=synthetic_fixture(relation='ambiguous');r=convert(canonical(p),d)['legacy_projection']
    require(r['extraction']['marker_dict']['SYNTHETIC_FLUOR_101']=='' and r['extraction']['clearing_total_time_hours']==2.5,'UNKNOWN_RELATION_ERASES_KNOWN_TIME')
    check('cooccurrence_does_not_infer_target_and_known_time_survives',lambda:None)
    d,p=synthetic_fixture();p['grounded_extraction']['relations']=[]
    r=convert(canonical(p),d)['legacy_projection'];require('unmapped_reported_target_identities' in r['projection_issues'],'OMITTED_RELATION_WAS_COMPLETE')
    check('unmapped_reported_targets_remain_partial',lambda:None)
    d,p=synthetic_fixture();p['grounded_extraction']['operations'][0]['phase']='unknown'
    r=convert(canonical(p),d)['legacy_projection'];require(r['time_calculation']['total_hours'] is None,'UNKNOWN_PHASE_BECAME_NUMERIC')
    check('unknown_phase_preserves_NA',lambda:None)
    d,p=synthetic_fixture();p['grounded_extraction']['operations'].pop();p['grounded_extraction']['timeline']['operation_ids']=['op1']
    r=convert(canonical(p),d)['legacy_projection'];require('source_duration_candidates_not_all_classified' in r['time_calculation']['issues'],'OMITTED_DURATION_UNDETECTED')
    check('source_duration_recall_detects_omitted_operation',lambda:None)
    d,p=synthetic_fixture();extra='Excluded staining can run in parallel for 4 hours.\n';d=document(d['text']+extra,d['source_id'])
    unit=d['units'][-1]['unit_id'];p['grounded_extraction']['operations'].append({'id':'excluded','operation':{'unit_id':unit,'quote':extra.strip(),'occurrence':0},
        'phase':'staining','duration':{'unit_id':unit,'quote':'4 hours','occurrence':0},'repeat_evidence':None,'execution_scope':'initial','condition_evidence':None})
    r=convert(canonical(p),d)['legacy_projection']['time_calculation'];require(r['total_hours']==2.5,'EXCLUDED_PARALLEL_STAINING_CHANGED_CORE_TIME')
    check('parallel_staining_does_not_invalidate_serial_clearing',lambda:None)
    d,p=synthetic_fixture();extra='If needed after storage, synthetic re-equilibration for 1 hour.\n';d=document(d['text']+extra,d['source_id'])
    unit=d['units'][-1]['unit_id'];p['grounded_extraction']['operations'].append({'id':'conditional','operation':{'unit_id':unit,'quote':extra.strip(),'occurrence':0},
        'phase':'ri_matching','duration':{'unit_id':unit,'quote':'1 hour','occurrence':0},'repeat_evidence':None,'execution_scope':'conditional_or_future',
        'condition_evidence':{'unit_id':unit,'quote':'If needed after storage','occurrence':0}})
    r=convert(canonical(p),d)['legacy_projection']['time_calculation']
    require(r['total_hours'] is None and r['initial_scope_candidate_bounds_hours']==[2.5,2.5] and r['initial_plus_at_most_one_conditional_execution_envelope_hours']==[2.5,3.5],'CONDITIONAL_ENDPOINT_WAS_FORCED')
    check('conditional_future_time_separate_without_forced_endpoint',lambda:None)
    # Existing Ollama adapter serialization, with a stub replacing HTTP; never
    # construct a real request or contact a socket in this probe.
    from models.Ollama_LLM import OllamaLLM
    captured=[]
    class NoNetwork:
        def generate(self,**kwargs):
            captured.append(copy.deepcopy(kwargs));return {'done':True,'done_reason':'stop','response':canonical(payload),
                'eval_count':1,'prompt_eval_count':1,'model':'SYNTHETIC_ONLY_MODEL'}
    adapter=OllamaLLM('SYNTHETIC_ONLY_MODEL',format=schema(),max_length=8192,temperature=0,enable_thinking=False)
    adapter.client=NoNetwork();response=adapter._generate('SYNTHETIC_ONLY source prompt')
    require(captured[0]['format']==schema() and captured[0]['prompt']=='SYNTHETIC_ONLY source prompt','FULL_SCHEMA_NOT_TRANSMITTED')
    require(response['content']==canonical(payload),'TRANSPORT_MUTATED_RAW')
    save(OUT/'synthetic_only/transmitted_payload.json',captured[0])
    check('existing_transport_full_format_schema_offline_capture',lambda:None)
    actual=[]
    for case in read(baseline.OUT/'cases.json')['cases']:
        aid=case['anonymous_answer_id'];d=read(OUT/'source_documents'/f'{aid}.json')
        require(d['text']==case['model_response'] and d['answer_sha256']==case['answer_sha256'],'ACTUAL_SOURCE_IDENTITY')
        candidates=evidence_inventory(d)
        for c in candidates:
            ref={k:c['span'][k] for k in ['unit_id','quote','occurrence']};require(resolve(ref,d)==c['span'],'ACTUAL_CANDIDATE_SPAN')
        actual.append({'anonymous_answer_id':aid,'answer_sha256':d['answer_sha256'],'all_units_reconstruct_original':True,
            'candidate_span_checks':len(candidates),'candidate_kinds':dict(collections.Counter(x['kind'] for x in candidates)),
            'labels_created':0,'semantic_correctness_inferred':False})
    report={'status':'pass','synthetic_only_checks':checks,'synthetic_fixture_count':len(checks),'actual_source_identity_checks':actual,
        'new_model_requests':0,'network_calls':0,'scientific_or_expert_labels_created':0,'script_sha256':sha(__file__),
        'schema_sha256':sha(OUT/'schema.json'),'plan_sha256':sha(OUT/'plan.json'),'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'software_probes.json',report)
    print(canonical({'status':'offline_checks_pass','synthetic_checks':len(checks),'actual_source_identity_checks':len(actual),'new_requests':0}))

INSTRUCTIONS='''[SOURCE-BOUND EXTRACTION CONTRACT v1]
Return one joint JSON instance: unchanged scores, score_evidence, and grounded_extraction. Do not emit a marker_dict or total-hours guess.
score_evidence must contain exactly one record for each of c_param, co_order, co_method, co_param and co_chem. Cite answer spans and a brief basis tied to the unchanged rubric. Use observed/mixed only with spans. An absence-based deduction has an empty span list and basis=absence; insufficient evidence can have no span. A quote is not proof that the score is correct. Do not manufacture source evidence for missing content.
All facts must point to the submitted answer, not QUESTION, reference protocols, scoring examples, or prior knowledge.
Select exact quotes from the lossless line-unit index; occurrence is zero-based within that unit. The program resolves code-point offsets. Never repair spelling or complete a name. Preserve distinguishing full names and numeric suffixes. Repeated names are allowed as separate records with unique IDs.
Record distinct fluorophores/proteins and targets/antibodies separately. Relations must quote an explicit assignment. Co-occurrence, ordering, 'respectively' without a unique explicit mapping, or common families do not authorize guessed targets. Keep ambiguities as records. A generic summary does not replace more specific body mentions.
Enumerate operations, not only favorable fields. Duration refers to the exact operation span, including explicit range and unit; repeats need their own exact evidence. Never count one source duration twice. Preserve duration-free operations, exclusions and unknown phases. Classify every candidate duration as an operation, a total claim, or explicitly unresolved; the recall inventory is not gold and may include irrelevant mentions.
Set execution_scope=initial, conditional_or_future, or unknown for each operation. Conditional/future operations require the actual condition_evidence within the operation; preserve after-storage re-entry and maintenance separately. The timeline lists initial included operations only. Do not silently fold optional later operations into the initial endpoint or silently discard them. Their durations remain separate and an unqualified total may be unknown.
Included time phases: delipidation, decalcification, decolorization, RI matching, clearing treatment and reagent-transition wash. Exclude fixation, antibody incubation, staining, imaging, routine wash and continuing storage. Scope assignments remain provisional extraction judgments.
Do not sum times yourself. The program performs unit conversion and source-order sum, or an explicitly supported all-parallel maximum; alternatives/ranges/missing durations remain nullable with candidate bounds. Do not infer overnight=8h; that old convention is recorded separately. Total claims must remain separate from operation durations. Precedence edges must have evidence and must not form a cycle.
Keep method mentions and RI roles distinct. A sample RI is not a tissue/scale extraction. Never generate protocol_time_hours reference values. Return complete/partial/unknown coverage honestly; empty arrays are not evidence of completeness and will not count as repair success.
No examples or output fact values are supplied. Exact-span validity is not scientific confirmation. The old five direct scales and c_step are unchanged.
'''

def make_prompt(case,doc):
    import contextlib,io
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
        aid=c['anonymous_answer_id'];doc=document(c['model_response'],c['case_id'])
        require(doc['answer_sha256']==c['answer_sha256'] and rawsha(c['specific_question'])==c['question_sha256'],'ORIGINAL_DEVELOPMENT_IDENTITY')
        save(OUT/'source_documents'/f'{aid}.json',doc);save(OUT/'candidate_inventories'/f'{aid}.json',evidence_inventory(doc))
        prompt=make_prompt(c,doc);p=OUT/'prompts'/f'{aid}.txt';p.parent.mkdir(exist_ok=True);p.write_text(prompt,encoding='utf8')
        old=(baseline.OUT/'prompts'/f'{aid}_prompt.txt').read_text(encoding='utf8')
        # De-indexing the new prefix must reproduce the retained score rubric
        # exactly, apart from the named output-group header which has changed.
        units=[{'unit_id':u['unit_id'],'text':u['text']} for u in doc['units']]
        newprefix=prompt.split(INSTRUCTIONS)[0].replace('[LOSSLESS INDEXED MODEL_PROTOCOL; concatenate text fields in order]\n'+canonical(units),c['model_response'],1)
        oldprefix=old.split(SECTION3)[0].replace('- extraction.marker_dict, extraction.clearing_total_time_hours','- grounded_extraction source evidence records').replace('scores and extraction groups','scores and grounded_extraction groups').replace("and 'extraction'.","and 'grounded_extraction'.")
        require(newprefix==oldprefix,'ORIGINAL_SCORE_RUBRIC_CHANGED')
        require(prompt.endswith(baseline.parent.v2.reference_suffix(c)),'REFERENCE_SUFFIX_CHANGED')
        (OUT/'prompts'/f'{aid}_from_identity_v2.diff').write_text(''.join(difflib.unified_diff(old.splitlines(keepends=True),prompt.splitlines(keepends=True),fromfile=aid+'/identity_v2',tofile=aid+'/grounded_extraction_v1')),encoding='utf8')
        bound=len(prompt.encode('utf8'))+8192+256
        matrices.append({'anonymous_answer_id':aid,'question_id':c['question_id'],'case_id':c['case_id'],
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
    plan={'status':'candidate_offline_contract_pending_root_review','version':VERSION,'matrix':matrices,
        'planned_call_shape':'one_joint_payload_per_answer; no separate extraction/judge call','planned_development_answers':5,
        'new_judge_requests':0,'old_scores_and_human_package_modified':False,'no_heldout_scientific_records_read':True,
        'scores_schema_byte_equivalent_to_original_subtree':schema_value['properties']['scores']==read(baseline.OUT/'final_output_schema.json')['properties']['scores'],
        'EGES_function_and_knowledge_base_changed':False,'proposed_model':'existing local_qwen3_8b; root must freeze settings and budget before calls',
        'ollama_format_schema_supported_by_existing_transport':True,'schema_decoder_is_not_a_semantic_or_duplicate_key_guarantee':True,
        'schema_transport':'Complete schema object supplied via Ollama format; prompt contains a compact program-generated type catalog. No completed output examples.',
        'score_evidence_contract':'Exactly five distinct direct metrics. Answer spans resolved against the original answer; observed/mixed require a span, absence requires no span. Rubric correctness remains unverified.',
        'time_policy_delta':'Source-exact unique arithmetic; unknown overnight stays NA. The old 8-hour convention is a separate comparison. Conditional/future operations retain separate initial-scope bounds and an explicitly conditional envelope; no unqualified endpoint is silently selected. Excluded non-clearing schedule cues do not invalidate core time.',
        'target_policy_delta':'Entity arrays retain repeated full identities; only mechanically explicit lexical relationships project to legacy targets. Unrepresentable/missing mappings retain sidecar and per-component NA eligibility.',
        'known_limits':['Lexical candidate inventory is not a completeness gold standard.','Phase assignment and source-order serial schedule are declared provisional conventions.','Nested parallel subgroups are not supported; keep unknown rather than flatten.','The model may still omit or misclassify valid spans; this contract makes evidence auditable, not scientifically true.','Legacy marker_dict cannot represent all entity graphs; do not treat partial projection as complete EGES.'],
        'input_sha256':{str(p.resolve()):sha(p) for p in sourcepaths},'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'plan.json',plan)
    require(all(r['fits_40960'] for r in matrices),'CONSERVATIVE_CONTEXT_BOUND_EXCEEDED')
    text='''# Source-bound extraction v1: offline candidate

This package contains **no model generation and no expert labels**. It uses the unchanged five original development answers. No sealed confirmation or holdout scientific output was used.

One joint response preserves the original scores schema and adds five score-evidence records plus entity, relationship, operation and time evidence arrays. Every quoted span resolves to the lossless original-answer index. The source text, question, reference suffix, old score rubric and fixed evidence files are hash-bound. The old EGES functions and lookup tables remain untouched.

`convert(raw, document(answer, case_id))` uses the original strict duplicate-key parser, checks the new contract, and returns `legacy_runner_content` plus an explicit source-audit/conversion sidecar. The original provider raw content is retained separately; this conversion must never be represented as raw identity. `legacy_runner_payload.scores` is exactly the returned scores subtree. The downstream runner must save both raw EGES and any distinct component-availability gate.

Entity identity and relation confidence differ: valid full names do not imply a target assignment. Co-occurrence alone is not projected. Repeated names are records with IDs; one name with multiple targets is not silently overwritten. Missing relationships leave the old empty-target representation plus an explicit partial-projection flag. That flag is an audit warning, not a command to erase every partial EGES result: a source-supported valid known zero can still determine the old nullable-min label component. Unknown components must not erase unaffected known components.

Durations are parsed and aggregated by code, conditional on the supplied phase and scheduling classifications. Ranges, missing durations, unspecified overnight, ambiguity and total/sum conflicts remain nullable with bounds and causes. The old overnight=8 h convention is retained only in a separate comparison. Nested parallel groups are not flattened. Source-order summation is a declared provisional convention, not a scientific gold schedule.

Coverage candidates enumerate durations, numeric/name leads, and existing knowledge-base names. They are recall prompts and auditable omission checks, not scientific labels or a proof of completeness. Alternative/negated names must be retained with their actual status rather than treated as all simultaneously required. Exact spans do not establish correct entity type, phase, RI role, scoring judgment or complete scientific validity.

The complete JSON Schema belongs in the actual Ollama `format` object. The prompt contains compact shape documentation, not a populated example. The isolated synthetic transport probe replaces HTTP with an in-memory stub and verifies the full schema is serialized. It does not validate real generation behavior.

Reproduce offline from repository root:

```powershell
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_grounded_extraction_v1.py prepare
& 'C:/ClearEval/review_artifacts/bioprobench_2026-09-29/python_portable/python.exe' scripts/cce_grounded_extraction_v1.py self-check
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
