"""Private parameter-only phase membership from complete reference action scopes."""
from copy import deepcopy
from types import SimpleNamespace,FunctionType,CellType
import hashlib,json,re
import cubic_scoring_identity as cubic
from parameter_action_requirement_binding_20261025_v1 import binder
from ..identity import phase_sets_v4

VERSION='parameter-private-complete-reference-action-scope-v1'
UNKNOWN={None,'','unknown','unresolved','UNKNOWN','UNRESOLVED'}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def known(value):
    return isinstance(value,str) and value not in UNKNOWN


def source_family(value):
    if isinstance(value,str) and (value.startswith('source_medium:CUBIC') or value.startswith('source_alternatives:CUBIC')):
        return 'CUBIC'
    return None


def alternative_medium_allowed(medium,candidate):
    allowed={'source_medium:CUBIC2018:R','source_medium:CUBIC2018:RA','source_medium:CUBIC2019:R+'}
    return (candidate.get('id','').startswith('C19:')
        and candidate.get('matching_identity')=='source_medium:CUBIC2019:R+' and medium in allowed)


def identity(row,protocol):
    current=row.get('matching_identity')
    primary=binder.identity_v4.vocabulary.operating_medium(row,binder.identity_v4._top_level)
    if primary and known(primary.get('identity')):
        medium=primary['identity']
        evidence={'kind':'REGISTERED_EXACT_PRIMARY_MEDIUM_PROOF','proof':deepcopy(primary)}
    else:
        text=binder.identity_v4._top_level(row.get('operation',''))
        names=cubic.names(text)
        if len(names)!=1:
            return None,None
        name=next(iter(names))
        medium='source_medium:'+cubic.NAME_IDS[name]
        evidence={'kind':'TOP_LEVEL_LITERAL_NAMED_CUBIC_MEDIUM','name':name,
            'parenthetical_alternatives_not_promoted_to_current_action':True,
            'operation':row['operation']}
    if known(current):
        if current!=medium:
            return None,None
        return current,{'kind':'EXISTING_SOURCE_DECLARED_PRIMARY_IDENTITY','identity':current,
            'source_proof':evidence}
    return medium,evidence


def action_role(row,medium):
    current=row.get('operation_role')
    if known(current):
        return current,{'kind':'EXISTING_SOURCE_TYPED_ACTION_ROLE','role':current}
    text=binder.identity_v4._top_level(row.get('operation',''))
    if (medium=='source_medium:PBS' and
            re.fullmatch(r'\s*PBS\s*(?:清洗|洗涤|漂洗)(?:\s*(?:去除|洗去)[^。；;]*)?\s*[。.]?\s*',text,re.I)):
        return 'wash',{'kind':'COMPLETE_LITERAL_CHINESE_PBS_WASH','operation':row['operation']}
    if '预平衡' in text and re.search(r'\bRI\s*匹配',row.get('phase',''),re.I):
        return 'ri_matching',{'kind':'LITERAL_EQUILIBRATION_IN_RI_MATCHING_SECTION','operation':row['operation']}
    return None,None


def proof(row,reference,protocol,allowed_phases):
    a,b=row.get('source',{}).get('start'),row.get('source',{}).get('end')
    if (row.get('execution_status')!='ASSERTED_OPERATION' or type(a) is not int or type(b) is not int
            or not 0<=a<b<=len(protocol) or protocol[a:b]!=row.get('raw_text')):
        return None
    if re.search(r'前处理|预处理',row.get('phase','')):
        return None
    medium,medium_proof=identity(row,protocol)
    role,role_proof=action_role(row,medium)
    if medium is None or role is None:
        return None
    matches=[]
    for candidate in reference:
        phase=candidate.get('phase')
        if phase not in allowed_phases or candidate.get('execution_status')!='ASSERTED_OPERATION':
            continue
        if candidate.get('operation_role')!=role:
            continue
        if not binder._identity_domain(medium)<=binder._identity_domain(candidate.get('matching_identity')):
            continue
        matches.append(candidate)
    alternative=False
    if not matches and source_family(medium)=='CUBIC':
        matches=[candidate for candidate in reference
            if candidate.get('phase') in allowed_phases
            and candidate.get('execution_status')=='ASSERTED_OPERATION'
            and candidate.get('operation_role')==role
            and source_family(candidate.get('matching_identity'))=='CUBIC'
            and alternative_medium_allowed(medium,candidate)]
        alternative=bool(matches)
    if not matches or len({candidate['phase'] for candidate in matches})!=1:
        return None
    phase=matches[0]['phase']
    return {'version':VERSION,'row_id':row['id'],'source':deepcopy(row['source']),
            'raw_text':row['raw_text'],'branch':row.get('branch','main'),
            'reference_operation_ids':[candidate['id'] for candidate in matches],
            'reference_phase':phase,'actual_primary_identity':medium,'actual_action_role':role,
            'medium_proof':medium_proof,'action_proof':role_proof,
            'all_compatible_reference_operations_retained':True,
            'reference_requirement_variants_not_collapsed':True,
            'alignment_scores_or_encoder_used':False,
            'parameter_values_used_to_select_applicability':False,
            'scientific_equivalence_or_recipe_identity_claimed':False,
            'different_named_medium_not_equated':alternative}


def phase_fact(row,proof):
    phase=proof['reference_phase']
    return {'version':'source-hierarchy-unified-phase-facts-v4-20261021',
            'derivation':VERSION,'row_id':row['id'],
            'source':{'start':row['source']['start'],'end':row['source']['end'],'quote':row['raw_text']},
            'source_record':deepcopy(row['source']),'raw_text':row['raw_text'],
            'branch':row.get('branch','main'),'phase_status':'RESOLVED',
            'possible_phases':[phase],'possible_set_complete':True,'conflicts':[],
            'execution_status':row['execution_status'],'operation_role':proof['actual_action_role'],
            'original_comparison_phase':row.get('comparison_phase'),
            'original_comparison_phase_candidates':deepcopy(row.get('comparison_phase_candidates',[])),
            'reference_action_scope_proof':deepcopy(proof)}


def apply_typed(row,value,protocol):
    evidence=row.get(VERSION)
    if evidence is None:
        return value
    a,b=evidence['source']['start'],evidence['source']['end']
    assert evidence['row_id']==row['id'] and evidence['source']==row['source']
    assert evidence['raw_text']==row['raw_text'] and protocol[a:b]==row['raw_text']
    assert evidence['actual_primary_identity']==row['matching_identity']
    assert evidence['actual_action_role']==row['operation_role']
    bound=phase_sets_v4.bound_phase_set(row)
    if bound is not None:
        assert bound.get('complete') is True and bound.get('scenarios')==[[evidence['reference_phase']]]
    else:
        bound={'values':[evidence['reference_phase']],'complete':True,
            'basis':'BOUND_COMPLETE_SOURCE_HIERARCHY_PHASE_SET',
            'fact':phase_fact(row,evidence),'scenarios':[[evidence['reference_phase']]]}
    result=deepcopy(value)
    for field,key in (('primary_identity','actual_primary_identity'),('action_role','actual_action_role')):
        if known(result.get(field)) and result[field]!=evidence[key]:
            raise ValueError('PRIVATE_TYPED_PROJECTION_CONFLICT:'+field)
        result[field]=evidence[key]
    proof=dict(result.get('primary_medium_proof') or {})
    proof.update(basis=VERSION,identity=evidence['actual_primary_identity'],
        reference_action_scope_proof=deepcopy(evidence))
    proof.setdefault('source',deepcopy(row['source']))
    proof.setdefault('raw_text',row['raw_text'])
    result['primary_medium_proof']=proof
    result['phase_fact']=deepcopy(bound)
    return result


def binding_replacements(units):
    from parameter_execution_unit_contract_20261025_v1 import binding_v4,binding_v5,binding_v10,binding_v12
    from ..parameter_literal_action_scope_v1 import private_binding,action_scope
    def typed_role_proof(row,value,protocol):
        return action_scope.role_proof(row,apply_typed(row,value,protocol),protocol)
    scoped_action=SimpleNamespace(**{**vars(action_scope),'role_proof':typed_role_proof})
    namespace={**private_binding.rebuild.__globals__,'action_scope':scoped_action}
    rebuild=FunctionType(private_binding.rebuild.__code__,namespace,private_binding.rebuild.__name__,
        private_binding.rebuild.__defaults__,private_binding.rebuild.__closure__ or ())
    rebuild.__kwdefaults__=private_binding.rebuild.__kwdefaults__
    return tuple((module._base,rebuild(module._base,units))
        for module in (binding_v4,binding_v5,binding_v10,binding_v12))


def _private_content(source):
    return {key:value for key,value in source.items()
        if key not in {VERSION,'explicit_operation_source_projection'}}


def _validate_source_annotation(source,protocol):
    if 'explicit_operation_source_projection' not in source:
        return
    from ..scope import explicit_operation_role_v4 as source_projection
    content={key:value for key,value in source.items() if key!='explicit_operation_source_projection'}
    expected=source_projection.project(content,protocol)['explicit_operation_source_projection']
    assert source['explicit_operation_source_projection']==expected,'PRIVATE_REFERENCE_SCOPE_SOURCE_CHANGED'


def project(source,protocol):
    _validate_source_annotation(source,protocol)
    if VERSION in source:
        marker=source[VERSION]
        assert marker['projected_source_sha256']==digest(_private_content(source)),'PRIVATE_REFERENCE_SCOPE_SOURCE_CHANGED'
        rows={row['id']:row for row in source['pair']['candidate']['operations']}
        allowed=set(source['pair']['comparison_scope_contract']['reference_phases'])
        members={}
        for member in [*source.get('membership',[]),
                *source['pair']['comparison_scope_contract'].get('source_ledger',[])]:
            if 'parameter_private_reference_scope' not in member:
                continue
            previous=members.setdefault(member['id'],member)
            if previous!=member:
                raise AssertionError('PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED')
        snapshots=marker.get('projection_input_rows')
        assert isinstance(snapshots,dict) and set(snapshots)==set(members),'PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED'
        expected={}
        for oid,member in members.items():
            evidence=member['parameter_private_reference_scope']
            row=rows.get(oid)
            raw=snapshots[oid]
            if (row is None or row['source']!=member['source'] or raw.get('id')!=oid
                    or any(raw.get(field)!=row.get(field) for field in
                        ('branch','source','raw_text','operation','phase','execution_status'))):
                raise AssertionError('PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED')
            computed=proof(raw,source['pair']['reference']['operations'],protocol,allowed)
            if (computed is None or computed!=evidence
                    or row.get('parameter_private_reference_scope')!=evidence
                    or row.get('matching_identity')!=computed['actual_primary_identity']
                    or row.get('operation_role')!=computed['actual_action_role']
                    or row.get('comparison_phase')!=computed['reference_phase']
                    or member.get('disposition')!='INSIDE' or member.get('phase')!=computed['reference_phase']):
                raise AssertionError('PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED')
            expected[oid]=computed
        assert expected and marker.get('proofs')==expected,'PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED'
        assert marker.get('proofs_sha256')==digest(expected),'PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED'
        return source,deepcopy(expected)
    before=digest(source)
    owner=source['pair']['candidate']
    if 'original_scoped_rows' in owner:
        assert owner['original_scoped_rows']==owner['operations'],'PARAMETER_PRIVATE_PARENT_VIEW_INPUT_MISMATCH'
    out=deepcopy(source)
    candidates={row['id']:row for row in out['pair']['candidate']['operations']}
    typed={row['id']:row for row in out['all_typed_rows']}
    proofs={};projection_input_rows={}
    allowed=set(out['pair']['comparison_scope_contract']['reference_phases'])
    for member in out.get('membership',[]):
        if member.get('disposition')!='UNRESOLVED':
            continue
        row=candidates.get(member['id'])
        if row is None or row['source']!=member['source'] or typed.get(row['id'],{}).get('source')!=row['source']:
            continue
        evidence=proof(row,out['pair']['reference']['operations'],protocol,allowed)
        if evidence is None:
            continue
        phase=evidence['reference_phase']
        projected_row=deepcopy(row)
        projected_typed=deepcopy(typed[row['id']])
        for target in (projected_row,projected_typed):
            target.update(comparison_phase=phase,comparison_phase_candidates=[phase],
                matching_identity=evidence['actual_primary_identity'],operation_role=evidence['actual_action_role'],
                source_hierarchy_phase_fact=phase_fact(target,evidence))
        bound=phase_sets_v4.bound_phase_set(projected_row)
        if bound is None or bound.get('complete') is not True or bound.get('scenarios')!=[[phase]]:
            continue
        projection_input_rows[row['id']]=deepcopy(row)
        row.update(projected_row)
        typed[row['id']].update(projected_typed)
        member.update(disposition='INSIDE',phase=phase,phase_fact=deepcopy(row['source_hierarchy_phase_fact']),
            previous_disposition='UNRESOLVED',parameter_private_reference_scope=deepcopy(evidence))
        proofs[row['id']]=evidence
    ledger=out['pair']['comparison_scope_contract']
    ledger['source_ledger']=deepcopy(out['membership'])
    ledger['unresolved_membership']=[deepcopy(member) for member in out['membership'] if member['disposition']=='UNRESOLVED']
    for choice in ledger.get('membership_choices',[]):
        if choice.get('side')!='candidate' or choice.get('group') not in proofs:
            continue
        evidence=proofs[choice['group']]
        member=next(member for member in out['membership'] if member['id']==choice['group'])
        assert choice.get('evidence',{}).get('source')==member['source']
        choice.update(values=[1],previous_values=deepcopy(choice['values']),
            uncertainty_origin=VERSION,resolution_proof=deepcopy(evidence),evidence=deepcopy(member))
    if proofs:
        for row in out['pair']['candidate']['operations']:
            if row['id'] in proofs:
                row['parameter_private_reference_scope']=deepcopy(proofs[row['id']])
        if 'original_scoped_rows' in owner:
            for original,projected in zip(owner['original_scoped_rows'],out['pair']['candidate']['operations']):
                for field in ('id','branch','source','raw_text','operation'):
                    assert original.get(field)==projected.get(field),'PARAMETER_PRIVATE_RAW_PARENT_CHANGED'
            out['pair']['candidate']['original_scoped_rows']=deepcopy(out['pair']['candidate']['operations'])
        out[VERSION]={'proofs':deepcopy(proofs),'proofs_sha256':digest(proofs),
                      'projection_input_rows':projection_input_rows,
                      'projected_source_sha256':digest(_private_content(out)),
                      'input_source_sha256':before,'raw_answer_not_modified':True,
                      'common_source_not_replaced_for_other_metrics':True}
    assert before==digest(source)
    return out,proofs


def namespace(base):
    def compile_candidate_units(source,protocol,source_time_facts=None,**kwargs):
        projected,proofs=project(source,protocol)
        result=base.compile_candidate_units(projected,protocol,source_time_facts,**kwargs)
        if proofs:
            result=deepcopy(result)
            result['parameter_private_reference_scope']={'version':VERSION,'proofs':deepcopy(proofs),
                'reference_variants_retained':True,'raw_source_not_modified':True}
        return result
    prior=SimpleNamespace(**{**vars(base.prior),'compile_candidate_units':compile_candidate_units})
    return SimpleNamespace(**{**vars(base),'VERSION':VERSION,'prior':prior,
        'compile_candidate_units':compile_candidate_units,'project':project})


def binding_namespace(original,postprocess=None):
    native=original.compile_binding
    assert native.__closure__ is None, 'PRIVATE_BINDING_NATIVE_MUST_BE_MODULE_LEVEL'
    def compile_projected(source,protocol,original_manifest,**kwargs):
        projected,_=reference_scope.project(source,protocol)
        result=prior_compile(projected,protocol,original_manifest,**kwargs)
        if postprocess is not None:
            result=postprocess(result,protocol,original_manifest,source=projected)
        return result
    namespace={**native.__globals__,'reference_scope':SimpleNamespace(project=project),
        'prior_compile':native,'postprocess':postprocess}
    wrapper=FunctionType(compile_projected.__code__,namespace,native.__name__,native.__defaults__,native.__closure__ or (CellType(postprocess),))
    wrapper.__kwdefaults__=native.__kwdefaults__
    return SimpleNamespace(**{**vars(original),'compile_binding':wrapper})
