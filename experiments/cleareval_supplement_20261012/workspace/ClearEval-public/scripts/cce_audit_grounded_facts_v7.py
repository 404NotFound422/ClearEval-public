"""V7 DRAFT pre-generation mechanical audit against the unchanged development inventory.

No calls, repairs, semantic gold labels, held-out inputs, or score changes.
An exact entity string is not a verified biological role or target relation.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, math, re, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
try:
    import cce_grounded_extraction_v7 as grounded
except ModuleNotFoundError as exc:
    if exc.name != "cce_grounded_extraction_v7": raise
    grounded = None

BASE=ROOT/'artifacts/cce_validation/optimizer_20261010'
OUT=BASE/'fact_audit_checker_v7'
INVENTORY=BASE/'validation_design_v1/development_inventory_v1/explicit_development_fact_inventory.json'
INVENTORY_SHA='0dd8cb9dedcfcd41ec754011bb276f88d92229e7fbd5b83e410c52a687220b82'
GROUND_SHA='29432711bb16e5624dc666693b4ceb47bbc86da7aa42245ad132c76f77a0994c'
GROUND_SCHEMA_SHA='75a8a6afdb2ee20738d1e44990c50d2beb4ee9eb00b9e05837bffc6b856bcbd2'
INDEPENDENT_REVIEW=BASE/'grounded_v7_fact_review_design_v1/execution_selected/results.json'
INDEPENDENT_REVIEW_SHA='b8b81990f98dfcb832d994f5c4666e3ea1579d9cdc7d8a7c42694164c1932084'
SELECTED_SPECS=BASE/'grounded_v7_fact_review_design_v1/selected_scope_specs.json'
EXTENT_REVIEW=BASE/'grounded_v7_fact_review_design_v1/execution_extents/results.json'
EXTENT_REVIEW_SHA='020790585b9277775d85414617c21dbe5ecab974054cbdff1d7e493bba84cd85'
EXTENT_SPECS=BASE/'grounded_v7_fact_review_design_v1/source_extent_specs.json'
REPEAT_OMISSION_SPECS=BASE/'grounded_v7_fact_review_design_v1/repeat_omission_specs.json'
NUMERIC_ELIGIBILITY=BASE/'grounded_v7_fact_review_design_v1/numeric_eligibility/summary.json'
NUMERIC_ELIGIBILITY_SHA='c963dedda4404df12ebf9644b541fa2f480d35f79765e714d2fc635e1f19f726'
FINAL_FREEZE_AUTHORIZED=True
FINAL_INDEPENDENT_REVIEW=BASE/'grounded_v7_fact_review_design_v1/independent_review.json'
FINAL_INDEPENDENT_REVIEW_SHA='5d2299892f5bb6e1ca98054ac293fbeee3e913cba26b9fee47cec63a7ecab2dc'
REVIEWED_DRAFT_SNAPSHOT=OUT/'pre_freeze_authorization_snapshot/checker.py'
V6_CHECKER=ROOT/'scripts/cce_audit_grounded_facts_v6.py'
V6_CHECKER_SHA='6cdd65ebf1e34530e529e0be3e6185c1bf89f542af6a7e3dc35bcf3868f53634'
METADATA_REVIEW=BASE/'grounded_v7_fact_review_design_v1/execution_metadata/results.json'
METADATA_REVIEW_SHA='22c5b1fd6dbde2fe0b829354627d5ca2ba8e2441d9642154239916d31df6b6b7'
V5_CHECKER=ROOT/'scripts/cce_audit_grounded_facts_v5.py'
V5_CHECKER_SHA='205ffbfc867cb0e75baadbe918665bc4ada30dda196169d4ce1598af58f92a36'
V4_CHECKER=ROOT/'scripts/cce_audit_grounded_facts_v4.py'
V4_CHECKER_SHA='1c3766ddd7fa61ff371206a6602991335596897ea76a23912d18055bf175a92f'
V1_CHECKER=ROOT/'scripts/cce_audit_grounded_facts_v1.py'
V1_CHECKER_SHA='5ea98164b52d36c11669417e2267062483fac9dbfefce941744d0cccc1a032e2'
V2_CHECKER=ROOT/'scripts/cce_audit_grounded_facts_v2.py'
V2_CHECKER_SHA='8e04b1e68377db4f03c8a4a061ffad60be9bdb7cb42216bcd51b0e7222a88795'
V3_CHECKER=ROOT/'scripts/cce_audit_grounded_facts_v3.py'
V3_CHECKER_SHA='7269e656aeed10614a9c72f5c1143de30cbd359220fdfc6b0ead880362ff40ca'
IDS=['A01','A02','A03','A04','A05'];TOL=1e-12
VERSION='draft-development-fact-audit-v7'
CONVERSION_METADATA_KEY='grounded_extraction_v7'

def require(ok,why):
    if not ok:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rawsha(t):return hashlib.sha256(t.encode('utf8')).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,o):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def same(a,b):return a is None and b is None or finite(a) and finite(b) and abs(a-b)<=TOL
def overlap(a,b):return a['start']<b['end'] and b['start']<a['end']
def contains(a,b):return a['start']<=b['start'] and b['end']<=a['end']

def entity_literal(entities,entity_id):
    """Nullable unresolved relation endpoints remain unknown, never an alias."""
    entity=entities.get(entity_id)
    return entity['name']['quote'] if entity is not None else None

def span_check(span,text):
    require(span.get('source_text_sha256',span.get('answer_sha256'))==rawsha(text),'SOURCE_SPAN_HASH_MISMATCH')
    a,b=span['start'],span['end'];require(isinstance(a,int) and isinstance(b,int) and 0<=a<b<=len(text),'SOURCE_SPAN_OFFSETS')
    require(text[a:b]==span['quote'],'SOURCE_SPAN_QUOTE_MISMATCH')
    if 'quote_sha256' in span:require(rawsha(span['quote'])==span['quote_sha256'],'QUOTE_HASH_MISMATCH')
    return True

def source_hours(quote):
    """Independent numeric/unit conversion, not grounded's aggregate or parser."""
    # An uppercase compact dimension is not a source duration.  This guard is
    # independent of the candidate catalog and does not infer an elapsed time.
    if re.fullmatch(r'\s*\d+\s*D\s*',quote):return None
    hits=list(re.finditer(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|min|days?|d|小时|分钟|天)(?![A-Za-z])',quote,re.I))
    if len(hits)!=1:return None
    value=float(hits[0][1]);unit=hits[0][2].lower()
    if unit.startswith('min') or unit=='分钟':value/=60
    elif unit.startswith('d') or unit=='天':value*=24
    return value

def verify_inventory(require_module=True):
    require(sha(INVENTORY)==INVENTORY_SHA,'FROZEN_INVENTORY_CHANGED')
    require(sha(V1_CHECKER)==V1_CHECKER_SHA,'ORIGINAL_V1_CHECKER_CHANGED')
    require(sha(V2_CHECKER)==V2_CHECKER_SHA,'ORIGINAL_V2_CHECKER_CHANGED')
    require(sha(V3_CHECKER)==V3_CHECKER_SHA,'ORIGINAL_V3_CHECKER_CHANGED')
    require(sha(V4_CHECKER)==V4_CHECKER_SHA,'ORIGINAL_V4_CHECKER_CHANGED')
    require(sha(V5_CHECKER)==V5_CHECKER_SHA,'ORIGINAL_V5_CHECKER_CHANGED')
    require(sha(V6_CHECKER)==V6_CHECKER_SHA,'ORIGINAL_V6_CHECKER_CHANGED')
    if require_module:
        require(grounded is not None and GROUND_SHA is not None and GROUND_SCHEMA_SHA is not None,'V7_MODULE_NOT_BOUND_DRAFT_ONLY')
        require(sha(Path(grounded.__file__))==GROUND_SHA,'FROZEN_GROUNDED_MODULE_CHANGED')
        require(sha(grounded.OUT/'draft/schema.json')==GROUND_SCHEMA_SHA,'GROUNDED_SCHEMA_CHANGED')
    inv=read(INVENTORY);source=inv['source_cases'];require(sha(source['path'])==source['sha256'],'INVENTORY_SOURCE_CASE_FILE_CHANGED')
    raw=read(source['path']);cases=raw['cases'];require([c['anonymous_answer_id'] for c in inv['cases']]==IDS,'FIXED_INVENTORY_SELECTION')
    indexed={c['anonymous_answer_id']:c for c in cases};checks=[]
    for row in inv['cases']:
        aid=row['anonymous_answer_id'];case=indexed[aid];text=case['model_response']
        require(row['case_id']==case['case_id'] and row['question_id']==case['question_id'],'INVENTORY_CASE_IDENTITY')
        require(rawsha(text)==row['source']['answer_sha256'] and rawsha(case['specific_question'])==row['source']['question_sha256'],'INVENTORY_TEXT_HASH')
        pointer=row['source']['answer_json_pointer'].split('/')[1:];node=raw
        for key in pointer:node=node[int(key)] if isinstance(node,list) else node[key]
        require(node==text and row['source']['case_file']==source,'INVENTORY_SOURCE_POINTER')
        def walk(x):
            if isinstance(x,dict):
                if {'start','end','quote','source_text_sha256'}<=set(x):span_check(x,text)
                for value in x.values():walk(value)
            elif isinstance(x,list):
                for value in x:walk(value)
        walk(row)
        for comp in row['time']['components']+row['time']['excluded_or_conditional_duration_mentions']:
            require(same(source_hours(comp['duration_span']['quote']),comp['hours']),'INVENTORY_SOURCE_DURATION_UNIT_MISMATCH')
            a=comp['step_label_span']['start'];b=text.find('\n',a);b=len(text) if b<0 else b
            require(rawsha(text[a:b])==comp['full_step_text_sha256'],'INVENTORY_FULL_STEP_LINE_HASH')
        require(same(sum(x['hours'] for x in row['time']['components']),row['time']['computed_sum_hours']),'INVENTORY_INITIAL_SUM')
        checks.append({'anonymous_answer_id':aid,'source_bound':True,'core_components':len(row['time']['components']),
            'explicit_names':len(row['explicit_names_to_retain']),'source_component_sum_hours':row['time']['computed_sum_hours']})
    counts={'methods':len(inv['cases']),'explicit_selected_or_used_entity_names':sum(c['explicit_names'] for c in checks),
            'source_core_duration_components':sum(c['core_components'] for c in checks),
            'explicit_label_target_relations':sum(len(c['explicitly_supported_label_relations']) for c in inv['cases']),
            'ambiguity_groups':sum(len(c['ambiguous_relations_or_alternatives']) for c in inv['cases'])}
    require(all(inv['fixed_denominators'][k]==v for k,v in counts.items()),'INVENTORY_DENOMINATOR_MISMATCH')
    return inv,indexed,checks

def name_audit(expected,entities,available=True):
    rows=[]
    for fact in expected:
        name=fact['name'];exact=[e for e in entities if e['name']['quote']==name]
        contained=[e for e in entities if name in e['name']['quote'] and e['name']['quote']!=name]
        status='exact' if exact else 'contained-only' if contained else 'missing' if available else 'unavailable'
        rows.append({'expected_name':name,'inventory_source_span':fact['source_span'],'status':status,
            'exact_record_ids':[e['id'] for e in exact],'contained_only_record_ids':[e['id'] for e in contained],
            'same_inventory_occurrence_present':any(contains(e['name'],fact['source_span']) or contains(fact['source_span'],e['name']) for e in exact),
            'returned_roles':[{'id':e['id'],'literal_name':e['name']['quote'],'kind':e['kind'],'usage':e['usage']} for e in exact+contained],
            'semantic_role_or_target_verified':False,
            'boundary':'Literal containment such as anti-GFP containing GFP is not exact identity or verified semantic equivalence.'})
    return rows

def atomic_name_risks(name):
    """Finite structural concerns, not an ontology or a closed name whitelist."""
    concerns=[]
    if not isinstance(name,str) or not name or name!=name.strip():return ['empty_or_padding']
    if re.search(r'[\r\n]|^\s*(?:\*\*|#{1,6}\s)',name):concerns.append('markup_or_multiline_as_name')
    if re.search(r'\b(?:chosen|selected)\s+(?:method|label(?:l?ing)?|signal|marker)s?\s*[:：]|^(?:method|labels?|markers?|方法|标记)\s*[:：]',name,re.I):concerns.append('declaration_header_as_name')
    if re.search(r'\[|\]|\s[/+;；]\s|,\s+|，',name):concerns.append('list_or_alternative_as_name')
    if re.search(r'\b(?:is used|is selected|can preserve|optimi[sz]ed to)\b',name,re.I):concerns.append('assertion_as_name')
    return concerns

def independent_name_binding_audit(g,source_text,available):
    records=[]
    for group in ['method_mentions','entities']:
        for entity in g.get(group,[]):
            name=entity['name'];support=entity.get('supporting_evidence');literal=entity.get('literal_name')
            span_check(name,source_text)
            if support:span_check(support,source_text)
            risks=atomic_name_risks(name['quote']);same_literal=literal==name['quote']
            mentions=[]
            if support and isinstance(literal,str):
                for match in re.finditer(re.escape(literal),support['quote']):
                    start=support['start']+match.start();end=start+len(literal)
                    # Boundaries are documented independently, without calling
                    # the evaluated module's resolver or name policy.
                    before=source_text[max(0,start-32):start];after=source_text[end:support.get('context_end',support['end'])]
                    clipped_left=bool(start and re.match(r'[A-Za-z0-9_]',source_text[start-1]) and re.match(r'[A-Za-z0-9_]',literal[:1]))
                    clipped_right=bool(end<len(source_text) and re.match(r'[A-Za-z0-9_]',source_text[end]) and re.match(r'[A-Za-z0-9_]',literal[-1:]))
                    anti=bool(re.search(r'\banti[-\s]+$',before,re.I))
                    suffix=bool(re.match(r'^\s+\d{2,4}\b(?!\s*(?:[%％]|[munpμµ]M\b|hours?\b|minutes?\b|days?\b))',after,re.I))
                    charge=bool(re.match(r'[+−-](?![A-Za-z0-9_])',source_text[end:]) and re.search(r'[A-Za-z0-9]$',literal))
                    mentions.append({'start':start,'end':end,'omitted_anti_qualifier':anti,'omitted_numeric_suffix':suffix,
                        'omitted_terminal_charge_or_positive_suffix':charge,
                        'clipped_ascii_boundary':clipped_left or clipped_right,'complete_under_finite_boundary_checks':not (anti or suffix or charge or clipped_left or clipped_right)})
            complete=[m for m in mentions if m['complete_under_finite_boundary_checks']]
            occurrence=entity.get('name_occurrence')
            occurrence_valid=isinstance(occurrence,int) and not isinstance(occurrence,bool) and 0<=occurrence<len(mentions)
            chosen=mentions[occurrence] if occurrence_valid else None
            precise=bool(support and contains(support,name) and chosen and chosen['complete_under_finite_boundary_checks'] and chosen['start']==name['start'] and chosen['end']==name['end'])
            records.append({'group':group,'record_id':entity['id'],'literal_name':literal,'derived_name':name,'supporting_evidence':support,
                'same_literal_and_derived_name':same_literal,'structural_atomicity_concerns':risks,'independent_occurrences':mentions,
                'declared_name_occurrence':occurrence,'declared_occurrence_valid':occurrence_valid,
                'literal_occurrence_count':len(mentions),'complete_literal_occurrence_count':len(complete),'selected_complete_literal_binding':precise,
                'source_literal_binding_verified':same_literal and precise,
                'binding_rule':'Explicit zero-based occurrence among all exact literal occurrences in the supplied source unit; validate the selected occurrence without skipping incomplete boundaries or renumbering.', 
                'atomicity_has_no_detected_structural_concern':not risks,'source_binding_is_not_atomicity_proof':True,
                'returned_kind':entity.get('kind'),'returned_usage':entity.get('usage'),'semantic_identity_confirmed':False})
    return {'available':available,'records':records,'source_literal_binding_records':sum(r['source_literal_binding_verified'] for r in records),
        'atomicity_concern_records':sum(bool(r['structural_atomicity_concerns']) for r in records),
        'not_an_exhaustive_semantic_name_validator':True}

def native_source_support(name,evidence,context,atomic_risks):
    """Predeclared finite source-declaration diagnostics; no KB/question facts."""
    native=bool(re.search(r'\b(?:native|endogenous|intrinsic)\b|内源|原生',evidence,re.I))
    negative=bool(re.search(r'\b(?:not|without|lost|quenched|absent)\b|不使用|不用|已丢失|已淬灭',evidence,re.I))
    capability=bool(re.search(r'\b(?:may|can|like)\b|\boptimi[sz]ed\s+(?:to|for)\b|e\.g\.|\bfor example\b|\bsuch as\b|例如|比如|能够|可以',evidence,re.I)
        or re.search(r'\b(?:method|technique)\b[^.;\n]*(?:\bcan\b|\bmay\b|\boptimi[sz]ed\b)|方法[^。\n]*(?:能够|可以)',context,re.I))
    alternative=bool(re.search(r'\b(?:either|or|alternative|instead)\b|备选|替代|任选',evidence,re.I))
    conditional=bool(re.search(r'\b(?:if|unless|conditional|in another)\b|如果|条件|另一',context,re.I))
    selected=bool(re.search(r'(?:chosen|selected)\s+(?:label(?:l?ing)?|signals?|markers?)\s*[:：][^\n]*'+re.escape(name),context,re.I))
    explicit_use=bool(re.search(r'\b(?:use|select|retain|preserve|used|retained|preserved)\b|选用|采用|保留',evidence,re.I))
    occurrence=len(list(re.finditer(re.escape(name),evidence))) if name else 0
    support=not atomic_risks and occurrence==1 and native and (selected or explicit_use) and not (negative or capability or alternative or conditional)
    state='supported_source_declaration_under_finite_checks' if support else 'non_atomic_name' if atomic_risks else 'negative_or_loss_source' if negative else 'capability_or_example_not_actual_native_use' if capability else 'conditional_or_alternative_scope' if conditional or alternative else 'insufficient_source_declaration'
    return {'state':state,'mechanically_supported_source_declaration':support,'native_literal':native,'explicit_used_or_selected':selected or explicit_use,
        'capability_or_example':capability,'negative_or_loss':negative,'conditional':conditional,'alternative':alternative,
        'complete_literal_occurrences':occurrence,'proposed_or_selected_usage_is_not_physical_execution':True,'semantic_native_use_verified':False,'biological_preservation_verified':False}

def strict_raw_payload(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'DUPLICATE_RAW_KEY:'+key);result[key]=value
        return result
    def constant(value):raise ValueError('NONFINITE_RAW_JSON:'+value)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)

def raw_name_presence(expected,raw):
    state='unavailable';payload=None;error=None
    if raw is not None:
        try:
            payload=strict_raw_payload(raw);require(isinstance(payload,dict),'RAW_ROOT_NOT_OBJECT')
            require(isinstance(payload.get('grounded_extraction'),dict),'RAW_GROUNDED_FIELD_MISSING');state='strictly_parseable'
        except (ValueError,TypeError) as exc:error=str(exc)
    entities=(payload or {}).get('grounded_extraction',{}).get('entities',[]) if state=='strictly_parseable' else []
    if not isinstance(entities,list):entities=[];state='invalid_entities_shape'
    rows=[]
    for fact in expected:
        hits=[e['id'] for e in entities if isinstance(e,dict) and e.get('literal_name')==fact['name'] and isinstance(e.get('id'),str)]
        rows.append({'expected_name':fact['name'],'status':'raw_literal_present' if hits else 'raw_literal_absent' if state=='strictly_parseable' else 'unavailable',
            'record_ids':hits,'does_not_establish_source_binding_or_successful_conversion':True})
    return {'state':state,'parse_error':error,'names':rows,'fixed_inventory_denominator':len(expected),'strict_raw_json_without_repairs':True}

def duration_audit(components,operations,initial,available=True):
    rows=[]
    for fact in components:
        matches=[o for o in operations if o.get('duration') and contains(fact['duration_span'],o['duration'])]
        observations=[]
        for o in matches:
            actual=source_hours(o['duration']['quote']);parsed=o.get('parsed_duration',{});bound=parsed.get('bounds_hours')
            parsed_agrees=isinstance(bound,list) and len(bound)==2 and same(bound[0],actual) and same(bound[1],actual)
            binding=o.get('duration_binding',{})
            observations.append({'operation_id':o['id'],'duration_span':o['duration'],'literal_unit_hours':actual,
                'equals_inventory_hours':same(actual,fact['hours']),'saved_parsed_duration_agrees':parsed_agrees,
                'phase':o['phase'],'execution_scope':o['execution_scope'],'repeat_count':o.get('repeat_count'),
                'operation_contains_duration':contains(o['operation'],o['duration']),
                'source_record_binding':binding,'source_record_binding_valid':binding.get('valid') is True,
                'retained_as_initial_included_operation':o['phase'] in grounded.INCLUDE and o['execution_scope']=='initial',
                'condition_evidence':o.get('condition_evidence')})
        exact=any(r['equals_inventory_hours'] and r['saved_parsed_duration_agrees'] and r['operation_contains_duration'] for r in observations)
        legacy_status='source_numeric_retained' if exact else 'span_present_numeric_mismatch' if matches else 'missing' if available else 'unavailable'
        literal_retained=any(r['equals_inventory_hours'] for r in observations)
        record_retained=any(r['equals_inventory_hours'] and r['saved_parsed_duration_agrees'] and r['source_record_binding_valid'] for r in observations)
        initial_retained=any(r['equals_inventory_hours'] and r['saved_parsed_duration_agrees'] and r['source_record_binding_valid'] and r['retained_as_initial_included_operation'] for r in observations)
        status='record_bound_numeric_retained' if record_retained else 'literal_numeric_retained_projection_unresolved' if literal_retained else 'span_present_numeric_mismatch' if matches else 'missing' if available else 'unavailable'
        rows.append({'step_label':fact['step_label'],'inventory_hours':fact['hours'],'inventory_duration_span':fact['duration_span'],
            'inventory_scope':'initial_core' if initial else fact.get('excluded_scope','excluded_or_conditional'),
            'status':status,'observations':observations,
            'literal_source_numeric_value_retained':literal_retained if available else None,
            'record_bound_numeric_retained':record_retained if available else None,
            'legacy_only':{'v1_short_quote_containment_status':legacy_status},
            'primary_status_definition':'Independent literal value at the frozen source occurrence, parsed numeric agreement, and verified source-record binding; returned initial scope is separate.',
            'initial_scope_preserved':initial_retained if initial and available else None,
            'phase_semantics_verified':False,'multiple_matching_operation_records':len(matches)>1})
    return rows

def relation_audit(expected,g,projection,available):
    ents={e['id']:e for e in g.get('entities',[])};mapping=projection.get('extraction',{}).get('marker_dict',{});rows=[]
    for fact in expected:
        edges=[]
        for edge in g.get('relations',[]):
            f=entity_literal(ents,edge['fluor_entity_id']);t=entity_literal(ents,edge['target_entity_id'])
            if f==fact['label'] and t==fact['target']:
                edges.append({'id':edge['id'],'status':edge['status'],'projection_allowed':edge['projection_allowed'],
                    'mechanical_relation_state':edge['mechanical_relation_state'],'evidence_span':edge['evidence'],
                    'relation_local_mentions':edge.get('relation_local_mentions'),
                    'primary_entity_spans_preserved':edge.get('primary_entity_spans_preserved'),
                    'inventory_relation_evidence_overlap':overlap(edge['evidence'],fact['source_span'])})
        projected=mapping.get(fact['label'])==fact['target']
        rows.append({'label':fact['label'],'target':fact['target'],'inventory_source_span':fact['source_span'],
            'returned_exact_endpoint_edges':edges,'edge_retained':bool(edges) if available else None,
            'exact_legacy_projection_retained':projected if available else None,
            'edge_present_but_projection_lost':bool(edges) and not projected if available else None,
            'semantic_relation_verified':False,'inventory_relation_is_expert_gold':False})
    return rows

def ambiguity_audit(expected,g,projection,available):
    rows=[];entities=g.get('entities',[]);ents={e['id']:e for e in entities};mapping=projection.get('extraction',{}).get('marker_dict',{})
    for fact in expected:
        spans=fact.get('source_spans') or [fact['source_span']]
        unresolved=[u for u in g.get('coverage',{}).get('unresolved',[]) if any(overlap(u['evidence'],s) for s in spans)]
        names=fact.get('named_options',[])+fact.get('known_labels',[])+fact.get('known_targets',[])
        records=[e for e in entities if e['name']['quote'] in names]
        edges=[r for r in g.get('relations',[]) if entity_literal(ents,r['fluor_entity_id']) in names or entity_literal(ents,r['target_entity_id']) in names]
        uncertain=any(e['usage'] in ['alternative','unknown'] for e in records) or any(r['status'] in ['ambiguous','unknown'] for r in edges) or bool(unresolved)
        specific=[{'label':k,'target':v} for k,v in mapping.items() if k in fact.get('known_labels',[]) and v]
        all_options_used=all(any(e['name']['quote']==n and e['usage']=='used' for e in records) for n in fact.get('named_options',[])) if fact.get('named_options') else None
        status='unavailable' if not available else 'specific_projection_for_inventory_ambiguous_group' if specific else 'explicit_ambiguity_retained' if uncertain else 'no_specific_projection_but_ambiguity_not_explicit'
        rows.append({'kind':fact['kind'],'inventory_spans':spans,'status':status,
            'retained_name_records':[{'id':e['id'],'name':e['name']['quote'],'kind':e['kind'],'usage':e['usage']} for e in records],
            'unresolved_evidence':unresolved,'specific_legacy_projections':specific,'all_slash_options_marked_used':all_options_used,
            'semantic_adjudication_pending':True})
    return rows

def ri_evidence_audit(expected_span,expected_value,mentions):
    """Exact span, containment, literal numeric value and projected RI stay distinct."""
    rows=[]
    for mention in mentions:
        span=mention['value'];numbers=re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])',span['quote'])
        unique=float(numbers[0]) if len(numbers)==1 else None
        rows.append({'id':mention['id'],'returned_role':mention['role'],'returned_span':span,
            'exact_inventory_span':bool(expected_span and span['start']==expected_span['start'] and span['end']==expected_span['end']),
            'returned_quote_contains_inventory_numeric_occurrence':bool(expected_span and contains(span,expected_span)),
            'inventory_quote_contains_returned_span':bool(expected_span and contains(expected_span,span)),
            'independent_unique_numeric_value':unique,
            'unique_value_equals_inventory':same(unique,expected_value) if expected_value is not None else None,
            'semantic_RI_role_verified':False})
    return rows

def intrinsic_identity_audit(g,projection,source_text,available):
    """Audit a new typed adapter separately from the frozen three dye pairs.

    These literal cue checks do not establish biological preservation, entity
    ontology, intended use, or task fulfillment. No question or KB is consulted.
    """
    entities={e['id']:e for e in g.get('entities',[])}
    conversions={r['intrinsic_record_id']:r for r in projection.get('intrinsic_identity_conversion',[])}
    mapping=projection.get('extraction',{}).get('marker_dict',{});rows=[]
    for record in g.get('intrinsic_signals',[]):
        entity=entities.get(record['entity_id']);require(entity is not None,'INTRINSIC_AUDIT_DANGLING_ENTITY')
        evidence=record['evidence'];name=entity['name']['quote'];entry=conversions.get(record['id'])
        require(entry is not None,'INTRINSIC_CONVERSION_RECORD_MISSING')
        if source_text is not None:
            span_check(evidence,source_text);span_check(entity['name'],source_text)
        occurrences=list(re.finditer(r'(?<![\w-])'+re.escape(name)+r'(?![\w-])',evidence['quote']))
        clause=evidence['quote'];context=evidence.get('context',clause)
        native=bool(re.search(r'\b(?:native|endogenous|intrinsic)\b|内源|原生',clause,re.I))
        affirmative=bool(re.search(r'\b(?:selected|chosen|used|retained|preserved)\b|选用|选择|采用|保留',context,re.I))
        negative=bool(re.search(r'\b(?:not|without|lost|quenched|absent)\b|不使用|不用|已丢失|已淬灭',clause,re.I))
        capability=bool(re.search(r'\b(?:may|can)\b|e\.g\.|\bfor example\b|\bsuch as\b|例如|比如|能够|可以',clause,re.I))
        alternative=bool(re.search(r'\b(?:either|or|alternative|instead)\b|备选|替代|任选',clause,re.I))
        antibody_only=bool(re.search(r'antibody[- ]only|only\s+(?:antibody|immuno)|仅抗体|仅免疫',clause,re.I))
        atomic_risks=atomic_name_risks(name)
        source_support=native_source_support(name,clause,context,atomic_risks)
        applied=entry.get('legacy_same_name_projection_applied') is True
        require(entry.get('entity_id')==entity['id'] and entry.get('exact_source_name')==name,'INTRINSIC_CONVERSION_IDENTITY_MISMATCH')
        require(not applied or entry.get('legacy_value_after')==name and mapping.get(name)==name,'INTRINSIC_SAME_NAME_SERIALIZATION_MISMATCH')
        require(entry.get('question_requirement_or_preserved_biological_signal_claimed') is False,'INTRINSIC_UNSUPPORTED_TASK_OR_PRESERVATION_CLAIM')
        rows.append({'record_id':record['id'],'entity_id':entity['id'],'literal_name':name,
            'source_entity_span':entity['name'],'source_evidence_span':evidence,'returned_status':record['status'],
            'returned_entity_kind':entity['kind'],'returned_entity_usage':entity['usage'],
            'independent_literal_cues':{'complete_name_occurrence_count_in_evidence':len(occurrences),
                'native_declaration':native,'affirmative_context':affirmative,'negation_or_loss':negative,
                'capability_or_example':capability,'alternative':alternative,'antibody_only':antibody_only},
            'module_identity_policy':record.get('identity_policy'),'legacy_adapter_entry':entry,
            'same_name_legacy_projection_applied':applied,'scientific_input_changed':applied,
            'independent_atomicity_concerns':atomic_risks,'independent_source_declaration_support':source_support,
            'serialization_without_independent_source_support':applied and not source_support['mechanically_supported_source_declaration'],
            'independent_cue_concern_if_applied':applied and (len(occurrences)!=1 or not native or not affirmative or negative or capability or alternative or antibody_only),
            'question_or_recommendation_used_by_this_audit':False,'biological_preservation_verified':False,
            'task_fulfillment_verified':False,'included_in_fixed_dye_relation_denominator':False})
    return {'available':available,'returned_records':len(rows),'same_name_serializations':sum(r['same_name_legacy_projection_applied'] for r in rows),
        'independent_cue_concerns':sum(r['independent_cue_concern_if_applied'] for r in rows),'records':rows,
        'source_declaration_support_states':dict(Counter(r['independent_source_declaration_support']['state'] for r in rows)),
        'serializations_without_independent_source_support':sum(r['serialization_without_independent_source_support'] for r in rows),
        'cue_zero_is_not_atomic_or_semantic_confirmation':True,
        'fixed_inventory_relation_denominator_unchanged':3,'not_a_completeness_or_accuracy_denominator':True}

def audit_case(fact,conversion,source_text=None):
    available=conversion is not None;g=conversion['source_audit']['resolved'] if available else {};projection=conversion['legacy_projection'] if available else {}
    names=name_audit(fact['explicit_names_to_retain'],g.get('entities',[]),available)
    core=duration_audit(fact['time']['components'],g.get('operations',[]),True,available)
    outside=duration_audit(fact['time']['excluded_or_conditional_duration_mentions'],g.get('operations',[]),False,available)
    retained=[r for r in core if r['record_bound_numeric_retained'] is True];all_retained=len(retained)==len(core) and available
    included=[r for r in core if r['initial_scope_preserved']];clock=projection.get('time_calculation',{});ex=projection.get('extraction',{})
    method_records=[m for m in g.get('method_mentions',[]) if m['name']['quote']==fact['method']['value']]
    ri=fact['RI'];ri_mentions=g.get('ri_mentions',[])
    return {'anonymous_answer_id':fact['anonymous_answer_id'],'question_id':fact['question_id'],
        'conversion_available':available,'names':names,'core_duration_components':core,'excluded_or_conditional_duration_components':outside,
        'independent_name_bindings':independent_name_binding_audit(g,source_text,available),
        'method':{'inventory_value':fact['method']['value'],'literal_record_present':bool(method_records) if available else None,
            'projected_method':ex.get('method_name'),'equals_inventory_literal':ex.get('method_name')==fact['method']['value'] if available else None,
            'selection_semantics_verified':False},
        'time_scope_comparison':{'inventory_initial_scope':fact['time']['scope'],'inventory_initial_sum_hours':fact['time']['computed_sum_hours'],
            'expected_core_components':len(core),'retained_numeric_components':len(retained),'returned_initial_included_components':len(included),
            'literal_numeric_components_retained':sum(r['literal_source_numeric_value_retained'] is True for r in core),
            'record_bound_numeric_components_retained':sum(r['record_bound_numeric_retained'] is True for r in core),
            'all_initial_scope_components_retained':available and len(included)==len(core),
            'hours_from_retained_inventory_components':sum(r['inventory_hours'] for r in retained) if retained else None,
            'all_inventory_initial_numeric_components_retained':all_retained,'returned_initial_scope_bounds':clock.get('initial_scope_candidate_bounds_hours'),
            'returned_primary_total_hours':ex.get('clearing_total_time_hours'),'primary_total_equals_inventory_initial_scope_sum':same(ex.get('clearing_total_time_hours'),fact['time']['computed_sum_hours']) if available else None,
            'initial_facts_available_despite_primary_NA':all_retained and ex.get('clearing_total_time_hours') is None,
            'primary_NA_with_literal_numeric_gaps':available and ex.get('clearing_total_time_hours') is None and any(r['literal_source_numeric_value_retained'] is not True for r in core),
            'primary_NA_with_record_binding_gaps':available and ex.get('clearing_total_time_hours') is None and not all_retained,
            'primary_NA_with_scope_disagreement_or_unknown':available and ex.get('clearing_total_time_hours') is None and all_retained and len(included)!=len(core),
            'returned_conditional_operations':clock.get('conditional_operations'),'returned_endpoint_scope':clock.get('endpoint_scope'),
            'returned_coverage_scopes':clock.get('coverage_scopes'),
            'returned_time_issues':clock.get('issues'),'inventory_sum_is_universal_endpoint':False},
        'relations':relation_audit(fact['explicitly_supported_label_relations'],g,projection,available),
        'ambiguities':ambiguity_audit(fact['ambiguous_relations_or_alternatives'],g,projection,available),
        'intrinsic_identity':intrinsic_identity_audit(g,projection,source_text,available),
        'RI':{'inventory_reagent_value':ri['reagent_value'],'inventory_numeric_span':ri['numeric_source_span'],
            'returned_reagent_value':ex.get('reagent_ri_value'),'reagent_literal_numeric_agreement':same(ri['reagent_value'],ex.get('reagent_ri_value')) if available else None,
            'numeric_span_retained':any(r['role']=='reagent_final' and contains(ri['numeric_source_span'],r['value']) for r in ri_mentions) if ri['numeric_source_span'] else None,
            'evidence_representation_diagnostics':ri_evidence_audit(ri['numeric_source_span'],ri['reagent_value'],ri_mentions),
            'module_RI_projection_audit':projection.get('ri_projection_audit'),
            'sample_target_unknown_preserved':ex.get('sample_ri_value') is None if available else None,
            'RI_role_semantics_verified':False},
        'contract_protocol_time_null_preserved':ex.get('protocol_time_hours') is None if available else None,
        'scientific_or_expert_accuracy_claimed':False}

def load_conversion(batch,cell,source_case):
    """Actual trial and provider identity, never trust a detached replay file."""
    trial_id=cell['planned_trial_id'];p=batch/'run/trials'/f'{trial_id}.json'
    if not p.exists():return None,{'state':'pending_actual_trial','trial_id':trial_id},[],None
    t=read(p);require(t['identity']==cell['identity'] and t['case_id']==source_case['case_id'],'ACTUAL_TRIAL_IDENTITY')
    conversion=(t.get('evaluation',{}).get(CONVERSION_METADATA_KEY) or {}).get('conversion')
    errors=(t.get('evaluation',{}).get(CONVERSION_METADATA_KEY) or {}).get('conversion_errors')
    files=[p];attempt=batch/'run/attempts'/f'{trial_id}_1';receipt=attempt/'request_receipt.json'
    require(receipt.exists(),'ACTUAL_RECEIPT_MISSING');r=read(receipt);files.append(receipt)
    source_id=grounded.source_id_for_case(source_case)
    doc=grounded.document(source_case['model_response'],source_id)
    stored_doc=batch/'source_documents'/f"{source_case['anonymous_answer_id']}.json"
    require(stored_doc.exists() and read(stored_doc)==doc,'OPAQUE_SOURCE_DOCUMENT_IDENTITY')
    files.append(stored_doc)
    provider=attempt/'provider_response.json';raw=None
    if provider.exists():
        files.append(provider);body=read(provider);raw=body.get('response')
        require(raw is None or isinstance(raw,str),'PROVIDER_RAW_NOT_TEXT')
    if conversion is not None:
        require(raw is not None,'ORIGINAL_PROVIDER_MISSING')
        replay=grounded.convert(raw,doc);require(replay==conversion,'CONVERSION_OR_SOURCE_REPLAY_MISMATCH')
        require(conversion['raw_response_sha256']==rawsha(raw),'RAW_CONTENT_SHA_MISMATCH')
    return conversion,{'state':'auditable_conversion' if conversion is not None else 'actual_trial_without_valid_conversion',
        'trial_id':trial_id,'trial_status':t['status'],'request_id':r['request_id'],'conversion_errors':errors},files,raw

def analyze(batch,out):
    inv,sources,inventory_checks=verify_inventory();freeze=read(OUT/'freeze.json')
    require(freeze['checker_sha256']==sha(__file__),'CHECKER_CHANGED_AFTER_PREGENERATION_FREEZE')
    contract_path=batch/'expected_contract.json';contract=read(contract_path)
    runtime_contexts=[m['settings'].get('num_ctx') for m in contract.get('models',[])]
    require(runtime_contexts and all(v==98304 for v in runtime_contexts),'V4_DECLARED_CONTEXT_BUNDLE_MISMATCH')
    cases=read(batch/'cases.json')['cases'];indexed={c['anonymous_answer_id']:c for c in cases}
    require(list(indexed)==IDS and len(cases)==5,'BATCH_NOT_EXACT_FIXED_FIVE')
    matrix=read(batch/'matrix.json');cells={c['anonymous_answer_id']:c for c in matrix}
    require(set(cells)==set(IDS) and len(matrix)==5,'BATCH_MATRIX_NOT_EXACT_FIXED_FIVE')
    rows=[];files=[INVENTORY,Path(inv['source_cases']['path']),batch/'cases.json',batch/'matrix.json',contract_path,OUT/'freeze.json',Path(__file__)]
    for fact in inv['cases']:
        aid=fact['anonymous_answer_id'];case=indexed[aid];original=sources[aid]
        require(all(case[k]==original[k] for k in ['case_id','question_id','model_response','specific_question']),'BATCH_ORIGINAL_TEXT_IDENTITY')
        conversion,provenance,inputs,raw=load_conversion(batch,cells[aid],case);row=audit_case(fact,conversion,case['model_response'])
        row['raw_name_presence']=raw_name_presence(fact['explicit_names_to_retain'],raw)
        row['actual_trial']=provenance;row['source_answer_sha256']=rawsha(case['model_response']);rows.append(row);files+=inputs
    name_counts=Counter(r['status'] for c in rows for r in c['names']);duration_counts=Counter(r['status'] for c in rows for r in c['core_duration_components'])
    summary={'version':VERSION,'status':'complete' if all(r['actual_trial']['state']!='pending_actual_trial' for r in rows) else 'pending_actual_trials',
        'batch_out':str(batch.resolve()),'fixed_answers':5,'auditable_conversions':sum(r['conversion_available'] for r in rows),
        'explicit_names_denominator':16,'name_states':dict(name_counts),'core_duration_denominator':31,'core_duration_states':dict(duration_counts),
        'raw_name_presence_separate':{'fixed_denominator':16,'states':dict(Counter(n['status'] for r in rows for n in r['raw_name_presence']['names'])),
            'strictly_parseable_answers':sum(r['raw_name_presence']['state']=='strictly_parseable' for r in rows),
            'does_not_count_as_conversion_or_source_validity':True},
        'independent_name_binding_summary':{'returned_records':sum(len(r['independent_name_bindings']['records']) for r in rows),
            'source_literal_binding_records':sum(r['independent_name_bindings']['source_literal_binding_records'] for r in rows),
            'atomicity_concern_records':sum(r['independent_name_bindings']['atomicity_concern_records'] for r in rows),
            'not_an_accuracy_denominator':True},
        'core_initial_scope_retained':sum(bool(d['initial_scope_preserved']) for r in rows for d in r['core_duration_components']),
        'literal_numeric_components_retained':sum(d['literal_source_numeric_value_retained'] is True for r in rows for d in r['core_duration_components']),
        'record_bound_numeric_components_retained':sum(d['record_bound_numeric_retained'] is True for r in rows for d in r['core_duration_components']),
        'legacy_only':{'v1_short_quote_duration_states':dict(Counter(d['legacy_only']['v1_short_quote_containment_status'] for r in rows for d in r['core_duration_components'])),
            'not_the_primary_v7_fact_retention_definition':True},
        'explicit_relation_denominator':3,'exact_endpoint_edges_retained':sum(bool(e['edge_retained']) for r in rows for e in r['relations']),
        'exact_relation_projections_retained':sum(bool(e['exact_legacy_projection_retained']) for r in rows for e in r['relations']),
        'ambiguity_group_denominator':2,'ambiguity_states':dict(Counter(a['status'] for r in rows for a in r['ambiguities'])),
        'intrinsic_identity_separate_from_fixed_relation_inventory':{'returned_records':sum(r['intrinsic_identity']['returned_records'] for r in rows),
            'same_name_serializations':sum(r['intrinsic_identity']['same_name_serializations'] for r in rows),
            'independent_literal_cue_concerns':sum(r['intrinsic_identity']['independent_cue_concerns'] for r in rows),
            'source_declaration_support_states':dict(Counter(record['independent_source_declaration_support']['state'] for r in rows for record in r['intrinsic_identity']['records'])),
            'serializations_without_independent_source_support':sum(r['intrinsic_identity']['serializations_without_independent_source_support'] for r in rows),
            'cue_zero_is_not_semantic_or_atomic_identity_confirmation':True,
            'accuracy_or_completeness_denominator':False},
        'answers_all_inventory_initial_numeric_components_retained':sum(r['time_scope_comparison']['all_inventory_initial_numeric_components_retained'] for r in rows),
        'answers_all_returned_initial_scope_components_retained':sum(r['time_scope_comparison']['all_initial_scope_components_retained'] for r in rows),
        'answers_primary_NA_despite_all_inventory_numeric_components_retained':sum(r['time_scope_comparison']['initial_facts_available_despite_primary_NA'] for r in rows),
        'answers_primary_NA_with_literal_numeric_gaps':sum(r['time_scope_comparison']['primary_NA_with_literal_numeric_gaps'] for r in rows),
        'answers_primary_NA_with_record_binding_gaps':sum(r['time_scope_comparison']['primary_NA_with_record_binding_gaps'] for r in rows),
        'answers_primary_NA_with_scope_disagreement_or_unknown':sum(r['time_scope_comparison']['primary_NA_with_scope_disagreement_or_unknown'] for r in rows),
        'tolerance':TOL,'new_model_calls':0,'expert_labels_created':0,'scientific_accuracy_claimed':False,
        'runtime_context_lengths_from_contract':runtime_contexts,
        'version_change_is_single_intervention':False,
        'bundle_boundary':'V7 adds per-operation eligible D/P metadata computed by frozen v6 binding rules and generic prompt clarification. Arithmetic, native policy, coverage and source gates remain unchanged from v6. Metadata eligibility is not a model selection or scientific-validity claim; the version is a metadata/prompt bundle.',
        'scope':'Frozen model-source inventory plus mechanical identity/unit/offset diagnostics. Exact strings are not semantic roles; inventory relationships are not expert gold. Missing known components never count as faithful merely because primary total is NA.',
        'inputs':[bind(p) for p in dict.fromkeys(files)],'actual_command':[sys.executable,*sys.argv]}
    save(out/'per_answer.json',rows);save(out/'summary.json',summary);save(out/'inventory_verification.json',inventory_checks)
    lines=['# Grounded development fact audit','',f"Auditable conversions: {summary['auditable_conversions']}/5. Names: {dict(name_counts)} / 16. Initial duration components: {dict(duration_counts)} / 31.",'',
        '| ID | conversion | raw exact names | converted exact / contained / missing / unavailable names | literal numeric / record-bound | returned initial scope | primary time | inventory initial sum |','|---|---|---|---|---|---|---|---|']
    for r in rows:
        n=Counter(x['status'] for x in r['names']);t=r['time_scope_comparison']
        values=f"{t['literal_numeric_components_retained']} / {t['record_bound_numeric_components_retained']} of {t['expected_core_components']}" if r['conversion_available'] else 'unavailable'
        initial=f"{t['returned_initial_included_components']}/{t['expected_core_components']}" if r['conversion_available'] else 'unavailable'
        raw_count=sum(n['status']=='raw_literal_present' for n in r['raw_name_presence']['names']) if r['raw_name_presence']['state']=='strictly_parseable' else 'unavailable'
        lines.append(f"| {r['anonymous_answer_id']} | {'available' if r['conversion_available'] else 'unavailable'} | {raw_count} | {n['exact']} / {n['contained-only']} / {n['missing']} / {n['unavailable']} | {values} | {initial} | {t['returned_primary_total_hours']} | {t['inventory_initial_sum_hours']} |")
    lines+=['','The two time columns use different declared scopes and are not automatically expected to agree. Conditional later operations and missing components remain separate in JSON. An exact entity string does not verify its role; anti-GFP containing GFP is only containment. Relationships and ambiguities still need semantic review. No model calls, source edits, score changes or expert labels.',
        '', 'The original v1 short-quote containment status is retained under legacy_only, never used as the primary fact-retention count. The primary diagnostics distinguish literal value, verified record binding, returned initial scope, and unqualified total. Unknown or conditional endpoints are not automatically numerical omissions. RI exact span, containment, independently parsed value, and projected value are separate.',
        '', 'This is a version comparison involving schema/prompt and projection policies, not a single-intervention causal test. Intrinsic signal identity is audited separately from the fixed three dye-target relations.','']
    lines += ['Raw literal-name presence and converted derived-name retention share the fixed 16-name inventory, but have separate availability denominators. Raw presence never upgrades a failed conversion. Structural whole-field/list checks and native-use source-support checks are recorded independently. Zero cue concerns does not certify atomic identity or semantic correctness.','']
    (out/'README.md').write_text('\n'.join(lines),encoding='utf8');print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs','scope']},ensure_ascii=True))

def self_check():
    require(FINAL_FREEZE_AUTHORIZED,'V7_DRAFT_FREEZE_NOT_AUTHORIZED_BY_ROOT')
    require(sha(FINAL_INDEPENDENT_REVIEW)==FINAL_INDEPENDENT_REVIEW_SHA,'FINAL_INDEPENDENT_REVIEW_CHANGED')
    final_review=read(FINAL_INDEPENDENT_REVIEW)
    require(final_review['module']['sha256']==GROUND_SHA and final_review['checker_draft']['sha256']==sha(REVIEWED_DRAFT_SNAPSHOT),'REVIEWED_MODULE_OR_DRAFT_SNAPSHOT_MISMATCH')
    inv,sources,checks=verify_inventory();doc,payload=grounded.synthetic_fixture();conv=grounded.convert(grounded.canonical(payload),doc);g=conv['source_audit']['resolved'];tests=[]
    independent=read(INDEPENDENT_REVIEW)
    selected=read(SELECTED_SPECS)
    require(INDEPENDENT_REVIEW_SHA is not None and sha(INDEPENDENT_REVIEW)==INDEPENDENT_REVIEW_SHA,'INDEPENDENT_REVIEW_NOT_BOUND_OR_CHANGED')
    require(independent['status']=='pass_for_selected_software_scope' and independent['failed']==[],'SELECTED_V7_PROBES_NOT_PASSED')
    require(independent['module']['sha256']==GROUND_SHA,'INDEPENDENT_PROBES_WRONG_MODULE')
    require(independent['harness_sha256']==sha(INDEPENDENT_REVIEW.parents[1]/'probe_v7.py'),'INDEPENDENT_HARNESS_CHANGED')
    require(independent['selected_specs_sha256']==sha(SELECTED_SPECS),'SELECTED_EXPECTATIONS_CHANGED')
    require(len(independent['rows'])==len(selected['specs']) and all(row['pass'] for row in independent['rows']),'SELECTED_ROW_RESULTS_NOT_PASSED')
    require(EXTENT_REVIEW_SHA is not None and sha(EXTENT_REVIEW)==EXTENT_REVIEW_SHA,'EXTENT_REVIEW_NOT_BOUND_OR_CHANGED')
    extents=read(EXTENT_REVIEW);extent_specs=read(EXTENT_SPECS);repeat_specs=read(REPEAT_OMISSION_SPECS)
    require(extents['module']['sha256']==GROUND_SHA and extents['status']=='pass_for_source_extent_software_scope' and extents['failed']==[],'SOURCE_EXTENT_PROBES_NOT_PASSED_FOR_CURRENT_MODULE')
    require(extents['harness_sha256']==sha(EXTENT_REVIEW.parents[1]/'probe_source_extents.py'),'SOURCE_EXTENT_HARNESS_CHANGED')
    require(extents['specifications_sha256']==sha(EXTENT_SPECS) and extents['additional_specifications_sha256']==sha(REPEAT_OMISSION_SPECS),'SOURCE_EXTENT_EXPECTATIONS_CHANGED')
    require(len(extents['rows'])==len(extent_specs['specs'])+len(repeat_specs['specs']) and all(r['pass'] for r in extents['rows']),'SOURCE_EXTENT_RESULTS_INVALID')
    require(NUMERIC_ELIGIBILITY_SHA is not None and sha(NUMERIC_ELIGIBILITY)==NUMERIC_ELIGIBILITY_SHA,'NUMERIC_ELIGIBILITY_NOT_BOUND_OR_CHANGED')
    eligibility=read(NUMERIC_ELIGIBILITY)
    require(eligibility['module']['sha256']==GROUND_SHA and eligibility['inventory']['sha256']==INVENTORY_SHA and eligibility['fixed_answers']==5,'NUMERIC_ELIGIBILITY_WRONG_SOURCE_OR_MODULE')
    require(eligibility['status']=='source_catalog_eligibility_only' and eligibility['model_selection_or_conversion_success_claimed'] is False,'NUMERIC_ELIGIBILITY_SCOPE_INVALID')
    require(METADATA_REVIEW_SHA is not None and sha(METADATA_REVIEW)==METADATA_REVIEW_SHA,'V7_METADATA_REVIEW_NOT_BOUND')
    metadata=read(METADATA_REVIEW)
    require(metadata['module']['sha256']==GROUND_SHA and metadata['failed']==[] and metadata['all_passed'],'V7_METADATA_REVIEW_NOT_PASSED')
    def check(name,condition):require(condition,'SYNTHETIC_CHECK:'+name);tests.append({'name':name,'pass':True,'synthetic_only':True})
    for aid in IDS:
        original=sources[aid];renamed=copy.deepcopy(original)
        renamed.update(case_id='SYNTHETIC_DIFFERENT_GENERATOR_AND_CONDITION',generator_model='SYNTHETIC_OTHER_GENERATOR',condition='SYNTHETIC_OTHER_CONDITION')
        check('opaque_source_id_not_external_identity_'+aid,grounded.source_id_for_case(original)==grounded.source_id_for_case(renamed))
    synthetic_case={'specific_question':'SYNTHETIC_QUESTION','model_response':'SYNTHETIC_ANSWER'}
    check('opaque_source_id_binds_full_question',grounded.source_id_for_case(synthetic_case)!=grounded.source_id_for_case({**synthetic_case,'specific_question':'SYNTHETIC_QUESTION_CHANGED'}))
    check('opaque_source_id_binds_full_answer',grounded.source_id_for_case(synthetic_case)!=grounded.source_id_for_case({**synthetic_case,'model_response':'SYNTHETIC_ANSWER_CHANGED'}))
    def factspan(s):return {'start':s['start'],'end':s['end'],'quote':s['quote'],'source_text_sha256':s['answer_sha256'],'quote_sha256':rawsha(s['quote'])}
    named={'name':'SYNTHETIC_TARGET','source_span':factspan(g['entities'][1]['name'])}
    check('exact_name_is_literal_only',name_audit([named],g['entities'])[0]['status']=='exact')
    changed=copy.deepcopy(g['entities']);changed[1]['name']['quote']='anti-SYNTHETIC_TARGET'
    check('anti_prefix_is_contained_only_not_semantic_equivalence',name_audit([named],changed)[0]['status']=='contained-only')
    check('missing_name_remains_missing',name_audit([named],[])[0]['status']=='missing')
    check('unavailable_conversion_is_not_false_zero_coverage',name_audit([named],[],False)[0]['status']=='unavailable')
    op=g['operations'][0];comp={'step_label':'SYNTHETIC_1','hours':2.0,'duration_span':factspan(op['duration'])}
    audit=duration_audit([comp],g['operations'],True)[0];check('duration_source_unit_scope_retained',audit['status']=='record_bound_numeric_retained' and audit['initial_scope_preserved'])
    modified=copy.deepcopy(g['operations']);modified[0]['parsed_duration']['bounds_hours']=[3,3]
    check('saved_numeric_tampering_detected',duration_audit([comp],modified,True)[0]['status']=='literal_numeric_retained_projection_unresolved')
    modified=copy.deepcopy(g['operations']);modified[0]['phase']='staining'
    audit=duration_audit([comp],modified,True)[0];check('numeric_fact_survives_scope_disagreement',audit['status']=='record_bound_numeric_retained' and not audit['initial_scope_preserved'])
    modified=copy.deepcopy(g['operations']);modified[0]['duration']['start']+=100;modified[0]['duration']['end']+=100
    check('same_number_wrong_offset_not_matched',duration_audit([comp],modified,True)[0]['status']=='missing')
    modified=copy.deepcopy(g['operations']);modified[0]['operation']['end']=modified[0]['duration']['start']
    modified[0]['duration_binding']={'valid':True,'mode':'SYNTHETIC_ADJACENT_RECORD_BINDING_FOR_CHECKER_ONLY'}
    separate=duration_audit([comp],modified,True)[0]
    check('new_primary_record_binding_separate_from_legacy_containment',separate['status']=='record_bound_numeric_retained' and separate['legacy_only']['v1_short_quote_containment_status']=='span_present_numeric_mismatch' and separate['record_bound_numeric_retained'] and separate['literal_source_numeric_value_retained'])
    adjacent_doc,adjacent_payload=grounded.synthetic_record_fixture(null_target=True)
    adjacent=grounded.convert(grounded.canonical(adjacent_payload),adjacent_doc)['source_audit']['resolved']
    adjacent_op=adjacent['operations'][0]
    adjacent_fact={'step_label':'SYNTHETIC_RECORD','hours':2.0,'duration_span':factspan(adjacent_op['duration'])}
    adjacent_check=duration_audit([adjacent_fact],adjacent['operations'],True)[0]
    check('actual_adjacent_record_fixture_literal_and_binding_retained',adjacent_check['literal_source_numeric_value_retained'] and adjacent_check['record_bound_numeric_retained'])
    extent=adjacent_op['operation']
    check('actual_ID_operation_extent_exact_replay_and_same_record_duration',adjacent_doc['text'][extent['start']:extent['end']]==extent['quote'] and adjacent_op['duration_binding']['valid'] and extent['unit_id']==adjacent_op['duration']['unit_id'])
    expected=[{'label':'SYNTHETIC_FLUOR_101','target':'SYNTHETIC_TARGET','source_span':factspan(g['relations'][0]['evidence'])}]
    ra=relation_audit(expected,g,conv['legacy_projection'],True)[0];check('exact_relation_and_projection_separate',ra['edge_retained'] and ra['exact_legacy_projection_retained'])
    lost=copy.deepcopy(conv['legacy_projection']);lost['extraction']['marker_dict']['SYNTHETIC_FLUOR_101']=''
    check('retained_edge_projection_loss_reported',relation_audit(expected,g,lost,True)[0]['edge_present_but_projection_lost'])
    ambiguity={'kind':'unassigned_secondary_names','source_spans':[factspan(g['relations'][0]['evidence'])],
        'known_labels':['SYNTHETIC_FLUOR_101'],'known_targets':['SYNTHETIC_TARGET']}
    check('specific_mapping_for_declared_ambiguity_is_flagged',ambiguity_audit([ambiguity],g,conv['legacy_projection'],True)[0]['status']=='specific_projection_for_inventory_ambiguous_group')
    uncertain=copy.deepcopy(g);uncertain['relations'][0]['status']='unknown'
    check('withheld_edge_explicit_ambiguity_preserved',ambiguity_audit([ambiguity],uncertain,lost,True)[0]['status']=='explicit_ambiguity_retained')
    uncertain['relations'][0]['target_entity_id']=None
    check('null_target_does_not_match_known_endpoint',not relation_audit(expected,uncertain,lost,True)[0]['edge_retained'])
    check('null_target_unknown_record_preserves_ambiguity',ambiguity_audit([ambiguity],uncertain,lost,True)[0]['status']=='explicit_ambiguity_retained')
    ri_expected={'start':4,'end':8,'quote':'1.23'}
    ri_broad={'id':'synthetic_ri','role':'reagent_final','value':{'start':0,'end':8,'quote':'RI: 1.23'}}
    ri_check=ri_evidence_audit(ri_expected,1.23,[ri_broad])[0]
    check('RI_prefixed_quote_containment_separate_from_exact',not ri_check['exact_inventory_span'] and ri_check['returned_quote_contains_inventory_numeric_occurrence'] and ri_check['unique_value_equals_inventory'])
    ri_broad['value']={'start':0,'end':14,'quote':'RI: 1.23 or 2'}
    check('RI_multiple_numbers_not_silently_selected',ri_evidence_audit(ri_expected,1.23,[ri_broad])[0]['independent_unique_numeric_value'] is None)
    wrong=factspan(g['entities'][0]['name']);wrong['start']+=1
    try:span_check(wrong,doc['text'])
    except ValueError:check('inventory_offset_tampering_rejected',True)
    else:raise ValueError('OFFSET_TAMPERING_ACCEPTED')
    check('independent_minutes_conversion',same(source_hours('Time: 30 minutes'),.5))
    check('independent_dimension_not_days',source_hours('3D') is None and source_hours('3 days')==72)
    native_doc,native_payload=grounded.synthetic_fixture()
    native_text=native_doc['text']+'Selected signal: SYNTHETIC_REPORTER (native).\n'
    native_doc=grounded.document(native_text,native_doc['source_id'])
    native_unit=native_doc['units'][-1]
    native_payload['grounded_extraction']['entities'].append({'id':'native_reporter','kind':'fluorescent_protein','usage':'used',
        'literal_name':'SYNTHETIC_REPORTER','supporting_evidence':{'unit_id':native_unit['unit_id']},'name_occurrence':0})
    native_payload['grounded_extraction']['intrinsic_signals']=[{'id':'native_identity','entity_id':'native_reporter','status':'source_declared',
        'evidence':{'unit_id':native_unit['unit_id']}}]
    native_conv=grounded.convert(grounded.canonical(native_payload),native_doc)
    native_audit=intrinsic_identity_audit(native_conv['source_audit']['resolved'],native_conv['legacy_projection'],native_text,True)
    check('typed_identity_is_separate_from_three_pair_inventory',native_audit['returned_records']==1 and native_audit['same_name_serializations']==1 and native_audit['fixed_inventory_relation_denominator_unchanged']==3)
    check('typed_identity_independent_literal_cues',native_audit['independent_cue_concerns']==0 and native_audit['records'][0]['independent_literal_cues']['native_declaration'])
    check('typed_identity_does_not_claim_task_or_preservation',not native_audit['records'][0]['task_fulfillment_verified'] and not native_audit['records'][0]['biological_preservation_verified'])
    altered=copy.deepcopy(native_conv['legacy_projection']);altered['extraction']['marker_dict']['SYNTHETIC_REPORTER']='OTHER_NAME'
    try:intrinsic_identity_audit(native_conv['source_audit']['resolved'],altered,native_text,True)
    except ValueError:check('typed_identity_serialization_tampering_rejected',True)
    else:raise ValueError('TYPED_IDENTITY_TAMPERING_ACCEPTED')
    name_bindings=independent_name_binding_audit(g,doc['text'],True)
    check('derived_name_and_wide_source_support_checked_independently',all(r['source_literal_binding_verified'] for r in name_bindings['records']))
    def synthetic_name_boundary(literal,text):
        start=text.index(literal);digest=rawsha(text)
        name={'start':start,'end':start+len(literal),'quote':literal,'source_text_sha256':digest}
        support={'start':0,'end':len(text),'quote':text,'source_text_sha256':digest}
        entity={'id':'synthetic_boundary','literal_name':literal,'name':name,'supporting_evidence':support,'name_occurrence':0}
        return independent_name_binding_audit({'entities':[entity]},text,True)['records'][0]
    for suffix in ['+','−','-']:
        literal='SYNTHETIC_CHARGED'+suffix;text='Selected marker: '+literal+'.'
        check('full_terminal_suffix_retained_'+suffix,synthetic_name_boundary(literal,text)['source_literal_binding_verified'])
        cropped=synthetic_name_boundary('SYNTHETIC_CHARGED',text)
        check('omitted_terminal_suffix_flagged_'+suffix,not cropped['source_literal_binding_verified'] and cropped['independent_occurrences'][0]['omitted_terminal_charge_or_positive_suffix'])
    connector=synthetic_name_boundary('SYNTHETIC_DYE','SYNTHETIC_DYE-labeled SYNTHETIC_TARGET.')
    check('grammatical_connector_not_terminal_charge',connector['source_literal_binding_verified'] and not connector['independent_occurrences'][0]['omitted_terminal_charge_or_positive_suffix'])
    check('open_set_multiword_parenthetical_name_not_blacklisted',not atomic_name_risks('Novel Multiword Name (AB-7)'))
    check('whole_field_name_flagged_even_when_exact_source_span',bool(atomic_name_risks('**Chosen Labeling:** [REPORTER_A (native), DYE_B]')))
    names_raw=raw_name_presence([named],grounded.canonical(payload))
    check('raw_literal_presence_is_separate_from_conversion',names_raw['names'][0]['status']=='raw_literal_present' and name_audit([named],[],False)[0]['status']=='unavailable')
    duplicate='{"grounded_extraction":{"entities":[]},"grounded_extraction":{"entities":[]}}'
    check('duplicate_raw_not_loosely_repaired',raw_name_presence([named],duplicate)['state']=='unavailable')
    missing='{"scores":{}}'
    check('missing_raw_grounded_field_not_numeric_zero',raw_name_presence([named],missing)['names'][0]['status']=='unavailable')
    broad='**Chosen Labeling:** [REPORTER_A (native), DYE_B]'
    support=native_source_support(broad,broad,broad,atomic_name_risks(broad))
    check('whole_field_native_cue_does_not_validate_atomic_identity',support['state']=='non_atomic_name' and not support['mechanically_supported_source_declaration'])
    support=native_source_support('REPORTER_A','preserve native signals (like REPORTER_A)','The method is optimized to preserve native signals (like REPORTER_A).',[])
    check('native_capability_example_is_not_actual_use',support['state']=='capability_or_example_not_actual_native_use')
    support=native_source_support('REPORTER_A','Native REPORTER_A is not used.','Native REPORTER_A is not used.',[])
    check('native_negation_is_not_affirmative_use',support['state']=='negative_or_loss_source')
    support=native_source_support('REPORTER_A','REPORTER_A (native)','Selected signal: REPORTER_A (native).',[])
    check('explicit_native_selection_supported_but_not_scientific_truth',support['mechanically_supported_source_declaration'] and not support['semantic_native_use_verified'])
    batch=BASE/'grounded_development_v7';observed_receipts=list((batch/'run/attempts').glob('*/request_receipt.json'))
    observed_trials=list((batch/'run/trials').glob('*.json'))
    observed_returns=list((batch/'run/attempts').glob('*/provider_response.json'))
    freeze={'version':VERSION,'created_utc':datetime.now(timezone.utc).isoformat(),'checker_sha256':sha(__file__),
        'inventory':bind(INVENTORY),'grounded_module':bind(grounded.__file__),'known_scope':'Only fixed A01–A05 exposed development answers.',
        'final_independent_review':bind(FINAL_INDEPENDENT_REVIEW),'reviewed_unapproved_checker_snapshot':bind(REVIEWED_DRAFT_SNAPSHOT),
        'grounded_schema':bind(grounded.OUT/'draft/schema.json'),'independent_interface_probes':bind(INDEPENDENT_REVIEW),
        'independent_probe_harness':bind(INDEPENDENT_REVIEW.parents[1]/'probe_v7.py'),
        'selected_scope_specifications':bind(SELECTED_SPECS),
        'source_extent_interface_probes':bind(EXTENT_REVIEW),'source_extent_specifications':bind(EXTENT_SPECS),
        'repeat_omission_specifications':bind(REPEAT_OMISSION_SPECS),
        'source_extent_probe_harness':bind(EXTENT_REVIEW.parents[1]/'probe_source_extents.py'),
        'fixed_source_numeric_candidate_eligibility':bind(NUMERIC_ELIGIBILITY),
        'root_selected_scope_delta':bind(INDEPENDENT_REVIEW.parents[1]/'root_selection_delta.json'),
        'independent_probe_counts':{'selected_scope_specs':len(selected['specs']),'passed':independent['pass'],'all_selected_passed':True,
            'source_extent_specs':len(extent_specs['specs']),'additional_repeat_omission_specs':len(repeat_specs['specs']),'source_extent_passed':extents['pass'],'all_source_extent_passed':True},
        'numeric_candidate_eligibility_not_model_retention':{k:eligibility[k] for k in ['initial_components','eligible_initial_components','fixed_source_RI_mentions','eligible_RI_mentions']},
        'unimplemented_original_design_claims':selected.get('not_implemented_original_claims',[]),
        'unchanged_original_v5_checker':bind(V5_CHECKER),'unchanged_original_v6_checker':bind(V6_CHECKER),
        'independent_metadata_review':bind(METADATA_REVIEW),
        'unchanged_original_v1_checker':bind(V1_CHECKER),
        'comparison_scope':'Original inventory unchanged. Primary fact retention separates source literal, verified record binding, returned initial scope and primary endpoint. Original v1 quote-containment comparisons are legacy_only. Intrinsic identity is separate from the fixed dye-target inventory.',
        'v7_bundle_changes':['per-O eligible duration/repeat IDs expose existing source bindings','generic prompt clarification of selected method, untimed operations and whole/core coverage','v6 original source gates, arithmetic, native policy and configured context98304 unchanged'],
        'inherited_representation_self_test':'Retains the frozen v6 exact ID-derived operation extent replay and same-record duration checks; no new adaptation is authorized.',
        'declared_v7_num_ctx':98304,'actual_generation_configuration_observed_at_freeze':False,
        'version_change_is_single_intervention':False,
        'unchanged_original_v2_checker':bind(V2_CHECKER),
        'unchanged_original_v3_checker':bind(V3_CHECKER),'unchanged_original_v4_checker':bind(V4_CHECKER),
        'grounded_v7_batch_receipts_present_at_freeze':len(observed_receipts),
        'candidate_trial_files_present_at_freeze':len(observed_trials),'provider_return_files_present_at_freeze':len(observed_returns),
        'frozen_before_candidate_generation':not observed_receipts,
        'checker_freeze_timing':'V7 checker must freeze before any v7 generation. Original inventory was frozen before v1 generation; v1/v2/v3/v4/v5/v6 development outputs have since been observed.',
        'candidate_output_contents_inspected_before_checker_freeze':False,
        'fixed_denominators':inv['fixed_denominators'],'rules':['Names: exact vs contained-only vs missing vs unavailable, case sensitive, no aliases.',
          'Time: source offsets plus independent units, parsed values, phase and execution scope separately; known source components survive primary NA.',
          'Relations: exact endpoint strings, source evidence and legacy projection reported separately; no semantic gold assertion.',
          'Ambiguities: explicit uncertainty, all-options-used and specific projection are separate diagnostics.',
          'Actual analysis requires raw provider-to-conversion replay and exact five original question/answer identities.'],
        'new_model_calls':0,'actual_command':[sys.executable,*sys.argv]}
    require(not observed_receipts and not observed_trials and not observed_returns,'V7_CHECKER_MUST_FREEZE_BEFORE_GENERATION')
    require(not (OUT/'freeze.json').exists(),'V7_CHECKER_ALREADY_FROZEN')
    OUT.mkdir(parents=True,exist_ok=True);save(OUT/'freeze.json',freeze);save(OUT/'software_probes.json',{'status':'pass','synthetic_checks':tests,
        'inventory_identity_checks':checks,'independent_interface_probes':bind(INDEPENDENT_REVIEW),
        'selected_scope_specifications':bind(SELECTED_SPECS),'independent_probe_counts':freeze['independent_probe_counts'],
        'new_model_calls':0,'checker_sha256':sha(__file__),'freeze_sha256':sha(OUT/'freeze.json')})
    print(json.dumps({'status':'pass','synthetic_checks':len(tests),'inventory_cases':len(checks),'checker_sha256':sha(__file__),
        'frozen_before_candidate_generation':freeze['frozen_before_candidate_generation'],
        'candidate_output_contents_inspected_before_checker_freeze':False,'provider_return_files':len(observed_returns),'trial_files':len(observed_trials)}))

def draft_check():
    """Independent checker helpers and five inventory identities only; no module pass."""
    inv,sources,checks=verify_inventory(require_module=False)
    tests=[]
    def check(name,ok):
        require(ok,'DRAFT_CHECK:'+name);tests.append({'name':name,'pass':True,'synthetic_only':True})
    for name in ['GFP+','NAD+','Ca2+']:
        text='Selected marker: '+name+'.'
        def sp(a,b):return {'start':a,'end':b,'quote':text[a:b],'answer_sha256':rawsha(text),'quote_sha256':rawsha(text[a:b])}
        a=text.index(name);entity={'id':'FICTIONAL','literal_name':name,'name':sp(a,a+len(name)),
            'supporting_evidence':sp(0,len(text)),'kind':'unknown','usage':'selected','name_occurrence':0}
        full=independent_name_binding_audit({'entities':[entity]},text,True)['records'][0]
        check('complete_suffix_retained_'+name,full['source_literal_binding_verified'])
        entity['literal_name']=name[:-1];entity['name']=sp(a,a+len(name)-1)
        cut=independent_name_binding_audit({'entities':[entity]},text,True)['records'][0]
        check('clipped_suffix_flagged_'+name,not cut['source_literal_binding_verified'] and cut['independent_occurrences'][0]['omitted_terminal_charge_or_positive_suffix'])
    support=native_source_support('REPORTER_A','Use native REPORTER_A in the proposed initial workflow.','Use native REPORTER_A in the proposed initial workflow.',[])
    check('proposed_native_source_declaration_not_physical_execution',support['mechanically_supported_source_declaration'] and support['proposed_or_selected_usage_is_not_physical_execution'] and not support['biological_preservation_verified'])
    for evidence in ['The method can preserve native signals like REPORTER_A.','Native REPORTER_A is not used.','If needed later, use native REPORTER_A.']:
        check('native_nonaffirmative_scope_'+str(len(tests)),not native_source_support('REPORTER_A',evidence,evidence,[])['mechanically_supported_source_declaration'])
    check('independent_hours_unchanged',source_hours('30 minutes')==.5 and source_hours('3D') is None and source_hours('3 days')==72)
    check('raw_unavailable_not_zero',name_audit([{'name':'REPORTER_A','source_span':{'start':0,'end':10}}],[],False)[0]['status']=='unavailable')
    repeated='anti-SYNTHETIC_NAME; SYNTHETIC_NAME; SYNTHETIC_NAME.'
    literal='SYNTHETIC_NAME';hits=list(re.finditer(re.escape(literal),repeated));digest=rawsha(repeated)
    wide={'start':0,'end':len(repeated),'quote':repeated,'source_text_sha256':digest}
    for occurrence,expected in [(0,False),(1,True),(2,True),(-1,False),(3,False),(True,False),(None,False)]:
        h=hits[occurrence] if isinstance(occurrence,int) and not isinstance(occurrence,bool) and 0<=occurrence<len(hits) else hits[1]
        narrow={'start':h.start(),'end':h.end(),'quote':literal,'source_text_sha256':digest}
        entity={'id':'synthetic_occurrence','literal_name':literal,'name_occurrence':occurrence,'name':narrow,'supporting_evidence':wide}
        audit=independent_name_binding_audit({'entities':[entity]},repeated,True)['records'][0]
        check('explicit_occurrence_all_literals_'+repr(occurrence),audit['source_literal_binding_verified']==expected and audit['literal_occurrence_count']==3)
    import ast
    trees=[ast.parse(p.read_text(encoding='utf8')) for p in [V4_CHECKER,Path(__file__)]]
    functions=['source_hours','name_audit','duration_audit','relation_audit','ambiguity_audit','ri_evidence_audit']
    for name in functions:
        nodes=[next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name==name) for t in trees]
        check('fixed_measurement_AST_unchanged_'+name,ast.dump(nodes[0],include_attributes=False)==ast.dump(nodes[1],include_attributes=False))
    design=BASE/'grounded_v7_fact_review_design_v1/design.json'
    require(read(design)['fixed_denominators']=={'names':16,'initial_duration_components':31,'explicit_dye_pairs':3,'ambiguity_groups':2},'PROSPECTIVE_DENOMINATORS_DRIFT')
    result={'status':'pass_checker_draft_only_not_module_review_or_freeze','checker_sha256':sha(__file__),
        'fixed_inventory':bind(INVENTORY),'original_v4_checker':bind(V4_CHECKER),'prospective_design':bind(design),
        'synthetic_checks':tests,'inventory_identity_checks':checks,'v7_module_imported':grounded is not None,
        'v7_module_hash_final':False,'v7_module_specs_executed':0,'freeze_created':False,'new_model_calls':0,
        'sealed_or_human_holdout_read':False,'actual_command':[sys.executable,*sys.argv]}
    save(OUT/'draft/checker_software_checks.json',result)
    print(json.dumps({'status':result['status'],'synthetic_checks':len(tests),'inventory_cases':len(checks),'freeze_created':False,'new_model_calls':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--draft-check',action='store_true');p.add_argument('--self-check',action='store_true');p.add_argument('--freeze',action='store_true');p.add_argument('--analyze',action='store_true');p.add_argument('--batch-out',type=Path);p.add_argument('--out',type=Path)
    args=p.parse_args();require(sum([args.draft_check,args.self_check,args.freeze,args.analyze])==1,'CHOOSE_EXACTLY_ONE_ACTION')
    if args.draft_check:draft_check()
    elif args.self_check or args.freeze:self_check()
    else:
        require(FINAL_FREEZE_AUTHORIZED,'V7_DRAFT_ANALYSIS_NOT_AUTHORIZED_OR_FROZEN')
        require(args.batch_out is not None,'ANALYZE_REQUIRES_BATCH_OUT');analyze(args.batch_out,args.out or args.batch_out/'independent_fact_audit_v7')
