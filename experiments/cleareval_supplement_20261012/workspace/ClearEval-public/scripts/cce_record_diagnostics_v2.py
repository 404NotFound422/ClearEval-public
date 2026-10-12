"""Record-local diagnostics with an explicit compact-reference dependency.

This is a diagnostic entry point. It does not call scoring, revise raw records,
or replace a frozen evaluation processor. Source and name policies are supplied
by the caller's existing backend.
"""
import copy
from cce_grounded_extraction_fieldwise_base_v1 import _expand_ref as expand_compact_reference
from cce_partial_components_v1 import ARRAYS, error


def records_audit(payload, doc, ground):
    """Apply the original record audit with its reference decoder named explicitly."""
    g = payload['grounded_extraction']
    spec = ground.schema_for_document(doc)['properties']['grounded_extraction']['properties']
    rows, issues, byid, duplicate_ids = [], [], {}, set()
    for group in ARRAYS:
        values = g.get(group)
        if not isinstance(values, list):
            issues.append(error('/grounded_extraction/' + group, 'RECORD_ARRAY_REQUIRED', values, [group]))
            continue
        for i, raw in enumerate(values):
            pointer = '/grounded_extraction/' + group + '/' + str(i)
            row = {'pointer': pointer, 'group': group, 'raw_record': copy.deepcopy(raw),
                'id': raw.get('i') if isinstance(raw, dict) else None,
                'valid_shape_and_local_source': False, 'resolved_fields': {}, 'errors': []}
            if isinstance(row['id'], str):
                if row['id'] in byid:
                    duplicate_ids.add(row['id'])
                byid.setdefault(row['id'], []).append(pointer)
            try:
                ground.validate_shape(raw, spec[group]['items'], pointer)
                fields = {'method_mentions': ['u'], 'entities': ['u'], 'relations': ['e'],
                    'intrinsic_signals': ['u'], 'operations': ['o', 'd', 'r', 'c'],
                    'total_time_claims': ['d'], 'ri_mentions': ['v']}[group]
                for field in fields:
                    if raw[field] is not None:
                        row['resolved_fields'][field] = ground.resolve(expand_compact_reference(raw[field]), doc)
                if group in ['method_mentions', 'entities']:
                    row['name'], row['name_binding'] = ground.bind_literal_name(
                        raw['n'], row['resolved_fields']['u'], doc, raw['a'])
                row['valid_shape_and_local_source'] = True
            except Exception as exc:
                row['errors'].append(error(pointer, exc, raw, [group]))
            rows.append(row)
    for row in rows:
        if isinstance(row['id'], str) and row['id'] in duplicate_ids:
            row['valid_shape_and_local_source'] = False
            row['errors'].append(error(row['pointer'], 'DUPLICATE_GLOBAL_RECORD_ID', row['raw_record'], [row['group']]))
        issues += row['errors']
    return rows, issues, {i: byid[i] for i in sorted(duplicate_ids)}
