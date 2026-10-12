"""Consistent local namespace/name checks plus explicit concentration suffixes."""
import types
from cce_marker_combination_boundary_v2 import *
import cce_marker_combination_boundary_v2 as previous
import cce_name_concentration_boundary_v1 as concentration

ADAPTER_VERSION='consistent-source-name-boundaries-concentration-posthoc-v2'
omitted_numeric_name_suffix=concentration.bind_original(namespace.omitted_numeric_name_suffix)
_environment={**previous._environment,'omitted_numeric_name_suffix':omitted_numeric_name_suffix}
for _name in previous._functions:
    _old=getattr(namespace,_name)
    _new=types.FunctionType(_old.__code__,_environment,name=_name,argdefs=_old.__defaults__,closure=_old.__closure__)
    _new.__kwdefaults__=_old.__kwdefaults__
    _environment[_name]=_new
    globals()[_name]=_new
_convert=_environment['_convert_namespace']
_boundary_convert=types.FunctionType(previous.first.convert.__code__,
    {**vars(previous.first),'_convert':_convert,'ADAPTER_VERSION':ADAPTER_VERSION},name='convert')

def convert(raw,doc):
    cv=_boundary_convert(raw,doc)
    records=[]
    for group in ['method_mentions','entities']:
        for r in cv['source_audit']['resolved'][group]:
            name=r['name'];unit=next(u for u in doc['units'] if u['unit_id']==name['unit_id'])
            trailing=doc['text'][name['end']:unit['end']]
            changed=namespace.omitted_numeric_name_suffix(trailing) and not omitted_numeric_name_suffix(trailing)
            if changed:records.append({'record_type':group,'raw_id':r['id'],'literal':name['quote'],
                'raw_name_occurrence':r['name_occurrence'],'name_span':name,
                'concentration_evidence':concentration.concentration_prefix(trailing),
                'name_or_ordinal_rewritten':False,'relationship_inferred':False})
    cv['concentration_name_boundary_audit']={'version':concentration.VERSION,'changed_records':records,
        'original_boundary_guards_otherwise_unchanged':True,'raw_modified':False}
    return cv
