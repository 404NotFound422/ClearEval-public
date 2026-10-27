"""Retain complete reference operation variants without inventing an actual recipe."""
from copy import deepcopy
from itertools import product
from ..parameter_finite_requirement_domains_v1 import finite_families_v1 as families
from parameter_execution_unit_contract_20261025_v1 import actual_formulation_applicability_v1 as dilution

VERSION='complete-reference-operation-variants-without-imputed-recipe-v1'
digest=families.digest


def operation_family(mapping,parent,rid,protocol,actual_decision=None):
    references={row['operation_id']:row for row in parent['reference_typed_source_ledger']}
    reference=references.get(rid)
    if reference is None:
        return None,'REFERENCE_OPERATION_NOT_IN_SOURCE_LEDGER'
    basis='REFERENCE_REQUIRED_PROCEDURE_SPECIFICATION'
    disposition=None
    if actual_decision is not None:
        disposition=actual_decision.get('disposition')
        if (disposition not in {'REQUIRED_FOR_ACTUAL_DECLARED_DILUTION','NOT_AN_ACTUAL_OPERATION_OR_ACTUAL_RECIPE_REQUIREMENT'}
                or actual_decision.get('recipe_expression_proof',{}).get('actual_parent_id')!=mapping['operation_id']
                or set(actual_decision.get('complete_source_templates',[]))!=set(mapping['selected_template_operations'])):
            return None,'ACTUAL_FORMULATION_APPLICABILITY_BINDING_CHANGED'
        basis='ACTUAL_FORMULATION_APPLICABILITY_AUDIT'
    full=[item for item in parent['original_full_fine_item_ledger']
          if item['operation_id']==rid and families.material.old.physical.OLD._scope_unit(item)!='ROUTE']
    if not full:
        return None,'EMPTY_FULL_OPERATION_FAMILY'
    required,conditional,required_conditional=[],{},{}
    for item in full:
        if item['dimension'] in families.material.physical.prior.PROCESS and families.material.physical.prior._portable(item):
            required.append(deepcopy(item))
            continue
        requirements=item.get('source_requirements',[])
        is_conditional=(item['dimension']=='concentration' and item.get('subject')=='transition dilution'
            and requirements and all(r.get('scope_unit')=='OPERATION' and r.get('selector',{}).get('kind')=='NAME'
                and r.get('applicability')=='REQUIRED_PROCEDURE_SPECIFICATION'
                and any(dilution.re.search('dilut',value,dilution.re.I) for value in r['selector'].get('values',[]))
                for r in requirements))
        if not is_conditional:
            return None,'NONPORTABLE_OPERATION_REQUIREMENT_REQUIRES_SOURCE_SCOPE'
        if disposition=='NOT_AN_ACTUAL_OPERATION_OR_ACTUAL_RECIPE_REQUIREMENT':
            conditional[item['id']]=deepcopy(item)
        elif disposition=='REQUIRED_FOR_ACTUAL_DECLARED_DILUTION' or dilution.DILUTION.search(reference['source_row']['operation']):
            required.append(deepcopy(item))
            required_conditional[item['id']]=deepcopy(item)
        else:
            conditional[item['id']]=deepcopy(item)
    if not required:
        return None,'EMPTY_APPLICABLE_OPERATION_FAMILY'
    return {'reference_operation_id':rid,'items':required,'conditional_original_items':conditional,
            'required_conditional_items':required_conditional,'applicability_basis':basis,
            'reference_support':{'operation':reference['source_row']['operation'],
                'source':deepcopy(reference['source_row']['source'])},
            'full_original_item_ids':[item['id'] for item in full],
            'full_criteria_unchanged':True,'actual_recipe_not_imputed':True},None


def slots(unit,variant,mapping,parent):
    result=[]
    for index,item in enumerate(variant['items']):
        rid=variant['reference_operation_id']
        identifier=unit['unit_id']+':reference-operation:'+rid+':'+str(index)
        proof={'kind':'COMPLETE_REFERENCE_OPERATION_VARIANT','reference_operation_id':rid,
            'reference_operation_ids':deepcopy(mapping['selected_template_operations']),
            'actual_primary_identity':mapping['typed'].get('primary_identity'),
            'actual_action_role':mapping['typed'].get('action_role'),
            'actual_recipe_not_imputed':True,
            'conditional_original_item_ids':sorted(variant['conditional_original_items']),
            'required_conditional_original_item_ids':sorted(variant['required_conditional_items']),
            'reference_operation':variant['reference_support']['operation'],
            'reference_source':deepcopy(variant['reference_support']['source']),
            'parameter_values_used_to_select_applicability':False,
            'template_not_selected_by_score':True}
        result.append({'id':identifier,'binding_id':identifier,
            'criterion':item['criterion'],'dimension':item['dimension'],'subject':item.get('subject'),
            'scope_unit':'OPERATION','requirement_source_scope':'OPERATION',
            'actual_operation_ids':[unit['unit_id']],'actual_source':deepcopy(unit['source_binding']['source']),
            'execution_unit_binding':deepcopy(unit),'source_requirement_items':[deepcopy(item)],
            'original_slot_ids':[item['id']],'contract':parent['contract'],
            'fine_item_weight':1,'not_multiplied_by_execution_unit_count':False,
            'full_criterion_unchanged':True,'fine_item_not_split_by_subobligations':True,
            'required_even_if_parameter_absent':True,'parameter_presence_not_judged':True,
            'applicability_proof':proof})
    return result


def continuation(text):
    return bool(dilution.re.search(r'\b(?:next\s+day|replace|fresh)\b|更换',text,dilution.re.I))


def continuation_conflict(mapping,reference):
    actual=mapping['source_row']['operation']
    expected=reference['source_row']['operation']
    if continuation(expected) and not continuation(actual):
        return {'reason':'REFERENCE_CONTINUATION_REQUIRES_ACTUAL_REPLACEMENT',
            'actual_operation':actual,'reference_operation':expected,
            'actual_source':deepcopy(mapping['source_row']['source']),
            'reference_source':deepcopy(reference['source_row']['source'])}
    return None


def apply(binding,protocol,original_manifest,max_template_worlds=4096):
    before=digest(binding)
    if binding.get('private_typed_rebind',{}).get('status')=='INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE':
        return binding
    parent=binding['parent_action_requirement_binding']
    deferred=[mapping['operation_id'] for mapping in parent['operation_mappings']
        if mapping['gaps']==['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']]
    if not deferred:
        return binding
    references={row['operation_id']:row for row in parent['reference_typed_source_ledger']}
    scope=binding.get('domain',{}).get('parameter_private_reference_scope')
    proofs=None if scope is None else scope.get('proofs',{})
    mappings={mapping['operation_id']:mapping for mapping in parent['operation_mappings']}
    def assigned(world):
        receipt=world.get('reference_operation_variant_assignment')
        if not isinstance(receipt,dict):
            return False
        for oid in deferred:
            assignment=receipt.get(oid,{})
            reference=references.get(assignment.get('reference_operation_id'))
            if (reference is None or not assignment.get('reference_operation')
                    or not assignment.get('reference_source')
                    or 'required_conditional_original_item_ids' not in assignment
                    or assignment['reference_operation']!=reference['source_row']['operation']
                    or assignment['reference_source']!=reference['source_row']['source']
                    or continuation_conflict(mappings[oid],reference)):
                return False
            decision=binding.get('actual_formulation_applicability_audit',{}).get('proved_parents',{}).get(oid)
            variant,error=operation_family(mappings[oid],parent,reference['operation_id'],protocol,decision)
            if error:
                return False
            expected={'reference_operation_id':variant['reference_operation_id'],
                'conditional_original_item_ids':sorted(variant['conditional_original_items']),
                'required_conditional_original_item_ids':sorted(variant['required_conditional_items']),
                'original_item_ids':[item['id'] for item in variant['items']],
                'applicability_basis':variant['applicability_basis'],
                'actual_parent_id':oid,'actual_operation':mappings[oid]['source_row']['operation'],
                'actual_recipe_not_imputed':True}
            if any(assignment.get(key)!=value for key,value in expected.items()):
                return False
        return proofs is None or all(oid in proofs for oid in deferred)
    cached_complete=all(assigned(world) for world in binding['worlds'])
    candidates={};rejections=[]
    for mapping in parent['operation_mappings']:
        oid=mapping['operation_id']
        if mapping['gaps']!=['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']:
            continue
        if proofs is not None and oid not in proofs:
            rejections.append({'parent':oid,'reason':'PRIVATE_REFERENCE_SCOPE_PROOF_MISSING'})
            continue
        if not mapping.get('selected_template_operations') or not (mapping['typed'].get('phase_fact') or {}).get('complete'):
            rejections.append({'parent':oid,'reason':'INCOMPLETE_SOURCE_ACTION_OR_PHASE_BINDING'})
            continue
        variants=[]
        actual_decision=binding.get('actual_formulation_applicability_audit',{}).get('proved_parents',{}).get(oid)
        for rid in mapping['selected_template_operations']:
            reference=references.get(rid)
            if reference is None:
                rejections.append({'parent':oid,'reference_operation_id':rid,
                    'reason':'REFERENCE_OPERATION_NOT_IN_SOURCE_LEDGER'})
                variants=[]
                break
            conflict=continuation_conflict(mapping,reference)
            if conflict:
                rejections.append({'parent':oid,'reference_operation_id':rid,**conflict})
                continue
            variant,error=operation_family(mapping,parent,rid,protocol,actual_decision)
            if error:
                rejections.append({'parent':oid,'reference_operation_id':rid,'reason':error})
                variants=[]
                break
            variants.append(variant)
        if variants:
            candidates[oid]=variants
    def incomplete(status,**details):
        out=deepcopy(binding)
        for world in out['worlds']:
            world.update(complete_applicability=False,denominator=None,
                denominator_status='INCOMPLETE_REFERENCE_OPERATION_VARIANTS')
        out['reference_operation_variant_audit']={'version':VERSION,'status':status,
            'deferred_operations':deferred,'rejections':rejections,'no_world_chosen':True,**details}
        assert digest(binding)==before
        return out
    if not candidates or set(candidates)!=set(deferred):
        return incomplete('INCOMPLETE_REFERENCE_OPERATION_VARIANTS',candidates=candidates)
    groups={}
    for world in binding['worlds']:
        key=digest([world.get('execution_assignments'),world['units']])
        groups.setdefault(key,[]).append(world)
    base_worlds=[]
    for group in groups.values():
        assignments=[]
        for world in group:
            receipt=world.get('reference_operation_variant_assignment') or {}
            if receipt and (set(receipt)!=set(deferred)
                    or any(not receipt.get(oid,{}).get('reference_operation_id') for oid in deferred)):
                return incomplete('INCOMPLETE_CACHED_REFERENCE_OPERATION_VARIANT_DOMAIN')
            assignments.append(tuple((oid,receipt.get(oid,{}).get('reference_operation_id')) for oid in deferred))
        if len(set(assignments))!=len(assignments):
            return incomplete('DUPLICATE_CACHED_REFERENCE_OPERATION_VARIANTS')
        choice_domains={oid:sorted({assignment[index][1] for assignment in assignments})
            for index,oid in enumerate(deferred)}
        expected={tuple(zip(deferred,values)) for values in product(*(choice_domains[oid] for oid in deferred))}
        if set(assignments)!=expected:
            return incomplete('INCOMPLETE_CACHED_REFERENCE_OPERATION_VARIANT_DOMAIN')
        base_worlds.append(group[0])
    if cached_complete:
        return binding
    required_world_count=len(base_worlds)
    for variants in candidates.values():
        required_world_count*=len(variants)
    if required_world_count>max_template_worlds:
        return incomplete('RESOURCE_LIMIT',required_world_count=required_world_count)
    keys=list(candidates)
    worlds=[];audits=[]
    for choices in product(*(candidates[key] for key in keys)):
        assignment=dict(zip(keys,choices))
        for original in base_worlds:
            world=deepcopy(original)
            parent_units={unit['parent_operation_id']:unit['unit_id'] for unit in world['units']}
            replaced_units={unit_id for oid,unit_id in parent_units.items() if oid in candidates}
            world['slots']=[slot for slot in world['slots']
                if not (slot.get('scope_unit')=='OPERATION' and slot.get('execution_unit_binding',{}).get('unit_id') in replaced_units)]
            for unit in world['units']:
                oid=unit['parent_operation_id']
                if oid in candidates:
                    world['slots']+=slots(unit,assignment[oid],mappings[oid],parent)
            for slot in world['slots']:
                if slot.get('scope_unit')=='OPERATION':
                    slot['fine_item_weight']=1
                    slot['not_multiplied_by_execution_unit_count']=False
            gaps=[gap for gap in world['gaps'] if gap.get('parent_operation_id') not in candidates]
            complete=not gaps and binding['domain']['status']=='FINITE_SOURCE_WORLDS'
            receipt={oid:{'reference_operation_id':variant['reference_operation_id'],
                'conditional_original_item_ids':sorted(variant['conditional_original_items']),
                'required_conditional_original_item_ids':sorted(variant['required_conditional_items']),
                'original_item_ids':[item['id'] for item in variant['items']],
                'reference_operation':variant['reference_support']['operation'],
                'reference_source':deepcopy(variant['reference_support']['source']),
                'applicability_basis':variant['applicability_basis'],
                'actual_parent_id':oid,'actual_operation':mappings[oid]['source_row']['operation'],
                'actual_recipe_not_imputed':True} for oid,variant in assignment.items()}
            world.update(world_id='reference-operation-variant-world:'+digest([original['world_id'],receipt])[:24],
                source_world_id=original['world_id'],reference_operation_variant_assignment=receipt,
                gaps=gaps,complete_applicability=complete,compiled_fine_item_count=len(world['slots']),
                denominator=len(world['slots']) if complete else None,
                denominator_status='COMPLETE_REFERENCE_OPERATION_VARIANTS' if complete else 'OTHER_SOURCE_SCOPES_RETAINED')
            worlds.append(world)
            origins=[origin for slot in world['slots'] for origin in slot['original_slot_ids']]
            multipliers={origin:origins.count(origin) for origin in sorted(set(origins))}
            audits.append({'world_id':world['world_id'],'assignment':receipt,
                'distinct_original_slot_ids':sorted(set(origins)),'slot_multipliers':multipliers,
                'full_source_items_retained_in_ledger':True,'conditional_items_not_silently_deleted':True})
    out=deepcopy(binding)
    out.update(version=VERSION,worlds=worlds,reference_operation_variant_audit={'version':VERSION,
        'status':'COMPLETE' if all(world['complete_applicability'] for world in worlds) else 'PARTIAL_OTHER_SOURCE_SCOPES_RETAINED',
        'candidates':candidates,'rejections':rejections,'world_audits':audits,
        'full_source_ledger_unchanged':True,'all_admissible_template_variants_required':True,
        'rejected_reference_variants_retained_in_audit':True,
        'denominator_policy':'ORIGINAL_REQUIREMENT_PER_ACTUAL_EXECUTION_UNIT_WITH_SHARED_ROUTE_ONCE_PER_SOURCE_SCOPE',
        'no_actual_recipe_or_parameter_value_imputed':True,'new_model_calls':0})
    assert digest(binding)==before
    return out
