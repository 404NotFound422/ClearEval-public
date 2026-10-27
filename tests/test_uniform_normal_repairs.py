from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research' / 'evaluator-research-cycle-20261018'
RESOLUTION = RESEARCH / 'execution_alignment_resolution_20261024_v1'
RUNNER = RESOLUTION / 'runtime' / 'uniform_normal_runner_v1'


def run_in_scorer_environment(source):
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    result = subprocess.run(
        [sys.executable, '-X', 'utf8', '-B', '-c', source],
        cwd=RESEARCH, env=env, capture_output=True, text=True,
        encoding='utf-8', timeout=600, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_component36_uses_atomic_multisource_private_core():
    observed = run_in_scorer_environment(f'''
import json, sys
sys.path.insert(0, {str(RUNNER)!r})
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v36 as entry
from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v2 import normal_adapter as multi, strict_core
from execution_alignment_resolution_20261024_v1.parameter_contract_dispatch_v1 import dispatch
multi_api = entry.parameter.native_backend.actual_multi_api
consume = multi_api.consume
closure = dict(zip(consume.__code__.co_freevars, consume.__closure__))
private = closure['template'].cell_contents
binding = strict_core.validate_private(private)
print(json.dumps({{
    'outer_dispatch': entry.parameter.VERSION == dispatch.VERSION,
    'multi_api': multi_api.VERSION == multi.VERSION,
    'private_core': binding['parameter_component']['source_file'],
    'global_fallback': binding['global_template_or_core_fallback_allowed'],
}}))
''')
    assert observed['outer_dispatch'] is True
    assert observed['multi_api'] is True
    assert Path(observed['private_core']).name == 'review_core_interface_v1.py'
    assert observed['global_fallback'] is False


def test_run38_selects_multisource_reviews_by_answer_and_branch():
    observed = run_in_scorer_environment(f'''
import json, sys
sys.path.insert(0, {str(RUNNER)!r})
import run_v38 as runner
mapping_path = runner.C.RES / 'parameter_atomic_multisource_v2/actual3_validation_v5/branch_review_sources.json'
mappings = runner.C.read(mapping_path)
checks = []
for mapping in mappings:
    selected = runner.actual_parameter_review(mapping['input_id'], mapping['branch'])
    expected = runner.C.read(mapping['review_sources_path'])
    checks.append(
        set(selected) == {{'review_sources'}}
        and selected['review_sources'] == expected
        and next(iter(expected)) == mapping['target_payload_sha256'])
print(json.dumps({{'branches': len(mappings), 'checks': checks}}))
''')
    assert observed == {'branches': 3, 'checks': [True, True, True]}


def test_saved_coverage_reentry_respects_score_status(tmp_path):
    observed = run_in_scorer_environment(f'''
import importlib.util, json, sys
from pathlib import Path
sys.path.insert(0, {str(RUNNER)!r})
path = Path({str(RESOLUTION / 'runtime' / 'step_packet_json_representation_v1' / 'validate_actual.py')!r})
spec = importlib.util.spec_from_file_location('_validate_actual_under_test', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.D = Path({str(tmp_path)!r})
module.main()
out = module.D / 'actual_validation_v1'
summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
records = json.loads((out / 'records3.json').read_text(encoding='utf-8'))
print(json.dumps({{'summary': summary, 'coverage': [
    [r['coverage_status'], r['public_coverage_revalidated']] for r in records
]}}))
''')
    assert observed['summary']['status'] == 'PASS'
    assert observed['summary']['actual_saved_normal_branches'] == 3
    assert observed['summary']['negative_controls_rejected'] == 10
    assert observed['coverage'] == [
        ['UNKNOWN', True], ['VALID', False], ['UNKNOWN', True]]


def test_current_component36_three_branch_acceptance(tmp_path):
    results = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/component36/normal033_current_v1')
    declaration = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/component36/declaration_v2/affected_branches.json')
    script = RESOLUTION / 'runtime' / 'component36_parameter_integration_v1' / 'verify_normal3.py'
    output = tmp_path / 'acceptance'
    observed = run_in_scorer_environment(f'''
import json, runpy, sys
from pathlib import Path
results = Path({str(results)!r})
summary = json.loads((results / 'summary.json').read_text(encoding='utf-8'))
assert summary['status'] == 'PASS' and summary['counts'] == {{'PASS': 3}}
sys.argv = [{str(script)!r}, '--results', str(results), '--output', {str(output)!r},
            '--affected-plan', {str(declaration)!r}]
runpy.run_path({str(script)!r}, run_name='__main__')
print(json.dumps(json.loads((Path({str(output)!r}) / 'summary.json').read_text(encoding='utf-8'))))
''')
    assert observed['status'] == 'PASS'
    assert observed['actual_full_normal_branches'] == 3
    assert observed['all_strict_slots_valid'] is True
    assert observed['current_certificates_and_original_Com_IA_formula_recomputed'] is True
    assert observed['saved_json_representation_revalidated'] is True
    assert observed['full193_merge_performed'] is False


def test_time_packet_pins_include_shared_count_dependencies():
    observed = run_in_scorer_environment('''
import json
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import time
print(json.dumps(sorted(time.pins())))
''')
    names = {Path(path).name for path in observed}
    assert {'counts.py', 'count_consumers.py'} <= names


def test_component37_uses_proved_quote_observer():
    observed = run_in_scorer_environment(f'''
import json, sys
sys.path.insert(0, {str(RUNNER)!r})
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v37 as entry
from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v2 import strict_core
multi_api = entry.parameter.native_backend.actual_multi_api
consume = multi_api.consume
closure = dict(zip(consume.__code__.co_freevars, consume.__closure__))
private = closure['template'].cell_contents
binding = strict_core.validate_private(private)
print(json.dumps({{
    'observer': binding['observations']['source_file'],
    'core': binding['parameter_component']['source_file'],
    'global_fallback': binding['global_template_or_core_fallback_allowed'],
}}))
''')
    assert Path(observed['observer']).parent.name == 'parameter_strict_source_quote_projection_v1'
    assert Path(observed['core']).name == 'review_core_interface_v1.py'
    assert observed['global_fallback'] is False


def test_metadata_source_normalizes_reference_interval_containers(tmp_path):
    observed = run_in_scorer_environment(f'''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import source_entry
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
plan = C.read(C.HERE / 'inventory_v3/plan193.json')
record = next(r for r in plan if r['input_id'] == 'EXPAND_170' and r['branch'] == 'G')
with source_entry.prepare_branch(record['job'], Path({str(tmp_path)!r}) / 'provider') as branch:
    source = branch['execution_source_scope']
canonical = json.loads(json.dumps(source, ensure_ascii=False, allow_nan=False))
proof = source['pair']['reference']['operations'][0]['reference_execution_resolution']['duration_alternatives_preserved']
print(json.dumps({{
    'canonical': canonical == source,
    'slice_hours': proof['slice_hours'],
    'whole_mount_hours': proof['whole_mount_hours'],
    'slice_thickness_micrometers': proof['slice_thickness_micrometers'],
}}))
''')
    assert observed == {
        'canonical': True,
        'slice_hours': [2.0, 4.0],
        'whole_mount_hours': [6.0, 10.0],
        'slice_thickness_micrometers': [200.0, 500.0],
    }


def test_component37_source_is_json_canonical(tmp_path):
    observed = run_in_scorer_environment(f'''
import json, sys
from pathlib import Path
sys.path.insert(0, {str(RUNNER)!r})
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v37 as entry
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
plan = C.read(C.HERE / 'inventory_v3/plan193.json')
record = next(r for r in plan if r['input_id'] == 'EXPAND_170' and r['branch'] == 'G')
with entry.prepare_branch(record['job'], Path({str(tmp_path)!r}) / 'provider') as branch:
    source = branch['execution_source_scope']
canonical = json.loads(json.dumps(source, ensure_ascii=False, allow_nan=False))
proof = source['pair']['reference']['operations'][0]['reference_execution_resolution']['duration_alternatives_preserved']
print(json.dumps({{'canonical': canonical == source, 'proof': proof}}))
''')
    assert observed['canonical'] is True
    assert observed['proof']['slice_hours'] == [2.0, 4.0]
    assert observed['proof']['whole_mount_hours'] == [6.0, 10.0]
    assert observed['proof']['slice_thickness_micrometers'] == [200.0, 500.0]


def test_metadata_parameter_keeps_quote_observer_and_actual_count_units(tmp_path):
    observed = run_in_scorer_environment(f'''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import parameter, source_entry
from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v2 import strict_core
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
plan = C.read(C.HERE / 'inventory_v3/plan193.json')
record = next(r for r in plan if r['input_id'] == 'EXPAND_024' and r['branch'] == 'CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
with source_entry.prepare_branch(record['job'], Path({str(tmp_path)!r}) / 'provider') as branch:
    private = parameter.consume.__globals__['template']
    binding = strict_core.validate_private(private)
    prepared = parameter.prepare(branch['case'], branch['execution_source_scope'], branch['request'])
worlds = prepared['binding']['domain']['worlds']
counts = [sum(u['parent_operation_id'] == 'step_6_4' for u in world['units']) for world in worlds]
print(json.dumps({{'observer': binding['observations']['source_file'], 'counts': counts, 'prepare': prepared['status']}}))
''')
    assert Path(observed['observer']).parent.name == 'parameter_strict_source_quote_projection_v1'
    assert observed['counts'] == [3, 3]


def test_metadata_parameter_reseals_independent_source_changes(tmp_path):
    observed = run_in_scorer_environment(f'''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import parameter, source_entry
from execution_alignment_resolution_20261024_v1.scope import explicit_operation_role_v4 as explicit
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
plan = C.read(C.HERE / 'inventory_v3/plan193.json')
record = next(r for r in plan if r['input_id'] == 'EXPAND_170' and r['branch'] == 'G')
with source_entry.prepare_branch(record['job'], Path({str(tmp_path)!r}) / 'provider') as branch:
    source = branch['execution_source_scope']
    prepared = parameter.prepare(branch['case'], source, branch['request'])
    replayed = explicit.project(source, branch['case']['protocol'])
proof = source['explicit_operation_source_projection']
print(json.dumps({{'status': prepared['status'], 'facts': len(proof['facts']), 'valid': replayed == source}}))
''')
    assert observed['status'] in {'PREPARED', 'UNRESOLVED'}
    assert observed['facts'] == 3
    assert observed['valid'] is True


def test_component38_composes_metadata_time_and_private_parameter_backends():
    observed = run_in_scorer_environment(f'''
import json, sys
sys.path.insert(0, {str(RUNNER)!r})
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v38 as entry
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import source_entry, time
from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v2 import strict_core
multi_api = entry.parameter.native_backend.actual_multi_api
consume = multi_api.consume
closure = dict(zip(consume.__code__.co_freevars, consume.__closure__))
private = closure['template'].cell_contents
binding = strict_core.validate_private(private)
print(json.dumps({{
    'source_version': entry.source_entry.VERSION,
    'expected_source_version': source_entry.VERSION,
    'time_version': entry.time.VERSION,
    'expected_time_version': time.VERSION,
    'observer': binding['observations']['source_file'],
}}))
''')
    assert observed['source_version'] == observed['expected_source_version']
    assert observed['time_version'] == observed['expected_time_version']
    assert Path(observed['observer']).parent.name == 'parameter_strict_source_quote_projection_v1'


def test_recipe_scope_shares_source_route_without_inventing_component_presence():
    observed = run_in_scorer_environment('''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.parameter_route_role_scope_v1 import recipe_scope
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES / 'parameter_literal_action_scope_v1/probe_v2/EXPAND_139/selected'
prepared = C.read(root / 'prepared_parameter.json')
records = C.read(C.RES / 'runtime/uniform_common193_component31_v1/records193.json')
record = next(r for r in records if r['input_id'] == 'EXPAND_139')
path = Path(record['result_path'])
path = path if path.is_absolute() else C.RES.parent / path
case = C.read(path.parent / 'case.json')
parent = prepared['binding']['parent_action_requirement_binding']
checks = {}
for origin in ('route:peg18_tb_carrier:carrier:tert_butanol', 'route:peg18_gradient_quadrol:formulation_component:Quadrol'):
    shared = next(s for s in parent['shared_material_route_bindings'] if s['original_slot']['id'] == origin)
    proof, error = recipe_scope.bind(shared, parent, case['protocol'])
    checks[origin] = {'error': error, 'parents': [] if proof is None else proof['actual_parent_ids']}
print(json.dumps(checks))
''')
    expected = ['R009', 'R010', 'R011', 'R012', 'R013', 'R014']
    for origin in (
        'route:peg18_tb_carrier:carrier:tert_butanol',
        'route:peg18_gradient_quadrol:formulation_component:Quadrol',
    ):
        assert observed[origin] == {'error': None, 'parents': expected}


def test_recipe_scope_prepares_all_pegasos_worlds_without_dropping_denominators():
    observed = run_in_scorer_environment('''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.parameter_literal_action_scope_v1 import normal_candidate_v1 as normal
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
records = C.read(C.RES / 'runtime/uniform_common193_component31_v1/records193.json')
record = next(r for r in records if r['input_id'] == 'EXPAND_139')
path = Path(record['result_path'])
path = path if path.is_absolute() else C.RES.parent / path
case = C.read(path.parent / 'case.json')
source = C.read(path.parent / 'execution_scope.json')
request = C.read(path.parent / 'request.json')
prepared = normal.prepare(case, source, request)
print(json.dumps({
    'status': prepared['status'],
    'complete': sum(w['complete_applicability'] for w in prepared['binding']['worlds']),
    'worlds': len(prepared['binding']['worlds']),
    'fine_counts': [len(w['slots']) for w in prepared['binding']['worlds']],
    'queries': sum(len(r['payload']['queries']) for r in prepared['requests'].values()),
}))
''')
    assert observed['status'] == 'PREPARED'
    assert observed['complete'] == observed['worlds'] == 9
    assert observed['fine_counts'] == [44, 50, 50, 42, 48, 48, 43, 49, 49]
    assert observed['queries'] > 0


def test_conditional_role_scope_preserves_complete_phase_worlds():
    observed = run_in_scorer_environment('''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.parameter_route_role_scope_v1 import conditional_scope
from execution_alignment_resolution_20261024_v1.parameter_literal_action_scope_v1 import normal_candidate_v1 as normal
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
records = C.read(C.RES / 'runtime/uniform_common193_component31_v1/records193.json')
record = next(r for r in records if r['input_id'] == 'EXPAND_005')
path = Path(record['result_path'])
path = path if path.is_absolute() else C.RES.parent / path
case = C.read(path.parent / 'case.json')
source = C.read(path.parent / 'execution_scope.json')
request = C.read(path.parent / 'request.json')
parent = normal.prepare(case, source, request)['binding']['parent_action_requirement_binding']
shared = next(s for s in parent['shared_material_route_bindings'] if s['original_slot']['id'] == 'route:fdisco_fresh_preparation:preparation')
variants, error = conditional_scope.variants(shared, parent, case['protocol'])
prepared = normal.prepare(case, source, request)
print(json.dumps({
    'error': error,
    'variant_parents': [] if variants is None else [v['actual_parent_ids'] for v in variants],
    'status': prepared['status'],
    'worlds': len(prepared['binding']['worlds']),
    'fine_counts': [len(w['slots']) for w in prepared['binding']['worlds']],
    'requests': len(prepared['requests']),
    'unique_requests': prepared['world_plan']['unique_request_count'],
    'fresh_queries': sum('freshly prepared clearing working solutions' in q['criterion'] for req in prepared['requests'].values() for q in req['payload']['queries']),
}))
''')
    assert observed['error'] is None
    assert observed['variant_parents'] == [
        ['R008', 'R009', 'R010', 'R011', 'R012'],
        ['R008', 'R009', 'R010', 'R011', 'R012', 'R013'],
    ]
    assert observed['status'] == 'PREPARED'
    assert observed['worlds'] == 2
    assert observed['fine_counts'] == [54, 54]
    assert observed['requests'] == observed['unique_requests'] == 1
    assert observed['fresh_queries'] == 2


def test_metadata_ea_returns_carrier_receipt_for_changed_count_domain():
    observed = run_in_scorer_environment(f'''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import execution as E
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
record = next(r for r in C.read(C.HERE / 'inventory_v3/plan193.json') if r['input_id'] == 'EXPAND_024' and r['branch'] == 'CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
base = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/metadata/local10_current_v3/cases/EXPAND_024/CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
source = C.read(base / 'source.json')
case = C.read(base / 'case.json')
baseline = next(r for r in C.read(C.RES / 'runtime/uniform_common193_component34_v1/records193.json') if r['input_id'] == 'EXPAND_024' and r['branch'] == 'CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
result_path = Path(baseline['result_path'])
result_path = result_path if result_path.is_absolute() else C.RES.parent / result_path
facts = C.read(result_path.parent / 'source_time_facts.json')
preparation = C.read(record['job']['preparation_path'])
bundle = C.read(record['job']['bundle_path'])
result = E.calculate(source, case['protocol'], facts,
    variable_source_operations=preparation['capacity_input'].get('variable_source_operations', []),
    family_id=bundle.get('spec', {{}}).get('reference_id'))
carrier = result['phase_world_operation_carrier_receipt']
print(json.dumps({{
    'same_original': carrier['same_original_final_callable_preserved'],
    'changed': carrier['projection_causal_change'],
    'private_projection': carrier['schema_bound_private_world_projector_used'],
    'execution': result['private_ea_execution_receipt']['execution'],
}}))
''')
    assert observed == {
        'same_original': False,
        'changed': True,
        'private_projection': True,
        'execution': 'ACTUAL_FINAL_CALLABLE_EXECUTED',
    }


def test_joint_parameter_backend_preserves_quote_count_and_recipe_contracts(tmp_path):
    observed = run_in_scorer_environment(f'''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.parameter_joint_scope_v1 import normal_candidate as joint
from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v2 import strict_core
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
private = joint.consume.__globals__['template']
binding = strict_core.validate_private(private)
records = C.read(C.RES / 'runtime/uniform_common193_component31_v1/records193.json')
record = next(r for r in records if r['input_id'] == 'EXPAND_139')
path = Path(record['result_path'])
path = path if path.is_absolute() else C.RES.parent / path
case, source, request = [C.read(path.parent / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
prepared139 = joint.prepare(case, source, request)
expected139 = C.read('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_scope139/prepared.json')
base = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/metadata/local10_current_v3/cases/EXPAND_024/CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
source024 = C.read(base / 'source.json')
case024 = C.read(base / 'case.json')
record024 = next(r for r in C.read(C.HERE / 'inventory_v3/plan193.json') if r['input_id'] == 'EXPAND_024' and r['branch'] == 'CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
request024 = C.read(record024['job']['request_path'])
prepared024 = joint.prepare(case024, source024, request024)
counts = [sum(u['parent_operation_id'] == 'step_6_4' for u in world['units']) for world in prepared024['binding']['domain']['worlds']]
print(json.dumps({{
    'observer': binding['observations']['source_file'],
    'counts': counts,
    'requests139_equal': prepared139['requests'] == expected139['requests'],
    'worlds139_equal': prepared139['binding']['worlds'] == expected139['binding']['worlds'],
}}))
''')
    assert Path(observed['observer']).parent.name == 'parameter_strict_source_quote_projection_v1'
    assert observed['counts'] == [3, 3]
    assert observed['requests139_equal'] is True
    assert observed['worlds139_equal'] is True


def test_component39_composes_joint_parameter_with_metadata_time_and_steps():
    observed = run_in_scorer_environment(f'''
import json, sys
from pathlib import Path
sys.path.insert(0, {str(RUNNER)!r})
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v39 as entry
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v38 as prior
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import source_entry, time
from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v2 import strict_core
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
multi_api = entry.parameter.native_backend.actual_multi_api
closure = dict(zip(multi_api.consume.__code__.co_freevars, multi_api.consume.__closure__))
private = closure['template'].cell_contents
binding = strict_core.validate_private(private)
record = next(r for r in C.read(C.HERE / 'inventory_v3/plan193.json') if r['input_id'] == 'EXPAND_024' and r['branch'] == 'CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
base = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/metadata/local10_current_v3/cases/EXPAND_024/CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
case, source = [C.read(base / (name + '.json')) for name in ('case', 'source')]
request = C.read(record['job']['request_path'])
prepared = entry.parameter.prepare(case, source, request)
counts = [sum(u['parent_operation_id'] == 'step_6_4' for u in w['units']) for w in prepared['binding']['domain']['worlds']]
print(json.dumps({{
    'source_version': entry.source_entry.VERSION == source_entry.VERSION,
    'time_version': entry.time.VERSION == time.VERSION,
    'step_version': entry.steps.VERSION == prior.steps.VERSION,
    'counts': counts,
    'observer': binding['observations']['source_file'],
}}))
''')
    assert observed['source_version'] is True
    assert observed['time_version'] is True
    assert observed['step_version'] is True
    assert observed['counts'] == [3, 3]
    assert Path(observed['observer']).parent.name == 'parameter_strict_source_quote_projection_v1'


def test_run41_loads_only_accepted_joint_review_evidence():
    observed = run_in_scorer_environment(f'''
import json, sys
sys.path.insert(0, {str(RUNNER)!r})
import run_v41 as runner
import run_v40 as prior
root = runner.Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451')
for iid, branch in [('EXPAND_139', 'selected')]:
    selected = runner.actual_parameter_review(iid, branch)
    expected = runner.C.read(root / ('parameter_scope' + iid[-3:]) / 'accepted_v1/review_sources.json')
    assert selected == {{'review_sources': expected}}
    assert prior.actual_parameter_review(iid, branch) is None
for iid in ['EXPAND_033', 'EXPAND_141', 'EXPAND_003', 'EXPAND_132', 'EXPAND_051', 'EXPAND_099', 'EXPAND_019', 'EXPAND_114', 'EXPAND_017', 'EXPAND_014', 'EXPAND_133', 'EXPAND_170']:
    plan = runner.C.read(runner.C.HERE / 'inventory_v3/plan193.json')
    for row in plan:
        if row['input_id'] == iid:
            assert runner.actual_parameter_review(iid, row['branch']) == prior.actual_parameter_review(iid, row['branch'])
print(json.dumps({{'joint_review_bound': True, 'legacy_review_sources_preserved': True}}))
''')
    assert observed == {'joint_review_bound': True, 'legacy_review_sources_preserved': True}


def test_metadata_merge_replays_source_projection_and_rejects_raw_text_changes(tmp_path):
    observed = run_in_scorer_environment(f'''
import copy, json, sys
from pathlib import Path
sys.path.insert(0, {str(RESOLUTION / 'runtime')!r})
sys.path.insert(0, {str(RUNNER)!r})
from execution_alignment_resolution_20261024_v1.runtime import apply_common_source_revisions_v4 as merger
from execution_alignment_resolution_20261024_v1.source_metadata_treatment_clock_20261025_v1 import source_entry
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/merge_stage1/roots/metadata8')
record = next(r for r in C.read(root / 'plan193.json') if r['input_id'] == 'EXPAND_024' and r['branch'] == 'CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
result_record = next(r for r in C.read(root / 'records193.json') if r['input_id'] == 'EXPAND_024' and r['branch'] == 'CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
old = next(r for r in C.read(C.RES / 'runtime/uniform_common193_component35_v1/records193.json') if r['input_id'] == 'EXPAND_024' and r['branch'] == 'CUBIC_2015_SIMPLE_IMMERSION_R1_R2')
old_path = Path(old['result_path'])
old_path = old_path if old_path.is_absolute() else C.RES.parent / old_path
new_path = Path(result_record['result_path'])
old_source = C.read(old_path.parent / 'execution_scope.json')
replay_prior_source = C.read(record['current_paths']['current_source'])
new_source = C.read(new_path.parent / 'execution_scope.json')
transition = C.read(new_path.parent / 'common_source_transition.json')
with source_entry.prepare_branch(record['job'], Path({str(tmp_path)!r}) / 'provider') as branch:
    proof = merger.validate_source_projection(branch, old_source, replay_prior_source, new_source, transition)
    changed = copy.deepcopy(replay_prior_source)
    changed['all_typed_rows'][0]['raw_text'] += 'UNAUTHORIZED'
    try:
        merger.validate_source_projection(branch, old_source, changed, new_source, transition)
    except AssertionError as error:
        assert str(error) == 'RAW_SOURCE_TEXT_CHANGED'
    else:
        raise AssertionError('RAW_TEXT_TAMPERING_ACCEPTED')
print(json.dumps(proof))
''')
    assert observed['status'] == 'PASS'
    assert observed['raw_source_text_unchanged'] is True
    assert observed['full_projection_replayed'] is True


def test_source_projection_merge_preserves_declared_parameter_metric_closure(tmp_path):
    observed = run_in_scorer_environment(f'''
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, {str(RESOLUTION / 'runtime')!r})
sys.path.insert(0, {str(RUNNER)!r})
from execution_alignment_resolution_20261024_v1.runtime import apply_common_source_revisions_v4 as merger
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/merge_stage1/roots/joint6')
record = next(r for r in C.read(root / 'plan193.json') if r['input_id'] == 'EXPAND_170' and r['branch'] == 'G')
new = next(r for r in C.read(root / 'records193.json') if r['input_id'] == 'EXPAND_170' and r['branch'] == 'G')
old = next(r for r in C.read(C.RES / 'runtime/uniform_common193_component35_v1/records193.json') if r['input_id'] == 'EXPAND_170' and r['branch'] == 'G')
prior = Path(record['current_paths']['current_source'])
policy = {{'policy': merger.PROJECTION_POLICY, 'prior_source_path': str(prior), 'prior_source_sha256': C.sha(prior)}}
proof = merger.validate(old, new, ['c_param', 'Com', 'IA'],
    causes=['EXACT_SOURCE_QUOTE_PROJECTION', 'CANONICAL_JSON_MAIN_SOURCE_BINDING'],
    source_projection=policy, job=record['job'], provider_output=Path({str(tmp_path)!r}) / 'provider')
print(json.dumps({{'changed': proof['changed_score_nodes'], 'projection': proof['source_projection_validation']['status'], 'exact': proof['shared_source_exact_for_component_only_revision']}}))
''')
    assert observed == {'changed': [], 'projection': 'PASS', 'exact': False}


def declared_material_case():
    return '''
from pathlib import Path
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA')
prepared = C.read(root / 'prepared.json')
case = C.read(root / 'case.json')
parent = prepared['binding']['parent_action_requirement_binding']
shared = parent['shared_material_route_bindings'][0]
'''


def test_recipe_scope_consumes_declared_material_alias_evidence():
    observed = run_in_scorer_environment(f'''
import json
{declared_material_case()}
from execution_alignment_resolution_20261024_v1.parameter_route_role_scope_v1 import recipe_scope
proof, error = recipe_scope.bind(shared, parent, case['protocol'])
print(json.dumps({{'proof': proof, 'error': error}}))
''')
    assert observed['error'] is None
    assert observed['proof']['actual_parent_ids'] == ['R001']
    assert observed['proof']['kind'] == 'EXACT_SOURCE_DECLARED_MATERIAL_SCOPE'
    assert observed['proof']['parameter_values_used_to_select_applicability'] is False
    assert observed['proof']['component_presence_not_inferred_from_route_binding'] is True


def test_recipe_scope_rejects_tampered_declared_material_alias():
    observed = run_in_scorer_environment(f'''
import copy, json
{declared_material_case()}
from execution_alignment_resolution_20261024_v1.parameter_route_role_scope_v1 import recipe_scope
changed = copy.deepcopy(parent)
changed['actual_material_mapping']['materials'][0]['source_primary_name_proof']['proofs'][0]['operation_span']['quote'] = 'PBS'
proof, error = recipe_scope.bind(shared, changed, case['protocol'])
print(json.dumps({{'proof': proof, 'error': error}}))
''')
    assert observed['proof'] is None
    assert observed['error'] == 'DECLARED_MATERIAL_ALIAS_PROOF_INVALID'


def test_reference_phase_units_bind_only_complete_cubic_actions():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from parameter_execution_unit_contract_20261025_v1 import source_units_v2
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope')]
projected, proofs = units.project(source, case['protocol'])
domain = units.namespace(source_units_v2).compile_candidate_units(source, case['protocol'])
print(json.dumps({{
    'resolved': sorted(proofs),
    'domain': domain['status'],
    'gaps': domain['gaps'],
    'unit_parents': sorted({{u['parent_operation_id'] for w in domain['worlds'] for u in w['units']}}),
    'references': {{key: value['reference_operation_ids'] for key, value in proofs.items()}},
    'raw_text_exact': [r['raw_text'] for r in source['all_typed_rows']] == [r['raw_text'] for r in projected['all_typed_rows']],
}}))
''')
    assert observed['resolved'] == ['R001', 'R003', 'R004', 'R005', 'R017', 'R018']
    assert observed['domain'] == 'FINITE_SOURCE_WORLDS'
    assert observed['gaps'] == []
    assert observed['unit_parents'] == ['R001', 'R002', 'R003', 'R004', 'R005', 'R017', 'R018']
    assert observed['references']['R001'] == ['C18:L']
    assert observed['references']['R003'] == ['C18:WASH']
    assert set(observed['references']['R017']) == {'C18:HALF_R', 'C18:R'}
    assert observed['raw_text_exact'] is True


def test_reference_phase_units_reject_foreign_medium():
    observed = run_in_scorer_environment(f'''
import copy, json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope')]
changed = copy.deepcopy(source)
changed['pair']['candidate']['operations'][0]['matching_identity'] = 'source_medium:CUBIC2015:R1'
changed['pair']['candidate']['original_scoped_rows'][0]['matching_identity'] = 'source_medium:CUBIC2015:R1'
projected, proofs = units.project(changed, case['protocol'])
print(json.dumps({{'resolved': sorted(proofs), 'raw_text_unchanged': changed['pair']['candidate']['operations'][0]['raw_text'] == source['pair']['candidate']['operations'][0]['raw_text']}}))
''')
    assert 'R001' not in observed['resolved']
    assert observed['raw_text_unchanged'] is True


def test_missing_private_reference_proofs_invalidate_completed_binding():
    observed = run_in_scorer_environment('''
import copy, json
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units, rebind
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148'
output = []
for branch, missing in [
    ('CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA', ('R017', 'R018')),
    ('CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA', ('R003',)),
    ('CUBIC_2019_IMMERSION_L_R_PLUS', ('R017', 'R018'))]:
    case, source, request = [C.read(root / branch / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
    complete = joint.prepare(case, source, request)
    assert complete['status'] == 'PREPARED'
    projected, proofs = units.project(source, case['protocol'])
    changed = copy.deepcopy(projected)
    for oid in missing:
        changed[units.VERSION]['proofs'].pop(oid)
    out = rebind.rebind(complete['binding'], changed, case['protocol'])
    output.append({'branch': branch, 'missing': missing,
        'status': out.get('private_typed_rebind', {}).get('status'),
        'complete': [w['complete_applicability'] for w in out['worlds']],
        'denominators': [w['denominator'] for w in out['worlds']]})
print(json.dumps(output))
''')
    for row in observed:
        assert row['status'] == 'INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE', row
        assert all(complete is False for complete in row['complete']), row
        assert all(denominator is None for denominator in row['denominators']), row


def test_cached_reference_projection_recomputes_deleted_and_rehashed_proofs():
    observed = run_in_scorer_environment('''
import copy, json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope')]
projected, proofs = units.project(source, case['protocol'])
output = []
for oid, rehash in [('R017', False), ('R003', True)]:
    changed = copy.deepcopy(projected)
    changed[units.VERSION]['proofs'].pop(oid)
    if rehash and 'proofs_sha256' in changed[units.VERSION]:
        changed[units.VERSION]['proofs_sha256'] = C.digest(changed[units.VERSION]['proofs'])
    try:
        units.project(changed, case['protocol'])
    except AssertionError as error:
        output.append(str(error))
    else:
        raise AssertionError('DELETED_REFERENCE_PROOF_ACCEPTED')
print(json.dumps(output))
''')
    assert observed == ['PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED'] * 2


def test_uncompiled_original_ledger_item_cannot_claim_complete_cubic_worlds():
    observed = run_in_scorer_environment(f'''
import copy, json
{projected_148_case()}
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units, rebind
from execution_alignment_resolution_20261024_v1.parameter_operation_variant_scope_v1 import apply as variants
from execution_alignment_resolution_20261024_v1.parameter_cubic_route_scope_v1 import apply as cubic_routes
source = C.read(root / 'parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/execution_scope.json')
request = C.read(root / 'parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/request.json')
projected, proofs = units.project(source, case['protocol'])
binding = variants.apply(rebind.rebind(prepared['binding'], projected, case['protocol']),
    case['protocol'], request['original_slot_manifest'])
binding['original_full_fine_item_ledger'].append({{'id': 'NEG_UNLISTED_ROUTE_ITEM',
    'operation_id': 'C18:L', 'dimension': 'carrier', 'subject': None,
    'criterion': 'NEGATIVE_CONTROL_ONLY', 'scope_unit': 'ROUTE', 'source_requirements': []}})
out = cubic_routes.apply(binding, case['protocol'], request['original_slot_manifest'])
print(json.dumps({{'status': out.get('cubic_route_audit', {{}}).get('status'),
    'complete': [w['complete_applicability'] for w in out['worlds']],
    'denominators': [w['denominator'] for w in out['worlds']]}}))
''')
    assert observed['status'] == 'INCOMPLETE_CUBIC_ORIGINAL_LEDGER_COVERAGE'
    assert observed['complete'] == [False] * 4
    assert observed['denominators'] == [None] * 4


def test_joint_reference_scope_prepares_complete_148_2018_parameter_worlds():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source, request = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
prepared = joint.prepare(case, source, request)
worlds = prepared.get('binding', {{}}).get('worlds', [])
print(json.dumps({{
    'status': prepared['status'], 'reason': prepared.get('reason'),
    'worlds': len(worlds), 'complete': sum(w.get('complete_applicability') is True for w in worlds),
    'fine_counts': [len(w.get('slots', [])) for w in worlds],
    'queries': sum(len(r['payload']['queries']) for r in prepared.get('requests', {{}}).values()),
    'reference_scope': prepared.get('binding', {{}}).get('domain', {{}}).get('parameter_private_reference_scope'),
}}))
''')
    assert observed['status'] == 'PREPARED'
    assert observed['worlds'] == 4
    assert observed['complete'] == observed['worlds']
    assert observed['fine_counts'] == [34, 33, 33, 32]
    assert observed['queries'] > 0
    assert observed['reference_scope']['reference_variants_retained'] is True


def projected_148_case():
    return '''
from pathlib import Path
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451')
prepared = C.read(root / 'parameter_scope148/phase_prepare_v1/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/prepared.json')
case = C.read(root / 'parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/case.json')
parent = prepared['binding']['parent_action_requirement_binding']
'''


def test_reference_recipe_scope_preserves_owner_and_alternative_templates():
    observed = run_in_scorer_environment(f'''
import json
{projected_148_case()}
from execution_alignment_resolution_20261024_v1.parameter_route_role_scope_v1 import recipe_scope
shared = parent['shared_material_route_bindings'][2]
proof, error = recipe_scope._reference_action_scope(shared, parent, case['protocol'])
print(json.dumps({{'proof': proof, 'error': error}}))
''')
    assert observed['error'] is None
    assert observed['proof']['actual_parent_ids'] == ['R017', 'R018']
    assert set(observed['proof']['reference_operation_ids']) == {'C18:HALF_R', 'C18:R'}
    assert observed['proof']['missing_component_can_be_scored'] is True


def test_reference_recipe_scope_rejects_changed_actual_identity():
    observed = run_in_scorer_environment(f'''
import copy, json
{projected_148_case()}
from execution_alignment_resolution_20261024_v1.parameter_route_role_scope_v1 import recipe_scope
changed = copy.deepcopy(parent)
for mapping in changed['operation_mappings']:
    if mapping['operation_id'] in ('R017', 'R018'):
        mapping['typed']['primary_identity'] = 'source_medium:CUBIC2015:R1'
shared = changed['shared_material_route_bindings'][2]
proof, error = recipe_scope._reference_action_scope(shared, changed, case['protocol'])
print(json.dumps({{'proof': proof, 'error': error}}))
''')
    assert observed['proof'] is None


def test_operation_variants_preserve_half_and_full_requirements():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_operation_variant_scope_v1 import apply as variants
{projected_148_case()}
request = C.read(root / 'parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/request.json')
out = variants.apply(prepared['binding'], case['protocol'], request['original_slot_manifest'])
original = {{item['id']: item['criterion'] for item in prepared['binding']['original_full_fine_item_ledger']}}
choices = []
for world in out['worlds']:
    assignment = world['reference_operation_variant_assignment']
    choices.append([assignment[parent]['reference_operation_id'] for parent in ('R017', 'R018')])
    for unit in world['units']:
        if unit['parent_operation_id'] in ('R017', 'R018'):
            slots = [s for s in world['slots'] if s.get('execution_unit_binding', {{}}).get('unit_id') == unit['unit_id']]
            rid = assignment[unit['parent_operation_id']]['reference_operation_id']
            dilution = [s for s in slots if s['dimension'] == 'concentration']
            assert len(dilution) == int(rid == 'C18:HALF_R')
            assert all(s['criterion'] == original[s['original_slot_ids'][0]] for s in slots)
            assert all(s['applicability_proof']['actual_recipe_not_imputed'] for s in slots)
            assert all(s['fine_item_weight'] == 1 for s in slots)
            assert all(s['not_multiplied_by_execution_unit_count'] is False for s in slots)
            for slot in dilution:
                assert slot['applicability_proof']['required_conditional_original_item_ids'] == slot['original_slot_ids']
                assert 'water-diluted' in slot['applicability_proof']['reference_source']['quote']
print(json.dumps({{
    'worlds': len(out['worlds']), 'choices': choices,
    'parent_gaps': [g['reason'] for w in out['worlds'] for g in w['gaps'] if g['reason'] == 'COMPLETE_PARENT_ACTION_REQUIREMENT_SET_NOT_BOUND'],
    'slot_counts': [len(w['slots']) for w in out['worlds']],
    'base_fine_count': len(prepared['binding']['worlds'][0]['slots']),
}}))
''')
    assert observed['worlds'] == 4
    assert sorted(observed['choices']) == [['C18:HALF_R', 'C18:HALF_R'], ['C18:HALF_R', 'C18:R'], ['C18:R', 'C18:HALF_R'], ['C18:R', 'C18:R']]
    assert observed['parent_gaps'] == []
    assert observed['slot_counts'] == [observed['base_fine_count'] + sum(rid == 'C18:HALF_R' for rid in choice) for choice in observed['choices']]


def test_private_rebind_defers_operation_variants_until_they_are_expanded():
    observed = run_in_scorer_environment(f'''
import json
{projected_148_case()}
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import rebind
source = C.read(root / 'parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/execution_scope.json')
projected, proofs = units.project(source, case['protocol'])
out = rebind.rebind(prepared['binding'], projected, case['protocol'])
parents = {{m['operation_id']: m for m in out['parent_action_requirement_binding']['operation_mappings']}}
print(json.dumps({{
    'complete': [w['complete_applicability'] for w in out['worlds']],
    'denominators': [w['denominator'] for w in out['worlds']],
    'parent_gaps': [w['gaps'] for w in out['worlds']],
    'deferred': [parents[oid]['gaps'] for oid in ('R017', 'R018')],
}}))
''')
    assert observed['complete'] == [False]
    assert observed['denominators'] == [None]
    assert observed['deferred'] == [
        ['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES'],
        ['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']]
    assert all(any(gap.get('reason') == 'COMPLETE_PARENT_ACTION_REQUIREMENT_SET_NOT_BOUND'
                   and gap.get('deferred_reference_operation_variants') is True
                   for gap in gaps) for gaps in observed['parent_gaps'])


def test_operation_variant_limit_and_missing_template_cannot_claim_a_denominator():
    observed = run_in_scorer_environment(f'''
import copy, json
{projected_148_case()}
from execution_alignment_resolution_20261024_v1.parameter_operation_variant_scope_v1 import apply as variants
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import rebind
source = C.read(root / 'parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/execution_scope.json')
request = C.read(root / 'parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/request.json')
projected, proofs = units.project(source, case['protocol'])
out = rebind.rebind(prepared['binding'], projected, case['protocol'])
limited = variants.apply(out, case['protocol'], request['original_slot_manifest'], max_template_worlds=3)
missing = copy.deepcopy(out)
missing['parent_action_requirement_binding']['operation_mappings'][-1]['selected_template_operations'] = []
missing = variants.apply(missing, case['protocol'], request['original_slot_manifest'])
print(json.dumps({{
    'limited_status': limited.get('reference_operation_variant_audit', {{}}).get('status'),
    'limited_worlds': [(w['complete_applicability'], w['denominator']) for w in limited['worlds']],
    'missing_status': missing.get('reference_operation_variant_audit', {{}}).get('status'),
    'missing_worlds': [(w['complete_applicability'], w['denominator']) for w in missing['worlds']],
}}))
''')
    assert observed['limited_status'] == 'RESOURCE_LIMIT'
    assert observed['limited_worlds'] == [[False, None]]
    assert observed['missing_status'] == 'INCOMPLETE_REFERENCE_OPERATION_VARIANTS'
    assert observed['missing_worlds'] == [[False, None]]


def test_operation_variants_leave_a_binding_without_deferred_operations_unchanged():
    observed = run_in_scorer_environment('''
import json
from execution_alignment_resolution_20261024_v1.parameter_operation_variant_scope_v1 import apply as variants
binding = {'worlds': [{'complete_applicability': True, 'denominator': 0}],
    'parent_action_requirement_binding': {'operation_mappings': []}}
result = variants.apply(binding, '', {'slots': []})
print(json.dumps({'unchanged': result == binding}))
''')
    assert observed == {'unchanged': True}


def alternative_2019_case():
    return '''
from pathlib import Path
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2019_IMMERSION_L_R_PLUS')
case, source, request = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
parent = C.read(root / 'prepared.json')['binding']['parent_action_requirement_binding']
'''


def test_alternative_cubic_phase_binding_does_not_equate_media():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
{alternative_2019_case()}
row = next(row for row in source['pair']['candidate']['operations'] if row['id'] == 'R017')
proof = units.proof(row, source['pair']['reference']['operations'], case['protocol'], {{'clearing', 'ri_matching'}})
print(json.dumps(proof))
''')
    assert observed['actual_primary_identity'] == 'source_medium:CUBIC2018:R'
    assert set(observed['reference_operation_ids']) == {'C19:HALF_R', 'C19:R:1', 'C19:R:2'}
    assert observed['different_named_medium_not_equated'] is True


def test_alternative_recipe_scope_keeps_source_family_and_science_separate():
    observed = run_in_scorer_environment(f'''
import json
{alternative_2019_case()}
from execution_alignment_resolution_20261024_v1.parameter_route_role_scope_v1 import recipe_scope
shared = next(s for s in parent['shared_material_route_bindings'] if s['original_slot']['subject'] == 'antipyrine')
proof, error = recipe_scope._alternative_recipe_scope(shared, parent, case['protocol'])
print(json.dumps({{'proof': proof, 'error': error}}))
''')
    assert observed['error'] is None
    assert observed['proof']['actual_parent_ids'] == ['R017', 'R018']
    assert set(observed['proof']['reference_operation_ids']) == {'C19:HALF_R', 'C19:R:1', 'C19:R:2'}
    assert observed['proof']['different_named_medium_not_equated'] is True
    assert observed['proof']['scientific_equivalence_or_recipe_identity_claimed'] is False


def test_alternative_scope_rejects_non_cubic_medium():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
{alternative_2019_case()}
row = {{'id': 'NEG', 'source': {{'start': 0, 'end': 14}}, 'raw_text': 'vortex in PBS.', 'operation': 'vortex in PBS.',
    'matching_identity': 'source_medium:PBS', 'operation_role': 'ri_matching', 'execution_status': 'ASSERTED_OPERATION', 'phase': 'RI matching'}}
proof = units.proof(row, source['pair']['reference']['operations'], 'vortex in PBS.', {{'clearing', 'ri_matching'}})
print(json.dumps(proof))
''')
    assert observed is None


def test_alternative_scope_rejects_cross_generation_and_l_media():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
{alternative_2019_case()}
output = {{}}
for label, identity, text in [
    ('R1', 'source_medium:CUBIC2015:R1', 'Immerse in CUBIC-R1 with gentle shaking.'),
    ('L', 'source_medium:CUBIC_L', 'Immerse in CUBIC-L with gentle shaking.'),
    ('R', 'source_medium:CUBIC2018:R', 'Immerse in CUBIC-R with gentle shaking.')]:
    row = {{'id': 'NEG_' + label, 'source': {{'start': 0, 'end': len(text)}}, 'raw_text': text,
        'operation': text, 'matching_identity': identity, 'operation_role': 'ri_matching',
        'execution_status': 'ASSERTED_OPERATION', 'phase': 'RI matching'}}
    proof = units.proof(row, source['pair']['reference']['operations'], text, {{'clearing', 'ri_matching'}})
    output[label] = None if proof is None else {{'references': proof['reference_operation_ids'],
        'different_named_medium_not_equated': proof['different_named_medium_not_equated']}}
print(json.dumps(output))
''')
    assert observed['R1'] is None
    assert observed['L'] is None
    assert observed['R']['different_named_medium_not_equated'] is True
    assert set(observed['R']['references']) == {'C19:HALF_R', 'C19:R:1', 'C19:R:2'}


def test_joint_reference_scope_prepares_alternative_2019_parameter_worlds():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
{alternative_2019_case()}
prepared = joint.prepare(case, source, request)
worlds = prepared.get('binding', {{}}).get('worlds', [])
proofs = prepared.get('binding', {{}}).get('domain', {{}}).get('parameter_private_reference_scope', {{}}).get('proofs', {{}})
print(json.dumps({{
    'status': prepared['status'], 'reason': prepared.get('reason'), 'worlds': len(worlds),
    'complete': sum(w.get('complete_applicability') is True for w in worlds),
    'fine_counts': [len(w.get('slots', [])) for w in worlds],
    'queries': sum(len(r['payload']['queries']) for r in prepared.get('requests', {{}}).values()),
    'alternative_R017': proofs.get('R017', {{}}).get('different_named_medium_not_equated'),
}}))
''')
    assert observed['status'] == 'PREPARED'
    assert observed['worlds'] == 6
    assert observed['complete'] == observed['worlds']
    assert observed['fine_counts'] == [37, 36, 36, 36, 35, 35]
    assert observed['queries'] > 0
    assert observed['alternative_R017'] is True


def test_next_day_reference_cannot_bind_pre_equilibration():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
{alternative_2019_case()}
prepared = joint.prepare(case, source, request)
binding = prepared['binding']
choices = [{{oid: assignment['reference_operation_id'] for oid, assignment in world['reference_operation_variant_assignment'].items()}} for world in binding['worlds']]
for world in binding['worlds']:
    for assignment in world['reference_operation_variant_assignment'].values():
        assert assignment['reference_operation']
        assert assignment['reference_source']['quote']
print(json.dumps({{'choices': choices, 'rejections': binding['reference_operation_variant_audit']['rejections']}}))
''')
    assert len(observed['choices']) == 6
    assert all(choice['R017'] != 'C19:R:2' for choice in observed['choices'])
    assert any(choice['R018'] == 'C19:R:2' for choice in observed['choices'])
    assert any(row['parent'] == 'R017' and row['reference_operation_id'] == 'C19:R:2'
               and row['reason'] == 'REFERENCE_CONTINUATION_REQUIRES_ACTUAL_REPLACEMENT'
               and 'next day' in row['reference_operation'] and '预平衡' in row['actual_operation']
               for row in observed['rejections'])


def test_cubic_preparation_preserves_original_criteria_and_all_reference_items():
    observed = run_in_scorer_environment(f'''
import json
from collections import Counter
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
output = []
for branch, expected_slots in [('CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA', [34, 33, 33, 32]), ('CUBIC_2019_IMMERSION_L_R_PLUS', [37, 36, 36, 36, 35, 35])]:
    root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148' / branch
    case, source, request = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
    prepared = joint.prepare(case, source, request)
    repeated = joint.prepare(case, source, request)
    assert repeated == prepared
    binding = prepared['binding']
    originals = {{item['id']: item['criterion'] for item in binding['original_full_fine_item_ledger']}}
    covered, conditional = set(), set()
    audits = {{row['world_id']: row for row in binding['cubic_route_audit']['world_audits']}}
    assert binding['cubic_route_audit']['status'] == binding['reference_operation_variant_audit']['status'] == 'COMPLETE'
    for index, world in enumerate(binding['worlds']):
        assert world['complete_applicability'] is True
        assert world['denominator'] == expected_slots[index] == len(world['slots'])
        for assignment in world['reference_operation_variant_assignment'].values():
            conditional.update(assignment['conditional_original_item_ids'])
        for slot in world['slots']:
            assert slot['fine_item_weight'] == 1
            assert slot['not_multiplied_by_execution_unit_count'] is (slot['scope_unit'] in ('ROUTE', 'MATERIAL'))
            for origin in slot['original_slot_ids']:
                assert slot['criterion'] == originals[origin]
            covered.update(slot['original_slot_ids'])
        origins = [origin for slot in world['slots'] for origin in slot['original_slot_ids']]
        audit = audits[world['world_id']]
        assert audit['distinct_original_slot_ids'] == sorted(set(origins))
        assert audit['slot_multipliers'] == dict(Counter(origins))
    assert set(originals) <= covered | conditional
    output.append({{'branch': branch, 'worlds': len(binding['worlds']), 'covered': len(covered), 'conditional': len(conditional)}})
print(json.dumps(output))
''')
    assert [row['worlds'] for row in observed] == [4, 6]


def test_apply_typed_preserves_exact_primary_name_proof():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.parameter_route_role_scope_v1 import route_scope_v1 as route
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope')]
parent = C.read(root / 'prepared.json')['binding']['parent_action_requirement_binding']
mapping = next(m for m in parent['operation_mappings'] if m['operation_id'] == 'R003')
evidence = units.proof(mapping['source_row'], source['pair']['reference']['operations'], case['protocol'], {{'clearing', 'ri_matching'}})
row = {{**mapping['source_row'], units.VERSION: evidence,
    'matching_identity': evidence['actual_primary_identity'], 'operation_role': evidence['actual_action_role']}}
typed = units.apply_typed(row, mapping['typed'], case['protocol'])
proof = route.primary_proof({{'source_row': mapping['source_row'], 'typed': typed, 'source_bound': True}}, case['protocol'])
print(json.dumps({{'proof_present': proof is not None, 'rule': typed['primary_medium_proof'].get('rule')}}))
''')
    assert observed['proof_present'] is True
    assert observed['rule'] == 'EXACT_NAME_IN_DIRECT_OPERATING_POSITION'


def test_rejected_reference_projection_leaves_source_unchanged():
    observed = run_in_scorer_environment(f'''
import json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope')]
original = units.phase_sets_v4.bound_phase_set
units.phase_sets_v4.bound_phase_set = lambda row: None
try:
    projected, proofs = units.project(source, case['protocol'])
finally:
    units.phase_sets_v4.bound_phase_set = original
print(json.dumps({{'proofs': proofs, 'unchanged': projected == source}}))
''')
    assert observed == {'proofs': {}, 'unchanged': True}


def test_native_binding_rejects_unexpected_closure():
    observed = run_in_scorer_environment('''
import json
from types import SimpleNamespace
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
def outer():
    marker = None
    def native():
        return marker
    return native
native = outer()
assert native.__closure__ is not None
try:
    units.binding_namespace(SimpleNamespace(compile_binding=native))
except AssertionError as error:
    print(json.dumps({'rejected': str(error)}))
else:
    raise AssertionError('UNEXPECTED_NATIVE_CLOSURE_ACCEPTED')
''')
    assert observed['rejected'] == 'PRIVATE_BINDING_NATIVE_MUST_BE_MODULE_LEVEL'


def test_rejected_148_preparation_is_quarantined_with_unexpanded_operations():
    root = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_scope148')
    prepared = json.loads((root / 'validated_preparation_v1/prepared.json').read_text(encoding='utf-8'))
    parent = prepared['binding']['parent_action_requirement_binding']
    deferred = [mapping['operation_id'] for mapping in parent['operation_mappings']
                if mapping['gaps'] == ['MULTIPLE_DIFFERENT_COMPLETE_FINE_REQUIREMENT_TEMPLATES']]
    assert deferred == ['R017', 'R018']
    assert all(world['complete_applicability'] for world in prepared['binding']['worlds'])
    rejection = json.loads((root / 'INVALIDATION.json').read_text(encoding='utf-8'))
    assert rejection['status'] == 'PREPARATION_REJECTED_MISSING_OPERATION_ITEMS'
    assert rejection['model_score_generated'] is False
    assert rejection['accepted_for_scoring'] is False
    assert rejection['accepted_for_merge'] is False


def test_cached_reference_projection_replays_and_recomputes_original_inputs():
    observed = run_in_scorer_environment('''
import copy, json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope')]
projected, proofs = units.project(source, case['protocol'])
replayed, replayed_proofs = units.project(projected, case['protocol'])
assert replayed == projected and replayed_proofs == proofs
changed = copy.deepcopy(projected)
changed[units.VERSION]['projection_input_rows']['R017']['matching_identity'] = 'source_medium:CUBIC2015:R1'
try:
    units.project(changed, case['protocol'])
except AssertionError as error:
    rejected = str(error)
else:
    raise AssertionError('FORGED_PROJECTION_INPUT_ACCEPTED')
print(json.dumps({'replayed': True, 'proof_count': len(proofs), 'rejected': rejected}))
''')
    assert observed == {'replayed': True, 'proof_count': 6, 'rejected': 'PRIVATE_REFERENCE_SCOPE_PROOFS_CHANGED'}


def test_missing_marker_with_private_membership_fails_closed():
    observed = run_in_scorer_environment('''
import json
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source, request = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
projected, _ = units.project(source, case['protocol'])
stripped = {key: value for key, value in projected.items() if key != units.VERSION}
prepared = joint.prepare(case, stripped, request)
print(json.dumps({'status': prepared['status'],
    'rebind_status': prepared['binding'].get('private_typed_rebind', {}).get('status'),
    'complete': [world['complete_applicability'] for world in prepared['binding']['worlds']],
    'denominators': [world['denominator'] for world in prepared['binding']['worlds']]}))
''')
    assert observed['status'] == 'UNRESOLVED'
    assert observed['rebind_status'] == 'INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE'
    assert observed['complete'] == [False]
    assert observed['denominators'] == [None]


def test_reference_variants_respect_actual_formulation_applicability_decision():
    observed = run_in_scorer_environment(f'''
import copy, json
{projected_148_case()}
from execution_alignment_resolution_20261024_v1.parameter_operation_variant_scope_v1 import apply as variants
request = C.read(root / 'parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA/request.json')
binding = copy.deepcopy(prepared['binding'])
mapping = next(m for m in binding['parent_action_requirement_binding']['operation_mappings'] if m['operation_id'] == 'R017')
binding['actual_formulation_applicability_audit']['proved_parents']['R017'] = {{
    'disposition': 'NOT_AN_ACTUAL_OPERATION_OR_ACTUAL_RECIPE_REQUIREMENT',
    'recipe_expression_proof': {{'actual_parent_id': 'R017'}},
    'complete_source_templates': copy.deepcopy(mapping['selected_template_operations']),
    'fixture': 'NEGATIVE_CONTROL_FOR_PRECEDENCE_NOT_AN_ACTUAL_148_DECISION'}}
out = variants.apply(binding, case['protocol'], request['original_slot_manifest'])
observed = []
for world in out['worlds']:
    rid = world['reference_operation_variant_assignment']['R017']['reference_operation_id']
    dilution = [slot for slot in world['slots'] if slot['dimension'] == 'concentration'
        and slot['execution_unit_binding']['parent_operation_id'] == 'R017']
    observed.append({{'reference': rid, 'dilution': len(dilution),
        'basis': world['reference_operation_variant_assignment']['R017']['applicability_basis']}})
print(json.dumps({{'worlds': observed, 'status': out['reference_operation_variant_audit']['status']}}))
''')
    assert observed['status'] == 'PARTIAL_OTHER_SOURCE_SCOPES_RETAINED'
    assert all(row['dilution'] == 0 for row in observed['worlds'])
    assert all(row['basis'] == 'ACTUAL_FORMULATION_APPLICABILITY_AUDIT' for row in observed['worlds'])


def test_cubic_route_cache_requires_private_proof_coverage():
    observed = run_in_scorer_environment('''
import copy, json
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
from execution_alignment_resolution_20261024_v1.parameter_cubic_route_scope_v1 import apply as cubic_routes
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source, request = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
binding = copy.deepcopy(joint.prepare(case, source, request)['binding'])
binding.pop('private_typed_rebind', None)
binding['domain'].pop('parameter_private_reference_scope', None)
out = cubic_routes.apply(binding, case['protocol'], request['original_slot_manifest'])
print(json.dumps({'status': out['cubic_route_audit']['status'],
    'complete': [world['complete_applicability'] for world in out['worlds']],
    'denominators': [world['denominator'] for world in out['worlds']]}))
''')
    assert observed['status'] == 'INCOMPLETE_PRIVATE_REFERENCE_SCOPE_PROOF_COVERAGE'
    assert observed['complete'] == [False] * 4
    assert observed['denominators'] == [None] * 4


def test_chunked_request_plan_retains_complete_target_and_source_proofs(tmp_path):
    observed = run_in_scorer_environment(f'''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
from execution_alignment_resolution_20261024_v1.runtime import prepare_parameter_reference_scope_v1 as planner
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
source = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
root = Path({str(tmp_path / 'source')!r})
for name in ('case', 'execution_scope', 'request'):
    C.save(root / (name + '.json'), C.read(source / (name + '.json')))
case, scope, request = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
prepared = joint.prepare(case, scope, request)
assert prepared['status'] == 'PREPARED'
C.save(root / 'prepared_parameter.json', prepared)
output = Path({str(tmp_path / 'chunks')!r})
plan = planner.prepare(root, output)
audit = planner.verify_plan(output / 'plan.json')
changed = C.read(plan['schedule'][0]['request'])
changed['payload']['queries'] = changed['payload']['queries'][:-1]
Path(plan['schedule'][0]['request']).write_text(
    json.dumps(changed, ensure_ascii=False, indent=2), encoding='utf-8')
try:
    planner.verify_plan(output / 'plan.json')
except AssertionError:
    rejected = True
else:
    rejected = False
print(json.dumps({{'audit': audit, 'changed_request_rejected': rejected}}))
''')
    audit = observed['audit']
    assert audit['full_target_queries'] == 34
    assert audit['chunk_query_counts'] == [12, 12, 10]
    assert audit['disjoint_complete_query_partition'] is True
    assert audit['source_worlds'] == 4
    assert audit['new_model_calls'] == 0
    assert observed['changed_request_rejected'] is True


def test_actual_declared_dilution_is_required_without_reference_keyword():
    observed = run_in_scorer_environment(f'''
import copy, json
{projected_148_case()}
from execution_alignment_resolution_20261024_v1.parameter_operation_variant_scope_v1 import apply as variants
mapping = next(m for m in parent['operation_mappings'] if m['operation_id'] == 'R017')
decision = {{'disposition': 'REQUIRED_FOR_ACTUAL_DECLARED_DILUTION',
    'recipe_expression_proof': {{'actual_parent_id': 'R017'}},
    'complete_source_templates': copy.deepcopy(mapping['selected_template_operations'])}}
changed = copy.deepcopy(parent)
reference = next(r for r in changed['reference_typed_source_ledger'] if r['operation_id'] == 'C18:HALF_R')
reference['source_row']['operation'] = 'Immerse in 1:1 CUBIC-R at room temperature.'
variant, error = variants.operation_family(mapping, changed, 'C18:HALF_R', case['protocol'], decision)
print(json.dumps({{'error': error, 'required': sorted(variant['required_conditional_items']),
    'conditional': sorted(variant['conditional_original_items']), 'basis': variant['applicability_basis']}}))
''')
    assert observed['error'] is None
    assert observed['required'] == ['C18:HALF_R:concentration:transition_dilution']
    assert observed['conditional'] == []
    assert observed['basis'] == 'ACTUAL_FORMULATION_APPLICABILITY_AUDIT'


def test_cached_private_projection_survives_registered_source_annotation():
    observed = run_in_scorer_environment('''
import copy, json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.scope import explicit_operation_role_v4 as explicit
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope')]
projected, proofs = units.project(source, case['protocol'])
annotated = explicit.project(projected, case['protocol'])
replayed, replayed_proofs = units.project(annotated, case['protocol'])
assert replayed == annotated and replayed_proofs == proofs
changed = copy.deepcopy(annotated)
changed['explicit_operation_source_projection']['facts'] = [{'forged': 'NEGATIVE_CONTROL'}]
try:
    units.project(changed, case['protocol'])
except AssertionError as error:
    rejected = str(error)
else:
    raise AssertionError('FORGED_SOURCE_ANNOTATION_ACCEPTED')
print(json.dumps({'replayed': True, 'rejected': rejected}))
''')
    assert observed == {'replayed': True, 'rejected': 'PRIVATE_REFERENCE_SCOPE_SOURCE_CHANGED'}


def test_cached_variant_worlds_recompute_actual_applicability_decisions():
    observed = run_in_scorer_environment('''
import copy, json
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
from execution_alignment_resolution_20261024_v1.parameter_operation_variant_scope_v1 import apply as variants
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source, request = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope', 'request')]
binding = joint.prepare(case, source, request)['binding']
mapping = next(m for m in binding['parent_action_requirement_binding']['operation_mappings'] if m['operation_id'] == 'R017')
binding['actual_formulation_applicability_audit']['proved_parents']['R017'] = {
    'disposition': 'NOT_AN_ACTUAL_OPERATION_OR_ACTUAL_RECIPE_REQUIREMENT',
    'recipe_expression_proof': {'actual_parent_id': 'R017'},
    'complete_source_templates': copy.deepcopy(mapping['selected_template_operations']),
    'fixture': 'NEGATIVE_CONTROL_FOR_IDEMPOTENT_REEVALUATION'}
out = variants.apply(binding, case['protocol'], request['original_slot_manifest'])
counts = [sum(slot['dimension'] == 'concentration'
    and slot['execution_unit_binding']['parent_operation_id'] == 'R017'
    for slot in world['slots']) for world in out['worlds']]
bases = [world['reference_operation_variant_assignment']['R017']['applicability_basis'] for world in out['worlds']]
print(json.dumps({'counts': counts, 'bases': bases}))
''')
    assert observed['counts'] == [0] * 4
    assert observed['bases'] == ['ACTUAL_FORMULATION_APPLICABILITY_AUDIT'] * 4


def test_projection_snapshots_only_include_phase_complete_members():
    observed = run_in_scorer_environment('''
import json
from execution_alignment_resolution_20261024_v1.parameter_private_reference_scope_v1 import units
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = C.RES.parents[3] / 'deliverables/cleareval_repair_20261025_232451/parameter_remaining/EXPAND_148/CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'
case, source = [C.read(root / (name + '.json')) for name in ('case', 'execution_scope')]
original = units.phase_sets_v4.bound_phase_set
units.phase_sets_v4.bound_phase_set = lambda row: None if row['id'] == 'R017' else original(row)
try:
    projected, proofs = units.project(source, case['protocol'])
finally:
    units.phase_sets_v4.bound_phase_set = original
assert 'R017' not in proofs and proofs
replayed, replayed_proofs = units.project(projected, case['protocol'])
assert replayed == projected and replayed_proofs == proofs
print(json.dumps({'proofs': sorted(proofs), 'replayed': True}))
''')
    assert observed['replayed'] is True
    assert 'R017' not in observed['proofs']


def test_revision_causes_derive_exact_parameter_and_metadata_closures():
    observed = run_in_scorer_environment('''
import json, sys
sys.path.insert(0, 'execution_alignment_resolution_20261024_v1/runtime')
from execution_alignment_resolution_20261024_v1.runtime import apply_common_source_revisions_v4 as merger
parameter = merger.resolve_changed_metrics(['COMPLETE_RECIPE_CARRIER_AND_PHASE_WORLD_SCOPES',
    'ACTUAL_PRIVATE_PARAMETER_CORE_INTERFACE'])
metadata = merger.resolve_changed_metrics(['SOURCE_METADATA_VIEW_PURE_RECIPE_OR_LITERAL_COUNT',
    'CANONICAL_JSON_AND_PROJECTION_REPLAY'])
replay = merger.resolve_changed_metrics(['CANONICAL_JSON_AND_PROJECTION_REPLAY'], [])
print(json.dumps({'parameter': sorted(parameter), 'metadata': sorted(metadata), 'replay': sorted(replay)}))
''')
    assert observed['parameter'] == ['Com', 'IA', 'c_param']
    assert observed['metadata'] == ['Com', 'Eff', 'IA', 'bio_sp', 'bio_sr',
        'cleareval_coverage', 'cleareval_sp_eligible', 's_time']
    assert 'c_param' not in observed['metadata']
    assert observed['replay'] == []


def test_revision_rejects_unknown_or_overbroad_metric_closure():
    observed = run_in_scorer_environment('''
import json, sys
sys.path.insert(0, 'execution_alignment_resolution_20261024_v1/runtime')
from execution_alignment_resolution_20261024_v1.runtime import apply_common_source_revisions_v4 as merger
errors = []
for causes, declared in [(['UNREGISTERED_TEST_CAUSE'], None),
    (['SOURCE_METADATA_VIEW_PURE_RECIPE_OR_LITERAL_COUNT'], ['c_param', 'Com', 'IA']),
    (['SOURCE_METADATA_VIEW_PURE_RECIPE_OR_LITERAL_COUNT'], ['s_time', 'Eff', 'IA']),
    (['ACTUAL_PRIVATE_PARAMETER_CORE_INTERFACE'], ['s_time', 'Eff', 'IA'])]:
    try:
        merger.resolve_changed_metrics(causes, declared)
    except AssertionError as error:
        errors.append(str(error))
    else:
        raise AssertionError('INVALID_REVISION_CLOSURE_ACCEPTED')
try:
    merger.resolve_changed_metrics(None)
except AssertionError as error:
    errors.append(str(error))
print(json.dumps(errors))
''')
    assert observed[0].startswith('UNREGISTERED_REVISION_CAUSE')
    assert observed[1:] == ['REVISION_CAUSE_METRIC_CLOSURE_MISMATCH'] * 3 + ['REVISION_CAUSES_REQUIRED']


def test_revision_code_migration_requires_matching_evidence_pins(tmp_path):
    observed = run_in_scorer_environment(f'''
import json, sys
from pathlib import Path
sys.path.insert(0, 'execution_alignment_resolution_20261024_v1/runtime')
from execution_alignment_resolution_20261024_v1.runtime import apply_common_source_revisions_v4 as merger
root = Path({str(tmp_path)!r})
prior = root / 'prior.py'
current = root / 'current.py'
prior.write_text('VALUE = 1\\n', encoding='utf-8')
current.write_text('VALUE = 2\\n', encoding='utf-8')
before, after = merger.sha(prior), merger.sha(current)
pins = {{str(current): before}}
support = root / 'support.json'
support.write_text(json.dumps({{str(current): after}}), encoding='utf-8')
bad_support = root / 'bad_support.json'
bad_support.write_text(json.dumps({{str(current): before}}), encoding='utf-8')
normal = root / 'normal'
normal.mkdir()
(normal / 'loaded_code_sha256.json').write_text(json.dumps({{str(current): after}}), encoding='utf-8')
bad_normal = root / 'bad_normal'
bad_normal.mkdir()
(bad_normal / 'loaded_code_sha256.json').write_text('{{}}', encoding='utf-8')
migration = {{'path': str(current), 'before_sha256': before, 'after_sha256': after,
    'supporting_pin_files': [str(support)]}}
resolved = merger.resolve_prior_pins(pins, [{{'code_revisions': [migration]}}], [normal])
errors = []
cases = [
    ([{{'code_revisions': [migration]}}, {{'code_revisions': [dict(migration, after_sha256='0' * 64)]}}], [normal]),
    ([{{'code_revisions': [dict(migration, before_sha256='0' * 64)]}}], [normal]),
    ([{{'code_revisions': [dict(migration, after_sha256='0' * 64)]}}], [normal]),
    ([{{'code_revisions': [dict(migration, supporting_pin_files=[str(bad_support)])]}}], [normal]),
    ([{{'code_revisions': [migration]}}], [bad_normal]),
    ([{{}}], [normal]),
]
for selected, roots in cases:
    try:
        merger.resolve_prior_pins(pins, selected, roots)
    except AssertionError as error:
        marker = error.args[0]
        errors.append(marker[0] if isinstance(marker, tuple) else marker)
    else:
        raise AssertionError('INVALID_CODE_MIGRATION_ACCEPTED')
print(json.dumps({{'resolved': resolved[str(current)], 'current_sha256': after,
    'input_pins_unchanged': pins == {{str(current): before}}, 'errors': errors}}))
''')
    assert observed['resolved'] == observed['current_sha256']
    assert observed['input_pins_unchanged'] is True
    assert observed['errors'] == ['CONFLICTING_CODE_REVISION', 'CODE_REVISION_BASELINE_PIN_MISMATCH',
        'CODE_REVISION_CURRENT_PIN_MISMATCH', 'CODE_REVISION_SUPPORT_PIN_MISMATCH',
        'CODE_REVISION_REPLAY_PIN_MISMATCH', 'PRIOR_PIN_CHANGED']


def test_apply148_with_explicit_code_migration_preserves_other_branches(tmp_path):
    observed = run_in_scorer_environment(f'''
import json, sys
from pathlib import Path
sys.path.insert(0, 'execution_alignment_resolution_20261024_v1/runtime')
from execution_alignment_resolution_20261024_v1.runtime import apply_common_source_revisions_v4 as merger
root = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451')
base = root / 'merge_stage1/merged193_v4'
affected = root / 'final_candidate_v1/affected148.json'
output = Path({str(tmp_path / 'merged193')!r})
merger.apply(base, output, affected, [root / 'parameter_scope148/normal_v2'])
summary = merger.read(output / 'summary.json')
before = {{(r['input_id'], r['branch']): r for r in merger.read(base / 'records193.json')}}
after = {{(r['input_id'], r['branch']): r for r in merger.read(output / 'records193.json')}}
code_path = 'C:/ClearEval/ClearEval-runtime-4b42b5a/research/evaluator-research-cycle-20261018/execution_alignment_resolution_20261024_v1/parameter_route_role_scope_v1/recipe_scope.py'
pins = merger.read(output / 'input_and_code_sha256.json')
changed = [sorted(name for name in before[key]['all17'] if before[key]['all17'][name] != after[key]['all17'][name])
    for key in before if key[0] == 'EXPAND_148']
plan = merger.read(output / 'revision_plan.json')
print(json.dumps({{'summary': summary, 'unchanged_191': all(after[key] == value for key, value in before.items() if key[0] != 'EXPAND_148'),
    'changed': changed, 'current_code_pin': pins[str(Path(code_path).resolve())],
    'expected_code_pin': merger.sha(code_path),
    'migration_declared': all(len(row.get('code_revisions', [])) == 1 for row in plan['revisions'])}}))
''')
    assert observed['summary']['status'] == 'PASS'
    assert observed['summary']['reexecuted_branches'] == 2
    assert observed['summary']['retained_unaffected_normal_branches'] == 191
    assert observed['unchanged_191'] is True
    assert observed['changed'] == [['Com', 'IA', 'c_param']] * 2
    assert observed['current_code_pin'] == observed['expected_code_pin']
    assert observed['migration_declared'] is True


def test_actual_review_driver_emits_valid_json_without_model_call():
    observed = run_in_scorer_environment('''
import importlib.util, io, json
from contextlib import redirect_stdout
from pathlib import Path
path = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_scope148/run_actual_v2.py')
spec = importlib.util.spec_from_file_location('_actual148_driver_under_test', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
event = {'event': 'BATCH_START', 'branch': 'TEST', 'input_id': 'NO_MODEL_CALL'}
stream = io.StringIO()
with redirect_stdout(stream):
    module.emit(event)
print(json.dumps(json.loads(stream.getvalue())))
''')
    assert observed == {'event': 'BATCH_START', 'branch': 'TEST', 'input_id': 'NO_MODEL_CALL'}


def test_component40_uses_reference_scope_parameter_and_private_core():
    observed = run_in_scorer_environment('''
import json
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v40 as entry
from execution_alignment_resolution_20261024_v1.parameter_atomic_multisource_v2 import strict_core
from execution_alignment_resolution_20261024_v1.parameter_joint_reference_scope_v1 import normal_candidate as joint
multi = entry.parameter.native_backend.actual_multi_api
closure = dict(zip(multi.consume.__code__.co_freevars, multi.consume.__closure__))
private = closure['template'].cell_contents
binding = strict_core.validate_private(private)
print(json.dumps({
    'actual_reference_backend': entry.parameter.native_backend.actual_native_api.prepare is joint.parameter.native_backend.prepare,
    'observer': binding['observations']['source_file'],
    'core': binding['parameter_component']['source_file'],
    'aggregate_binding': entry.component_evidence.parameter is entry.parameter,
    'consumer_binding': entry.apply_components.__globals__['parameter'] is entry.parameter,
    'final_aggregation_binding': entry.finalize_aggregates.__globals__['component_evidence'] is entry.component_evidence,
    'fallback': binding['global_template_or_core_fallback_allowed']}))
''')
    assert observed['actual_reference_backend'] is True
    assert observed['aggregate_binding'] is True
    assert observed['consumer_binding'] is True
    assert observed['final_aggregation_binding'] is True
    assert observed['fallback'] is False
    assert Path(observed['observer']).parent.name == 'parameter_strict_source_quote_projection_v1'
    assert Path(observed['core']).name == 'review_core_interface_v1.py'


def test_real148_multisource_consume_apply_and_native_revalidation():
    observed = run_in_scorer_environment('''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.runtime import consume_parameter_reference_scope_v1 as consumer
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
root = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_scope148/accepted_v2')
summary = C.read(root / 'summary.json')
assert summary['status'] == 'PASS' and summary['input_id'] == 'EXPAND_148'
assert summary['actual_judge_calls'] == 7 and summary['native_revalidation_passed'] is True
assert summary['full_normal_pipeline_executed'] is False
records = C.read('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/merge_stage1/merged193_v4/records193.json')
output = []
for branch in summary['branches']:
    name = branch['branch']
    source_root = root.parent / 'preparation_v5/source' / name
    case, source, request = [C.read(source_root / (field + '.json')) for field in ('case', 'execution_scope', 'request')]
    prepared = C.read(root / name / 'prepared_parameter.json')
    packet = C.read(root / name / 'packet.json')
    applied = C.read(root / name / 'applied.json')
    assert consumer.API.prepare(case, source, request) == prepared
    checked = consumer.API.revalidate_parameter_graph(applied, case, source, request)
    assert checked['packet']['component'] == packet['component']
    assert checked['packet']['consumer_receipts'] == packet['consumer_receipts']
    assert checked['packet']['atomic_multi_origin_certificate_sha256'] == packet['atomic_multi_origin_certificate_sha256']
    assert checked['packet']['actual_private_core_consumption'] == packet['actual_private_core_consumption']
    record = next(row for row in records if row['input_id'] == 'EXPAND_148' and row['branch'] == name)
    result_path = Path(record['result_path'])
    result_path = result_path if result_path.is_absolute() else C.RES.parent / result_path
    assert C.sha(result_path) == record['result_sha256']
    baseline = C.read(result_path)
    assert all(applied['components'][key] == value for key, value in baseline['components'].items() if key != 'c_param')
    assert applied['aggregates'] == baseline['aggregates']
    assert applied.get('execution_alignment') == baseline.get('execution_alignment')
    assert applied.get('supplementary_components') == baseline.get('supplementary_components')
    assert packet['complete_target_query_coverage'] is True
    assert packet['actual_private_core_consumption']['global_core_fallback_used'] is False
    assert all(world['strict_slots_all_valid'] for world in packet['actual_private_core_consumption']['worlds'])
    assert C.read(root / branch['review_sources']) and C.sha(root / branch['review_sources']) == branch['review_sources_sha256']
    output.append({'branch': name, 'worlds': len(packet['world_observations']),
        'status': packet['component']['status'], 'value': packet['component'].get('value'),
        'bounds': packet['component'].get('bounds'), 'native_revalidated': True})
print(json.dumps(output))
''')
    assert len(observed) == 2
    assert all(row['native_revalidated'] for row in observed)
    assert [row['worlds'] for row in observed] == [4, 6]
    for row in observed:
        assert row['status'] in ('VALID', 'UNKNOWN')
        assert len(row['bounds']) == 2
        assert row['bounds'][0] <= row['bounds'][1]


def test_run42_binds_reference_reviews_by_answer_and_branch():
    observed = run_in_scorer_environment(f'''
import json, sys
sys.path.insert(0, {str(RUNNER)!r})
import run_v42 as runner
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v40 as entry40, component_entry_v39 as entry39
root = runner.REVIEW_ROOT
branches = ['CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA', 'CUBIC_2019_IMMERSION_L_R_PLUS']
checks = []
for branch in branches:
    selected = runner.actual_parameter_review('EXPAND_148', branch)
    expected = runner.C.read(root / branch / 'review_sources.json')
    checks.append(selected == {{'review_sources': expected}}
        and all(branch in origin['review_directory'] for origin in expected[next(iter(expected))]['sources']))
print(json.dumps({{'branch_bindings': checks,
    'new_entry_is_40': runner.RUNNER40.entry is entry40,
    'prior_entry_is_39': runner.RUNNER39.entry is entry39,
    'legacy_preserved': runner.actual_parameter_review('EXPAND_139', 'selected') == runner.prior.actual_parameter_review('EXPAND_139', 'selected')}}))
''')
    assert observed == {'branch_bindings': [True, True], 'new_entry_is_40': True,
        'prior_entry_is_39': True, 'legacy_preserved': True}


def test_run42_full_normal148_scores_and_invariants(tmp_path):
    observed = run_in_scorer_environment(f'''
import copy, json, sys
from pathlib import Path
sys.path.insert(0, {str(RUNNER)!r})
import run_v42 as runner
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v40 as entry
from execution_alignment_resolution_20261024_v1.runtime import aggregate_score_bounds_v3 as aggregates
from execution_alignment_resolution_20261024_v1.runtime.phase_world_operational_scope_v2 import execution as final_ea
C = runner.C
sys.path.insert(0, str(C.RES / 'runtime'))
from execution_alignment_resolution_20261024_v1.runtime import normal_revision_equivalence_v1 as equivalence
output = Path({str(tmp_path / 'normal')!r})
sys.argv = [str(Path({str(RESOLUTION / 'runtime' / 'uniform_normal_runner_v1' / 'run_v42.py')!r})),
    '--ids', 'EXPAND_148', '--output', str(output)]
runner.main()
summary = C.read(output / 'summary.json')
assert summary['status'] == 'PASS' and summary['counts'] == {{'PASS': 2}}
assert summary['new_model_calls'] == summary['new_encoder_calls'] == 0
records = C.read(output / 'records193.json')
baseline_records = C.read('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/merge_stage1/merged193_v4/records193.json')
plan = C.read(C.HERE / 'inventory_v3/plan193.json')
observed = []
for record in records:
    name = record['branch']
    result = C.read(record['result_path'])
    baseline_record = next(row for row in baseline_records if row['input_id'] == 'EXPAND_148' and row['branch'] == name)
    baseline_path = Path(baseline_record['result_path'])
    baseline_path = baseline_path if baseline_path.is_absolute() else C.RES.parent / baseline_path
    baseline = C.read(baseline_path)
    case, source, request = [C.read(Path(record['result_path']).parent / (field + '.json')) for field in ('case', 'execution_scope', 'request')]
    baseline_case = C.read(baseline_path.parent / 'case.json')
    assert C.sha(case['reference']['file']['path']) == C.sha(baseline_case['reference']['file']['path'])
    assert case['reference']['file']['sha256'] == baseline_case['reference']['file']['sha256']
    expected_case = copy.deepcopy(baseline_case)
    expected_case['reference']['file']['path'] = case['reference']['file']['path']
    assert case == expected_case
    assert source == C.read(baseline_path.parent / 'execution_scope.json')
    assert request == C.read(baseline_path.parent / 'request.json')
    assert result['normal_component_composition']['version'] == entry.VERSION
    assert all(result['components'][key] == value for key, value in baseline['components'].items() if key != 'c_param')
    job = next(row for row in plan if row['input_id'] == 'EXPAND_148' and row['branch'] == name)['job']
    bundle = C.read(job['bundle_path']) if job.get('bundle_path') else {{}}
    family_id = bundle.get('spec', {{}}).get('reference_id')
    preparations = [C.read(folder / 'preparation.json') for folder in (Path(record['result_path']).parent, baseline_path.parent)]
    variables = [p['capacity_input'].get('variable_source_operations', []) for p in preparations]
    assert variables[0] == variables[1]
    time_facts = [C.read(folder / 'source_time_facts.json') for folder in (Path(record['result_path']).parent, baseline_path.parent)]
    assert time_facts[0] == time_facts[1]
    prepared = [final_ea.prepare(src, c['protocol'], times, variable_source_operations=variable, family_id=family_id)
        for src, c, times, variable in zip((source, C.read(baseline_path.parent / 'execution_scope.json')),
            (case, baseline_case), time_facts, variables)]
    values, _, namespace, fn, facts = prepared[0]
    old_values, _, old_namespace, old_fn, old_facts = prepared[1]
    assert old_values == values and old_facts == facts
    assert fn is old_fn is namespace.calculate is old_namespace.calculate is final_ea.E.boundary.ORIGINAL_CALCULATE
    assert fn.__globals__['runtime'] is namespace.runtime is old_namespace.runtime
    actual_ea, baseline_ea = result['execution_alignment'], baseline['execution_alignment']
    actual_receipt = actual_ea['private_ea_execution_receipt']
    baseline_receipt = baseline_ea['private_ea_execution_receipt']
    assert facts == actual_receipt['final_callable_binding']
    assert actual_receipt['canonical_five_input_sha256'] == baseline_receipt['canonical_five_input_sha256'] == final_ea.E.digest(values)
    assert actual_receipt['input_field_sha256'] == baseline_receipt['input_field_sha256'] == {{key: final_ea.E.digest(value) for key, value in values.items()}}
    assert result['execution_alignment_input_contract']['actual_final_callable_receipt'] == actual_receipt
    carrier_fields = ('phase_operation_carrier_audit', 'phase_operation_carrier_audit_sha256', 'phase_operation_carrier_private_projection')
    assert baseline_receipt['final_callable_binding'] == {{key: value for key, value in facts.items() if key not in carrier_fields}}
    carrier = actual_ea['phase_world_operation_carrier_receipt']
    assert 'phase_world_operation_carrier_receipt' not in baseline_ea
    assert carrier['version'] == final_ea.VERSION and carrier['source_values_unchanged'] is True
    assert carrier['projection_causal_change'] is False and carrier['schema_bound_private_world_projector_used'] is False
    assert carrier['same_original_final_callable_preserved'] is True and facts['phase_operation_carrier_private_projection'] is False
    assert carrier['canonical_five_input_sha256'] == actual_receipt['canonical_five_input_sha256']
    assert carrier['source_sha256'] == actual_receipt['input_field_sha256']['source']
    assert carrier['projection_domain_proof_sha256'] == facts['phase_operation_carrier_audit_sha256'] == C.digest(facts['phase_operation_carrier_audit'])
    pure_results = []
    for packet in (actual_ea, baseline_ea):
        value = copy.deepcopy(packet)
        for key in ('private_ea_execution_receipt', 'ordinary_ea_reuse_receipt', 'phase_world_operation_carrier_receipt'):
            value.pop(key, None)
        pure_results.append(value)
    assert actual_receipt['pure_result_sha256_before_receipt'] == baseline_receipt['pure_result_sha256_before_receipt'] == final_ea.E.digest(pure_results[0])
    assert equivalence.ea_identity(pure_results[0]) == equivalence.ea_identity(pure_results[1])
    def receipt_identity(receipt):
        value = copy.deepcopy(receipt)
        aliases = value['input_normalization'].pop('original_repeated_container_references')
        assert type(aliases) is int and aliases >= 0
        for key in carrier_fields:
            value['final_callable_binding'].pop(key, None)
        for lookup in value['ordinary_cache_admission_proof']['catalog_lookups']:
            count = lookup.pop('internal_prior_issued_plan_entries')
            assert type(count) is int and count >= 0
        return value
    assert receipt_identity(actual_receipt) == receipt_identity(baseline_receipt)
    def reuse_identity(receipt):
        value = copy.deepcopy(receipt)
        assert value['global_cache_context_used'] is False and value['ordinary_17_scores_read_or_reused'] is False
        for lookup in value['catalog_lookups']:
            count = lookup.pop('internal_prior_issued_plan_entries')
            assert type(count) is int and count >= 0
        return value
    assert reuse_identity(actual_ea['ordinary_ea_reuse_receipt']) == reuse_identity(baseline_ea['ordinary_ea_reuse_receipt'])
    expected_supplementary = copy.deepcopy(baseline.get('supplementary_components'))
    for metric in ('ea_p', 'ea_r', 'ea_f1'):
        expected_supplementary[metric]['metric_version'] = entry.source_entry.VERSION
    assert result.get('supplementary_components') == expected_supplementary
    assert result['aggregates']['Co'] == baseline['aggregates']['Co']
    assert result['aggregates']['Eff'] == baseline['aggregates']['Eff']
    assert result['components']['c_param']['status'] == 'VALID' and result['components']['c_param']['value'] == 2
    certificates = result['normal_component_aggregate_evidence']['certificates']
    recomputed = aggregates.evaluate(result['components'], certificates=certificates,
        protocol_sha256=case['protocol_sha256'])['aggregates']
    for metric in ('Com', 'IA'):
        assert result['aggregates'][metric] == recomputed[metric]
    for metric in C.sources.METRICS:
        node = result['components'][metric] if metric in result['components'] else result['aggregates'][metric]
        if node['status'] == 'VALID':
            assert type(node.get('value')) in (int, float)
        else:
            assert node['status'] == 'UNKNOWN' and node['complete_bounds_available'] is True
            assert len(node['bounds']) == 2 and node['bounds'][0] <= node['bounds'][1]
    checked = entry.parameter.revalidate_parameter_graph(result, case, source, request)
    assert checked['packet']['component'] == result['components']['c_param']
    assert C.digest(checked['packet']['actual_private_core_consumption']) == result['normal_actual_parameter']['actual_private_core_consumption_sha256']
    packet = C.read(Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_scope148/accepted_v2') / name / 'packet.json')
    assert result['normal_actual_parameter']['atomic_multi_origin_certificate_sha256'] == packet['atomic_multi_origin_certificate_sha256']
    observed.append({{'branch': name, 'c_param': 2, 'all17_bounded': True,
        'Com': {{k: result['aggregates']['Com'].get(k) for k in ('status', 'value', 'bounds')}},
        'IA': {{k: result['aggregates']['IA'].get(k) for k in ('status', 'value', 'bounds')}},
        'aggregate_formula_verified': True}})
print(json.dumps({{'summary': summary, 'observed': observed}}))
''')
    assert observed['summary']['status'] == 'PASS'
    assert len(observed['observed']) == 2
    assert all(row['all17_bounded'] and row['aggregate_formula_verified'] for row in observed['observed'])
    assert all(row['c_param'] == 2 for row in observed['observed'])


def test_component40_prepare_branch_has_valid_context_manager(tmp_path):
    observed = run_in_scorer_environment(f'''
import json
from pathlib import Path
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v40 as entry
from execution_alignment_resolution_20261024_v1.runtime.uniform_normal_runner_v1 import criteria_loader as C
record = next(row for row in C.read(C.HERE / 'inventory_v3/plan193.json')
    if row['input_id'] == 'EXPAND_148' and row['branch'] == 'CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA')
with entry.prepare_branch(record['job'], Path({str(tmp_path / 'provider')!r})) as branch:
    valid = (branch['case']['protocol_sha256'] == record['protocol_sha256']
        and branch['request'] == C.read(record['current_paths']['request']))
print(json.dumps({{'context_manager': valid}}))
''')
    assert observed == {'context_manager': True}
