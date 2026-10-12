"""Resolve section-title recall and routine antibody washes against source text.

Implements the original time rubric's exclusion of routine PBS washes while
retaining clearing reagent transitions. Does not supply unreported durations.
"""
import copy
import math
import re
import cce_reported_operation_scope_v1 as previous
b=previous.b
VERSION='time-heading-and-label-wash-scope-v1'
TITLE=re.compile(r'^(?:\d+\s+)?(?:dehydration(?:\s*\([^)]*\))?|rehydration|delipidation|'
    r'decolori[sz]ation|wash(?:ing)?|storage(?:\s+and\s+imaging\s+preparation)?)$',re.I)
BUFFER=re.compile(r'\b(?:PBS|PBST|PBT|PTwH)\b',re.I)


def title_evidence(item,conversion,doc):
    span=item['span'];b.verify_span(doc['text'],span)
    unit=next(u for u in doc['units'] if u['unit_id']==span['unit_id'])
    title=unit['text'].strip().strip('*# ').strip()
    if not TITLE.fullmatch(title):return {'supported':False,'reason':'not_a_standalone_phase_title','source':span}
    source=conversion['source_audit'];operations=source['resolved']['operations']
    after=[u for u in doc['units'] if u['start']>=unit['end']]
    end=len(doc['text'])
    for later in after:
        probe={'start':later['end']}
        # The existing title locator also recognizes antibody phases. It is
        # used only to identify the end of this section, not to infer times.
        headings=previous.preceding_heading(doc,probe)
        if any(h['start']==later['start'] for h in headings):
            end=later['start'];break
    children=[op for op in operations if unit['end']<=op['operation']['start']<end]
    leads=[x for x in source['inventory'] if x.get('kind')=='operation_record_lead'
           and unit['end']<=x['span']['start']<end]
    def represented(lead):
        return any(op['operation']['start']<=lead['span']['start'] and op['operation']['end']>=lead['span']['end']
                   for op in children)
    supported=bool(children) and all(represented(lead) for lead in leads)
    return {'supported':supported,'reason':'section_title_with_explicit_recorded_children' if supported else 'section_has_unrepresented_actions',
        'source':span,'section_end':end,'child_operation_ids':[op['id'] for op in children],
        'action_candidate_ids':[x['candidate_id'] for x in leads]}


def time_interpretation(conversion,doc,previous_hours):
    candidate=copy.deepcopy(conversion)
    calc=candidate['legacy_projection']['time_calculation']
    original_calc=conversion['legacy_projection']['time_calculation']
    original_issues=list(calc.get('issues',[]));changes=[]
    if 'source_action_records_not_all_classified' in calc.get('issues',[]):
        missing=[x for x in conversion['source_audit']['inventory'] if x.get('kind')=='operation_record_lead'
                 and x.get('coverage_state')!='covered_operation_record']
        evidence=[title_evidence(x,conversion,doc) for x in missing]
        if evidence and all(x['supported'] for x in evidence):
            calc['issues'].remove('source_action_records_not_all_classified')
            changes.append({'rule':'phase_titles_are_not_additional_unclassified_operations','evidence':evidence})
    wash_ids=[];wash_evidence=[]
    for op in conversion['source_audit']['resolved']['operations']:
        if op['phase']!='reagent_transition_wash' or op['id'] not in calc.get('included_operation_ids',[]):continue
        evidence=previous.preparation_evidence(op,doc)
        if (evidence.get('supported') and evidence['reason']=='wash_within_explicit_labeling_sequence'
                and BUFFER.search(op['operation']['quote'])):
            wash_ids.append(op['id']);wash_evidence.append({'operation_id':op['id'],'raw_phase':op['phase'],
                'interpreted_phase':'routine_wash_after_antibody_labeling','source':op['operation'],**evidence})
    parts=calc.get('known_operation_contributions',[])
    if wash_ids:
        byid={p['operation_id']:p for p in parts}
        if not all(i in byid for i in wash_ids):
            return {**previous.time_interpretation(conversion,doc,previous_hours),
                'heading_scope_candidate':{'version':VERSION,'unapplied_wash_evidence':wash_evidence,
                'reason':'no_complete_ledger_for_subtraction'}}
        before=calc.get('candidate_bounds_hours')
        if not (isinstance(before,list) and len(before)==2 and all(b.finite(v) for v in before)):
            return {**previous.time_interpretation(candidate,doc,previous_hours),
                'heading_scope_candidate':{'version':VERSION,'unapplied_wash_evidence':wash_evidence,
                'reason':'original_core_time_ledger_has_open_bounds','title_changes':changes}}
        # Only subtract source-grounded entries from a fully represented ledger.
        if any(not math.isclose(sum(p[k] for p in parts),v,abs_tol=1e-10)
               for k,v in zip(['lower_hours','upper_hours'],before)):
            raise ValueError('Duration ledger and bounds disagree before scope change')
        excluded=[p for p in parts if p['operation_id'] in wash_ids]
        calc['known_operation_contributions']=[p for p in parts if p['operation_id'] not in wash_ids]
        calc['included_operation_ids']=[i for i in calc['included_operation_ids'] if i not in wash_ids]
        calc['candidate_bounds_hours']=[sum(p[k] for p in calc['known_operation_contributions']) for k in ['lower_hours','upper_hours']]
        changes.append({'rule':'exclude_routine_antibody_labeling_washes_per_original_rubric','evidence':wash_evidence,
            'removed_contributions':excluded,'bounds_before':before,'bounds_after':calc['candidate_bounds_hours']})
        previous_hours=None
    result=previous.time_interpretation(candidate,doc,previous_hours)
    result['heading_scope_candidate']={'version':VERSION,'original_issues':original_issues,'changes':changes,
        'source_operations_not_modified':True,'raw_phase_assignments_preserved':True}
    return result
