"""Code-only draft: root may build a primary release after actual E2/E4 review.

No import-time artifact writes, approval, unsealing or generation. The explicit execute path
requires a separate root decision and a descriptor-only input metadata file.
It never hashes or opens the eight source targets and never touches a ledger.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_grounded_confirmation_v3 as c

BASE = c.BASE
DESIGN = c.DESIGN
GENERATED = {'final_configuration', 'reference_policy', 'blind_packet_policy_freeze'}
CONTEXT = BASE / 'grounded_v7_design_v1/context_configuration.json'
REFERENCE_DRAFT = DESIGN / 'reference_policy_draft.json'
DEFAULT_INPUT_BINDINGS = BASE / 'grounded_v7_design_v1/confirmation_input_bindings_metadata.json'
FORBIDDEN = ('sealed_confirmation', 'confirmation_manifest', 'identity_key', '/human_review/')
FINAL_ROLES = ['budget_allocation_amendment', 'converter', 'schema', 'development_backend', 'fact_checker', 'fact_checker_freeze',
    'model_config', 'model_contract', 'development_contract', 'reference_catalog', 'reference_projection',
    'reference_integrity_amendment', 'projection_script', 'method_family_policy', 'step_core', 'step_scorer', 'encoder_manifest', 'numeric_adapter']
REFERENCE_ROLES = ['reference_catalog', 'reference_projection', 'reference_integrity_amendment', 'projection_script',
    'method_family_policy', 'step_core', 'step_scorer']


def install_no_source_or_network_access():
    ledger = c.LEDGER.resolve()
    def audit(event, args):
        if event == 'open' and args and isinstance(args[0], (str, bytes, Path)):
            path = Path(args[0]).resolve()
            text = str(path).lower().replace('\\', '/')
            c.require(path != ledger and not any(x in text for x in FORBIDDEN), 'RELEASE_BUILDER_PROTECTED_ACCESS_FORBIDDEN')
            c.require(not re.search(r'/grounded_confirmation_v\d+/(?:cases\.json|source_documents/|prompts/|run/|observations\.json)', text),
                      'CONFIRMATION_FEEDBACK_READ_FORBIDDEN')
        if event in ['socket.connect', 'socket.getaddrinfo', 'subprocess.Popen']:
            raise ValueError('RELEASE_BUILDER_NETWORK_OR_PROCESS_FORBIDDEN')
    sys.addaudithook(audit)


def public_path(path):
    path = Path(path).resolve()
    c.require(not c.forbidden_metadata_path(path), 'PROTECTED_METADATA_PATH')
    c.require(path != c.LEDGER.resolve(), 'LEDGER_IS_NOT_RELEASE_METADATA')
    return path


def read(path):
    return c.j.read(public_path(path))


def bind(path):
    return c.bind(public_path(path))


def default_source_paths(encoder_manifest):
    """No reads: public path construction only; not a declaration of readiness."""
    dev = BASE / 'grounded_development_v7'
    e2 = BASE / 'grounded_controls_v1'
    e4 = BASE / 'grounded_stability_dev_v1'
    return {
        'budget_allocation_amendment': c.BUDGET_ALLOCATION,
        'converter': ROOT / 'scripts/cce_grounded_extraction_v7.py', 'schema': BASE / 'grounded_extraction_v7/schema.json',
        'development_backend': ROOT / 'scripts/cce_grounded_development_v7.py', 'development_plan': dev / 'plan.json',
        'development_completion': dev / 'completion_summary.json',
        'development_fact_summary': dev / 'independent_fact_audit_v7/summary.json',
        'development_fact_verification': BASE / 'fact_verification_interface_v1/verification.json',
        'fact_checker': ROOT / 'scripts/cce_audit_grounded_facts_v7.py', 'fact_checker_freeze': BASE / 'fact_audit_checker_v7/freeze.json',
        'model_config': e4 / 'model_config.json', 'model_contract': e4 / 'expected_contract.json',
        'development_contract': dev / 'expected_contract.json',
        'reference_catalog': c.projection.CAT,
        'reference_projection': c.REFERENCE_REVISION / 'projected_all_references.json',
        'reference_integrity_amendment': c.REFERENCE_REVISION / 'integrity_amendment.json',
        'projection_script': Path(c.projection.__file__), 'method_family_policy': c.family.DEST / 'policy.json',
        'step_core': Path(c.family.core.__file__), 'step_scorer': Path(c.family.__file__),
        'encoder_manifest': Path(encoder_manifest), 'numeric_adapter': Path(c.numeric.__file__),
        'E2_completion': e2 / 'completion_summary.json', 'E2_per_answer': e2 / 'per_answer.json',
        'E2_matrix': e2 / 'matrix.json', 'E2_verification': e2 / 'analysis_verification.json', 'E2_contract': e2 / 'expected_contract.json',
        'E4_completion': e4 / 'analysis/completion_summary.json', 'E4_observations': e4 / 'analysis/observations.json',
        'E4_matrix': e4 / 'matrix.json', 'E4_verification': e4 / 'analysis/analysis_verification.json', 'E4_contract': e4 / 'expected_contract.json'}


def decision_binding_paths(paths, input_bindings, report):
    """Root binds its decision to all selected public inputs, including limits."""
    return list(dict.fromkeys([Path(__file__), Path(c.__file__), public_path(input_bindings), public_path(report),
        CONTEXT, REFERENCE_DRAFT, *paths.values()]))


def verify_root_decision(path, required_paths):
    decision = read(path)
    c.require(decision.get('status') == 'approved_for_primary_confirmation_release_build'
        and decision.get('selected_by') == 'root_agent' and decision.get('selected_backend_version') == 'v7'
        and decision.get('approved_for_primary_confirmation') is True, 'ROOT_FINAL_PRIMARY_DECISION_REQUIRED')
    c.require(decision.get('configuration_frozen_before_confirmation') is True and decision.get('no_post_confirmation_tuning') is True
        and decision.get('optional_blind_execution_allowed') is False
        and decision.get('post_confirmation_blind_reactivation_allowed') is False, 'ROOT_FINAL_CONFIGURATION_MUST_BE_CLOSED')
    c.require(all(decision.get(key) is True for key in ['development_fact_review_complete', 'development_report_complete',
        'E2_terminal_review_complete', 'E4_terminal_review_complete', 'confirmation_not_started']),
        'ROOT_FINAL_REVIEWS_AND_PRECONFIRMATION_STATE_REQUIRED')
    c.require(isinstance(decision.get('created_utc'), str) and decision['created_utc']
        and isinstance(decision.get('development_limitations_acknowledgement'), str)
        and decision['development_limitations_acknowledgement'].strip(), 'ROOT_MUST_ACKNOWLEDGE_ACTUAL_DEVELOPMENT_LIMITS')
    bindings = decision.get('bindings', [])
    c.require(isinstance(bindings, list) and bindings, 'ROOT_DECISION_BINDINGS_REQUIRED')
    indexed = {}
    for item in bindings:
        c.require(c.terminal_binding_shape(item), 'ROOT_DECISION_BINDING_SHAPE')
        p = public_path(item['path']); c.verify(item)
        c.require(str(p) not in indexed, 'ROOT_DECISION_DUPLICATE_BINDING')
        indexed[str(p)] = item['sha256']
    for p in required_paths:
        item = bind(p)
        c.require(indexed.get(item['path']) == item['sha256'], 'ROOT_DECISION_NOT_BOUND_TO_SELECTED_INPUT:' + item['path'])
    return decision


def input_descriptors(path):
    metadata = read(path)
    rows = metadata.get('confirmation_inputs')
    c.require(isinstance(rows, list) and len(rows) == 8 and [r.get('anonymous_answer_id') for r in rows] == c.IDS,
              'ROOT_INPUT_METADATA_MUST_LIST_C01_THROUGH_C08')
    seen = set()
    for row in rows:
        c.require(set(row) == {'anonymous_answer_id', 'path', 'sha256'}, 'INPUT_METADATA_MUST_NOT_CONTAIN_SCIENTIFIC_OR_IDENTITY_CONTENT')
        # Deliberately inspect only the supplied descriptor strings. No exists,
        # read, stat, hash, glob or JSON decode is performed on a source target.
        p = Path(row['path'])
        normalized = str(p).replace('\\', '/').lower()
        c.require(p.is_absolute() and '/sealed_confirmation/' in normalized
            and p.name == row['anonymous_answer_id'] + '.json', 'EXPLICIT_CXX_DESCRIPTOR_REQUIRED')
        c.require(normalized not in seen, 'DUPLICATE_SOURCE_DESCRIPTOR'); seen.add(normalized)
        c.require(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-fA-F]{64}', row['sha256']), 'SOURCE_DESCRIPTOR_SHA256_REQUIRED')
    return copy.deepcopy(rows)


def verify_encoder_manifest(path):
    manifest = read(path)
    c.require(manifest.get('encoder') == 'all-mpnet-base-v2' and manifest.get('bindings'), 'COMPLETE_ENCODER_MANIFEST_REQUIRED')
    actual = {str(p.resolve()) for p in (c.family.core.ASSETS / 'assets/all-mpnet-base-v2').rglob('*') if p.is_file()}
    c.require({str(public_path(x['path'])) for x in manifest['bindings']} == actual, 'ENCODER_MANIFEST_ASSET_SET_CHANGED')
    for item in manifest['bindings']: public_path(item['path']); c.verify(item)


def verified_families(paths):
    context = read(CONTEXT)
    c.require(context.get('num_ctx') == 98304 and context.get('selected_by') == 'root_agent', 'V7_CONTEXT_REQUIRED')
    models = read(paths['model_contract'])['models']; result = {}
    for model in models:
        settings = model['settings']
        matches = [r for r in context['models'] if r['local_model_name'] == settings['model'] and r['digest'] == settings['model_digest']]
        c.require(len(matches) == 1 and matches[0]['details'] == settings['model_details'], 'MODEL_ARCHITECTURE_NOT_BOUND_TO_CONTEXT_METADATA')
        row = matches[0]
        c.require(settings['enable_thinking'] is row['request_enable_thinking'], 'ORIGINAL_THINKING_VALUE_CHANGED')
        family = row['details'].get('family')
        c.require(isinstance(family, str) and family and row.get('reported_architecture') == family, 'VERIFIED_FAMILY_METADATA_REQUIRED')
        result[model['name']] = family
    c.require(len(result) == 2 and len(set(result.values())) == 2, 'TWO_ACTUAL_REPORTED_FAMILIES_REQUIRED')
    return result


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf8')


def predicted(path, value):
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(encoded(value)).hexdigest()}


def documents(directory, paths, decision_path, decision, inputs_path, inputs, report_path, families):
    generated = {k: directory / (k + '.json') for k in GENERATED}
    allpaths = {**paths, **generated}
    assets = {k: bind(p) for k, p in paths.items()}
    # Reuse the existing complete scientific policy. Only its prospective
    # approval status and explicit root provenance are added; no science filter.
    policy = read(REFERENCE_DRAFT)
    c.require(policy.get('status') == 'draft_not_frozen', 'EXPECTED_REFERENCE_POLICY_DRAFT')
    c.require(policy.get('selection') == c.family.policy()['selection'], 'ORIGINAL_REFERENCE_SELECTION_CHANGED')
    for key in REFERENCE_ROLES:
        c.require(policy.get(key) == assets[key], 'REFERENCE_DRAFT_BINDING_DIFFERS:' + key)
    policy.update(status='frozen_before_confirmation', frozen_by='root_agent', root_decision=bind(decision_path))
    assets['reference_policy'] = predicted(generated['reference_policy'], policy)
    final = {'status': 'frozen_before_confirmation', 'created_utc': decision['created_utc'], 'selected_by': 'root_agent',
        'selected_backend_version': 'v7', 'num_ctx': 98304, 'verified_model_families': families,
        'optional_blind_execution_allowed': False, 'post_confirmation_blind_reactivation_allowed': False,
        'no_post_confirmation_tuning': True, 'formal_eligible': False, 'expert_confirmation': None,
        'development_limitations_acknowledgement': decision['development_limitations_acknowledgement'],
        'bindings': [assets[k] for k in FINAL_ROLES] + [bind(c.__file__), bind(__file__), bind(CONTEXT),
            bind(decision_path), bind(inputs_path), bind(report_path), assets['reference_policy']]}
    assets['final_configuration'] = predicted(generated['final_configuration'], final)
    packet = {'status': 'frozen_before_primary_unsealing', 'frozen_by': 'root_agent', 'created_utc': decision['created_utc'],
        'optional_blind_execution_allowed': False, 'post_confirmation_blind_reactivation_allowed': False,
        'blind_assessments_planned': 0, 'no_packet_generation_or_dispatch_authorized': True,
        'scope': 'Preserve disabled optional design; no source packet or blinded assessment is generated by this file.',
        'bindings': [assets[k] for k in ['budget_allocation_amendment', 'converter', 'schema', 'reference_policy']] + [bind(decision_path)]}
    assets['blind_packet_policy_freeze'] = predicted(generated['blind_packet_policy_freeze'], packet)
    c.require(set(assets) == c.ASSETS, 'EXACT_RELEASE_ROLE_SET')
    release = {'status': 'released_for_primary_confirmation', 'selected_by': 'root_agent', 'created_utc': decision['created_utc'],
        'configuration_frozen_before_confirmation': True, 'no_post_confirmation_tuning': True,
        'optional_blind_execution_allowed': False, 'post_confirmation_blind_reactivation_allowed': False,
        'assets': assets, 'confirmation_inputs': inputs, 'root_decision': bind(decision_path),
        'confirmation_descriptor_metadata': bind(inputs_path), 'development_report': bind(report_path),
        'builder': bind(__file__), 'sealed_targets_read_or_hashed_by_builder': False,
        'actual_model_requests_by_builder': 0, 'formal_eligible': False, 'expert_confirmation': None}
    return allpaths, {generated['reference_policy']: policy, generated['final_configuration']: final,
        generated['blind_packet_policy_freeze']: packet, directory / 'final_release.json': release}


def write_new(path, value):
    path = Path(path).resolve()
    c.require(DESIGN.resolve() in path.parents, 'GENERATED_FILE_OUTSIDE_PRIMARY_DESIGN')
    c.require(not path.exists(), 'NEVER_OVERWRITE_RELEASE_BUILD_ARTIFACT:' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    c.require(not temporary.exists(), 'STALE_RELEASE_BUILD_TEMPORARY')
    with temporary.open('xb') as stream: stream.write(encoded(value))
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--root-decision', type=Path, required=True)
    parser.add_argument('--input-bindings', type=Path, default=DEFAULT_INPUT_BINDINGS)
    parser.add_argument('--encoder-manifest', type=Path, required=True)
    parser.add_argument('--development-report', type=Path, required=True)
    parser.add_argument('--asset-overrides', type=Path, help='Optional public JSON mapping existing asset role to path; never generated roles.')
    args = parser.parse_args()
    c.require(args.execute, 'ROOT_EXPLICIT_BUILD_EXECUTION_REQUIRED')
    install_no_source_or_network_access()
    for version in ['v1', 'v2', 'v3']:
        target = BASE / ('grounded_confirmation_' + version)
        c.require(not (target / 'prepared_inputs.json').exists() and not (target / 'unsealing_receipt.json').exists(),
                  'NO_RELEASE_BUILD_AFTER_ANY_PRIMARY_UNSEALING')
    c.require(not c.RELEASE.exists(), 'ACTUAL_RELEASE_ALREADY_EXISTS')
    paths = default_source_paths(args.encoder_manifest)
    if args.asset_overrides:
        overrides = read(args.asset_overrides)
        c.require(isinstance(overrides, dict) and set(overrides) <= set(paths), 'UNKNOWN_OR_GENERATED_ASSET_OVERRIDE')
        paths.update({k: Path(v) for k, v in overrides.items()})
    paths = {k: public_path(v) for k, v in paths.items()}
    c.require(set(paths) == c.ASSETS - GENERATED, 'SOURCE_ROLE_SET')
    required = decision_binding_paths(paths, args.input_bindings, args.development_report)
    if args.asset_overrides: required.append(public_path(args.asset_overrides))
    decision = verify_root_decision(args.root_decision, required)
    source_snapshot = [bind(p) for p in required] + [bind(args.root_decision)]
    inputs = input_descriptors(args.input_bindings)
    c.verify_budget_allocation(paths['budget_allocation_amendment'])
    c.verify_terminal_metadata(paths)
    c.require(read(paths['development_plan']).get('planned_new_requests') == 5, 'V7_DEVELOPMENT_PLAN_REQUIRED')
    c.require(read(paths['schema'])['properties']['grounded_extraction']['properties']['schema_version']['const'] == 'source_bound_extraction_v7', 'V7_SCHEMA_REQUIRED')
    backend = c.load_backend(paths)
    c.require(backend.grounded.VERSION == 'source_bound_extraction_v7' and backend.OUT.name == 'grounded_development_v7', 'V7_BACKEND_REQUIRED')
    verify_encoder_manifest(paths['encoder_manifest'])
    families = verified_families(paths)
    # Stage a complete graph and exercise ORIGINAL gates, not permissive mocks.
    stage = DESIGN / 'release_build_audit' / bind(args.root_decision)['sha256'][:16]
    c.require(not stage.exists(), 'AUDIT_STAGE_ALREADY_EXISTS_USE_EXPLICIT_RECOVERY_REVIEW')
    stagepaths, staged = documents(stage, paths, args.root_decision, decision, args.input_bindings, inputs, args.development_report, families)
    for path, value in staged.items(): write_new(path, value)
    original_release = c.RELEASE
    try:
        c.RELEASE = stage / 'final_release.json'
        _, checked = c.release_gate()
        c.public_models(checked); c.projected_catalog(checked)
    finally:
        c.RELEASE = original_release
    # Rebind generated edges to their final names; never change scientific data.
    finalpaths, output = documents(DESIGN, paths, args.root_decision, decision, args.input_bindings, inputs, args.development_report, families)
    c.require(all(not p.exists() for p in output), 'FINAL_OUTPUT_ALREADY_EXISTS')
    for item in source_snapshot: c.verify(item)
    for path, value in output.items():
        if path.name != 'final_release.json': write_new(path, value)
    write_new(c.RELEASE, output[c.RELEASE])  # Release is published LAST.
    _, checked = c.release_gate()
    c.public_models(checked); c.projected_catalog(checked)
    write_new(stage / 'build_verification.json', {'status': 'pass_metadata_release_build_no_unsealing',
        'actual_command': [sys.executable, *sys.argv], 'builder': bind(__file__), 'runner': bind(c.__file__),
        'final_artifacts': [bind(p) for p in output], 'source_snapshot': source_snapshot,
        'sealed_target_reads_or_hashes': 0, 'ledger_access': False, 'model_requests': 0, 'embeddings': 0,
        'actual_primary_prepared': False, 'formal_integration_review_created': False,
        'scientific_acceptance_inferred': False, 'expert_confirmation_created': False})
    print(json.dumps({'status': 'release_built_from_root_decision_no_unsealing', 'release': bind(c.RELEASE), 'model_requests': 0}))


if __name__ == '__main__':
    main()
