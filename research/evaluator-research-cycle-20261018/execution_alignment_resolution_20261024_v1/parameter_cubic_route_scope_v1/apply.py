"""Compile CUBIC route obligations without changing their original criteria."""
from copy import deepcopy
from parameter_execution_unit_contract_20261025_v1.shared_scopes import compile_shared_items
from parameter_execution_unit_contract_20261025_v1.source_units import digest
from ..parameter_route_role_scope_v1 import recipe_scope

VERSION='cubic-original-route-obligations-with-unchanged-criteria-v1'


def declared(binding):
    contract=binding.get('parent_action_requirement_binding',{}).get('source_scope_contract',{})
    return contract.get('reference_source_id','').startswith('cubic-source-scoring-interface-')


def apply(binding,protocol,original_manifest,max_template_worlds=4096):
    if not declared(binding):
        return binding
    before=digest(binding)
    parent=binding['parent_action_requirement_binding']
    shared_items=parent['shared_material_route_bindings']
    def incomplete(status,**details):
        out=deepcopy(binding)
        for world in out['worlds']:
            world.update(complete_applicability=False,denominator=None,
                denominator_status='INCOMPLETE_CUBIC_ORIGINAL_ROUTE_SCOPE')
        out['cubic_route_audit']={'version':VERSION,'status':status,
            'original_full_fine_item_ledger_unchanged':True,'no_world_chosen':True,**details}
        assert digest(binding)==before
        return out
    scope=binding.get('domain',{}).get('parameter_private_reference_scope',{})
    proofs=scope.get('proofs',{})
    if not isinstance(proofs,dict):
        proofs={}
    proof_parents={mapping['operation_id'] for mapping in parent['operation_mappings']
        if mapping['gaps']==['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']}
    proof_parents.update(assignment['actual_parent_id'] for world in binding['worlds']
        for assignment in world.get('reference_operation_variant_assignment',{}).values())
    missing=sorted(proof_parents-set(proofs))
    if ((proof_parents and binding.get('private_typed_rebind',{}).get('status')!='COMPLETE')
            or missing):
        return incomplete('INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE',
            required_proof_operation_ids=sorted(proof_parents),missing_proof_operations=missing)
    if binding.get('private_typed_rebind',{}).get('status')=='INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE':
        return incomplete('INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE')
    if binding.get('reference_operation_variant_audit',{}).get('status') in {
            'RESOURCE_LIMIT','INCOMPLETE_REFERENCE_OPERATION_VARIANTS'}:
        return binding
    required={shared['original_slot']['id'] for shared in shared_items}
    if all(required and required<=set(world.get('cubic_original_route_assignment',{})) for world in binding['worlds']):
        return binding
    mappings={mapping['operation_id']:mapping for mapping in parent['operation_mappings']}
    if len(binding['worlds'])>max_template_worlds:
        return incomplete('RESOURCE_LIMIT',required_world_count=len(binding['worlds']))
    pending={item['original_slot']['id'] for world in binding['worlds']
        for gap in world['gaps'] if gap['reason']=='SHARED_MATERIAL_ROUTE_FULL_SCOPE_BINDING_NOT_YET_COMPILED'
        for item in gap['original_items']}
    if not shared_items:
        return binding
    candidates={};rejections=[]
    for shared in shared_items:
        original=shared['original_slot'];origin=original['id']
        proof,error=recipe_scope.bind(shared,parent,protocol)
        if error:
            rejections.append({'original_slot_id':origin,'reason':error})
            continue
        proof=deepcopy(proof)
        parents=sorted(set(proof.get('actual_parent_ids',[])))
        references=set(proof.get('reference_operation_ids',[]))
        for oid in parents:
            mapping=mappings.get(oid)
            if (mapping is None or not recipe_scope.bound(mapping,protocol)
                    or (mapping['typed'].get('phase_fact') or {}).get('complete') is not True):
                error='CUBIC_ACTUAL_ROUTE_PARENT_PROOF_INCOMPLETE'
                break
            references.update(mapping.get('selected_template_operations',[]))
        else:
            if not parents or not references:
                error='CUBIC_ROUTE_PARENT_OR_REFERENCE_DOMAIN_EMPTY'
            else:
                proof['reference_operation_ids']=sorted(references)
                candidates[origin]={'original_slot':deepcopy(original),'proof':proof,
                    'actual_parent_ids':parents,'reference_operation_ids':sorted(references)}
                continue
        rejections.append({'original_slot_id':origin,'reason':error})
    if set(candidates)!=required:
        return incomplete('INCOMPLETE_CUBIC_ORIGINAL_ROUTE_SCOPES',
            pending_original_slot_ids=sorted(pending),required_original_slot_ids=sorted(required),
            candidates=candidates,rejections=rejections)
    worlds=[];audits=[]
    for original_world in binding['worlds']:
        world=deepcopy(original_world)
        active={unit['parent_operation_id'] for unit in world['units']}
        world['slots']=[slot for slot in world['slots']
            if slot.get('scope_unit') not in {'MATERIAL','ROUTE'}
            or not set(slot.get('original_slot_ids',[]))&set(candidates)]
        items=[];assignment={};errors=[]
        for origin,candidate in candidates.items():
            parents=candidate['actual_parent_ids']
            if not set(parents)<=active:
                errors.append({'original_slot_id':origin,
                    'reason':'CUBIC_ROUTE_PARENTS_NOT_ALL_PRESENT_IN_THIS_WORLD'})
                continue
            spans=[{'start':mappings[oid]['source_row']['source']['start'],
                'end':mappings[oid]['source_row']['source']['end'],
                'quote':mappings[oid]['source_row']['raw_text']} for oid in parents]
            original=candidate['original_slot']
            item={key:deepcopy(original.get(key)) for key in ('criterion','dimension','subject')}
            item.update(original_slot_ids=[origin],scope_unit='ROUTE',
                actual_operation_ids=parents,scope_binding_proof={
                    'source_scope_id':'cubic-original-route:'+digest([origin,parents,candidate['reference_operation_ids']]),
                    'source_refs':spans,'source_role_or_name_proof':candidate['proof'],
                    'parameter_values_used_to_select_applicability':False,
                    'original_requirement_scope_unit':'ROUTE',
                    'one_item_per_original_route_requirement':True})
            items.append(item)
            assignment[origin]={'actual_parent_ids':parents,
                'reference_operation_ids':candidate['reference_operation_ids'],
                'original_slot_id':origin,'original_criterion_sha256':digest(original['criterion'])}
        try:
            compiled=compile_shared_items(items,world['units'],protocol,original_manifest)
        except (KeyError,ValueError) as error:
            errors.append({'reason':'CUBIC_ORIGINAL_ROUTE_COMPILATION_REJECTED','detail':str(error)})
        else:
            if compiled['gaps']:
                errors.extend(compiled['gaps'])
            elif {origin for slot in compiled['slots'] for origin in slot['original_slot_ids']}!=set(candidates):
                errors.append({'reason':'CUBIC_ORIGINAL_ROUTE_LEDGER_NOT_COVERED'})
            else:
                world['slots']+=compiled['slots']
        gaps=[]
        for gap in world['gaps']:
            if gap['reason']=='SHARED_MATERIAL_ROUTE_FULL_SCOPE_BINDING_NOT_YET_COMPILED':
                rest=[item for item in gap['original_items']
                    if item['original_slot']['id'] not in candidates]
                if rest:
                    gaps.append({**gap,'original_items':rest})
            else:
                gaps.append(gap)
        gaps.extend({'reason':'CUBIC_ORIGINAL_ROUTE_SCOPE_REJECTED','detail':error} for error in errors)
        for slot in world['slots']:
            if slot.get('scope_unit')=='OPERATION':
                slot['fine_item_weight']=1
                slot['not_multiplied_by_execution_unit_count']=False
        complete=not gaps and binding['domain']['status']=='FINITE_SOURCE_WORLDS'
        if not errors:
            world['cubic_original_route_assignment']=assignment
        world.update(world_id='cubic-original-route-world:'+digest([original_world['world_id'],assignment,errors])[:24],
            source_world_id=original_world['world_id'],gaps=gaps,complete_applicability=complete,
            compiled_fine_item_count=len(world['slots']),denominator=len(world['slots']) if complete else None,
            denominator_status='COMPLETE_CUBIC_ORIGINAL_ROUTE_SCOPE' if complete else 'INCOMPLETE_CUBIC_ORIGINAL_ROUTE_SCOPE')
        worlds.append(world)
        origins=[origin for slot in world['slots'] for origin in slot['original_slot_ids']]
        audits.append({'world_id':world['world_id'],'assignment':assignment,'errors':errors,
            'distinct_original_slot_ids':sorted(set(origins)),
            'slot_multipliers':{origin:origins.count(origin) for origin in sorted(set(origins))},
            'original_criteria_preserved':not errors})
    covered={origin for world in worlds for slot in world['slots'] for origin in slot['original_slot_ids']}
    conditional={origin for world in worlds for assignment in world.get('reference_operation_variant_assignment',{}).values()
        for origin in assignment['conditional_original_item_ids']}
    missing={item['id'] for ledger in (binding,parent) for item in ledger['original_full_fine_item_ledger']}-covered-conditional
    if missing:
        return incomplete('INCOMPLETE_CUBIC_ORIGINAL_LEDGER_COVERAGE',
            missing_original_slot_ids=sorted(missing),covered_original_slot_ids=sorted(covered),
            conditional_original_slot_ids=sorted(conditional),world_audits=audits)
    complete_worlds=all(world['complete_applicability'] for world in worlds)
    final_status='COMPLETE' if complete_worlds else (
        'INCOMPLETE_CUBIC_ORIGINAL_ROUTE_SCOPES' if any(audit['errors'] for audit in audits)
        else 'PARTIAL_OTHER_SOURCE_SCOPES_RETAINED')
    out=deepcopy(binding)
    if out.get('reference_operation_variant_audit'):
        variant_audit=deepcopy(out['reference_operation_variant_audit'])
        variant_audit.update(pre_cubic_route_status=variant_audit['status'],status=final_status,
            finalized_by=VERSION)
        out['reference_operation_variant_audit']=variant_audit
    out.update(version=VERSION,worlds=worlds,cubic_route_audit={'version':VERSION,
        'status':final_status,'candidates':candidates,'rejections':rejections,'world_audits':audits,
        'original_full_fine_item_ledger_unchanged':True,'original_ledger_union_verified':True,
        'original_criteria_not_rewritten':True,
        'denominator_policy':'ORIGINAL_REQUIREMENT_PER_ACTUAL_EXECUTION_UNIT_WITH_SHARED_ROUTE_ONCE_PER_SOURCE_SCOPE',
        'parameter_presence_not_judged':True,'scientific_equivalence_claimed':False,'new_model_calls':0})
    assert digest(binding)==before
    return out
