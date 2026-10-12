"""Check plotted rows against actual records; record the completed render inspection."""
from pathlib import Path
import csv
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cce_validation import OUT, read, write, filehash


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    folder = OUT / 'figures_supplement_v2'
    pairs = {p['pair_id']: p for p in read(OUT / 'judges/local_controls_supplement_v2/paired_results.json')}
    plotted = rows(folder / 'controls_supplement_v2.csv')
    assert len(plotted) == 135
    for row in plotted:
        p = pairs[row['pair_id']]
        for key in ['baseline', 'variant', 'delta']:
            assert float(row[key + '_raw']) == p[key + '_' + row['metric']]
        assert float(row['plotted_delta']) == float(row['delta_raw']) / float(row['normalization_divisor'])
    observations = {r['trial_id']: r for r in read(OUT / 'judges/local_stability_supplement_v2/per_observation.json')}
    stability_rows = rows(folder / 'stability_supplement_v2.csv')
    assert len(stability_rows) == 60
    for row in stability_rows:
        original = observations[row['trial_id']]
        assert float(row['score']) == original[row['metric']]
        assert int(row['repeat_index']) == original['repeat_index']
        assert row['judge'] == original['judge']
    alternatives = {p['pair_id']:p for p in read(OUT / 'judges/local_alternative_development/paired_results.json')}
    alternative_rows = rows(folder / 'alternative_development_pairs.csv')
    assert len(alternative_rows) == 30
    for row in alternative_rows:
        p = alternatives[row['pair_id']]
        if p['technical_pipeline_complete']:
            assert float(row['delta_alternative_minus_baseline']) == p['delta_' + row['metric']]
        else:
            assert row['delta_alternative_minus_baseline'] == ''
    # These six renders were actually opened with view_image in this work session.
    inspected = {'reference_version_effects', 'alternative_development_pairs',
                 'controls_supplement_v2', 'stability_supplement_v2',
                 'development_cce_projections', 'threshold_sensitivity'}
    historical = {'canonical_order_diagnostics', 'step_only_pairs',
                  'full_pipeline_controls', 'local_judge_stability'}
    manifest = []
    for png in sorted(folder.glob('*.png')):
        siblings = [png.with_suffix(ext) for ext in ['.png', '.svg', '.pdf', '.csv']]
        assert all(p.exists() and p.stat().st_size for p in siblings)
        old = OUT / 'figures_two_source' / png.name
        unchanged = old.exists() and filehash(old) == filehash(png)
        assert png.stem in inspected or unchanged
        manifest.append({'figure': png.stem,
                         'scope': 'historical_v1_mirror' if png.stem in historical else 'current_analysis_or_coverage',
                         'review_basis': 'opened_and_visually_inspected_in_this_session' if png.stem in inspected else 'byte_identical_png_to_prior_inspected_render',
                         'same_png_as_previous': unchanged,
                         'readable_labels_and_no_clipping': True,
                         'artifact_sha256': {str(p): filehash(p) for p in siblings}})
    result = {'status': 'pass', 'scope': 'plot_data_identity_and_render_readability_not_scientific_validation',
              'control_rows_checked': len(plotted), 'stability_rows_checked': len(stability_rows),
              'alternative_rows_checked': len(alternative_rows), 'render_sets': len(manifest),
              'new_or_changed_renders_directly_inspected': len(inspected),
              'observed_visual_limitations': ['Repeated values intentionally overlap in reference-version scatter; changed counts and CSV preserve the denominator.',
                  'Threshold panels use within-model common questions; model-specific n differs and is not a shared cross-model ranking.',
                  'Llama values are retained development outputs with 6/6 copied-example extraction failures; the figure does not validate extraction.'],
              'figures': manifest, 'new_model_requests': 0,
              'command': f'{sys.executable} scripts/cce_verify_figures_supplement.py'}
    write(OUT / 'analysis_supplement_v2/figure_visual_qa.json', result)
    plot_run = read(folder / 'supplement_plot_run.json')
    plot_run['visual_qa'] = 'passed_render_inspection_and_data_identity'
    plot_run['visual_qa_file'] = str(OUT / 'analysis_supplement_v2/figure_visual_qa.json')
    write(folder / 'supplement_plot_run.json', plot_run)
    print({k: v for k,v in result.items() if k not in ['figures','observed_visual_limitations']})


if __name__ == '__main__':
    main()
