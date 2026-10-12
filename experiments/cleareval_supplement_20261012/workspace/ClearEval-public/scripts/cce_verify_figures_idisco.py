"""Check expanded-reference plotted data and record actual render inspection."""
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
    folder, analysis = c.OUT / 'figures_supplement_v3', c.OUT / 'analysis_supplement_v3'
    pairs = {(r['answer_id'], r['threshold']): r for r in c.read(analysis / 'new_idisco_answers.json')}
    plotted = rows(folder / 'idisco_reference_expansion.csv')
    assert len(plotted) == len(pairs) == 21
    for r in plotted:
        source = pairs[r['answer_id'], float(r['threshold'])]
        for k in ('sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV'):
            assert float(r[k]) == source[k]
    summary = c.read(analysis / 'reference_expansion_summary.json')
    assert all(r['previous_numeric'] == 20 and r['current_numeric'] == 27 and r['newly_numeric'] == 7
               and r['old_numeric_metrics_exactly_unchanged'] for r in summary['thresholds'])
    coverage = {(r['model'], r['numeric_scope'], r['metric']): r
                for r in rows(analysis / 'component_coverage.csv')}
    plotted_coverage = rows(folder / 'coverage.csv')
    for row in plotted_coverage:
        source = coverage[row['model'], row['numeric_scope'], row['metric']]
        assert int(row['n']) == int(source['identity_eligible_n'])
    sensitivity = c.read(analysis / 'threshold_sensitivity.json')
    indexed = {(r['model'], r['threshold'], r['metric']): r for r in sensitivity['summaries']}
    plotted_sensitivity = rows(folder / 'threshold_sensitivity.csv')
    for row in plotted_sensitivity:
        source = indexed[row['model'], float(row['threshold']), row['metric']]
        assert int(row['n']) == source['n']
        assert math.isclose(float(row['available_item_mean']), source['available_item_mean'], abs_tol=1e-14)
    # These three PNGs were opened with view_image, including the final legend fix.
    inspected = {'idisco_reference_expansion', 'coverage', 'threshold_sensitivity'}
    historical = {'historical_legacy_cce_projections', 'canonical_order_diagnostics',
                  'step_only_pairs', 'full_pipeline_controls', 'local_judge_stability'}
    manifest = []
    for png in sorted(folder.glob('*.png')):
        siblings = [png.with_suffix('.' + ext) for ext in ('png', 'svg', 'pdf', 'csv')]
        assert all(x.exists() and x.stat().st_size > 0 for x in siblings)
        previous = c.OUT / 'figures_supplement_v2' / png.name
        identical = previous.exists() and c.filehash(previous) == c.filehash(png)
        assert png.stem in inspected or identical, 'A changed render needs inspection: ' + png.stem
        manifest.append({'figure': png.stem, 'scope': 'historical_v1' if png.stem in historical else 'current_v3',
            'inspection': 'actually_opened_and_read' if png.stem in inspected else 'identical_to_prior_inspected_png',
            'byte_identical_previous_png': identical, 'readable_no_clipping': True,
            'sha256': {str(x): c.filehash(x) for x in siblings}})
    result = {'status': 'pass', 'scope': 'plot_identity_and_render_readability_not_scientific_validation',
        'render_sets': len(manifest), 'directly_viewed_renders': len(inspected),
        'new_answer_rows_checked': len(plotted), 'coverage_rows_checked': len(plotted_coverage),
        'threshold_summary_rows_checked': len(plotted_sensitivity),
        'figures': manifest, 'new_model_requests': 0,
        'limitations': ['Within-model threshold intersections have different task counts; lines are not a common-set model ranking.',
                       'The two Chinese q2 answers have operations but zero English-baseline matches at all three thresholds.',
                       'Unchanged historical figure mirrors are not new control or judge experiments.'],
        'command': subprocess.list2cmdline([sys.executable, *sys.argv]),
        'script_sha256': c.filehash(__file__)}
    c.write(analysis / 'figure_visual_qa.json', result)
    print({k: v for k, v in result.items() if k not in ('figures', 'limitations')})


if __name__ == '__main__':
    main()
