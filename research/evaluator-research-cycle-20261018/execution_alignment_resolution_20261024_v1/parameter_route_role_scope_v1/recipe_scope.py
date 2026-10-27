"""Bind route obligations from the same exact source passage without requiring presence."""
from copy import deepcopy
import re
from .route_scope_v1 import original_requirement, primary_proof, bound

VERSION='source-passage-carrier-and-formulation-component-scope-v1'


def _normalized(text):
    return re.sub(r'[\W_]+', '_', str(text).casefold()).strip('_')


def _full_requirements(shared, dimensions):
    item = shared['original_slot']
    if item['dimension'] not in dimensions:
        return None, 'UNSUPPORTED_SOURCE_PASSAGE_RECIPE_DIMENSION'
    requirements = item.get('source_requirements', [])
    if not requirements:
        return None, 'ORIGINAL_ROUTE_REQUIREMENT_SOURCE_MISSING'
    if any(r.get('scope_unit') != 'ROUTE' or r.get('condition_quote') or
           r.get('applicability') != 'REQUIRED_PROCEDURE_SPECIFICATION' for r in requirements):
        return None, 'ROUTE_REQUIREMENT_HAS_UNRESOLVED_CONDITION_OR_UNIT'
    if any(r.get('criterion') != item['criterion'] or r.get('dimension') != item['dimension'] or
           r.get('subject') != item.get('subject') for r in requirements):
        return None, 'ORIGINAL_FULL_REQUIREMENT_FIELDS_DISAGREE'
    return requirements, None


def _passage(requirements):
    return sorted({(r.get('source_card_id'), r.get('passage_id'), r.get('quote')) for r in requirements})


def _carrier_scope(shared, parent, protocol):
    requirements, error = original_requirement(shared)
    if error:
        return None, error
    if any(r.get('selector', {}).get('kind') != 'NAME' for r in requirements):
        return None, 'CARRIER_ROUTE_SELECTOR_NOT_COMPLETE'
    names = {_normalized(value) for r in requirements for value in r['selector'].get('values', [])}
    if not names:
        return None, 'CARRIER_ROUTE_SELECTOR_NOT_COMPLETE'
    parents, proofs = [], {}
    for mapping in parent['operation_mappings']:
        proof = primary_proof(mapping, protocol)
        if not proof:
            continue
        actual = {_normalized(m.get(key, '')) for m in proof.get('primary_mentions', [])
                  for key in ('name', 'quote')}
        if not names & actual:
            continue
        if not bound(mapping, protocol):
            return None, 'ACTUAL_CARRIER_PARENT_SOURCE_UNBOUND'
        parents.append(mapping['operation_id'])
        proofs[mapping['operation_id']] = deepcopy(proof)
    if not parents:
        return None, 'NO_SOURCE_PROVED_CARRIER_RECIPIENT'
    return {'kind': 'EXACT_ALIAS_AND_SOURCE_PASSAGE_CARRIER_SCOPE',
            'actual_parent_ids': sorted(parents), 'source_primary_proofs': proofs,
            'source_passage': _passage(requirements),
            'parameter_values_used_to_select_applicability': False,
            'nominal_recipe_identity_not_pure_formulation_assertion': True}, None


def _declared_material_scope(shared, parent, protocol):
    requirements, error = _full_requirements(shared, {'formulation_component'})
    if error:
        return None, error
    origin = shared['original_slot']['id']
    entries = [entry for entry in parent['actual_material_mapping']['materials']
               if origin in {item['id'] for item in entry['source_requirement_items']}]
    if not entries:
        return None, 'NO_DECLARED_MATERIAL_ALIAS_SCOPE'
    if len(entries) != 1:
        return None, 'MULTIPLE_DECLARED_MATERIAL_SCOPES_REQUIRE_JOINT_VARIANTS'
    entry = entries[0]
    proof = entry.get('source_primary_name_proof', {})
    witnesses = proof.get('proofs', [])
    if (proof.get('rule') != 'EXACT_SOURCE_DECLARED_NAME_WITH_ORTHOGRAPHIC_NORMALIZATION'
            or proof.get('recipe_parameters_used') is not False
            or proof.get('functional_substitution_claimed') is not False or not witnesses):
        return None, 'DECLARED_MATERIAL_ALIAS_PROOF_INVALID'
    mappings = {mapping['operation_id']: mapping for mapping in parent['operation_mappings']}
    parents = entry.get('actual_operation_ids', [])
    if not parents:
        return None, 'DECLARED_MATERIAL_ALIAS_PROOF_INVALID'
    for oid in parents:
        if oid not in mappings or not bound(mappings[oid], protocol):
            return None, 'DECLARED_MATERIAL_ALIAS_PROOF_INVALID'
        if mappings[oid]['typed'].get('primary_identity') != proof.get('identity'):
            return None, 'DECLARED_MATERIAL_ALIAS_PROOF_INVALID'
    aliases = {_normalized(value) for requirement in requirements
               for value in requirement.get('selector', {}).get('values', [])}
    matched = False
    for witness in witnesses:
        donor = witness.get('source_donor', {})
        span = witness.get('operation_span', {})
        a, b = span.get('start'), span.get('end')
        if (_normalized(donor.get('alias', '')) not in aliases
                or donor.get('identity') != proof.get('identity')
                or donor.get('requirement_alias_not_claimed_as_chemical_equivalence') is not True):
            continue
        if not any(type(a) is int and type(b) is int and 0 <= a < b <= len(mappings[oid]['source_row']['operation'])
                   and mappings[oid]['source_row']['operation'][a:b] == span.get('quote')
                   and _normalized(span['quote']) == _normalized(donor['alias'])
                   for oid in parents):
            return None, 'DECLARED_MATERIAL_ALIAS_PROOF_INVALID'
        matched = True
    if not matched:
        return None, 'DECLARED_MATERIAL_ALIAS_PROOF_INVALID'
    spans = entry['approved_material_compiler_input'].get('definition_spans', [])
    if not spans or any(protocol[s['start']:s['end']] != s['quote'] for s in spans):
        return None, 'DECLARED_MATERIAL_ALIAS_PROOF_INVALID'
    return {'kind': 'EXACT_SOURCE_DECLARED_MATERIAL_SCOPE', 'actual_parent_ids': parents,
            'source_primary_name_proof': deepcopy(proof), 'definition_spans': deepcopy(spans),
            'source_passage': _passage(requirements),
            'parameter_values_used_to_select_applicability': False,
            'component_presence_not_inferred_from_route_binding': True,
            'missing_component_can_be_scored': True}, None


def _reference_action_scope(shared, parent, protocol):
    from parameter_action_requirement_binding_20261025_v1 import binder
    from ..parameter_joint_applicability_v1 import incremental_material_v1 as reference
    dimension = shared['original_slot']['dimension']
    requirements, error = _full_requirements(shared, {'formulation_component', 'carrier', 'formulation_carrier'})
    if error:
        return None, error
    origin = shared['original_slot']['id']
    references = {row['operation_id']: row for row in parent['reference_typed_source_ledger']}
    parents, proofs = [], []
    for mapping in parent['operation_mappings']:
        if mapping['gaps'] not in ([], ['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']):
            continue
        if not bound(mapping, protocol):
            continue
        typed = mapping['typed']
        phase = typed.get('phase_fact') or {}
        if phase.get('complete') is not True or len(phase.get('scenarios', [])) != 1:
            continue
        for rid in mapping.get('selected_template_operations', []):
            ref = references[rid]
            if (typed.get('action_role') != ref['typed'].get('action_role')
                    or not binder._identity_domain(typed.get('primary_identity')) <= binder._identity_domain(ref['typed'].get('primary_identity'))
                    or phase['scenarios'] != [[ref['source_row']['phase']]]):
                continue
            groups, error = reference.reference_materials(parent, rid)
            if error:
                if error == 'NO_BOUND_REFERENCE_MATERIAL_REQUIREMENT_OWNER':
                    continue
                return None, error
            for group in groups:
                originals = group['items']
                if origin not in {item['id'] for item in originals}:
                    continue
                original = next(item for item in originals if item['id'] == origin)
                if any(original.get(key) != shared['original_slot'].get(key) for key in ('criterion', 'dimension', 'subject')):
                    return None, 'REFERENCE_RECIPE_ORIGINAL_CRITERION_CHANGED'
                parents.append(mapping['operation_id'])
                proofs.append({'reference_operation_id': rid, 'requirement_scope': deepcopy(group),
                               'actual_primary_identity': typed.get('primary_identity'),
                               'reference_primary_identity': ref['typed'].get('primary_identity'),
                               'complete_phase_fact': deepcopy(phase)})
    if not parents:
        return None, 'NO_COMPLETE_REFERENCE_RECIPE_REQUIREMENT_OWNER'
    return {'kind': 'COMPLETE_REFERENCE_RECIPE_REQUIREMENT_OWNER_AND_IDENTITY_SCOPE',
            'actual_parent_ids': sorted(set(parents)),
            'reference_operation_ids': sorted({proof['reference_operation_id'] for proof in proofs}),
            'reference_recipient_proofs': proofs, 'source_passage': _passage(requirements),
            'parameter_values_used_to_select_applicability': False,
            'scientific_equivalence_or_recipe_identity_claimed': False,
            'component_presence_not_inferred_from_route_binding': True,
            'missing_component_can_be_scored': True}, None


def _alternative_recipe_scope(shared, parent, protocol):
    from ..parameter_private_reference_scope_v1 import units
    from ..parameter_joint_applicability_v1 import incremental_material_v1 as reference
    dimension = shared['original_slot']['dimension']
    requirements, error = _full_requirements(shared, {'formulation_component', 'carrier', 'formulation_carrier'})
    if error:
        return None, error
    criterion = shared['original_slot']['criterion']
    if 'An explicit differing value is present' not in criterion and 'prepared-stock identity' not in criterion:
        return None, 'ALTERNATIVE_RECIPE_NOT_EXPLICITLY_ADMITTED'
    if not parent['source_scope_contract']['reference_source_id'].startswith('cubic-source-scoring-interface-'):
        return None, 'ALTERNATIVE_SOURCE_FAMILY_NOT_DECLARED'
    origin = shared['original_slot']['id']
    reference_rows = [row['source_row'] for row in parent['reference_typed_source_ledger']]
    typed_references = {row['operation_id']: row for row in parent['reference_typed_source_ledger']}
    allowed_phases = set(parent['source_scope_contract']['reference_phases'])
    allowed_gaps = {'ACTUAL_OPERATION_SCOPE_MEMBERSHIP_UNRESOLVED',
                    'NO_SOURCE_BOUND_ACTION_MEDIUM_TEMPLATE',
                    'MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES'}
    parents, proofs = [], []
    for mapping in parent['operation_mappings']:
        if not bound(mapping, protocol) or any(gap not in allowed_gaps for gap in mapping['gaps']):
            continue
        evidence = units.proof(mapping['source_row'], reference_rows, protocol, allowed_phases)
        if evidence is None or evidence.get('different_named_medium_not_equated') is not True:
            continue
        if mapping['typed'].get('primary_identity') not in (None, evidence['actual_primary_identity']):
            continue
        for rid in evidence['reference_operation_ids']:
            ref = typed_references[rid]
            if ref['source_row']['phase'] != evidence['reference_phase'] or ref['typed'].get('action_role') != evidence['actual_action_role']:
                continue
            groups, error = reference.reference_materials(parent, rid)
            if error:
                if error == 'NO_BOUND_REFERENCE_MATERIAL_REQUIREMENT_OWNER':
                    continue
                return None, error
            for group in groups:
                originals = group['items']
                if origin not in {item['id'] for item in originals}:
                    continue
                original = next(item for item in originals if item['id'] == origin)
                if any(original.get(key) != shared['original_slot'].get(key) for key in ('criterion', 'dimension', 'subject')):
                    return None, 'ALTERNATIVE_RECIPE_ORIGINAL_CRITERION_CHANGED'
                parents.append(mapping['operation_id'])
                proofs.append({'reference_operation_id': rid, 'requirement_scope': deepcopy(group),
                               'private_reference_scope': deepcopy(evidence),
                               'actual_primary_identity': mapping['typed'].get('primary_identity')})
    if not parents:
        return None, 'NO_ADMITTED_ALTERNATIVE_REFERENCE_RECIPE_SCOPE'
    return {'kind': 'DECLARED_ALTERNATIVE_RECIPE_SOURCE_FAMILY_SCOPE',
            'actual_parent_ids': sorted(set(parents)),
            'reference_operation_ids': sorted({proof['reference_operation_id'] for proof in proofs}),
            'reference_recipient_proofs': proofs,
            'different_named_medium_not_equated': True,
            'source_passage': _passage(requirements),
            'parameter_values_used_to_select_applicability': False,
            'scientific_equivalence_or_recipe_identity_claimed': False,
            'component_presence_not_inferred_from_route_binding': True,
            'missing_component_can_be_scored': True}, None


def bind(shared, parent, protocol):
    dimension = shared['original_slot']['dimension']
    if dimension == 'carrier':
        candidate, error = _carrier_scope(shared, parent, protocol)
        if error is None:
            return candidate, None
        candidate, error = _reference_action_scope(shared, parent, protocol)
        if error is None:
            return candidate, None
        return _alternative_recipe_scope(shared, parent, protocol)
    if dimension != 'formulation_component':
        return None, 'UNSUPPORTED_SOURCE_PASSAGE_RECIPE_DIMENSION'
    requirements, error = _full_requirements(shared, {'formulation_component'})
    if error:
        return None, error
    signature = _passage(requirements)
    for other in parent['shared_material_route_bindings']:
        if other['original_slot']['dimension'] != 'carrier':
            continue
        other_requirements, other_error = original_requirement(other)
        if other_error or _passage(other_requirements) != signature:
            continue
        candidate, candidate_error = _carrier_scope(other, parent, protocol)
        if candidate_error:
            continue
        return {'kind': 'SAME_SOURCE_PASSAGE_FORMULATION_COMPONENT_SCOPE',
                'actual_parent_ids': candidate['actual_parent_ids'],
                'source_primary_proofs': candidate['source_primary_proofs'],
                'source_passage': signature,
                'parameter_values_used_to_select_applicability': False,
                'component_presence_not_inferred_from_route_binding': True,
                'missing_component_can_be_scored': True}, None
    candidate, error = _declared_material_scope(shared, parent, protocol)
    if error == 'NO_DECLARED_MATERIAL_ALIAS_SCOPE':
        candidate, error = _reference_action_scope(shared, parent, protocol)
        if error is None:
            return candidate, None
        return _alternative_recipe_scope(shared, parent, protocol)
    return candidate, error


def compile_definition_proofs(world, parent, protocol, original_manifest):
    from parameter_execution_unit_contract_20261025_v1.shared_scopes import compile_bound_materials
    from ..parameter_actual_carrier_role_v1 import carrier_scope
    from .route_scope_v1 import digest
    out = deepcopy(world)
    for slot in out['slots']:
        if slot.get('dimension') != 'preparation' or not slot.get('parent_material_binding'):
            continue
        entry = slot['parent_material_binding']
        origins = slot.get('original_slot_ids', [])
        if not origins:
            continue
        projected = deepcopy(parent)
        projected['actual_material_mapping']['materials'] = [deepcopy(entry)]
        compiled = compile_bound_materials(projected, world['units'], protocol,
            original_manifest, carrier_scope.compiler)
        if compiled['gaps']:
            raise ValueError('COMPOSITE_DEFINITION_REPLAY_REJECTED')
        replacements = [item for item in compiled['slots'] if item['id'] == slot['id']]
        if len(replacements) != 1:
            raise ValueError('COMPOSITE_DEFINITION_SLOT_NOT_UNIQUE')
        replacement = replacements[0]
        expected = deepcopy(slot)
        expected.pop('whole_criterion_origin_proof', None)
        if replacement != expected:
            raise ValueError('COMPOSITE_DEFINITION_REPLAY_CHANGED_SLOT')
        originals = [next(item for item in original_manifest['slots'] if item['id'] == origin) for origin in origins]
        slot['whole_criterion_origin_proof'] = {
            'kind': 'APPROVED_COMPLETE_ACTUAL_FORMULATION_DEFINITION_REBIND',
            'original_slot_ids': deepcopy(origins),
            'original_criteria_sha256': digest(originals),
            'compiled_material_entry_sha256': digest(entry),
            'compiled_slot_sha256': digest(replacement)}
    return out


def support_namespace(original):
    from ..scope.stage_context_candidate_v1.consumers import clone
    from .route_scope_v1 import digest
    native = original._source_origin

    def source_origin(slot, ledger):
        proof = slot.get('whole_criterion_origin_proof')
        if proof is None:
            return native(slot, ledger)
        origins = slot.get('original_slot_ids', [])
        if (proof.get('kind') != 'APPROVED_COMPLETE_ACTUAL_FORMULATION_DEFINITION_REBIND'
                or not origins or proof.get('original_slot_ids') != origins
                or not set(origins) <= set(ledger)):
            raise ValueError('INVALID_COMPOSITE_DEFINITION_ORIGIN_PROOF')
        originals = [ledger[origin] for origin in origins]
        if proof.get('original_criteria_sha256') != digest(originals):
            raise ValueError('COMPOSITE_DEFINITION_ORIGINAL_CRITERIA_CHANGED')
        if proof.get('compiled_material_entry_sha256') != digest(slot.get('parent_material_binding')):
            raise ValueError('COMPOSITE_DEFINITION_MATERIAL_BINDING_CHANGED')
        current = deepcopy(slot)
        current.pop('whole_criterion_origin_proof')
        if proof.get('compiled_slot_sha256') != digest(current):
            raise ValueError('COMPOSITE_DEFINITION_SLOT_CHANGED_AFTER_REPLAY')
        return deepcopy(proof)

    return clone(original, {'_source_origin': source_origin})
