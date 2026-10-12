"""Render saved complete-common-task CCE means, keeping the three-dimensional frontier fixed."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cce_plot_four_hour_evidence_v1 as style
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    assert not args.out.exists()
    paths = [args.source / name for name in ['common_joint.json', 'summary.json', 'verification.json']]
    bindings = [style.bind(path) for path in paths]
    common = style.read(paths[0])
    source_summary = style.read(paths[1])
    assert common['common_n'] == source_summary['common_n'] > 0
    means = common['means']
    models = common['model_cohort']
    assert len(models) == 2 and set(means) == set(models)
    frontier = set(common['empirical_nondominated'])
    args.out.mkdir(parents=True)
    fig, axes = plt.subplots(1, 3, figsize=(183 / 25.4, 103 / 25.4))
    fig.subplots_adjust(left=.075, right=.975, bottom=.28, top=.75, wspace=.40)
    rows = []
    for panel, (ax, (xkey, ykey)) in enumerate(zip(axes, [('Com', 'Cor'), ('Com', 'Eff'), ('Cor', 'Eff')])):
        ax.set_title(f'{chr(97 + panel)}  {xkey}–{ykey}', loc='left', fontweight='bold')
        ax.set(xlabel=xkey, ylabel=ykey, xlim=(0, 1), ylim=(0, 1))
        ax.set_xticks([0, .5, 1]); ax.set_yticks([0, .5, 1])
        ax.set_aspect('equal', adjustable='box')
        for i, model in enumerate(models):
            point = means[model]
            ax.scatter(point[xkey], point[ykey], marker=['o', 's'][i], color=style.CATEGORICAL[i],
                       edgecolors='black' if model in frontier else 'none', linewidth=.8, s=35, zorder=3)
            rows.append(dict(panel=chr(97 + panel), model=model, common_n=common['common_n'],
                             x_metric=xkey, y_metric=ykey, x=point[xkey], y=point[ykey], nondominated_3d=model in frontier))
    handles = [Line2D([], [], marker=['o', 's'][i], color='none', markerfacecolor=style.CATEGORICAL[i],
                      markeredgecolor='black' if m in frontier else style.CATEGORICAL[i], markersize=5,
                      label=m.replace('openai_qwen3-', 'Qwen3-').replace('b', 'B')) for i, m in enumerate(models)]
    fig.suptitle('Complete-task CCE comparison after source-record recovery', y=.955, fontsize=9)
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .895), ncol=2, fontsize=8)
    qids = ', '.join(map(str, common['common_question_ids']))
    fig.text(.5, .19, f"Same complete tasks for both generators: {common['common_n']}/5; question IDs: {qids}.", ha='center', fontsize=7)
    fig.text(.5, .135, 'Black outlines identify the same three-dimensional nondominated set in every panel.', ha='center', fontsize=7)
    fig.text(.5, .08, 'Conditional references and exposed tasks; this small cohort does not establish a full-benchmark ranking.', ha='center', fontsize=6.7)
    basename = args.out / 'complete_cce_three_projections'
    for suffix in ['svg', 'pdf', 'png']:
        fig.savefig(basename.with_suffix('.' + suffix), dpi=300)
    plt.close(fig)
    style.csvwrite(args.out / 'figure_data.csv', rows)
    style.csvwrite(args.out / 'model_means.csv', [dict(model=m, nondominated_3d=m in frontier, **means[m]) for m in models])
    assert bindings == [style.bind(path) for path in paths]
    outputs = [style.bind(basename.with_suffix('.' + suffix)) for suffix in ['svg', 'pdf', 'png']]
    (args.out / 'provenance.json').write_text(json.dumps({'inputs': bindings, 'outputs': outputs,
        'script': style.bind(Path(__file__)), 'actual_command': [sys.executable, *sys.argv],
        'new_model_calls': 0, 'scores_recomputed': False, 'frontier_reused_from_3D_common_summary': True}, indent=2), encoding='utf-8')
    caption = f"""# 共同完整题集上的三个CCE投影

两生成模型仅在共同完整题集 {common['common_question_ids']}（{common['common_n']}/5）上计算均值。三个面板展示同一三维点的投影，黑色描边在每个面板都使用同一个三维非支配集合，不逐面板另挑前沿。IA/HV逐题计算后取平均，数值见model_means.csv。

本图是实际完整向量的条件性小队列比较；全部五题的部分信息界另图。开发暴露、来源资格及标签规则零的限制仍在。图中点不代表其余缺项答案，也不构成全库模型排名。

[逐图数据](figure_data.csv) · [五维模型均值](model_means.csv) · [输入、图件哈希及实际命令](provenance.json)
"""
    (args.out / 'CAPTION_zh.md').write_text(caption, encoding='utf-8')
    print(json.dumps({'status': 'rendered', 'common_n': common['common_n'], 'questions': common['common_question_ids'], 'frontier': sorted(frontier), 'out': str(args.out)}))


if __name__ == '__main__':
    main()
