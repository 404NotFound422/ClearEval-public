"""Source-bound local duration relationships for ordinary OEQ diagnostics.

Local textual arithmetic is independent of scientific applicability. No phase,
complete candidate membership or full-protocol elapsed total is inferred.
"""
from copy import deepcopy
import math
import re
from extract_clearing_time import audit_duration_scope
from experiments.construct_validity.fidelity import text_hash, validate_span, CONDITION, NEGATION

VERSION='oeq-quantity-scope-v3'
ROLE_INPUT_VERSION='oeq-quantity-role-inputs-v1'
_STEP=re.compile(r'^\s*(\d+(?:\.\d+)+)\s+')
_HEADING=re.compile(r'^\s*\d+\s+\S')
_CANDIDATE=re.compile(r'^\s*(?:#+\s*)?(?:\d+\s+)?(?:candidate|alternative|option)\s+[A-Za-z0-9]',re.I)
_OPEN_CONTROL=re.compile(r'^\s*(?:[>*#-]\s*)*(?:if\b|unless\b|provided that\b|do\s+not\b|never\b|如果|若|仅当|不得|不要).*(?:[:：;；]\s*$|\b(?:following|below)\b)',re.I)


def _bounds(audit):
    if audit['status']=='AMBIGUOUS':return None
    if audit.get('range') is not None:
        if audit.get('repeats') is not None and audit['range'].get('scope')!='TOTAL_ELAPSED_DERIVED_FROM_EXPLICIT_REPEAT':return None
        return [audit['range']['min_h'],audit['range']['max_h']]
    if audit['status']=='EXPLICIT' and audit.get('total') is not None:
        return [audit['total']['hours'],audit['total']['hours']]
    return None


def audit_quantity_scope(protocol, extraction=None):
    if not isinstance(protocol,str):raise ValueError('Original complete answer text required')
    records=[];offset=0;heading=None;open_controls=[];candidate_started=False
    for raw in protocol.splitlines(keepends=True):
        line=raw.rstrip('\r\n')
        start,end=offset,offset+len(line);offset+=len(raw)
        match=_STEP.match(line)
        candidate_heading=re.sub(r'[*_`]', '', line)
        if _CANDIDATE.match(candidate_heading):
            if candidate_started:
                open_controls=[c for c in open_controls if c['scope']=='BEFORE_DECLARED_CANDIDATES']
            candidate_started=True
        if _HEADING.match(line):heading=dict(start=start,end=end,quote=line)
        if not match:
            if _OPEN_CONTROL.search(line):
                open_controls.append(dict(source_span=dict(start=start,end=end,quote=line),
                    scope='WITHIN_DECLARED_CANDIDATE' if candidate_started else 'BEFORE_DECLARED_CANDIDATES'))
            continue
        duration=audit_duration_scope(line)
        duration['offset_basis']='STEP_LOCAL_UNICODE_CODEPOINTS'
        for item in (duration.get(k) for k in ('per_repeat','repeats','total','range','interval','metadata','declared_total_window')):
            if isinstance(item,dict) and item.get('span') is not None:
                left,right=item['span'];item['protocol_span']=dict(start=start+left,end=start+right,quote=protocol[start+left:start+right])
                validate_span(protocol,item['protocol_span'])
        bounds=_bounds(duration)
        controls=deepcopy(open_controls)
        if CONDITION.search(line) or NEGATION.search(line):
            controls.append(dict(source_span=dict(start=start,end=end,quote=line),scope='LOCAL_STEP'))
        conditional=bool(controls)
        records.append(dict(source_record_id=f'{match.group(1)}@{start}',step_id=match.group(1),
            source_span=dict(start=start,end=end,quote=line),source_section=deepcopy(heading),
            local_duration_relation=duration,reported_local_elapsed_bounds_h=bounds,
            execution_status='NEGATED_OR_CONDITIONAL_NOT_CERTIFIED' if conditional else 'NOT_CERTIFIED_BY_DURATION_TEXT',
            source_control_guards=controls,
            quantity_relation_status='EXPLICIT_LOCAL_RELATION' if bounds is not None else 'UNRESOLVED',
            candidate_identity=None,scientific_truth=None))
    checks=[]
    if isinstance(extraction,dict):
        values=extraction.get('protocol_time_hours')
        supports=extraction.get('field_support',{})
        if isinstance(values,list):
            for index,value in enumerate(values):
                path=f'/protocol_time_hours/{index}'
                check=dict(path=path,reported_hours=value,status='UNRESOLVED',source_record_id=None,
                           reason='EXACT_STEP_AND_SOURCE_SCOPE_NOT_BOUND',scientific_truth=None)
                support=supports.get(path) if isinstance(supports,dict) else None
                try:
                    if (not isinstance(support,dict) or support.get('kind')!='EXPLICIT'
                            or not isinstance(support.get('spans'),list) or len(support['spans'])!=1):
                        raise ValueError('No one exact field span')
                    span=support['spans'][0];context=support['context_span']
                    validate_span(protocol,span);validate_span(protocol,context)
                    if not context['start']<=span['start']<span['end']<=context['end']:
                        raise ValueError('Value outside supplied context')
                    matches=[r for r in records if r['source_span']['start']<=span['start']<span['end']<=r['source_span']['end']]
                    if len(matches)!=1:raise ValueError('Original step not uniquely bound')
                    row=matches[0];source=row['source_span'];bounds=row['reported_local_elapsed_bounds_h']
                    check.update(source_record_id=row['source_record_id'],source_span=deepcopy(source),
                                 local_elapsed_bounds_h=deepcopy(bounds))
                    if context['start']>source['start'] or context['end']<source['end']:
                        raise ValueError('Supplied context clips original step')
                    if bounds is None or row['source_control_guards']:
                        raise ValueError('Duration relation or execution condition unresolved')
                    witnesses=[item['protocol_span'] for item in row['local_duration_relation'].values()
                               if isinstance(item,dict) and 'protocol_span' in item]
                    if not any(w['start'] < span['end'] and span['start'] < w['end'] for w in witnesses):
                        raise ValueError('Field does not overlap a duration witness')
                    if support.get('raw_value') != span['quote'] or not re.search(r'\d+\s*(?:hours?|hrs?|h|days?|minutes?|mins?|小时|分钟|天)\b',span['quote'],re.I):
                        raise ValueError('Field value is not an explicit duration quantity')
                    if type(value) not in {int,float} or not math.isfinite(value) or value<0:
                        raise ValueError('Invalid reported hours')
                    consistent=bounds[0]-1e-12<=value<=bounds[1]+1e-12
                    check.update(status='CONSISTENT_LOCAL_ELAPSED_BOUNDS' if consistent else 'CONTRADICTED_LOCAL_ELAPSED',
                                 reason='FINITE_ORIGINAL_STEP_ARITHMETIC_NOT_PROTOCOL_TOTAL')
                except (ValueError,KeyError,TypeError) as exc:
                    check['detail']=str(exc)
                checks.append(check)
    return dict(schema_version=VERSION,protocol_sha256=text_hash(protocol),
        scope='NUMBERED_ORIGINAL_STEP_QUANTITY_RELATION_NOT_SCIENTIFIC_TIME_FEASIBILITY',
        records=records,record_count=len(records),
        explicit_local_relation_count=sum(r['quantity_relation_status']=='EXPLICIT_LOCAL_RELATION' for r in records),
        unresolved_local_relation_count=sum(r['quantity_relation_status']=='UNRESOLVED' for r in records),
        flat_time_field_checks=checks,
        contradicted_local_time_field_count=sum(c['status']=='CONTRADICTED_LOCAL_ELAPSED' for c in checks),
        full_protocol_total_h=None,clearing_total_validation='UNRESOLVED_MEMBERSHIP_AND_EXECUTION_TOPOLOGY_NOT_BOUND',
        scientific_accuracy=None,full_content_recall=None,
        numerical_scores_replaced=False,policy='KEEP_LOCAL_REPEAT_RANGE_INTERVAL;NO_INFERRED_CANDIDATE_OR_PHASE_SUM')


def sum_declared_duration_bounds(ledger, source_record_ids, *, protocol):
    """Finite arithmetic for explicitly supplied unique membership; no global total."""
    if (not isinstance(source_record_ids,list) or not source_record_ids
            or any(not isinstance(i,str) for i in source_record_ids)
            or len(set(source_record_ids))!=len(source_record_ids)):
        raise ValueError('Nonempty unique source record IDs required')
    rebuilt=audit_quantity_scope(protocol)
    if ledger.get('protocol_sha256')!=rebuilt['protocol_sha256'] or ledger.get('records')!=rebuilt['records']:
        raise ValueError('Ledger changed or does not bind this complete original answer')
    by_id={r['source_record_id']:r for r in ledger['records']}
    if any(i not in by_id for i in source_record_ids):raise ValueError('Unknown source record')
    selected=[by_id[i] for i in source_record_ids]
    if any(r['reported_local_elapsed_bounds_h'] is None or r['source_control_guards'] for r in selected):
        return dict(status='UNRESOLVED',bounds_h=None,scope='CALLER_DECLARED_MEMBERSHIP_ONLY_NOT_PROTOCOL_TOTAL')
    return dict(status='ARITHMETIC_COMPUTED',bounds_h=[sum(r['reported_local_elapsed_bounds_h'][k] for r in selected) for k in (0,1)],
                source_record_ids=list(source_record_ids),scope='CALLER_DECLARED_MEMBERSHIP_ONLY_NOT_PROTOCOL_TOTAL',
                phase_and_candidate_membership_certified=False,scientific_time_feasibility=None)

def _validate_role_value(role, value):
    if value is None:
        return
    if isinstance(value, list):
        if (role == 'repeat_count' or len(value) != 2
                or any(type(v) not in {int,float} or not math.isfinite(v) or v < 0 for v in value)
                or value[0] > value[1]):
            raise ValueError('Ordered finite nonnegative quantity range required')
    elif (role == 'range_h' or type(value) not in {int,float}
          or not math.isfinite(value) or value < 0):
        raise ValueError('Finite nonnegative numerical quantity role required')


def audit_local_duration_claim(protocol, step_span, claim):
    """Check source role values, preserving ranges and unresolved total topology."""
    validate_span(protocol,step_span)
    allowed={'per_repeat_h','repeat_count','total_elapsed_h','interval_h','range_h'}
    if not isinstance(claim,dict) or set(claim)-allowed:raise ValueError('Finite duration role fields required')
    for role,value in claim.items():_validate_role_value(role,value)
    ledger=audit_quantity_scope(protocol)
    matches=[r for r in ledger['records'] if r['source_span']==step_span]
    if len(matches)!=1:raise ValueError('One complete original numbered step required')
    row=matches[0];a=row['local_duration_relation'];per=a['per_repeat']
    per_value=(per.get('hours',[per['min_h'],per['max_h']]) if per and 'min_h' in per else per.get('hours') if per else None)
    expected={'per_repeat_h':per_value,
              'repeat_count':a['repeats']['count'] if a['repeats'] else None,
              'total_elapsed_h':row['reported_local_elapsed_bounds_h'],
              'interval_h':a['interval']['hours'] if a['interval'] else None,
              'range_h':[a['range']['min_h'],a['range']['max_h']] if a['range'] else None}
    checks=[]
    for role,value in claim.items():
        target=expected[role];status='UNRESOLVED';reason='ROLE_OR_EXECUTION_SCOPE_NOT_EXPLICIT'
        supported=(a['status']!='AMBIGUOUS' or a.get('quantity_role_supported',{}).get(role) is True)
        if value is not None and target is not None and not row['source_control_guards'] and supported:
            if isinstance(value,list):
                target_bounds=target if isinstance(target,list) else [target,target]
                equal=all(math.isclose(value[k],target_bounds[k],rel_tol=1e-12,abs_tol=1e-12) for k in (0,1))
            elif isinstance(target,list):
                equal=target[0]-1e-12<=value<=target[1]+1e-12
                if role!='total_elapsed_h' and equal and target[0]!=target[1]:
                    checks.append(dict(role=role,proposed_value=value,source_expected_value_or_bounds=target,
                                       status='UNRESOLVED',reason='SOURCE_RANGE_DOES_NOT_CERTIFY_EXACT_ROLE_VALUE'))
                    continue
            else:equal=math.isclose(value,target,rel_tol=1e-12,abs_tol=1e-12)
            status='SATISFIED' if equal else 'VIOLATED';reason='FINITE_ORIGINAL_STEP_QUANTITY_ROLE_CHECK'
        checks.append(dict(role=role,proposed_value=value,source_expected_value_or_bounds=target,status=status,reason=reason))
    return dict(schema_version=VERSION,scope='TEXTUAL_QUANTITY_RELATION_NOT_SCIENTIFIC_ACCEPTABILITY',
                protocol_sha256=ledger['protocol_sha256'],source_record_id=row['source_record_id'],source_span=deepcopy(step_span),
                checks=checks,scientific_truth=None,task_necessity=None)


def audit_quantity_role_inputs(protocol, supplied=None):
    """Validate and replay optional model/source role claims in normal OEQ.

    A continuous quoted fragment can be valid input but cannot prove a complete
    step. Such claims remain unresolved. No independent or scientific reference
    is inferred from a caller-provided record, regardless of its label/name.
    """
    from collections import Counter
    if not isinstance(protocol, str) or not protocol.strip():
        raise ValueError('Complete original answer text required')
    base = dict(schema_version=ROLE_INPUT_VERSION,
                protocol_sha256=text_hash(protocol),
                scope='SOURCE_QUANTITY_ROLE_FAITHFULNESS_NOT_SCIENTIFIC_ACCEPTABILITY',
                independent_reference_count=0, scientific_accuracy=None,
                numerical_scores_replaced=False)
    if supplied is None:
        return dict(base, status='UNAVAILABLE', reason='BOUND_QUANTITY_ROLE_CLAIMS_NOT_SUPPLIED',
                    record_count=0, field_check_count=0, status_counts={},
                    confirmed_contradiction_count=0, records=[])
    if (not isinstance(supplied, dict)
            or set(supplied) != {'schema_version', 'records'}
            or supplied['schema_version'] != ROLE_INPUT_VERSION
            or not isinstance(supplied['records'], list)):
        raise ValueError('Versioned quantity role input records required')
    allowed = {'per_repeat_h', 'repeat_count', 'total_elapsed_h', 'interval_h', 'range_h'}
    ids, keys, records, statuses = set(), set(), [], []
    for row in supplied['records']:
        if (not isinstance(row, dict) or set(row) != {'record_id', 'source_span', 'claim'}
                or not isinstance(row['record_id'], str) or not row['record_id'].strip()
                or row['record_id'] in ids or not isinstance(row['claim'], dict)
                or not row['claim'] or set(row['claim']) - allowed):
            raise ValueError('Unique bound quantity role record and finite typed claims required')
        ids.add(row['record_id'])
        validate_span(protocol, row['source_span'])
        for role, value in row['claim'].items():
            key = (row['source_span']['start'], row['source_span']['end'], role)
            if key in keys:
                raise ValueError('Duplicate source quantity role claim')
            keys.add(key)
            _validate_role_value(role, value)
        try:
            audit = audit_local_duration_claim(protocol, row['source_span'], row['claim'])
        except ValueError as exc:
            if str(exc) != 'One complete original numbered step required':
                raise
            audit = dict(schema_version=VERSION,
                         scope='TEXTUAL_QUANTITY_RELATION_NOT_SCIENTIFIC_ACCEPTABILITY',
                         protocol_sha256=text_hash(protocol), source_record_id=None,
                         source_span=deepcopy(row['source_span']),
                         checks=[dict(role=role, proposed_value=value,
                                      source_expected_value_or_bounds=None, status='UNRESOLVED',
                                      reason='COMPLETE_ORIGINAL_NUMBERED_STEP_NOT_BOUND')
                                 for role, value in row['claim'].items()],
                         scientific_truth=None, task_necessity=None)
        records.append(dict(record_id=row['record_id'], input_claim=deepcopy(row['claim']), audit=audit))
        statuses.extend(check['status'] for check in audit['checks'])
    return dict(base, status='VALID_SOURCE_ROLE_AUDIT', record_count=len(records),
                field_check_count=len(statuses), status_counts=dict(Counter(statuses)),
                confirmed_contradiction_count=statuses.count('VIOLATED'), records=records)
