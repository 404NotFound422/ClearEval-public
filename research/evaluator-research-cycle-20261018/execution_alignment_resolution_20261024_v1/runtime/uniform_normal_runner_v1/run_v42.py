"""Replay 148 with reference-bound reviews while retaining other branch contracts."""
from pathlib import Path
import run_v41 as prior
from endpoint_execution import clone_namespace
from execution_alignment_resolution_20261024_v1.runtime import component_entry_v40 as entry40
from execution_alignment_resolution_20261024_v1.runtime.phase_world_operational_scope_v2 import execution as ea_cache_module

C = prior.C
REVIEW_ROOT = Path('C:/ClearEval/deliverables/cleareval_repair_20261025_232451/parameter_scope148/accepted_v2')
REFERENCE_BRANCHES = {
    ('EXPAND_148', 'CUBIC_2018_PROTOCOL_I_MOUSE_L_R_RA'),
    ('EXPAND_148', 'CUBIC_2019_IMMERSION_L_R_PLUS'),
}


def actual_parameter_review(iid, branch):
    if (iid, branch) not in REFERENCE_BRANCHES:
        return prior.actual_parameter_review(iid, branch)
    summary = C.read(REVIEW_ROOT / 'summary.json')
    assert summary['status'] == 'PASS' and summary['input_id'] == iid
    assert summary['native_revalidation_passed'] is True
    assert summary['accepted_for_normal_replay'] is True
    matching = [row for row in summary['branches'] if row['branch'] == branch]
    assert len(matching) == 1
    selected = matching[0]
    assert selected['status'] == 'PASS' and selected['input_id'] == iid
    assert selected['native_revalidation_passed'] is True
    assert selected['accepted_for_normal_replay'] is True
    path = REVIEW_ROOT / selected['review_sources']
    assert C.sha(path) == selected['review_sources_sha256']
    return {'review_sources': C.read(path)}


RUNNER40 = clone_namespace(prior, {
    'entry': entry40,
    'actual_parameter_review': actual_parameter_review,
    'ea_cache_module': ea_cache_module,
})
RUNNER39 = clone_namespace(prior, {'ea_cache_module': ea_cache_module})


def run_record(*args, **kwargs):
    record = args[0] if args else kwargs['record']
    runner = RUNNER40 if (record['input_id'], record['branch']) in REFERENCE_BRANCHES else RUNNER39
    return runner.run_record(*args, **kwargs)


main = clone_namespace(prior, {
    'run_record': run_record,
    'ea_cache_module': ea_cache_module,
}).main


if __name__ == '__main__':
    main()
