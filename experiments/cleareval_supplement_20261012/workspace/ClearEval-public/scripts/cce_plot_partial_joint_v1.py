"""Plot already-computed CCE bounds without inventing missing point scores."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_plot_four_hour_evidence_v1 as style
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert not args.out.exists(), 'Use a new output directory for a new analysis.'
    paths = [args.source / name for name in ['summary.json', 'per_answer_bounds.json', 'verification.json']]
    bindings = [style.bind(path) for path in paths]
    summary = style.read(paths[0])
    means = summary['mean_bounds']
    models = summary['fixed_models']
    assert len(models) == 2
    assert all(summary['identified_nondominance'][m]['guaranteed_nondominated'] for m in models)
    args.out.mkdir(parents=True)
    fig, axes = plt.subplots(1, 3, figsize=(183 / 25.4, 111 / 25.4))
    fig.subplots_adjust(left=.075, right=.975, bottom=.31, top=.76, wspace=.40)
    dimensions = [('Com', 'Cor'), ('Com', 'Eff'), ('Cor', 'Eff')]
    colors = [style.CATEGORICAL[0], style.CATEGORICAL[1]]
    rows = []
    for panel, (ax, (xkey, ykey)) in enumerate(zip(axes, dimensions)):
        ax.set_title(f'{chr(97 + panel)}  {xkey}–{ykey}', loc='left', fontweight='bold')
        ax.set(xlabel=xkey, ylabel=ykey, xlim=(0, 1), ylim=(0, 1))
        ax.set_xticks([0, .5, 1]); ax.set_yticks([0, .5, 1])
        ax.set_aspect('equal', adjustable='box')
        for index, model in enumerate(models):
            xlow, xhigh = means[model][xkey]
            ylow, yhigh = means[model][ykey]
            assert xlow == xhigh
            if ylow == yhigh:
                ax.scatter(xlow, ylow, s=29, marker=['o', 's'][index], color=colors[index], zorder=3)
            else:
                # No midpoint is shown: only attainable-range outer boundaries.
                ax.plot([xlow, xlow], [ylow, yhigh], color=colors[index], lw=2)
                ax.plot([xlow - .018, xlow + .018], [ylow, ylow], color=colors[index], lw=1)
                ax.plot([xlow - .018, xlow + .018], [yhigh, yhigh], color=colors[index], lw=1)
            rows.append(dict(panel=chr(97 + panel), model=model, x_metric=xkey, y_metric=ykey,
                             x_lower=xlow, x_upper=xhigh, y_lower=ylow, y_upper=yhigh))
    labels = [model.replace('openai_qwen3-', 'Qwen3-').upper().replace('QWEN', 'Qwen') for model in models]
    handles = [Line2D([], [], marker=shape, color=color, linewidth=1.5, label=label, markersize=4)
               for shape, color, label in zip(['o', 's'], colors, labels)]
    fig.suptitle('Five-task secondary cohort: known trade-off and partial CCE bounds', y=.955, fontsize=9)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .895), ncol=2, fontsize=8)
    fig.text(.5, .225, 'Both models are guaranteed incomparable in this two-model cohort by Com and Cor alone.',
             ha='center', fontsize=7)
    fig.text(.5, .177, 'Eff bars are deterministic outer bounds from missing components, not confidence intervals.',
             ha='center', fontsize=7)
    fig.text(.5, .129, 'All 10 original answers retained; no midpoint, replacement score, or complete-CCE frontier is drawn.',
             ha='center', fontsize=7)
    fig.text(.5, .081,
             f"Original complete CCE: {summary['original_complete_CCE']}/10; complete common tasks: "
             f"{summary['original_complete_common_n']}/5. Conditional references; tasks exposed during development.",
             ha='center', fontsize=6.7)
    style.export(fig, args.out, 'partial_cce_three_projections')
    style.csvwrite(args.out / 'figure_data.csv', rows)
    assert bindings == [style.bind(path) for path in paths]
    style.write(args.out / 'provenance.json', dict(inputs=bindings, script=style.bind(Path(__file__)),
        style_module=style.bind(Path(style.__file__)), actual_command=[sys.executable, *sys.argv],
        original_scores_changed=False, new_model_requests=0, new_embeddings=0,
        print_width_mm=183, minimum_text_pt=6.7, formats=['PDF', 'SVG', 'PNG'], visual_review='pending'))
    (args.out / 'CAPTION_zh.md').write_text(
        '# 固定五题的部分联合信息\n\n'
        '同五题、同两生成器的Com和Cor均为真实已保存值；Eff未知分项按其原定义域形成外界。'
        '图a为已知均值，图b/c仅画区间端点及连接线，不画缺失Eff的点估计。两个模型的Com和Cor方向相反，'
        '所以无论未知Eff取何允许值，二者在本两模型队列中都不能支配对方。该判断不依赖Eff中点或缺失值补零。\n\n'
        '这些区间不是置信区间，也不是已完成CCE的帕累托图；分项之间可能存在未表达的依赖，'
        '故区间仅为外界。本图是开发暴露材料上的条件性、后验诊断，不替代原共同完整题集分析。'
        '逐题IA/HV区间先按原公式计算再平均，另存源表；不由图中的均值向量反推。\n', encoding='utf8')
    print(json.dumps(dict(status='rendered', out=str(args.out), points_imputed=0, figure_rows=len(rows))))


if __name__ == '__main__':
    main()
