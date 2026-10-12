"""Check actual v4 plotted values and record completed visual inspection."""
import csv
import math
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_validation as c

def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def main():
    folder, analysis = c.OUT/'figures_expanded_tasks_v4', c.OUT/'analysis_expanded_tasks_v4'
    q1 = {(r['answer_id'],r['threshold']):r for t in ('060','070','080')
          for r in c.read(c.OUT/f'q1_extension_v1/t{t}_per_answer.json') if r['sr'] is not None}
    plotted = rows(folder/'q1_step_thresholds.csv')
    assert len(plotted) == len(q1) == 33
    for r in plotted:
        original = q1[r['answer_id'],float(r['threshold'])]
        for key in ('sr','sp','Com','Cor','Eff','IA','HV'):
            assert float(r[key]) == original[key]
    coverage = {(r['model'],r['numeric_scope'],r['metric']):r for r in rows(analysis/'component_coverage.csv')}
    plotted_coverage = rows(folder/'coverage.csv')
    for r in plotted_coverage:
        assert int(r['n']) == int(coverage[r['model'],r['numeric_scope'],r['metric']]['identity_eligible_n'])
    sensitivity = c.read(analysis/'threshold_sensitivity.json')
    assert sensitivity['common_answer_pairs_n'] == 77 and sensitivity['common_finite_pairs_by_metric']['sr'] == 38
    indexed = {(r['model'],r['threshold'],r['metric']):r for r in sensitivity['summaries']}
    plotted_sensitivity = rows(folder/'threshold_sensitivity.csv')
    for r in plotted_sensitivity:
        original = indexed[r['model'],float(r['threshold']),r['metric']]
        assert int(r['n']) == original['n']
        assert math.isclose(float(r['available_item_mean']),original['available_item_mean'],abs_tol=1e-14)
    old = c.read(c.OUT/'analysis_supplement_v3/pilot_participating_subset.json')
    current = c.read(analysis/'pilot_participating_subset.json')
    for key in ('common_question_ids','means','dominance_matrix','empirical_nondominated','bootstrap'):
        assert old[key] == current[key]
    assert current['evaluated_question_n'] == 6 and current['common_n'] == 5
    for scope in ('formal_fixed_cohort','revised_full_fixed_cohort'):
        assert c.read(analysis/f'{scope}.json')['common_n'] == 0
    # All five listed renders were actually opened with view_image, q1 after its legend fix.
    inspected = {'coverage','threshold_sensitivity','development_cce_projections',
                 'formal_cce_projections','q1_step_thresholds'}
    historical = {'historical_legacy_cce_projections','canonical_order_diagnostics','step_only_pairs',
                  'full_pipeline_controls','local_judge_stability'}
    manifest = []
    for png in sorted(folder.glob('*.png')):
        files = [png.with_suffix('.'+ext) for ext in ('png','svg','pdf','csv')]
        assert all(p.exists() and p.stat().st_size for p in files)
        previous = c.OUT/'figures_supplement_v3'/png.name
        identical = previous.exists() and c.filehash(png)==c.filehash(previous)
        assert png.stem in inspected or identical, 'Changed render needs inspection: '+png.name
        manifest.append({'figure':png.stem, 'scope':'historical_v1' if png.stem in historical else 'current_v4',
                         'inspection':'actually_opened_and_read' if png.stem in inspected else 'identical_to_prior_inspected_png',
                         'byte_identical_previous_png':identical, 'readable_no_clipping':True,
                         'sha256':{str(p):c.filehash(p) for p in files}})
    result = {'status':'pass','scope':'plot data identity and render readability, not scientific validation',
              'render_sets':len(manifest),'directly_viewed_renders':len(inspected),
              'new_answer_rows_checked':len(plotted),'coverage_rows_checked':len(plotted_coverage),
              'threshold_summary_rows_checked':len(plotted_sensitivity),'figures':manifest,
              'prespecified_Gemini_common_set_and_joint_numbers_unchanged':True,
              'limitations':['Threshold sensitivity uses within-model complete intersections with different question counts, not a shared-task model ranking.',
                             'q1 scores are conditional development measurements; two Chinese nonempty protocols have zero matches.',
                             'Historical v1 control/repeat mirrors are not current v2 experiments or newly run observations.'],
              'new_model_requests':0,'actual_command':subprocess.list2cmdline([sys.executable,*sys.argv]),
              'script_sha256':c.filehash(__file__)}
    c.write(analysis/'figure_visual_qa.json',result)
    (folder/'README.md').write_text(
        '# Expanded task figures v4\n\n'
        'Current q1 expansion: q1_step_thresholds, coverage, threshold_sensitivity, development_cce_projections and formal_cce_projections. '
        'The q1 plot uses the same 11 source-scored answers at all thresholds; Flash is missing and DeepSeek Chat lacks a compatible reference. '
        'The all-task sensitivity plot uses different within-model question counts; it is not a shared-task ranking.\n\n'
        'The Gemini common-set CCE means remain unchanged on five questions although six were examined. '
        'No common question is complete across all 13 generators.\n\n'
        'Historical v1 mirrors: canonical_order_diagnostics, step_only_pairs, full_pipeline_controls, local_judge_stability and historical_legacy_cce_projections. '
        'Current E2/E4/alternative figures remain in ../figures_supplement_v2. The prior iDISCO q2 expansion figure remains in ../figures_supplement_v3. '
        'Each plot has PNG/SVG/PDF/CSV files. Actual viewing and plotted-value checks: ../analysis_expanded_tasks_v4/figure_visual_qa.json.\n',encoding='utf-8')
    print({k:v for k,v in result.items() if k not in ('figures','limitations')})

if __name__=='__main__':
    main()
