"""Numerical-only CCE analysis of archived scores and separately labelled pilot scores.

No answer, reference-step, or scientific protocol text is read by this program.
The inventory binding table supplies archived numeric scores and identity flags.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "cce_validation"
BLOCKS = {
    "completeness": {"c_step": 2, "c_param": 3},
    "correctness": {"co_order": 3, "co_method": 2, "co_param": 2, "co_chem": 1},
    "effectiveness": {"s_method": 2.5, "s_label": 6, "s_trans": 3, "s_time": 3},
}
MAXIMA = {k: v for block in BLOCKS.values() for k, v in block.items()}
DIMENSIONS = ("Com", "Cor", "Eff")
SUMMARY_METRICS = (*DIMENSIONS, "IA", "HV")
RAW_METRICS = tuple(MAXIMA)
COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#555555"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "<", ">", "h", "p", "*", "8"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def finite(value):
    return not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value)


def valid_raw(key, value):
    return finite(value) and (-MAXIMA[key] if key == "s_method" else 0) <= value <= MAXIMA[key]


def derive(raw, *, sr=None, legacy=False):
    """Same original parameter/Cor/EGES formulas, without filling missing items."""
    result = {k: float(v) if valid_raw(k, v) else None for k, v in ((k, raw.get(k)) for k in RAW_METRICS)}
    norm = {k: v / MAXIMA[k] if v is not None else None for k, v in result.items()}
    if norm["s_method"] is not None:
        norm["s_method"] = (norm["s_method"] + 1) / 2
    step = norm["c_step"] if legacy else sr
    result["Com"] = 0.4 * step + 0.6 * norm["c_param"] if finite(step) and norm["c_param"] is not None else None
    for dim, block in (("Cor", "correctness"), ("Eff", "effectiveness")):
        values = [norm[k] for k in BLOCKS[block]]
        result[dim] = sum(values) / len(values) if all(v is not None for v in values) else None
    values = [result[k] for k in DIMENSIONS]
    result["IA"] = min(values) if all(v is not None for v in values) else None
    result["HV"] = math.prod(values) if all(v is not None for v in values) else None
    return result


def archive_rows(bindings):
    rows = []
    for b in bindings:
        # Unique, matching archived answer and score identities are a minimum
        # inclusion condition; source settings and evaluator versions remain unknown.
        bound = (b.get("answer_count_for_id") == 1 and b.get("score_count_for_id") == 1
                 and b.get("answer_is_nonempty_text") is True
                 and b.get("score_question_matches_answer") is True
                 and b.get("question_matches_historical") is True)
        raw = b.get("legacy_raw_scores") or {}
        row = {"model": b["model"], "question_id": str(b["question_id"]),
               "question_sha256": b.get("question_sha256"),
               "numeric_scope": "historical_legacy_cstep", "formal_eligible": False,
               "identity_eligible": bound, "answer_hash_recorded_in_score": b.get("score_has_answer_hash", False),
               "family_id": None, **derive(raw, legacy=True)}
        rows.append(row)
    return rows


def project_pilot(data):
    """Retain only numeric fields and identity metadata from a pilot score file."""
    fields = {"answer_id", "model", "question_id", "question_sha256", "answer_sha256", "numeric_scope",
              "formal_eligible", "family_id", "task_family_id", "threshold", "config_hash",
              "score_stem_matches", "reference_status", "step_missing_reason", "score_missing_reasons",
              "sr", "sp", *RAW_METRICS, *SUMMARY_METRICS, "historical_Com"}
    rows = []
    for source in data:
        row = {k: v for k, v in source.items() if k in fields}
        row["question_id"] = str(row["question_id"])
        row["identity_eligible"] = row.get("score_stem_matches") is True
        row.setdefault("numeric_scope", "scope_unspecified")
        row.setdefault("formal_eligible", False)
        # Numerical verification is kept separate from the source-provided scores.
        expected = derive(row, sr=row.get("sr"))
        failures = [k for k in SUMMARY_METRICS if finite(row.get(k)) and finite(expected[k])
                    and not math.isclose(row[k], expected[k], abs_tol=1e-12)]
        row["formula_check"] = "pass" if not failures else "mismatch:" + ",".join(failures)
        if failures:
            row["identity_eligible"] = False
        rows.append(row)
    return rows


def qsort(values):
    return sorted(values, key=lambda q: (0, int(q)) if str(q).isdigit() else (1, str(q)))


def matrix_and_pareto(means, tolerance=1e-12):
    models = list(means)
    matrix = {a: {b: False for b in models} for a in models}
    for a in models:
        for b in models:
            av, bv = [means[a][d] for d in DIMENSIONS], [means[b][d] for d in DIMENSIONS]
            matrix[a][b] = all(x >= y - tolerance for x, y in zip(av, bv)) and any(x > y + tolerance for x, y in zip(av, bv))
    front = [b for b in models if not any(matrix[a][b] for a in models)]
    return matrix, front


def common_summary(rows, models, *, scope, denominator, formal=False):
    evaluated_qids = qsort({str(r['question_id']) for r in rows if r['model'] in models})
    counts = Counter((r["model"], str(r["question_id"])) for r in rows)
    by_model = {m: {} for m in models}
    excluded = Counter()
    for row in rows:
        m, q = row["model"], str(row["question_id"])
        if m not in by_model:
            continue
        if counts[m, q] != 1:
            excluded["duplicate_model_question"] += 1
        elif not row.get("identity_eligible"):
            excluded["identity_or_formula_unverified"] += 1
        elif formal and not row.get("formal_eligible"):
            excluded["formal_eligibility_pending"] += 1
        elif not all(finite(row.get(k)) for k in DIMENSIONS):
            excluded["incomplete_CCE"] += 1
        else:
            by_model[m][q] = row
    common = set.intersection(*(set(v) for v in by_model.values())) if by_model else set()
    # Across-model pairing must use the same original stem identity.
    mismatched = {q for q in common if len({by_model[m][q].get("question_sha256") for m in models}) != 1
                  or any(not by_model[m][q].get("question_sha256") for m in models)}
    common -= mismatched
    excluded["cross_model_question_hash_mismatch"] = len(mismatched)
    common = qsort(common)
    means = {m: {k: math.fsum(by_model[m][q][k] for q in common) / len(common) for k in SUMMARY_METRICS}
             for m in models} if common else {}
    matrix, front = matrix_and_pareto(means)
    summary = {"numeric_scope": scope, "model_cohort": models, "cohort_size": len(models),
               "question_denominator": denominator, "common_question_ids": common,
               "evaluated_question_ids": evaluated_qids,
               "evaluated_question_n": len(evaluated_qids),
               "common_fraction_of_evaluated_questions": len(common) / len(evaluated_qids) if evaluated_qids else 0,
               "common_n": len(common), "common_coverage": len(common) / denominator if denominator else 0,
               "per_model_eligible_n": {m: len(v) for m, v in by_model.items()},
               "excluded_counts": dict(excluded), "means": means,
               "dominance_matrix": matrix, "empirical_nondominated": front,
               "dominance_tolerance": 1e-12,
               "aggregation": "mean of per-question IA=min(Com,Cor,Eff) and HV=Com*Cor*Eff",
               "formal_result": formal and bool(common)}
    return summary, by_model


def family_bootstrap(summary, by_model, repeats, seed):
    common, models = summary["common_question_ids"], summary["model_cohort"]
    result = {"repeats_requested": repeats, "repeats_completed": 0, "seed": seed,
              "unit": "synchronized source family cluster", "confidence_level": 0.95,
              "source_family_count": 0, "status": "pending_no_common_questions"}
    if not common:
        return result, []
    family_ids = {}
    for q in common:
        fs = {by_model[m][q].get("family_id") for m in models}
        if len(fs) != 1 or None in fs or "" in fs:
            result["status"] = "pending_source_family_map_missing_or_inconsistent"
            return result, []
        family_ids[q] = next(iter(fs))
    groups = defaultdict(list)
    for q, f in family_ids.items():
        groups[f].append(q)
    families = sorted(groups)
    rng = np.random.default_rng(seed)
    values = {m: {k: [] for k in SUMMARY_METRICS} for m in models}
    dominant = {a: {b: 0 for b in models} for a in models}
    nondominated = Counter()
    draws = []
    for trial in range(repeats):
        selected = rng.choice(len(families), len(families), replace=True)
        qs = [q for i in selected for q in groups[families[i]]]
        means = {}
        for m in models:
            means[m] = {k: math.fsum(by_model[m][q][k] for q in qs) / len(qs) for k in SUMMARY_METRICS}
            for k in SUMMARY_METRICS:
                values[m][k].append(means[m][k])
            draws.append({"replicate": trial, "model": m, "question_draws": len(qs), **means[m]})
        matrix, front = matrix_and_pareto(means)
        nondominated.update(front)
        for a in models:
            for b in models:
                dominant[a][b] += int(matrix[a][b])
    result.update({"repeats_completed": repeats, "source_family_count": len(families),
                   "source_families": families, "question_to_family": family_ids,
                   "status": "degenerate_single_source_family" if len(families) == 1 else "descriptive_few_source_families" if len(families) < 10 else "completed",
                   "limitations": "Few source families limit inferential interpretation; one family produces identical resamples and uninformative zero-width intervals.",
                   "percentile_intervals": {m: {k: [float(x) for x in np.quantile(values[m][k], [0.025, 0.975])]
                                                for k in SUMMARY_METRICS} for m in models},
                   "nondominance_frequency": {m: nondominated[m] / repeats for m in models},
                   "dominance_frequency": {a: {b: dominant[a][b] / repeats for b in models} for a in models}})
    return result, draws


def coverage_rows(rows, models, denominator, scope):
    metrics = ("sr", "sp", *RAW_METRICS, *SUMMARY_METRICS)
    out = []
    for m in models:
        subset = [r for r in rows if r["model"] == m]
        counts = Counter(r["question_id"] for r in subset)
        for key in metrics:
            valid = [r for r in subset if counts[r["question_id"]] == 1 and finite(r.get(key))]
            bound = [r for r in valid if r.get("identity_eligible")]
            out.append({"numeric_scope": scope, "model": m, "metric": key,
                        "rows_present": len(subset), "valid_numeric_n": len(valid),
                        "identity_eligible_n": len(bound), "question_denominator": denominator,
                        "valid_fraction": len(valid) / denominator,
                        "identity_eligible_fraction": len(bound) / denominator,
                        "available_item_mean": math.fsum(r[key] for r in valid) / len(valid) if valid else None,
                        "mean_note": "available-item descriptive mean; not cross-model common-set comparison"})
    return out


def revised_full_rows(archived, pilot):
    """Full benchmark scaffold; uncomputed revised components remain explicit NA."""
    pilot_index = {(r['model'], r['question_id']): r for r in pilot}
    if len(pilot_index) != len(pilot):
        raise ValueError('Duplicate pilot model/question pairs cannot replace archived rows.')
    result = []
    for old in archived:
        row = {**old, 'historical_Com': old.get('Com'), 'numeric_scope': 'revised_CCE_partial_archived_components',
               'sr': None, 'sp': None, 'Com': None, 'IA': None, 'HV': None,
               'step_missing_reason': 'revised_step_score_not_run', 'formal_eligible': False}
        new = pilot_index.get((old['model'], old['question_id']))
        if new is not None:
            if old.get('question_sha256') != new.get('question_sha256'):
                raise ValueError(f"Pilot/archive question identity mismatch: {old['model']} / {old['question_id']}")
            row.update(new)
        result.append(row)
    archived_pairs = {(r['model'], r['question_id']) for r in archived}
    if set(pilot_index) - archived_pairs:
        raise ValueError('Pilot pairs absent from archive scaffold.')
    return result


def step_controls(path, out, figures):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as f:
        records = list(csv.DictReader(f))
    fields = ['baseline_sr', 'variant_sr', 'delta_sr', 'baseline_sp', 'variant_sp', 'delta_sp']
    for r in records:
        for k in fields:
            r[k] = float(r[k]) if r.get(k) else None
    conditions = list(dict.fromkeys(r['condition'] for r in records))
    base_ids = list(dict.fromkeys(r['base_id'] for r in records))
    summaries = []
    for condition in conditions:
        sub = [r for r in records if r['condition'] == condition]
        summary = {'condition': condition, 'pair_n': len(sub), 'numeric_scope': 'STEP_ONLY',
                   'full_CCE_pairs_completed': sum(r.get('full_pipeline_complete','').lower() == 'true' for r in sub)}
        for metric in ('sr', 'sp'):
            vals = [r['delta_' + metric] for r in sub if finite(r.get('delta_' + metric))]
            summary['mean_delta_' + metric] = math.fsum(vals) / len(vals) if vals else None
            summary['decreased_' + metric + '_n'] = sum(x < -1e-12 for x in vals)
            summary['unchanged_' + metric + '_n'] = sum(abs(x) <= 1e-12 for x in vals)
        summaries.append(summary)
    fig, axes = plt.subplots(2, max(1,len(conditions)), figsize=(9.8,5.2), squeeze=False, constrained_layout=True)
    names = {'necessary_step_deletion':'Step removal', 'necessary_parameter_deletion':'Parameter removal',
             'deterministic_equivalent_representation':'Equivalent numbering'}
    for col, condition in enumerate(conditions):
        for rownum, metric in enumerate(('sr','sp')):
            ax = axes[rownum,col]
            for r in records:
                if r['condition'] != condition:
                    continue
                i = base_ids.index(r['base_id'])
                ax.plot([0,1], [r['baseline_'+metric], r['variant_'+metric]], color=COLORS[i%len(COLORS)],
                        marker=MARKERS[i%len(MARKERS)], label='Q'+r['question_id'])
            ax.set(xticks=[0,1], xticklabels=['Baseline','Edited full text'], ylim=(-.03,1.03), ylabel=metric.upper())
            ax.grid(axis='y', color='#DDDDDD', linewidth=.5)
            if rownum == 0:
                ax.set_title(names.get(condition,condition), fontsize=9)
    axes[0,-1].legend(frameon=False, fontsize=7)
    fig.suptitle('STEP-ONLY paired results: full-text reparse; fresh CCE judge pending\nThree base answers, one source family; semantic applicability review pending',fontsize=9)
    plot_save(fig, figures/'step_only_pairs')
    write_csv(figures/'step_only_pairs.csv', records)
    write_csv(out/'step_only_control_summary.csv', summaries)
    save(out/'step_only_control_summary.json', {'numeric_scope':'STEP_ONLY', 'pairs':len(records),
         'base_answers':len(base_ids), 'summaries':summaries,
         'limitations':'No fresh correctness/EGES/parameter-completeness scores; step matching changes alone do not establish full-pipeline validity.'})
    return [path]


def full_pipeline_controls(path, out, figures):
    """Plot actual matched fresh-pipeline results without changing their eligibility."""
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as f:
        records=list(csv.DictReader(f))
    if not records:
        return []
    if len({r['case_id'] for r in records}) != len(records):
        raise ValueError('Full-pipeline controls contain duplicate cases.')
    if any(r.get('full_pipeline_complete','').lower()!='true' for r in records):
        raise ValueError('The full-pipeline pair file contains incomplete rows.')
    for field in ('judge_config_sha256','step_config_sha256'):
        if len({r.get(field) for r in records})!=1 or not records[0].get(field):
            raise ValueError(f'Full-pipeline controls do not share one explicit {field}.')
    conditions=[c for c in ('necessary_step_deletion','necessary_parameter_deletion',
                           'deterministic_equivalent_representation') if any(r['condition']==c for r in records)]
    base_ids=sorted({r['base_id'] for r in records}, key=lambda b:int(next(r['question_id'] for r in records if r['base_id']==b)))
    condition_names={'necessary_step_deletion':'Step\nremoval','necessary_parameter_deletion':'Parameter\nremoval',
                     'deterministic_equivalent_representation':'Equivalent\nnumbering'}
    plotted=[];summaries=[]
    fig,axes=plt.subplots(2,3,figsize=(10.5,6.0),constrained_layout=True)
    for ax,metric in zip(axes.flat,SUMMARY_METRICS):
        all_deltas=[]
        for x,condition in enumerate(conditions):
            sub=[r for r in records if r['condition']==condition]
            deltas=[]
            for r in sub:
                numeric={key:float(r[key]) if r.get(key) not in (None,'') else None
                         for key in ('baseline_'+metric,'variant_'+metric,'delta_'+metric)}
                a,b,delta=[numeric[k+metric] for k in ('baseline_','variant_','delta_')]
                if all(finite(v) for v in (a,b,delta)):
                    if not math.isclose(b-a,delta,abs_tol=1e-12):
                        raise ValueError(f"Incorrect paired delta: {r['case_id']} / {metric}")
                    i=base_ids.index(r['base_id']);offset=(i-(len(base_ids)-1)/2)*.12
                    ax.scatter(x+offset,delta,color=COLORS[i%len(COLORS)],marker=MARKERS[i%len(MARKERS)],s=40,zorder=3)
                    deltas.append(delta);all_deltas.append(delta)
                plotted.append({**{k:r.get(k) for k in ('case_id','base_id','question_id','condition','judge','numeric_scope','formal_eligible',
                                                        'judge_config_sha256','step_config_sha256','baseline_trial_id','variant_trial_id')},
                                'row_type':'pair','metric':metric,'baseline':a,'variant':b,'delta':delta})
            avg=math.fsum(deltas)/len(deltas) if deltas else None
            if avg is not None:
                ax.plot([x-.24,x+.24],[avg,avg],color='black',linewidth=1.3,zorder=4)
            summaries.append({'condition':condition,'metric':metric,'pairs':len(sub),'finite_pairs':len(deltas),
                              'mean_delta':avg,'numeric_scope':'local_substitute_full_pipeline_development',
                              'formal_eligible':False})
        ax.axhline(0,color='#888888',linestyle='--',linewidth=.7,zorder=1)
        ax.set_xticks(range(len(conditions)),[condition_names[c] for c in conditions])
        ax.set_ylabel('Change in '+metric+' (variant - baseline)')
        ax.set_title(metric,loc='left',fontweight='bold')
        ax.grid(axis='y',color='#DDDDDD',linewidth=.5)
        ax.ticklabel_format(axis='y',style='sci',scilimits=(-2,3))
        low=min(all_deltas+[0]);high=max(all_deltas+[0]);span=high-low
        pad=span*.15 if span else .02
        ax.set_ylim(low-pad,high+pad)
    legend_ax=axes.flat[-1];legend_ax.axis('off')
    from matplotlib.lines import Line2D
    handles=[Line2D([],[],linestyle='',marker=MARKERS[i%len(MARKERS)],color=COLORS[i%len(COLORS)],
                    label='Q'+next(r['question_id'] for r in records if r['base_id']==b)) for i,b in enumerate(base_ids)]
    handles.append(Line2D([],[],color='black',label='Arithmetic mean'))
    legend_ax.legend(handles=handles,loc='upper left',frameon=False,fontsize=8)
    legend_ax.text(0,.44,f"{len(records)} actual pairs / {len(base_ids)} base answers\nFixed paired judge and step configurations\nPoints are paired answer changes.\nEach panel has its own vertical scale.\nNo confidence intervals or formal validation.",
                   transform=legend_ax.transAxes,fontsize=8,va='top',linespacing=1.6)
    fig.suptitle('Development full-pipeline controls: local Qwen3-8B substitute\nFresh full-text extraction and preserved CCE functions; formal eligibility remains false',fontsize=10)
    plot_save(fig,figures/'full_pipeline_controls')
    plotted.extend({'row_type':'mean','metric':r['metric'],'condition':r['condition'],'delta':r['mean_delta'],
                    'finite_pairs':r['finite_pairs'],'numeric_scope':r['numeric_scope'],'formal_eligible':False}
                   for r in summaries)
    write_csv(figures/'full_pipeline_controls.csv',plotted)
    write_csv(out/'full_pipeline_control_plot_summary.csv',summaries)
    save(out/'full_pipeline_control_plot_summary.json',{'source_path':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'pair_n':len(records),'base_answer_n':len(base_ids),'judge_config_sha256':records[0]['judge_config_sha256'],
         'step_config_sha256':records[0]['step_config_sha256'],'numeric_scope':'local_substitute_full_pipeline_development',
         'formal_eligible':False,'summaries':summaries})
    return [path]


def order_conflict_plot(path, out, figures):
    """Separate canonical-order diagnostic; never pool with natural baselines."""
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig',newline='') as f:
        records=list(csv.DictReader(f))
    if not records:
        return []
    records.sort(key=lambda r:int(r['question_id']))
    if len({r['question_id'] for r in records})!=len(records):
        raise ValueError('Duplicate questions in canonical order-pair table.')
    numeric_metrics=('c_param','co_order','co_method','co_param','co_chem','sr','sp','Cor','Eff')
    plotted=[]
    for r in records:
        for flag in ('same_judge_configuration','exact_operation_multiset_preserved','consistent_numbering'):
            if r.get(flag,'').lower()!='true':
                raise ValueError(f'Order diagnostic pairing condition failed: {flag}')
        for prefix in ('baseline_','variant_'):
            for metric in numeric_metrics:
                value=r.get(prefix+metric)
                r[prefix+metric]=float(value) if value not in (None,'') else None
            cp,sr=r[prefix+'c_param'],r[prefix+'sr']
            r[prefix+'Com']=.4*sr+.6*cp/3 if finite(cp) and finite(sr) else None
            values=[r[prefix+k] for k in DIMENSIONS]
            r[prefix+'IA']=min(values) if all(finite(v) for v in values) else None
            r[prefix+'HV']=math.prod(values) if all(finite(v) for v in values) else None
            cor_values=[r[prefix+k] for k in ('co_order','co_method','co_param','co_chem')]
            if all(finite(v) for v in cor_values) and finite(r[prefix+'Cor']):
                co,cm,cp,ch=cor_values
                if not math.isclose((co/3+cm/2+cp/2+ch)/4,r[prefix+'Cor'],abs_tol=1e-12):
                    raise ValueError('Canonical order-pair Cor formula mismatch.')
        for metric in (*numeric_metrics,'Com','IA','HV'):
            a,b=r['baseline_'+metric],r['variant_'+metric]
            delta=b-a if finite(a) and finite(b) else None
            r['delta_'+metric]=delta
            plotted.append({'question_id':r['question_id'],'metric':metric,'baseline':a,'variant':b,'delta':delta,
                            'scope':r['scope'],'formal_eligible':False,
                            'baseline_case_id':r['baseline_case_id'],'variant_case_id':r['variant_case_id'],
                            'baseline_trial_id':r['baseline_trial_id'],'variant_trial_id':r['variant_trial_id'],
                            'source_status':r['source_status'],'source_path':str(path),
                            'value_origin':'derived_from_preserved_numeric_components' if metric in ('Com','IA','HV') else 'paired_order_input_table'})
    fig,axes=plt.subplots(1,2,figsize=(9.2,3.9),constrained_layout=True)
    x=np.arange(len(records));width=.32
    for prefix,label,color,offset in [('baseline_','Canonical baseline',COLORS[0],-.18),('variant_','Reordered variant',COLORS[1],.18)]:
        values=[r[prefix+'co_order'] for r in records]
        axes[0].bar(x+offset,values,width=width,color=color,label=label)
        for index,value in enumerate(values):
            axes[0].text(index+offset,value+.05,f'{value:g}',ha='center',fontsize=8)
    axes[0].set(xticks=x,xticklabels=['Q'+r['question_id'] for r in records],ylabel='co_order (0-3)',ylim=(0,3.45))
    axes[0].set_title('Order-score response',loc='left',fontweight='bold')
    axes[0].legend(frameon=False,fontsize=7,loc='lower left')
    for metric_index,metric in enumerate(SUMMARY_METRICS):
        vals=[]
        for i,r in enumerate(records):
            value=r['delta_'+metric]
            if finite(value):
                offset=(i-(len(records)-1)/2)*.13
                axes[1].scatter(metric_index+offset,value,color=COLORS[i%len(COLORS)],marker=MARKERS[i%len(MARKERS)],
                                s=40,label='Q'+r['question_id'] if metric_index==0 else None,zorder=3)
                vals.append(value)
        if vals:
            axes[1].plot([metric_index-.27,metric_index+.27],[math.fsum(vals)/len(vals)]*2,color='black',linewidth=1.3,zorder=4)
    axes[1].axhline(0,color='#888888',linewidth=.7,linestyle='--')
    axes[1].set_xticks(range(len(SUMMARY_METRICS)),SUMMARY_METRICS)
    deltas=[r['delta_'+metric] for r in records for metric in SUMMARY_METRICS if finite(r['delta_'+metric])]
    low=min(deltas+[0]);high=max(deltas+[0]);pad=(high-low)*.15 if high>low else .02
    axes[1].set(ylabel='Variant - canonical baseline',ylim=(low-pad,high+pad))
    axes[1].set_title('Paired CCE changes (bars = mean)',loc='left',fontweight='bold')
    axes[1].legend(frameon=False,fontsize=7,loc='lower left')
    for ax in axes:
        ax.grid(axis='y',color='#DDDDDD',linewidth=.5);ax.set_axisbelow(True)
    total_observations=sum(int(r['fresh_full_text_evaluations']) for r in records)
    fig.suptitle('Development order-conflict diagnostics: canonicalized baselines\n'+
                 f'{len(records)} pairs from {len(records)} source answers; {total_observations} fresh pipeline observations; expert confirmation pending',fontsize=9)
    plot_save(fig,figures/'canonical_order_diagnostics')
    write_csv(figures/'canonical_order_diagnostics.csv',plotted)
    summary={'scope':'canonicalized_natural_answer_order_diagnostic','formal_eligible':False,
             'source_path':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'pairs':len(records),'fresh_observations':total_observations,
             'derived_formulas':{'Com':'0.4*SR + 0.6*c_param/3','IA':'min(Com,Cor,Eff)','HV':'Com*Cor*Eff'},
             'mean_deltas':{metric:math.fsum(r['delta_'+metric] for r in records)/len(records)
                            if all(finite(r['delta_'+metric]) for r in records) else None for metric in (*numeric_metrics,'Com','IA','HV')},
             'note':'Canonicalized baselines are separate from the original nine natural-answer control pairs; unchanged scores preserve a diagnostic nonresponse, not evidence of validity.'}
    save(out/'canonical_order_diagnostics.json',summary)
    summary_path=path.parent/'paired_order_summary.json'
    return [path]+([summary_path] if summary_path.exists() else [])


def repeat_stability_plot(path, out, figures):
    """Optional E4 plot from actual repeat summaries; no empty-data placeholder."""
    audited=path.parent/'audited_cce_repeat_spread.csv'
    if audited.exists():
        path=audited
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig',newline='') as f:
        records=list(csv.DictReader(f))
    is_audited=path.name=='audited_cce_repeat_spread.csv'
    required=({'case_id','judge','config_hash','metric','observations','finite_n','sd','range'} if is_audited else
              {'case_id','question_id','judge','metric','finite_metric_repeats','sample_sd','range'})
    if records and not required.issubset(records[0]):
        raise ValueError('Unexpected repeat_spread.csv schema; refusing to infer numeric columns.')
    import re
    data=[]
    for r in records:
        count_key='finite_n' if is_audited else 'finite_metric_repeats'
        sd_key='sd' if is_audited else 'sample_sd'
        if r['metric'] not in SUMMARY_METRICS or int(r[count_key])<2:
            continue
        qid=r.get('question_id')
        if qid is None:
            match=re.search(r'(?:^|__)q(\d+)(?:__|$)',r['case_id'])
            if not match:
                raise ValueError('Audited case_id has no recoverable question identifier.')
            qid=match.group(1)
        data.append({**r, 'question_id':str(qid),'finite_metric_repeats':int(r[count_key]),
                     'observations':int(r.get('observations') or r.get('successful_pipeline_repeats') or r[count_key]),
                     'config_hash':r.get('config_hash') or r.get('judge_contract_sha256'),
                     'sample_sd':float(r[sd_key]) if r.get(sd_key) else None,
                     'range':float(r['range']) if r.get('range') else None})
    if not data:
        return [path]
    group=lambda r:(r['case_id'],r['judge'],r['config_hash'])
    cases=list(dict.fromkeys(group(r) for r in data))
    cases.sort(key=lambda key:(0 if 'qwen' in key[1].lower() else 1 if 'llama' in key[1].lower() else 2,
                               int(next(r['question_id'] for r in data if group(r)==key)),key[2] or ''))
    judge_label=lambda judge:'Qwen' if 'qwen' in judge.lower() else 'Llama' if 'llama' in judge.lower() else judge
    labels=[judge_label(judge)+' q'+next(r['question_id'] for r in data if group(r)==case)
            for case in cases for _,judge,_ in [case]]
    if len(labels)!=len(set(labels)):
        labels=[label+' ['+str(case[2])[:6]+']' for label,case in zip(labels,cases)]
    failure_path=path.parent/'scientific_failure_flags.json'
    summary_path=path.parent/'cce_stability_summary.json'
    failure_flags=load(failure_path) if failure_path.exists() else []
    llama_failures=sum('llama' in r.get('judge','').lower() and r.get('extraction_exactly_copies_rubric_example') is True for r in failure_flags)
    llama_observations=sum(max(r['observations'] for r in data if group(r)==case) for case in cases if 'llama' in case[1].lower())
    failure_note=(f'Llama: {llama_failures}/{llama_observations} rubric-copy extraction failures. ' if llama_observations else '')
    failure_note+='Zero variation does not validate accuracy.'
    fig,axes=plt.subplots(1,2,figsize=(10.5,max(4.3,.42*len(cases)+2.1)),constrained_layout=True)
    for ax,field,title in zip(axes,('sample_sd','range'),('Sample standard deviation','Observed range')):
        matrix=np.full((len(cases),len(SUMMARY_METRICS)),np.nan)
        for r in data:
            if finite(r.get(field)):
                matrix[cases.index(group(r)),SUMMARY_METRICS.index(r['metric'])]=r[field]
        maximum=float(np.nanmax(matrix)) if np.isfinite(matrix).any() else 0
        mesh=ax.imshow(np.ma.masked_invalid(matrix),cmap='cividis',vmin=0,vmax=maximum if maximum>0 else 1,aspect='auto')
        ax.set_xticks(range(len(SUMMARY_METRICS)),SUMMARY_METRICS)
        ax.set_yticks(range(len(cases)),labels);ax.set_title(title,fontsize=9)
        for y,case in enumerate(cases):
            for x,metric in enumerate(SUMMARY_METRICS):
                r=next((r for r in data if group(r)==case and r['metric']==metric),None)
                if r is not None and finite(r.get(field)):
                    ax.text(x,y,f"{r[field]:.2g}\n(n={r['finite_metric_repeats']})",ha='center',va='center',
                            color='white' if r[field]<maximum*.5 or maximum==0 else 'black',fontsize=7)
        if maximum>0:
            fig.colorbar(mesh,ax=ax,shrink=.85,label='Normalized score units')
        else:
            ax.set_xlabel('All observed dispersion values = 0')
    independent_answers=len({r['case_id'] for r in data})
    repeat_counts=sorted({max(r['observations'] for r in data if group(r)==case) for case in cases})
    repeat_phrase=(f'{repeat_counts[0]} actual observations each' if len(repeat_counts)==1 else
                   'actual observations per group: '+','.join(map(str,repeat_counts)))
    fig.suptitle('Development repeat stability: local Qwen / Llama substitutes\n'+
                 f'{len(cases)} case/judge groups; {repeat_phrase}; {independent_answers} independent answers\n'+failure_note,fontsize=10)
    plot_save(fig,figures/'local_judge_stability')
    write_csv(figures/'local_judge_stability.csv',data)
    save(out/'local_judge_stability_plot.json',{'source_path':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'case_judge_groups':len(cases),'distinct_question_ids':len({r['question_id'] for r in data}),
         'row_labels':labels,'audited_CCE_source':is_audited,'independent_answers':independent_answers,
         'llama_rubric_copy_extraction_failures':llama_failures,'llama_observations':llama_observations,
         'failure_note':failure_note,'failure_source':str(failure_path) if failure_path.exists() else None,
         'judges':sorted({r['judge'] for r in data}),'numeric_scope':'local_substitute_stability_development','formal_eligible':False})
    return [path]+[p for p in (failure_path,summary_path) if p.exists()]


def dataset_metadata_coverage(out, figures):
    """Read structured category metadata, never inspect question/answer strings."""
    mcq = ROOT/'dataset/MCQ/final/all_mcq_data.jsonl'
    basic = ROOT/'dataset/MCQ/basic_question/class_basic_question_all_in_one.json'
    taxonomy = ROOT/'dataset/MCQ/class_knowledge_point.json'
    qar = ROOT/'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json'
    sources = [p for p in (mcq,basic,taxonomy,qar) if p.exists()]
    rows = []
    metadata = {}
    def count_records(records,dataset,fields,source):
        for field in fields:
            values = Counter(str(r.get(field)) if r.get(field) not in (None,'') else 'MISSING' for r in records)
            for value,n in values.most_common():
                rows.append({'dataset':dataset,'field':field,'value':value,'count':n,'denominator':len(records),
                             'fraction':n/len(records) if records else None,'source_path':str(source),
                             'count_unit':'structured_question_record'})
    if mcq.exists():
        records = []
        with mcq.open(encoding='utf-8-sig') as f:
            for line in f:
                if line.strip():
                    r=json.loads(line)
                    records.append({k:r.get(k) for k in ('question_id','category','knowledge_point','specific')})
        count_records(records,'MCQ final',('category','knowledge_point','specific'),mcq)
        ids=Counter(str(r.get('question_id')) for r in records)
        metadata['mcq_final']={'rows':len(records),'unique_question_ids':len(ids),
                               'duplicate_question_id_groups':sum(n>1 for n in ids.values())}
    if basic.exists():
        records=[]
        def collect(value):
            if isinstance(value,dict):
                if 'basic_question_id' in value:
                    records.append({k:value.get(k) for k in ('basic_question_id','category','knowledge_point','specific')})
                else:
                    for v in value.values():collect(v)
            elif isinstance(value,list):
                for v in value:collect(v)
        data=load(basic);collect(data)
        count_records(records,'MCQ base templates',('category','knowledge_point','specific'),basic)
        metadata['mcq_base']={'structured_rows_with_basic_question_id':len(records),
                              'unstructured_top_level_list_strings':sum(isinstance(v,str) for item in data if isinstance(item,dict)
                              for lst in item.values() if isinstance(lst,list) for v in lst),
                              'note':'Unstructured template text is not classified or combined with structured category counts.'}
    if qar.exists():
        records=[]
        for item in load(qar):
            hierarchy=item.get('tissue_hierarchy_from_tissue_xlsx') or {}
            records.append({k:hierarchy.get(k) for k in ('tissue_inferred','tissue_tier_code','tissue_tier_label')})
        count_records(records,'QAR historical',('tissue_inferred','tissue_tier_code','tissue_tier_label'),qar)
        metadata['qar_historical']={'question_rows':len(records),'dimensions':'Existing tissue and tier labels only; scale is not inferred from prose.'}
    if taxonomy.exists():
        schema=[]
        for version,tree in enumerate(load(taxonomy)):
            if isinstance(tree,dict):
                for field,value in tree.items():
                    if field!='note':
                        schema.append({'schema_entry_index':version,'top_level_domain':field,
                                       'declared_direct_children':len(value) if isinstance(value,dict) else None,
                                       'count_unit':'schema_branch_not_question_count'})
        write_csv(out/'declared_taxonomy_metadata.csv',schema)
        metadata['declared_taxonomy']={'entries':len(load(taxonomy)),
                                      'note':'Alternative schema entries/languages are retained separately and not mapped onto final category, knowledge_point, or specific fields.'}
    write_csv(out/'dataset_coverage.csv',rows)
    save(out/'dataset_coverage_metadata.json',metadata)
    panels=[('MCQ final','category','A  MCQ category'),('MCQ final','knowledge_point','B  MCQ knowledge_point'),
            ('MCQ final','specific','C  MCQ specific'),('QAR historical','tissue_tier_label','D  QAR tissue/scale tier')]
    fig,axes=plt.subplots(2,2,figsize=(12,10),constrained_layout=True)
    from matplotlib.font_manager import FontProperties
    chinese_font_path=Path('C:/Windows/Fonts/msyh.ttc')
    font=FontProperties(fname=str(chinese_font_path),size=7) if chinese_font_path.exists() else FontProperties(size=7)
    plotted=[]
    for ax,(dataset,field,title) in zip(axes.flat,panels):
        selected=[r for r in rows if r['dataset']==dataset and r['field']==field]
        ax.barh(range(len(selected)),[r['count'] for r in selected],color=COLORS[len(plotted)%len(COLORS)])
        ax.set_yticks(range(len(selected)),[r['value'] for r in selected],fontproperties=font)
        ax.invert_yaxis();ax.set_title(title,loc='left',fontsize=9);ax.set_xlabel('Questions')
        ax.grid(axis='x',color='#DDDDDD',linewidth=.5);ax.set_axisbelow(True)
        for i,r in enumerate(selected):
            ax.text(r['count'],i,' '+str(r['count']),va='center',fontsize=6)
        ax.margins(x=.15)
        plotted.extend(selected)
    fig.suptitle('Dataset coverage from original structured metadata\n'+
                 f"MCQ n={metadata.get('mcq_final',{}).get('rows',0)}; QAR n={metadata.get('qar_historical',{}).get('question_rows',0)}; separate denominators and original labels",fontsize=10)
    plot_save(fig,figures/'dataset_category_coverage')
    write_csv(figures/'dataset_category_coverage.csv',plotted)
    return sources


def plot_save(fig, path):
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(Path(path).with_suffix("." + suffix), dpi=300, bbox_inches="tight")
    plt.close(fig)


def projections(summary, name, figures, title):
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4), constrained_layout=True)
    pairs = [("Com", "Cor"), ("Com", "Eff"), ("Cor", "Eff")]
    means = summary["means"]
    for p, (ax, (x, y)) in enumerate(zip(axes, pairs)):
        ax.set(xlabel=x, ylabel=y, xlim=(-0.025, 1.025), ylim=(-0.025, 1.025))
        ax.set_title(chr(65 + p), loc="left", fontweight="bold")
        ax.grid(color="#DDDDDD", linewidth=0.5, zorder=0)
        if not means:
            ax.text(.5, .5, "No common eligible questions\nJoint result pending", ha="center", va="center", transform=ax.transAxes)
        for i, (m, vals) in enumerate(means.items()):
            front = m in summary["empirical_nondominated"]
            ax.scatter(vals[x], vals[y], c=COLORS[i % len(COLORS)], marker=MARKERS[i % len(MARKERS)],
                       s=48 if front else 32, edgecolor="black" if front else "none", linewidth=.6,
                       label=m.removeprefix("openai_"), zorder=3)
    if means:
        axes[-1].legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=6, frameon=False)
    fig.suptitle(title + f"\nCommon n={summary['common_n']}/{summary['evaluated_question_n']} evaluated; full benchmark n={summary['question_denominator']}; frontier determined in 3D", fontsize=9)
    plot_save(fig, figures / name)
    write_csv(figures / (name + ".csv"), [{"model": m, "numeric_scope": summary["numeric_scope"],
              "common_n": summary["common_n"], "nondominated_3d": m in summary["empirical_nondominated"], **v}
              for m, v in means.items()], ["model", "numeric_scope", "common_n", "nondominated_3d", *SUMMARY_METRICS])


def plot_coverage(all_coverage, models, denominator, figures):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8), constrained_layout=True, sharey=True)
    labels = [m.removeprefix("openai_") for m in models]
    rows = []
    for ax, (scope, metric, title, color) in zip(axes, [
        ("historical_legacy_cstep", "IA", "Archived complete CCE (legacy c_step)", COLORS[0]),
        ("development_provisional_archive_linked", "sr", "Development SR coverage", COLORS[1])]):
        subset = [next((r for r in all_coverage if r["model"] == m and r["numeric_scope"] == scope and r["metric"] == metric), None) for m in models]
        counts = [r["identity_eligible_n"] if r else 0 for r in subset]
        ax.barh(range(len(models)), counts, color=color)
        ax.set_yticks(range(len(models)), labels)
        ax.set_xlim(0, denominator * 1.15)
        ax.set_xlabel(f"Answers / {denominator} historical questions")
        ax.set_title(title, fontsize=9)
        ax.grid(axis="x", color="#DDDDDD", linewidth=.5)
        ax.set_axisbelow(True)
        for i, n in enumerate(counts):
            ax.text(n + denominator * .015, i, str(n), va="center", fontsize=7)
            rows.append({"model": models[i], "numeric_scope": scope, "metric": metric, "n": n, "denominator": denominator})
    axes[0].invert_yaxis()
    plot_save(fig, figures / "coverage")
    write_csv(figures / "coverage.csv", rows)


def sensitivity_analysis(files, models, denominator, out, figures):
    rows = []
    identities = {}
    for path in files:
        data = project_pilot(load(path))
        for r in data:
            if not finite(r.get("threshold")):
                continue
            rows.append({"input_file": str(path), **r})
    by_threshold = defaultdict(list)
    for r in rows:
        by_threshold[r["threshold"]].append(r)
        identities.setdefault((r["model"], r["question_id"]), set()).add((r.get("answer_sha256"), r.get("question_sha256")))
    bad_pairs = [list(pair) for pair, value in identities.items() if len(value) != 1]
    per_threshold_sets = {t: {(r['model'], r['question_id']) for r in rr} for t, rr in by_threshold.items()}
    common_pairs = set.intersection(*per_threshold_sets.values()) if per_threshold_sets else set()
    common_pairs -= {tuple(pair) for pair in bad_pairs}
    common_metric_pairs={}
    for metric in ('sr','sp','Com','IA','HV'):
        finite_sets=[]
        for data in by_threshold.values():
            counts=Counter((r['model'],r['question_id']) for r in data)
            finite_sets.append({(r['model'],r['question_id']) for r in data if finite(r.get(metric))
                                and counts[r['model'],r['question_id']]==1})
        common_metric_pairs[metric]=(set.intersection(*finite_sets) & common_pairs) if finite_sets else set()
    summary_rows = []
    for threshold, data in sorted(by_threshold.items()):
        for model in models:
            selected = [r for r in data if r["model"] == model and (r['model'], r['question_id']) in common_pairs]
            for metric in ("sr", "sp", "Com", "IA", "HV"):
                vals = [r[metric] for r in selected if (r['model'],r['question_id']) in common_metric_pairs[metric]]
                if vals:
                    summary_rows.append({"model": model, "threshold": threshold, "metric": metric,
                                         "n": len(vals), "available_item_mean": math.fsum(vals) / len(vals),
                                         "numeric_scope": "development_threshold_sensitivity"})
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2), constrained_layout=True)
    for ax, metric in zip(axes, ("sr", "sp")):
        present = sorted({r["model"] for r in summary_rows if r["metric"] == metric})
        for i, m in enumerate(present):
            sub = sorted([r for r in summary_rows if r["metric"] == metric and r["model"] == m], key=lambda r: r["threshold"])
            ax.plot([r["threshold"] for r in sub], [r["available_item_mean"] for r in sub],
                    marker=MARKERS[i % len(MARKERS)], color=COLORS[i % len(COLORS)], label=m.removeprefix("openai_"))
        ax.set(xlabel="Cosine threshold", ylabel=metric.upper(), ylim=(-.03, 1.03))
        ax.set_xticks([.6, .7, .8])
        ax.grid(color="#DDDDDD", linewidth=.5)
        if not present:
            ax.text(.5, .5, "Threshold inputs pending", transform=ax.transAxes, ha="center")
    if summary_rows:
        axes[-1].legend(fontsize=6, frameon=False, loc="best")
    fig.suptitle("Development threshold sensitivity; no held-out calibration", fontsize=9)
    plot_save(fig, figures / "threshold_sensitivity")
    write_csv(figures / "threshold_sensitivity.csv", summary_rows, ["model", "threshold", "metric", "n", "available_item_mean", "numeric_scope"])
    paired_deltas = []
    base = {(r['model'], r['question_id']): r for r in by_threshold.get(0.7, [])}
    for t, data in sorted(by_threshold.items()):
        for row in data:
            pair = row['model'], row['question_id']
            if pair not in common_pairs or pair not in base:
                continue
            for metric in ('sr', 'sp', 'Com', 'IA', 'HV'):
                if pair not in common_metric_pairs[metric]:
                    continue
                a, b = base[pair].get(metric), row.get(metric)
                paired_deltas.append({'model': pair[0], 'question_id': pair[1], 'threshold': t,
                                      'metric': metric, 'baseline_0_7': a, 'value': b,
                                      'delta_from_0_7': b - a if finite(a) and finite(b) else None})
    write_csv(out / 'threshold_paired_deltas.csv', paired_deltas,
              ['model', 'question_id', 'threshold', 'metric', 'baseline_0_7', 'value', 'delta_from_0_7'])
    save(out / "threshold_sensitivity.json", {"thresholds": sorted(by_threshold), "input_files": [str(p) for p in files],
         "common_answer_pairs_n": len(common_pairs),
         "common_finite_pairs_by_metric":{metric:len(pairs) for metric,pairs in common_metric_pairs.items()},
         "per_threshold_answer_pairs_n": {str(t): len(v) for t,v in per_threshold_sets.items()},
         "cross_threshold_identity_mismatches": bad_pairs, "summaries": summary_rows,
         "status": "descriptive_only" if not bad_pairs else "invalid_identity_mismatch",
         "limitation": "Threshold choice requires development labels and an untouched holdout; these score changes do not validate semantic accuracy."})
    return summary_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=ART / "pilot_per_answer.json")
    parser.add_argument("--inventory", type=Path, default=ART / "inventory" / "cohort_inventory.json")
    parser.add_argument("--bindings", type=Path, default=ART / "inventory" / "answer_score_bindings.json")
    parser.add_argument("--cohort", type=Path, default=ART / "cohort_frozen.json")
    parser.add_argument("--out", type=Path, default=ART / "analysis")
    parser.add_argument("--figures", type=Path, default=ART / "figures")
    parser.add_argument("--question-denominator", type=int, default=253)
    parser.add_argument("--bootstrap-repeats", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--sensitivity-files", type=Path, nargs="*")
    parser.add_argument('--supplement-only',action='store_true',
                        help='Only plot newly available full-pipeline controls and actual repeat summaries')
    parser.add_argument("--exploratory-models", nargs="*", default=["gemini-3-flash", "gemini-3-pro"],
                        help="Prespecified first-route development models; never replaces the fixed main cohort")
    args = parser.parse_args()
    if args.bootstrap_repeats < 1 or args.question_denominator < 1:
        parser.error("Positive repeat and denominator values are required.")
    args.out.mkdir(parents=True, exist_ok=True)
    args.figures.mkdir(parents=True, exist_ok=True)
    if args.supplement_only:
        plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.labelsize':8,
                             'xtick.labelsize':7,'ytick.labelsize':7,'pdf.fonttype':42,
                             'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
        supplemental_inputs=full_pipeline_controls(ART/'controls/full_pipeline_pairs.csv',args.out,args.figures)
        supplemental_inputs+=repeat_stability_plot(ART/'judges/local_stability/repeat_spread.csv',args.out,args.figures)
        supplemental_inputs+=order_conflict_plot(ART/'judges/local_order_conflicts/paired_order_results.csv',args.out,args.figures)
        save(args.out/'supplemental_analysis_run.json',{'command':subprocess_command(),'python':sys.version,
             'executable':sys.executable,'numpy':np.__version__,'matplotlib':matplotlib.__version__,
             'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in supplemental_inputs},
             'main_analysis_recomputed':False,'numeric_scope':'development_local_substitute','formal_eligible':False})
        print(json.dumps({'supplemental_inputs':[str(p) for p in supplemental_inputs],
                          'main_analysis_recomputed':False},indent=2))
        return
    inventory, frozen = load(args.inventory), load(args.cohort)
    models = frozen["models"]
    if len(models) != 13 or set(models) != {r["model"] for r in inventory["models"]}:
        raise ValueError("Frozen full cohort must contain the same 13 archived models as the inventory.")
    archived = archive_rows(load(args.bindings))
    pilot = project_pilot(load(args.pilot)) if args.pilot.exists() else []
    revised = revised_full_rows(archived, pilot)
    unknown = {r["model"] for r in pilot + archived} - set(models)
    if unknown:
        raise ValueError(f"Unknown models outside frozen cohort: {unknown}")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.labelsize": 8,
                         "xtick.labelsize": 7, "ytick.labelsize": 7, "pdf.fonttype": 42,
                         "svg.fonttype": "none", "axes.spines.top": False, "axes.spines.right": False})
    analyses = {}
    configs = [("historical_legacy", archived, models, "historical_legacy_cstep", False),
               ("revised_full_fixed_cohort", revised, models, "revised_CCE_partial_archived_components", False),
               ("pilot_fixed_cohort", pilot, models, "development_provisional_archive_linked", False),
               ("formal_fixed_cohort", pilot, models, "formal_confirmed", True)]
    participating = args.exploratory_models if pilot else []
    if set(participating) - set(models):
        raise ValueError("Exploratory models must belong to the frozen main cohort.")
    if participating:
        configs.append(("pilot_participating_subset", pilot, participating, "development_provisional_archive_linked_subset", False))
    for name, data, cohort, scope, formal in configs:
        summary, index = common_summary(data, cohort, scope=scope, denominator=args.question_denominator, formal=formal)
        boot, draws = family_bootstrap(summary, index, args.bootstrap_repeats, args.seed)
        summary["bootstrap"] = boot
        summary["limitation"] = ("Legacy c_step is not SR; archived evaluator settings are incomplete." if name == "historical_legacy" else
                                 "Source applicability, extraction, and inherited score provenance remain provisional; no formal validation claim.")
        analyses[name] = summary
        save(args.out / (name + ".json"), summary)
        write_csv(args.out / (name + "_means.csv"), [{"model": m, "numeric_scope": scope, "common_n": summary["common_n"], **v} for m, v in summary["means"].items()],
                  ["model", "numeric_scope", "common_n", *SUMMARY_METRICS])
        write_csv(args.out / (name + "_dominance.csv"), [{"dominator": a, "dominated": b, "dominates": value} for a, row in summary["dominance_matrix"].items() for b, value in row.items()],
                  ["dominator", "dominated", "dominates"])
        write_csv(args.out / (name + "_bootstrap_draws.csv"), draws, ["replicate", "model", "question_draws", *SUMMARY_METRICS])
    coverage = coverage_rows(archived, models, args.question_denominator, "historical_legacy_cstep")
    coverage += coverage_rows(pilot, models, args.question_denominator, "development_provisional_archive_linked")
    revised_coverage=coverage_rows(revised,models,args.question_denominator,'revised_CCE_partial_archived_components')
    write_csv(args.out/'revised_component_coverage.csv',revised_coverage)
    write_csv(args.out / "component_coverage.csv", coverage)
    write_csv(args.out / "historical_numeric_rows.csv", archived)
    write_csv(args.out / 'revised_full_numeric_rows.csv',revised)
    save(args.out/'revised_full_numeric_rows.json',revised)
    write_csv(args.out / "pilot_numeric_rows.csv", pilot)
    save(args.out / "joint_summary.json", analyses)
    projections(analyses["historical_legacy"], "historical_legacy_cce_projections", args.figures, "Historical archive only: legacy c_step completeness")
    projections(analyses["formal_fixed_cohort"], "formal_cce_projections", args.figures, "Formal revised CCE: fixed 13-model cohort")
    if "pilot_participating_subset" in analyses:
        projections(analyses["pilot_participating_subset"], "development_cce_projections", args.figures, "Development subset only: provisional SR plus archived scores")
    plot_coverage(coverage, models, args.question_denominator, args.figures)
    files = args.sensitivity_files if args.sensitivity_files is not None else [p for p in [ART/'pilot_t060_per_answer.json', args.pilot, ART/'pilot_t080_per_answer.json'] if p.exists()]
    sensitivity_analysis(files, models, args.question_denominator, args.out, args.figures)
    extra_inputs=step_controls(ART/'controls/step_pairs.csv',args.out,args.figures)
    extra_inputs+=dataset_metadata_coverage(args.out,args.figures)
    extra_inputs+=full_pipeline_controls(ART/'controls/full_pipeline_pairs.csv',args.out,args.figures)
    extra_inputs+=repeat_stability_plot(ART/'judges/local_stability/repeat_spread.csv',args.out,args.figures)
    extra_inputs+=order_conflict_plot(ART/'judges/local_order_conflicts/paired_order_results.csv',args.out,args.figures)
    inputs = [args.inventory, args.bindings, args.cohort, *([args.pilot] if args.pilot.exists() else []), *files,*extra_inputs]
    save(args.out / "analysis_run.json", {"command": subprocess_command(), "python": sys.version, "executable": sys.executable,
         "numpy": np.__version__, "matplotlib": matplotlib.__version__, "platform": platform.platform(),
         "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
         "cohort": models, "seed": args.seed, "bootstrap_repeats": args.bootstrap_repeats,
         "pilot_present": args.pilot.exists(), "formula_mismatches": [r.get("answer_id") for r in pilot if r["formula_check"] != "pass"]})
    lines = ["# CCE numerical analysis", "", "All outputs are separated by numeric scope. Historical legacy c_step scores are not revised SR scores.", ""]
    for name, summary in analyses.items():
        lines.append(f"- {name}: {summary['cohort_size']} models; common questions {summary['common_n']}/{args.question_denominator}; bootstrap {summary['bootstrap']['status']}.")
    lines += ["", "The 13-model cohort is fixed. The participating pilot subset is a separately labelled development description.",
              "Missing components remain missing. IA and HV are computed per answer before averaging. The Pareto frontier is determined in 3D before projection.",
              "A single source family produces degenerate bootstrap resamples; those intervals cannot establish generalization or confidence.",
              "Archived score-to-answer binding lacks original answer hashes and evaluator/evidence settings. No formal revised-CCE claim is supported by these inherited scores.",
              "", "Each figure has SVG, PDF, PNG and a CSV of the plotted data. See analysis_run.json for exact command and input hashes."]
    (args.out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({name: {"common_n": s["common_n"], "models": s["cohort_size"], "bootstrap": s["bootstrap"]["status"]} for name, s in analyses.items()}, indent=2))


def subprocess_command():
    import subprocess
    return subprocess.list2cmdline([sys.executable, *sys.argv])


if __name__ == "__main__":
    main()
