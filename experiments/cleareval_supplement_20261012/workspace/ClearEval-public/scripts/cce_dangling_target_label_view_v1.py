"""Explicit label dependency view for a dangling target ID; no invented target.

The original converter is always tried first. Only its exact dangling-entity
failure can produce a view. The caller retains the original full failure and
uses this result for s_label alone, not as a successful original conversion.
"""
import copy
import hashlib
import json
import evaluator_integrity as integrity

VERSION='dangling-target-label-dependency-view-v1'


def _sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def prepare_view(raw):
    """Return a derived payload and every original dangling relation.

    This is not a standalone acceptance check. convert_with_isolation runs the
    original converter before and after this narrow dependency transformation.
    """
    original=integrity.parse_judge_object(raw)
    view=copy.deepcopy(original)
    records=view['grounded_extraction']
    entity_ids=[row['i'] for row in records['entities']]
    if len(entity_ids)!=len(set(entity_ids)):
        raise ValueError('DUPLICATE_ENTITY_ID_NOT_ISOLATABLE')
    known=set(entity_ids)
    changes=[]
    for row in records['relations']:
        # A missing fluorophore would invalidate the identity of the usage.
        # It cannot be repaired by inventing an entity or discarding the row.
        if row['f'] not in known:
            raise ValueError('DANGLING_FLUOR_NOT_ISOLATABLE')
        target=row['t']
        if target is None:
            continue
        if not isinstance(target,str) or not target:
            raise ValueError('NONSTRING_DANGLING_TARGET_NOT_ISOLATABLE')
        if target in known:
            continue
        before=copy.deepcopy(row)
        row['t']=None
        row['s']='unknown'
        row['to']=None
        changes.append({'relation_id':row['i'],'original_record':before,
          'derived_record':copy.deepcopy(row),
          'reason':'undeclared_target_id_preserved_as_unknown_in_label_dependency_view',
          'invented_target':False,'record_deleted':False})
    if not changes:
        raise ValueError('NO_DANGLING_TARGET_TO_ISOLATE')
    return original,view,changes


def convert_with_isolation(raw,doc,case,convert_fn):
    """Call convert_fn(raw, doc, case); locally isolate only dangling targets.

    The returned conversion contains the explicit derived wire as its input,
    plus the exact original raw/wire in dangling_target_label_view_v1. It is
    never a claim that the original return passed conversion. A caller must
    keep the full failure/status and retain unknown relations in label scoring.
    Do not pass a converter that infers targets from null records: this view
    deliberately means unknown, not a new source-target completion request.
    """
    try:
        return convert_fn(raw,doc,case)
    except Exception as exc:
        if str(exc)!='RELATION_DANGLING_ENTITY':
            raise
        original_error={'type':type(exc).__name__,'message':str(exc)}
    original,view,changes=prepare_view(raw)
    derived_raw=_canonical(view)
    conversion=convert_fn(derived_raw,doc,case)
    # If another record is malformed, the original converter raises above.
    # In particular: source/version, duplicate IDs, names and evidence still
    # pass the unchanged validator. No converter failure is hidden here.
    resolved=conversion['source_audit']['resolved']['relations']
    unresolved=[]
    for change in changes:
        matches=[row for row in resolved if row['id']==change['relation_id']]
        if len(matches)!=1:
            raise ValueError('ISOLATION_RESOLVED_RECORD_NOT_UNIQUE')
        row=matches[0]
        if row['status']!='unknown' or row.get('target_entity_id') is not None or row.get('projection_allowed'):
            raise ValueError('ISOLATION_MUST_REMAIN_UNKNOWN')
        unresolved.append({'relation_id':row['id'],
          'original_record':copy.deepcopy(change['original_record']),
          'source_evidence':copy.deepcopy(row.get('evidence')),
          'derived_record':copy.deepcopy(change['derived_record']),
          'unknown_not_deleted':True,'relationship_established':False})
    conversion['dangling_target_label_view_v1']={
      'version':VERSION,'dependency_view':True,'allowed_metric':'s_label',
      'original_full_conversion_success':False,'original_failure':original_error,
      'original_raw':raw,'original_raw_sha256':_sha(raw),
      'original_wire_payload':original,'original_wire_sha256':_sha(_canonical(original)),
      'derived_raw':derived_raw,'derived_raw_sha256':_sha(derived_raw),
      'derived_wire_payload':view,'derived_wire_sha256':_sha(_canonical(view)),
      'changes':changes,'unresolved_relations':unresolved,
      'original_raw_modified':False,'original_status_promoted':False,
      'target_source_reattachment_applied':False,'scientific_values_added':False,
      'new_model_calls':0}
    return conversion
