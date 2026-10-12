"""Posthoc core-coverage scope separation for fully represented numbered sources.

The original partial declaration/unresolved records are retained. No number,
phase, operation or formula is changed. Unrecognized source structures leave
the existing partial gate in place rather than asserting complete recall.
"""
from __future__ import annotations
import copy,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_fieldwise_scoring_v3 as previous
VERSION='fieldwise-scoring-v4-posthoc-core-coverage-scope'
numeric,ground,base=previous.numeric,previous.ground,previous.base
noncore=previous.previous.noncore_context
NUMBERED=re.compile(r'^\s*(\d+(?:\.\d+)*)(?:[.)])?\s+(.+?)\s*$')
PROTOCOL=re.compile(r'^\s*(?:\*\*|#{1,6}\s*)?Protocol\s+Steps\s*:?\s*(?:\*\*)?\s*$',re.I)
META=re.compile(r'^\s*\*\*(?:Chosen\s+(?:Method|Labeling)|Selected\s+(?:Method|Labeling)|Justification)\s*:\*\*',re.I)
TITLE_WORDS={'pre','clearing','immunostaining','treatment','dehydration','delipidation','decalcification','decolorization',
    'ri','matching','and','refractive','index','storage','long','term','imaging','preservation','nuclear','staining',
    'permeabilization','blocking','dual','target','immunolabeling','tissue','optical','fdisco'}
IMPERATIVE=re.compile(r'\b(?:then\s+|;\s*|\.\s+)(?:incubate|wash|transfer|immerse|soak|equilibrate|dehydrate|clear|add|remove)\b',re.I)

def fullspan(s,u,doc):return previous.full_unit_span(s,u,doc)
def source_heading(unit,units):
    m=NUMBERED.fullmatch(unit['text'].strip())
    if not m or not any(NUMBERED.fullmatch(u['text'].strip()) and NUMBERED.fullmatch(u['text'].strip())[1].startswith(m[1]+'.') for u in units):return False
    words=re.findall(r'[A-Za-z]+',m[2].lower())
    return bool(words and set(words)<=TITLE_WORDS and not re.search(r'\d|[=:;%]',m[2]))

def noncore_support(op,audit):
    text=op['operation']['quote'];phase=op['phase']
    if phase in ['labeling_preparation','antibody_incubation','staining','routine_wash'] and noncore.previous.CORE.search(text):return False
    if phase=='labeling_preparation':return bool(op.get('phase_support',{}).get('supported') and not op.get('phase_support',{}).get('possible_core_function'))
    if phase=='antibody_incubation':return bool(re.search(r'\bantibod(?:y|ies)\b',text,re.I))
    if phase=='staining':return bool(re.search(r'\b(?:stain\w*|labeling|labelling)\b',text,re.I))
    if phase=='storage':return bool(re.search(r'^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?(?:Store|Storage)\b',text,re.I)
        and not re.search(r'\b(?:incubat\w*|equilibrat\w*|delipid\w*|decalcif\w*|decolor\w*)\b',text,re.I))
    if phase=='imaging':return noncore.previous.explicit_mounting_only(text)
    if phase=='routine_wash':return bool(re.search(r'\bwash\w*\b',text,re.I)
        and re.search(r'\b(?:PBS|PTwH|washing\s+buffer)\b',text,re.I)
        and not re.search(r'\b(?:THF|DBE|ethanol|methanol|transition|transfer|exchange)\b',text,re.I))
    return False

def source_completion(audit,doc):
    """Inspect the whole source, not merely the finite accumulated bounds."""
    if audit['source_binding']['source_id']!=doc['source_id'] or audit['source_binding']['answer_sha256']!=doc['answer_sha256'] or ground.rawsha(doc['text'])!=doc['answer_sha256']:
        raise ValueError('SOURCE_IDENTITY_MISMATCH')
    units=doc['units']; markers=[i for i,u in enumerate(units) if PROTOCOL.fullmatch(u['text'].strip())]
    proof={'supported':False,'domain':'complete_numbered_single_action_source_records','units':[],'issues':[]}
    if len(markers)!=1:proof['issues'].append('source_protocol_boundary_not_unique');return proof
    cut=markers[0];ops=audit['resolved']['operations']; seen=set()
    for i,u in enumerate(units):
        if doc['text'][u['start']:u['end']]!=u['text']:raise ValueError('SOURCE_UNIT_CHANGED')
        if not u['text'].strip():continue
        entry={'unit_id':u['unit_id'],'source_unit':copy.deepcopy(u)}
        if i<cut:
            if META.match(u['text']) and not IMPERATIVE.search(u['text']):entry['role']='declarative_metadata_or_rationale'
            else:entry['role']='unresolved_prologue';proof['issues'].append('unclassified_source_unit:'+u['unit_id'])
        elif i==cut:entry['role']='protocol_boundary'
        elif source_heading(u,units):entry['role']='nominal_parent_section_heading'
        else:
            matching=[o for o in ops if o['operation']['unit_id']==u['unit_id'] and fullspan(o['operation'],u,doc)]
            if not NUMBERED.fullmatch(u['text'].strip()) or len(matching)!=1:
                entry['role']='source_action_not_fully_represented';proof['issues'].append('unrepresented_source_action:'+u['unit_id'])
            else:
                op=matching[0];seen.add(op['id']);entry['operation_id']=op['id'];entry['phase']=op['phase'];entry['execution_scope']=op['execution_scope']
                # A whole quoted line containing multiple commands cannot prove
                # one operation's complete assignment. Prefix clauses are kept.
                heads=ground.record_action_heads(u['text']);entry['action_heads']=heads
                if len(heads)>1:
                    entry['role']='multiple_source_actions_in_one_record';proof['issues'].append('multi_action_record:'+u['unit_id'])
                elif op['phase'] in ground.INCLUDE:
                    entry['role']='represented_core_action'
                    d=op.get('duration');p=op.get('parsed_duration',{})
                    valid=bool(d and ground.record_binding(op['operation'],d,doc)['valid'] and p.get('unique_hours') is not None
                        and type(op.get('repeat_count')) is int and op['repeat_count']>=1
                        and op['execution_scope'] in ['initial','conditional_or_future'])
                    entry['all_time_dependencies_bound']=valid
                    if not valid:proof['issues'].append('core_time_dependency_missing_or_nonunique:'+u['unit_id'])
                elif noncore_support(op,audit):entry['role']='source_supported_noncore_action'
                else:entry['role']='unresolved_phase_or_noncore_support';proof['issues'].append('unresolved_phase:'+u['unit_id'])
        proof['units'].append(entry)
    if seen!={o['id'] for o in ops}:proof['issues'].append('returned_operations_not_exactly_accounted')
    byunit={x['unit_id']:x for x in proof['units']};uncertainty=[]
    for u in audit['resolved']['coverage']['unresolved']:
        s=u['evidence'];unit=next((v for v in units if v['unit_id']==s['unit_id']),None)
        if not unit or not(unit['start']<=s['start']<s['end']<=unit['end']) or doc['text'][s['start']:s['end']]!=s['quote']:
            raise ValueError('UNRESOLVED_SOURCE_BINDING_CHANGED')
        role=byunit.get(s['unit_id'],{}).get('role')
        if role not in ['declarative_metadata_or_rationale','nominal_parent_section_heading','represented_core_action','source_supported_noncore_action']:
            proof['issues'].append('unresolved_has_unaccounted_source_scope:'+s['unit_id'])
        uncertainty.append({'original_unresolved':copy.deepcopy(u),'source_unit_role':role,
            'effect':'retained_for_its_original_field; no unbound core time dependency identified in this source record'})
    proof['unresolved_scope_audit']=uncertainty
    proof['supported']=not proof['issues'] and bool(uncertainty) and any(x.get('role')=='represented_core_action' for x in proof['units'])
    proof['semantic_recall_is_not_expert_gold']=True
    return proof

def derive_audit(original,doc):
    audit=copy.deepcopy(original);time=previous.previous.previous.project_first_pass(original)['time_calculation']
    record={'version':VERSION,'changed':False,'original_core_coverage':original['resolved']['coverage']['core_time_operations']}
    if time['issues']!=['reported_core_operation_coverage_incomplete'] or record['original_core_coverage']!='partial':
        record['reason']='not_an_isolated_reported_core_coverage_issue';return audit,record
    proof=source_completion(original,doc);record['source_completion_review']=proof
    if proof['supported']:
        audit['resolved']['coverage']['core_time_operations']='complete'
        record.update(changed=True,derived_core_coverage='complete',original_coverage=copy.deepcopy(original['resolved']['coverage']),
            policy='field-scoped core completeness derived from complete source records; original partial and unresolved remain sidecar')
    audit['derived_core_coverage_scope_v4']=record
    return audit,record

def convert(raw,doc,case=None):
    cv=previous.convert(raw,doc,case);audit,change=derive_audit(cv['source_audit'],doc);cv['source_audit']=audit
    projection=previous.previous.previous.project_first_pass(audit);cv['legacy_projection']=projection
    cv['legacy_runner_payload']={'scores':copy.deepcopy(cv['wire_payload']['scores']),'extraction':copy.deepcopy(projection['extraction'])}
    cv['legacy_runner_content']=ground.canonical(cv['legacy_runner_payload'])
    cv['fieldwise_processing_v4']={'version':VERSION,'core_coverage_scope':change,'raw_response_modified':False,'original_time_formula_unchanged':True,'new_model_requests':0}
    return cv
def score_conversion(case,conversion,step):
    result=previous.score_conversion(case,conversion,step);result['processing_version']=VERSION;return result
def evaluate(raw,doc,case,step):
    cv=convert(raw,doc,case);return cv,score_conversion(case,cv,step)
