"""Check the completed delivery navigation and save a bounded artifact manifest."""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'
OUT = R3 / 'delivery_completed_01'


def binding(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size}


docs = [
    OUT / 'README_zh.md', OUT / 'commands.md', R3 / 'STATUS.md', ROOT.parent / 'STATUS.md',
    R3 / 'FIGURES_CURRENT.md', R3 / 'E2_canonical_readout_complete_01/REPORT_zh.md',
    R3 / 'confirmation_readout_complete_01/REPORT_zh.md',
    R3 / 'problem_cycles/CURRENT_RESEARCH_INTERPRETATION_zh.md',
    R3 / 'delivery_draft/METHODS_EN.md', R3 / 'delivery_draft/RESULTS_ESTABLISHED_EN.md',
    R3 / 'delivery_draft/RESULTS_E2_COMPLETED_EN.md',
    R3 / 'delivery_draft/RESULTS_CONFIRMATION_COMPLETED_EN.md',
    R3 / 'delivery_draft/ABSTRACT_SUPPLEMENT_EN.md',
    R3 / 'delivery_draft/GAPS_COMPLETION_ADDENDUM_zh.md',
    R3 / 'confirmation_secondary_v4_01/README_zh.md',
    R3 / 'confirmation_diagnostics_01/step_matching_snapshot/REPORT_zh.md']
data_names = [
    'E2_canonical_readout_complete_01/summary.json',
    'E2_canonical_readout_complete_01/paired_results.json',
    'E2_canonical_readout_complete_01/repeatability.json',
    'E2_canonical_readout_complete_01/task_cluster_resampling.json',
    'E2_canonical_secondary_v4_01/summary.json',
    'confirmation_readout_complete_01/summary.json',
    'confirmation_readout_complete_01/per_answer.json',
    'confirmation_readout_complete_01/per_answer.csv',
    'confirmation_readout_complete_01/primary_joint.json',
    'confirmation_readout_complete_01/secondary_joint.json',
    'confirmation_readout_complete_01/primary_per_answer_bounds.json',
    'confirmation_readout_complete_01/verification.json',
    'confirmation_secondary_v4_01/summary.json',
    'confirmation_secondary_v4_01/independent_arithmetic_02/review.json',
    'confirmation_secondary_v4_01/independent_arithmetic_02/time_blockers_all8.json',
    'confirmation_readout_v1/actual_independent_review_01/actual_01/REPORT_zh.md',
    'confirmation_diagnostics_01/step_matching_snapshot/evidence.json',
    'problem_cycles/context_capacity_cycle01/confirmation_runtime_audit_01/complete_08/verification.json',
    'delivery_draft/claim_evidence.json', 'delivery_draft/claim_evidence_E2_completed.json',
    'delivery_draft/claim_evidence_confirmation_completed.json',
    'external_dependencies_check_01.json',
    'delivery_completed_01/configuration/resolved_config.yaml',
    'delivery_completed_01/configuration/budget_snapshot.json',
    'delivery_completed_01/configuration/verification.json']
figure_dirs = [('figures_E2_complete_01', 'controlled_validation'),
               ('figures_confirmation_01', 'confirmation_per_answer'),
               ('figures_complete_primary_v6_v7_01', 'complete_cce_three_projections'),
               ('figures_joint_primary_v6_v7_01', 'joint_partial_bounds')]

links, failures = [], []
for doc in docs:
    text = doc.read_text(encoding='utf-8-sig')
    for target in re.findall(r'\]\(([^\n)]+)\)', text):
        target = target.strip('<>')
        if target.startswith(('https://', 'http://', '#', 'app://')):
            continue
        target = target.split('#', 1)[0]
        path = Path(target)
        path = path if path.is_absolute() else doc.parent / path
        path = path.resolve()
        row = {'document': str(doc), 'target': target, 'resolved': str(path), 'exists': path.exists()}
        links.append(row)
        if not row['exists']:
            failures.append(row)
assert not failures, json.dumps(failures, ensure_ascii=True)
files = [*docs, *[R3 / n for n in data_names], Path(__file__)]
for folder, stem in figure_dirs:
    files += [R3 / folder / (stem + '.' + ext) for ext in ['pdf', 'svg', 'png']]
assert all(p.is_file() for p in files)
budget = json.loads((OUT / 'configuration/budget_snapshot.json').read_text())
assert budget['round_attempts'] == 40 and budget['remaining_request_capacity'] == 0
dependencies = json.loads((R3 / 'external_dependencies_check_01.json').read_text())
external_checked = []
for old in dependencies['human_input_bindings'] + [dependencies['wetlab_measurements']]:
    now = binding(Path(old['path']))
    assert now['sha256'] == old['sha256'], 'EXTERNAL_INPUT_CHANGED_RECHECK_COUNTS'
    external_checked.append(now)
manifest = {'created_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'computational_delivery_complete_scientific_requirements_pending',
    'overall_research_goal_complete': False,
    'round_model_calls': 40, 'package_model_calls': 428, 'new_model_calls_by_check': 0,
    'checked_local_links': len(links), 'missing_local_links': 0,
    'links': links, 'files': [binding(p) for p in files],
    'external_inputs_unchanged_at_delivery': external_checked,
    'actual_command': [sys.executable, *sys.argv],
    'interpretation': 'Navigation and artifact identity checks; not scientific validation.'}
target = OUT / 'artifact_manifest.json'
with target.open('x', encoding='utf8') as stream:
    json.dump(manifest, stream, ensure_ascii=False, indent=2)
print(json.dumps({'status': manifest['status'], 'files': len(files), 'checked_local_links': len(links),
                  'missing_local_links': 0, 'new_model_calls': 0}))
