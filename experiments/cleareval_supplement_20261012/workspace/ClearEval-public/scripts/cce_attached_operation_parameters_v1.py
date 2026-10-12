"""Source-bound, posthoc support for a numbered operation's attached metadata.

Raw references, spans, values and statuses are retained. A heading, ingredient
list and its sole trailing Time/Temperature line form one source record; they
need not be one physical line. No general cross-unit reference is permitted.
"""
import ast
import copy
import inspect
import re
import types
from cce_posthoc_name_boundary_v2 import *
import cce_posthoc_name_boundary_v2 as previous

VERSION_ADAPTER='attached-operation-parameter-record-posthoc-v1'
HEADER=re.compile(r'^\s*(\d+(?:\.\d+)+)\s+Incubation\s+with\s+([^:\n]+):\s*$',re.I)
BULLET=re.compile(r'^\s*[-*•–—]\s+\S')
META=re.compile(r'^\s*\(?\s*(?:Temperature\s*:[^,;()\n]+\s*[,;]\s*)?Time\s*:\s*[^()\n]+\)?\s*$' ,re.I)
ACTION=re.compile(r'\b(?:incubat\w*|wash\w*|rinse|transfer|replace|repeat|then|after|before|if|unless|optional|additional|further)\b',re.I)

def attached_parameter_support(operation,value,doc):
    units=doc['units'];index={u['unit_id']:i for i,u in enumerate(units)}
    if operation['unit_id'] not in index or value['unit_id'] not in index:return None
    i,j=index[operation['unit_id']],index[value['unit_id']]
    if not i<j:return None
    source=units[i];meta=units[j]
    if doc['text'][operation['start']:operation['end']]!=operation['quote'] or operation['quote'].strip()!=source['text'].strip():return None
    if doc['text'][value['start']:value['end']]!=value['quote'] or not(meta['start']<=value['start']<value['end']<=meta['end']):return None
    if not HEADER.fullmatch(source['text']) or not META.fullmatch(meta['text']):return None
    interior=units[i+1:j]
    if not interior or not all(BULLET.match(u['text']) and not ACTION.search(u['text']) for u in interior):return None
    if ACTION.search(meta['text']):return None
    # Exactly one duration and no next parameter line belonging to another
    # branch. Numbered next actions terminate this record without ambiguity.
    durations=[m for m in previous.DURATION.finditer(meta['text']) if previous.duration_role(m.group(),meta['text'][:m.start()],meta['text'][m.end():])[0]=='duration']
    if len(durations)!=1:return None
    if j+1<len(units) and META.fullmatch(units[j+1]['text']):return None
    return {'basis':'numbered_incubation_colon_ingredient_list_unique_trailing_parameter_line',
        'operation_span':copy.deepcopy(operation),'attached_value_span':copy.deepcopy(value),
        'record_units':copy.deepcopy(units[i:j+1]),'source_id':doc['source_id'],'answer_sha256':doc['answer_sha256'],
        'original_spans_retained':True,'conditional_meaning_inferred':False,'new_operation_created':False}

def same_operation_record(operation,value,doc):
    return operation['unit_id']==value['unit_id'] or attached_parameter_support(operation,value,doc) is not None

def record_binding(operation,value,doc):
    original=previous.record_binding(operation,value,doc)
    if original['valid'] or operation['unit_id']==value['unit_id']:return original
    support=attached_parameter_support(operation,value,doc)
    if not support:return original
    return {'valid':True,'mode':'attached_unique_parameter_line_of_numbered_operation',
        'original_binding':original,'source_record_support':support,'semantic_assignment_verified':False}

_environment={**previous._environment,'record_binding':record_binding,'same_operation_record':same_operation_record}
_old=previous._audit_expanded_payload
_tree=ast.parse(inspect.getsource(_old));_replacements=0
for _node in ast.walk(_tree):
    if isinstance(_node,ast.Call) and isinstance(_node.func,ast.Name) and _node.func.id=='require' and len(_node.args)==2 and isinstance(_node.args[1],ast.Constant) and _node.args[1].value=='CONDITION_OUTSIDE_OPERATION_RECORD':
        assert ast.unparse(_node.args[0])=="o['operation']['unit_id'] == o['condition_evidence']['unit_id']"
        _node.args[0]=ast.parse("same_operation_record(o['operation'], o['condition_evidence'], doc)",mode='eval').body
        _replacements+=1
assert _replacements==1
exec(compile(ast.fix_missing_locations(_tree),__file__,'exec'),_environment)
_audit_expanded_payload=_environment['_audit_expanded_payload']
for _name in ['audit_payload','_convert_namespace']:
    _f=getattr(previous,_name)
    _environment[_name]=types.FunctionType(_f.__code__,_environment,name=_name,argdefs=_f.__defaults__,closure=_f.__closure__)
_convert=_environment['_convert_namespace']
_boundary_convert=types.FunctionType(previous._boundary_convert.__code__,
    {**previous._boundary_convert.__globals__,'_convert':_convert},name='_boundary_convert')
_convert_original_shape=types.FunctionType(previous.convert.__code__,
    {**previous.convert.__globals__,'_boundary_convert':_boundary_convert},name='convert')

def convert(raw,doc):
    result=_convert_original_shape(raw,doc);rows=[]
    for o in result['source_audit']['resolved']['operations']:
        for field in ['condition_evidence','duration']:
            if o.get(field) and o['operation']['unit_id']!=o[field]['unit_id']:
                support=attached_parameter_support(o['operation'],o[field],doc)
                if support:rows.append({'operation_id':o['id'],'field':field,'support':support})
    result['attached_operation_parameters']={'version':VERSION_ADAPTER,'records':rows,
        'raw_modified':False,'only_one_original_condition_guard_expression_changed':True,
        'same_unit_guards_and_all_other_source_checks_preserved':True}
    return result

def build_backend(base):
    """Compose after a source-name/relation backend without losing its helpers."""
    environment={**base._environment,'record_binding':record_binding,'same_operation_record':same_operation_record}
    tree=ast.parse(inspect.getsource(base._audit_expanded_payload));replacements=0
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='require' and len(node.args)==2 and isinstance(node.args[1],ast.Constant) and node.args[1].value=='CONDITION_OUTSIDE_OPERATION_RECORD':
            assert ast.unparse(node.args[0])=="o['operation']['unit_id'] == o['condition_evidence']['unit_id']"
            node.args[0]=ast.parse("same_operation_record(o['operation'], o['condition_evidence'], doc)",mode='eval').body
            replacements+=1
    assert replacements==1
    exec(compile(ast.fix_missing_locations(tree),__file__,'exec'),environment)
    for name in ['audit_payload','_convert_namespace']:
        f=getattr(base,name)
        environment[name]=types.FunctionType(f.__code__,environment,name=name,argdefs=f.__defaults__,closure=f.__closure__)
    inner=base.convert.__globals__.get('_boundary_convert',base._boundary_convert)
    assert inner is base._boundary_convert,'STALE_BOUNDARY_BACKEND_ATTRIBUTE'
    rebound_inner=types.FunctionType(inner.__code__,{**inner.__globals__,'_convert':environment['_convert_namespace']},
        name='_boundary_convert',argdefs=inner.__defaults__,closure=inner.__closure__)
    original_shape=types.FunctionType(base.convert.__code__,{**base.convert.__globals__,'_boundary_convert':rebound_inner},
        name='convert',argdefs=base.convert.__defaults__,closure=base.convert.__closure__)
    output={**vars(base),**{name:environment[name] for name in ['_audit_expanded_payload','audit_payload','_convert_namespace']},
        '_environment':environment,'_boundary_convert':rebound_inner,
        'record_binding':record_binding,'same_operation_record':same_operation_record,'attached_parameter_support':attached_parameter_support}
    output['convert']=types.FunctionType(convert.__code__,{**globals(),'_convert_original_shape':original_shape},name='convert')
    return types.SimpleNamespace(**output)

converter_for=build_backend
