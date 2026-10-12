"""Candidate source-scoped time and repeated-channel interpretation.

Separates the duration of reported core operations from scientific workflow
completeness. Uses archived semantic assignments, explicit source headings and
exact evidence spans; never supplies missing operation durations.
"""
from __future__ import annotations
import copy
import math
import re
import cce_typed_label_scorer_v2 as typed
b=typed.base
VERSION='reported-operation-scope-v1.1'

PREP_HEADING=re.compile(r'permeabili[sz]|blocking|immunolabel|immunostain|antibody|counterstain|标记|染色|封闭|透化|渗透',re.I)
WASH_HEADING=re.compile(r'\bwash(?:ing)?\b|洗涤|清洗',re.I)
CORE_HEADING=re.compile(r'delipid|decolor|dehydrat|rehydrat|clearing|refractive|\bRI\b|脱脂|脱色|脱水|复水|透明|折射|折光',re.I)
OP_START=re.compile(r'^\s*(?:\d+(?:\.\d+)+[.)]?\s+|(?:incubat\w*|wash\w*|rinse|transfer|replace|repeat|store|immerse|place)\b)',re.I)


def preceding_heading(doc, operation):
    """Locate a short standalone title; preserve all source text and offsets."""
    headings=[]
    offset=0
    for raw in doc['text'].splitlines(keepends=True):
        if offset>=operation['start']:
            break
        text=raw.strip();clean=text.strip('*# ').strip()
        numbered=re.match(r'^\d+\s+(.+)$',clean)
        if numbered: clean=numbered[1]
        candidate=(0<len(clean)<110 and not OP_START.match(text) and
                   not re.search(r'[.!?。；;]|Temperature:|Time:|Chosen|Justification|Protocol Steps',clean,re.I) and
                   (numbered or PREP_HEADING.search(clean) or WASH_HEADING.search(clean) or CORE_HEADING.search(clean)))
        if candidate:
            headings.append({'start':offset,'end':offset+len(raw),'quote':raw,'title':clean})
        offset+=len(raw)
    return headings


def preparation_evidence(operation, doc):
    span=operation['operation'];b.verify_span(doc['text'],span)
    headings=preceding_heading(doc,span)
    if not headings:return {'supported':False,'reason':'no_explicit_phase_heading'}
    heading=headings[-1]
    # A clearing/delipidation title is evidence against excluding it as labeling.
    # A washing title may inherit a preceding explicit labeling phase.
    if PREP_HEADING.search(heading['title']) and not CORE_HEADING.search(heading['title']):
        return {'supported':True,'reason':'explicit_labeling_phase_heading','heading':heading,'operation':span}
    if WASH_HEADING.search(heading['title']):
        for earlier in reversed(headings[:-1]):
            if WASH_HEADING.search(earlier['title']):continue
            if PREP_HEADING.search(earlier['title']) and not CORE_HEADING.search(earlier['title']):
                return {'supported':True,'reason':'wash_within_explicit_labeling_sequence',
                        'heading':heading,'preceding_phase_heading':earlier,'operation':span}
            break
    return {'supported':False,'reason':'source_heading_does_not_establish_excluded_phase','heading':heading,'operation':span}


def time_interpretation(conversion, doc, previous_hours):
    calc=conversion['legacy_projection']['time_calculation']
    original=b.time_input(calc,previous_hours)
    if b.finite(original['hours']):return {**original,'scope':'reported_core_operations'}
    issues=set(calc.get('issues',[]));resolved=[];evidence=[]
    source=conversion['source_audit']['resolved']
    if 'labeling_preparation_not_source_supported_or_possible_core_function' in issues:
        preparations=[op for op in source['operations'] if op['phase']=='labeling_preparation']
        evidence=[{'operation_id':op['id'],**preparation_evidence(op,doc)} for op in preparations]
        if evidence and all(item['supported'] for item in evidence):
            issues.remove('labeling_preparation_not_source_supported_or_possible_core_function')
            resolved.append('labeling_preparation_not_source_supported_or_possible_core_function')
    # The model reports extraction of all described operations as complete. A
    # separate core-coverage flag may identify absent required workflow modules.
    # The computable statistic below is explicitly limited to reported actions.
    coverage=source.get('coverage',{})
    if ('reported_core_operation_coverage_incomplete' in issues and
            coverage.get('time_operations')=='complete'):
        issues.remove('reported_core_operation_coverage_incomplete')
        resolved.append('reported_core_operation_coverage_incomplete_for_reported_duration_only')
    permitted={'nonunique_duration_range'}
    bounds=calc.get('candidate_bounds_hours')
    parts=calc.get('known_operation_contributions',[])
    included=calc.get('included_operation_ids',[])
    computable=(not (issues-permitted) and calc.get('mode')=='serial' and included and
        set(included)=={p['operation_id'] for p in parts} and isinstance(bounds,list) and len(bounds)==2 and
        all(b.finite(v) for v in bounds) and 0<=bounds[0]<=bounds[1] and
        all(math.isclose(sum(p[k] for p in parts),v,abs_tol=1e-10)
            for k,v in zip(['lower_hours','upper_hours'],bounds)))
    return {'hours':sum(bounds)/2 if computable else None,'bounds_hours':bounds,
        'decision':'source_scoped_reported_core_duration' if computable else 'unresolved_source_input',
        'scope':'reported_core_operations','original_issues':calc.get('issues',[]),
        'resolved_scope_issues':resolved,'issues':[] if computable else sorted(issues),
        'phase_evidence':evidence,'operation_contributions':parts,
        'workflow_completeness_not_inferred':True,
        'complete_experimental_endpoint_duration':None if coverage.get('core_time_operations')!='complete' else 'not_separately_estimated',
        'saved_coverage_judgment':coverage}


def repeated_secondary_projection(conversion, doc, policy):
    projection=copy.deepcopy(conversion['label_occurrence_projection'])
    source=conversion['source_audit']['resolved']
    entities={e['id']:e for e in source['entities']}
    changes=[]
    # At this dictionary granularity, two separate targets must not be collapsed
    # merely because the same dye is named. Every used target must agree.
    used_targets={typed.key(e['literal_name']) for e in entities.values()
                  if e['kind']=='target' and e['usage']=='used'}
    # Refer only to the original supported relations, never to a newly resolved
    # copy. This keeps several repeated mentions independent of iteration order.
    supported=[p for p in copy.deepcopy(projection['pairs'])
               if p['kind']=='supported_relation' and p.get('marker_literal') and
               not p.get('same_occurrence_distinct_target_conflict')]
    if source.get('coverage',{}).get('entities')!='complete':
        return projection,changes
    for pair in projection['pairs']:
        if pair['kind']!='unresolved_relation' or pair.get('marker_literal'):
            continue
        if pair.get('same_occurrence_distinct_target_conflict'):
            continue
        span=pair.get('evidence') or {}
        if not re.search(r'secondary\s+antibod|二抗',span.get('quote',''),re.I):
            continue
        b.verify_span(doc['text'],span)
        donors=[p for p in supported if typed.key(p['fluor_literal'])==typed.key(pair['fluor_literal'])]
        target_names={typed.key(p['marker_literal']) for p in donors}
        if len(target_names)!=1 or used_targets!=target_names:
            continue
        donor=donors[0]
        donor_evidence=donor['evidence'] if isinstance(donor['evidence'],list) else [donor['evidence']]
        for donor_span in donor_evidence:b.verify_span(doc['text'],donor_span)
        original=copy.deepcopy(pair)
        pair.update(marker_literal=donor['marker_literal'],kind='supported_relation',
                    evidence=[*donor_evidence,span],scope='unique_source_declared_channel_reference',
                    reference_resolution_rule=VERSION,raw_relation_status=original.get('raw_relation_status'))
        removed=[u for u in projection['explicit_label_uncertainties']
                 if u.get('entity_id')==pair.get('entity_id') and u['kind']=='reported_unresolved_relation']
        projection['explicit_label_uncertainties']=[u for u in projection['explicit_label_uncertainties'] if u not in removed]
        changes.append({'pair_before':original,'pair_after':copy.deepcopy(pair),'removed_uncertainties':removed,
                        'sole_source_target':donor['marker_literal'],'donor_pair_ids':[p['pair_id'] for p in donors]})
    return projection,changes
