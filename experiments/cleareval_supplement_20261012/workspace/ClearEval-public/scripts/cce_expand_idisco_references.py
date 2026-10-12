"""Freeze a source-reviewed iDISCO+ candidate alongside unchanged v2 branches.

This is an offline collection change, not an expert confirmation or judge run.
"""
from pathlib import Path
import argparse
import copy
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as c


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    args = p.parse_args()
    old_path = c.OUT / 'reference_recovery/supplement_bound/references_supplement_v2.json'
    output = c.OUT / 'reference_recovery/idisco_plus_2016/references_expanded_v3.json'
    old, candidate = c.read(old_path), c.read(args.candidate)
    extra = candidate['references']
    assert len(old['references']) == 4 and len(extra) == 1
    ref = extra[0]
    assert ref['question_ids'] == [2], 'q248 is not task-applicable by default'
    assert ref['human_confirmation'] is None and not ref['formal_eligible']
    assert ref['route_id'] == 'iDISCO+'
    assert all('+' in a or 'plus' in a.lower() for a in ref['route_aliases'])
    assert c.filehash(ref['source_path']) == ref['source_sha256']
    assert ref['steps'] and all(s.get('source_anchor') for s in ref['steps'])
    expanded = copy.deepcopy(old['references']) + copy.deepcopy(extra)
    assert expanded[:4] == old['references']
    value = {
        'schema_version': 'source-extracted-supplement-v3-idisco-extension',
        'references': expanded,
        'formal_eligible': False,
        'scope': 'Development source candidates; expert applicability and completeness pending.',
        'unchanged_v2_branch_ids': [r['reference_id'] for r in old['references']],
        'added_branch_ids': [r['reference_id'] for r in extra],
        'task_scope': 'Clearing / RI matching / storage; upstream labeling is an explicit initial prerequisite.',
        'q248_status': 'iDISCO+ native tdTomato applicability unresolved; excluded from this collection.',
        'inputs': {str(x.resolve()): c.filehash(x) for x in (old_path, args.candidate)},
    }
    if output.exists():
        assert c.read(output) == value, 'Frozen expanded collection changed; use a new version'
    else:
        c.write(output, value)
    c.write(output.parent / 'expansion_run.json', {
        'command': subprocess.list2cmdline([sys.executable, *sys.argv]),
        'script_sha256': c.filehash(__file__), 'inputs': value['inputs'],
        'output': str(output), 'output_sha256': c.filehash(output),
        'old_references_deep_equal': expanded[:4] == old['references'],
        'reference_branches': len(expanded), 'new_model_requests': 0,
        'human_confirmation': None, 'formal_eligible': False,
    })
    print(json.dumps({'reference_branches': len(expanded), 'new_model_requests': 0,
                      'old_branches_unchanged': True, 'output': str(output)}))


if __name__ == '__main__':
    main()
