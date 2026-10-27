"""Rebind typed requirements after source projections, inside parameter evaluation only."""
from copy import deepcopy
from collections import defaultdict
from parameter_action_requirement_binding_20261025_v1 import binder
from . import units

VERSION='parameter-private-typed-and-fine-item-rebind-v1'


def items(parent,rid):
    return [item for item in parent['original_full_fine_item_ledger']
            if item['operation_id']==rid and binder._scope_unit(item)!='ROUTE']


def typed(mapping,evidence,protocol):
    row=deepcopy(mapping['source_row'])
    for field,key in (('matching_identity','actual_primary_identity'),('operation_role','actual_action_role')):
        if units.known(row.get(field)) and row[field]!=evidence[key]:
            raise ValueError('PRIVATE_REFERENCE_ROW_PROJECTION_CONFLICT:'+field)
        row[field]=evidence[key]
    row[units.VERSION]=deepcopy(evidence)
    return units.apply_typed(row,mapping['typed'],protocol)


def fine_records(oid,row,chosen,parent):
    if len(chosen)!=1:
        return [],['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']
    queues=[]
    for reference in chosen:
        queue=defaultdict(list)
        for item in items(parent,reference['operation_id']):
            queue[binder._signature([item])[0]].append(item)
        queues.append(queue)
    records=[]
    for index,item in enumerate(items(parent,chosen[0]['operation_id'])):
        origins=[queue[binder._signature([item])[0]].pop(0) for queue in queues]
        records.append({'binding_id':f'actual:{oid}:fine:{index:04d}',
            'actual_operation_ids':[oid],'actual_source':deepcopy(row['source']),
            'dimension':item['dimension'],'subject':item.get('subject'),'criterion':item['criterion'],
            'source_requirement_items':deepcopy(origins),'original_slot_ids':[origin['id'] for origin in origins],
            'scope_unit':'WRITTEN_OPERATION','contract':parent['contract'],
            'required_even_if_parameter_absent':True,'parameter_presence_not_judged':True,
            'full_criterion_unchanged':True,'template_selection_not_scientific_equivalence':True})
    return records,[]


def rebind(binding,source,protocol):
    members=[*source.get('membership',[]),
        *source['pair']['comparison_scope_contract'].get('source_ledger',[])]
    if units.VERSION not in source and not any('parameter_private_reference_scope' in member
            for member in members):
        return binding
    before=units.digest(binding)
    out=deepcopy(binding)
    proofs=source.get(units.VERSION,{}).get('proofs',{})
    required={member['id'] for member in members
        if member.get('disposition')=='INSIDE' and 'parameter_private_reference_scope' in member}
    if units.VERSION not in source or set(proofs)!=required:
        missing=sorted(required-set(proofs));unexpected=sorted(set(proofs)-required)
        for world in out['worlds']:
            world['gaps'].append({'reason':'PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE_INCOMPLETE',
                'missing_proof_operations':missing,'unexpected_proof_operations':unexpected})
            world.update(complete_applicability=False,denominator=None,
                denominator_status='INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE')
        out['domain']['parameter_private_reference_scope']={'version':units.VERSION,
            'proofs':deepcopy(proofs),'expected_proof_operation_ids':sorted(required),
            'missing_proof_operations':missing,'unexpected_proof_operations':unexpected,
            'reference_variants_retained':False,'raw_source_not_modified':True}
        out['private_typed_rebind']={'version':VERSION,'source_scope_version':units.VERSION,
            'status':'INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE',
            'expected_proof_operation_ids':sorted(required),'actual_proof_operation_ids':sorted(proofs),
            'raw_source_and_original_ledger_unchanged':True,'new_model_calls':0}
        assert units.digest(binding)==before
        return out
    parent=out['parent_action_requirement_binding']
    references=parent['reference_typed_source_ledger']
    relations={entry['actual_operation_id']:entry for entry in parent['template_relation_ledger']}
    new_fine=[];new_gaps=[]
    for mapping in parent['operation_mappings']:
        oid=mapping['operation_id']
        if oid not in proofs:
            new_gaps.extend({'operation_id':oid,'reason':reason} for reason in mapping['gaps'])
            continue
        evidence=proofs[oid]
        current_typed=typed(mapping,evidence,protocol)
        current=[{**binder._relation(current_typed,reference['typed']),
            'template_operation_id':reference['operation_id']} for reference in references]
        chosen=[]
        for index,(reference,relation) in enumerate(zip(references,current)):
            if relation['status']=='BOUND':
                chosen.append(reference)
                continue
            alternative=(evidence.get('different_named_medium_not_equated') is True
                and relation['status']=='DIFFERENT_PRIMARY_MEDIUM'
                and reference['operation_id'] in evidence['reference_operation_ids']
                and units.source_family(current_typed.get('primary_identity'))=='CUBIC'
                and units.source_family(reference['typed'].get('primary_identity'))=='CUBIC'
                and current_typed.get('action_role')==reference['typed'].get('action_role')
                and current_typed.get('phase_fact',{}).get('scenarios')==[[evidence['reference_phase']]])
            if alternative:
                current[index]={**relation,'status':'BOUND_ALTERNATIVE_RECIPE_REVIEW',
                    'evidence':{**relation['evidence'],'different_named_medium_not_equated':True,
                        'source_family':'DECLARED_CUBIC_METHOD_FAMILY','scientific_equivalence_claimed':False}}
                chosen.append(reference)
        signatures={tuple(binder._signature(items(parent,reference['operation_id']))) for reference in chosen}
        records,gaps=fine_records(oid,mapping['source_row'],chosen,parent) if len(signatures)==1 else ([],['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES'])
        if not chosen:
            gaps=['NO_SOURCE_BOUND_ACTION_MEDIUM_TEMPLATE']
        other=[gap for gap in mapping['gaps'] if gap not in {'ACTUAL_OPERATION_SCOPE_MEMBERSHIP_UNRESOLVED',
            'NO_SOURCE_BOUND_ACTION_MEDIUM_TEMPLATE','MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES'}]
        gaps=other+gaps
        member=next((deepcopy(member) for member in source.get('membership',[])
            if member['id']==oid and member['source']==mapping['source_row']['source']),None)
        if member is None:
            member={'id':oid,'source':deepcopy(mapping['source_row']['source'])}
        member.update(disposition='INSIDE',phase=evidence['reference_phase'],
            phase_fact=units.phase_fact(mapping['source_row'],evidence),
            parameter_private_reference_scope=deepcopy(evidence))
        mapping.update(typed=current_typed,status='BOUND' if records and not gaps else 'UNKNOWN',
            selected_template_operations=[reference['operation_id'] for reference in chosen],
            fine_binding_ids=[record['binding_id'] for record in records],gaps=gaps,
            membership_evidence=[member])
        relations[oid]={'actual_operation_id':oid,'relations':current}
        new_fine.extend(records)
        new_gaps.extend({'operation_id':oid,'reason':reason} for reason in gaps)
    parent['bound_written_operation_fine_items']=[item for item in parent['bound_written_operation_fine_items']
        if not set(item['actual_operation_ids'])&set(proofs)]+new_fine
    parent['template_relation_ledger']=[relations[key] for key in relations]
    parent['gaps']=new_gaps
    parent['parameter_private_reference_scope_rebind']={'version':VERSION,
        'source_scope_version':units.VERSION,'typed_and_fine_items_recomputed':True,
        'original_full_fine_item_ledger_unchanged':True,'reference_score_selection_used':False,
        'parameter_presence_not_judged':True}
    mappings={mapping['operation_id']:mapping for mapping in parent['operation_mappings']}
    worlds=[]
    for original in out['worlds']:
        world=deepcopy(original)
        world['slots']=[slot for slot in world['slots']
            if not (slot.get('scope_unit')=='OPERATION' and slot.get('execution_unit_binding',{}).get('unit_id')
                in {unit['unit_id'] for unit in world['units'] if unit['parent_operation_id'] in proofs})]
        gaps=[]
        for gap in world['gaps']:
            if gap.get('reason')!='COMPLETE_PARENT_ACTION_REQUIREMENT_SET_NOT_BOUND':
                gaps.append(gap)
                continue
            mapping=mappings[gap['parent_operation_id']]
            if mapping['gaps']==['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']:
                gaps.append({**gap,'deferred_reference_operation_variants':True,
                    'parent_gaps':deepcopy(mapping['gaps'])})
            elif mapping['gaps']:
                gaps.append({**gap,'parent_gaps':deepcopy(mapping['gaps'])})
        world['gaps']=gaps
        for unit in world['units']:
            oid=unit['parent_operation_id']
            if oid not in proofs:
                continue
            records=[item for item in parent['bound_written_operation_fine_items']
                if item['binding_id'] in mappings[oid]['fine_binding_ids']]
            for index,item in enumerate(records):
                identifier=unit['unit_id']+':fine:'+str(index)
                world['slots'].append({**deepcopy(item),'id':identifier,'binding_id':identifier,
                    'scope_unit':'OPERATION','contract':out['contract'],
                    'actual_operation_ids':[unit['unit_id']],
                    'parent_written_binding_id':item['binding_id'],
                    'execution_unit_binding':deepcopy(unit),'requirement_source_scope':'OPERATION',
                    'fine_item_not_split_by_subobligations':True})
        if not world['slots'] and not any(gap.get('reason')=='EMPTY_ACTUAL_OPERATION_DOMAIN_NO_PARAMETER_ESTIMAND' for gap in world['gaps']):
            world['gaps'].append({'reason':'EMPTY_ACTUAL_OPERATION_DOMAIN_NO_PARAMETER_ESTIMAND'})
        complete=not world['gaps'] and out['domain']['status']=='FINITE_SOURCE_WORLDS'
        world.update(complete_applicability=complete,compiled_fine_item_count=len(world['slots']),
            denominator=len(world['slots']) if complete else None,
            denominator_status='COMPLETE_FINITE_WORLD' if complete else 'INCOMPLETE_MAPPING_NOT_SCORE_DENOMINATOR')
        worlds.append(world)
    out['worlds']=worlds
    out['domain']=deepcopy(out['domain'])
    out['domain']['parameter_private_reference_scope']={'version':units.VERSION,
        'proofs':deepcopy(proofs),'reference_variants_retained':True,'raw_source_not_modified':True}
    out['private_typed_rebind']={'version':VERSION,'source_scope_version':units.VERSION,
        'status':'COMPLETE','raw_source_and_original_ledger_unchanged':True,'new_model_calls':0}
    assert units.digest(binding)==before
    return out
