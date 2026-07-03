"""Three-panel (all-violin, single row) failure-localization figure for ClearEval (Sec. 4.4).

Panel a: Effectiveness sub-score distributions (S_method, S_label, S_trans, S_time), all protocols.
Panel b: per-model S_label distribution (13 models) -- the labeling-failure mass sits at 0.
Panel c: per-model S_time distribution (13 models, same order as b).

Macaron palette (S_label rose #F8B7C5, S_time sky #A8DADC) + Nature-style formatting.
Run:  python article/BIBM/figures/gen_failure_localization.py
"""
import json
import glob
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
RESULT = os.path.join(ROOT, 'dataset', 'Q+AR', 'result')

matplotlib.rcParams.update({
    'font.size': 9, 'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
    'mathtext.fontset': 'dejavusans',
    'axes.labelsize': 9, 'xtick.labelsize': 7.5, 'ytick.labelsize': 8, 'legend.fontsize': 8,
    'figure.dpi': 400, 'savefig.dpi': 400, 'savefig.bbox': 'tight', 'savefig.pad_inches': 0.03,
    'axes.grid': False, 'axes.spines.top': False, 'axes.spines.right': False,
    'axes.linewidth': 0.6, 'xtick.major.width': 0.6, 'ytick.major.width': 0.6,
    'pdf.fonttype': 42, 'ps.fonttype': 42,
})

DISPLAY = {
    'openai_gpt-5.2-fast': 'GPT-5.2-Fast', 'openai_gpt-5.2-thinking': 'GPT-5.2-Think',
    'gemini-3-flash': 'Gemini-3-Flash', 'gemini-3-pro': 'Gemini-3-Pro',
    'openai_claude-sonnet-4.6': 'Claude-4.6-Son', 'glm4.7-thinking': 'GLM-4.7-Think',
    'glm4.7-unthinking': 'GLM-4.7', 'openai_deepseek-chat': 'DeepSeek-Chat',
    'openai_deepseek-reasoner': 'DeepSeek-Reas', 'openai_qwen3-max': 'Qwen3-Max',
    'openai_qwen3-235b': 'Qwen3-235B', 'openai_qwen3-32b': 'Qwen3-32B',
    'openai_qwen3-14b': 'Qwen3-14B',
}
SUBS = ['s_method', 's_label', 's_trans', 's_time']
NORM = {'s_method': lambda x: (x + 2.5) / 5.0, 's_label': lambda x: x / 6.0,
        's_trans': lambda x: x / 3.0, 's_time': lambda x: x / 3.0}

# Macaron fills + same-family darker edges
FILL = {'s_method': '#F6C9A8', 's_label': '#F8B7C5', 's_trans': '#C9C1E8', 's_time': '#A8DADC'}
EDGE = {'s_method': '#E0965F', 's_label': '#E1789A', 's_trans': '#9C86D2', 's_time': '#5FA9AC'}

dist = {k: [] for k in SUBS}
per = {}
for f in sorted(glob.glob(os.path.join(RESULT, 'evaluation_results_*_1-shot.json'))):
    model = os.path.basename(f)[len('evaluation_results_'):-len('_1-shot.json')]
    if model not in DISPLAY:
        continue
    rec = per.setdefault(model, {'slabel': [], 'stime': []})
    for it in json.load(open(f, encoding='utf-8')):
        ev = it.get('evaluation', {})
        if not isinstance(ev, dict) or ev.get('_error'):
            continue
        eff = ev.get('scores', {}).get('effectiveness', {})
        vals, ok = {}, True
        for k in SUBS:
            s = eff.get(k, {}).get('score')
            if s is None:
                ok = False; break
            vals[k] = float(s)
        if not ok:
            continue
        for k in SUBS:
            dist[k].append(NORM[k](vals[k]))
        rec['slabel'].append(NORM['s_label'](vals['s_label']))
        rec['stime'].append(NORM['s_time'](vals['s_time']))

order = sorted(per, key=lambda m: np.mean(per[m]['slabel']))  # worst labeling first
disp = [DISPLAY[m] for m in order]


def violins(ax, data, fills, edges):
    parts = ax.violinplot(data, showextrema=False, showmeans=False, widths=0.82)
    for i, pc in enumerate(parts['bodies']):
        pc.set_facecolor(fills[i]); pc.set_alpha(0.65)
        pc.set_edgecolor(edges[i]); pc.set_linewidth(0.9)
    for i, d in enumerate(data):
        ax.scatter(i + 1, np.mean(d), color='#333333', marker='D', s=9, zorder=3)
        ax.hlines(np.median(d), i + 0.72, i + 1.28, color='#333333', lw=0.9, zorder=3)


def panel_label(ax, letter):
    ax.text(-0.02, 1.15, letter, transform=ax.transAxes, fontsize=11,
            fontweight='bold', va='top', ha='left')


from matplotlib.lines import Line2D
_lg = [Line2D([0], [0], marker='D', color='none', markerfacecolor='#333333', markersize=5, label='mean'),
       Line2D([0], [0], color='#333333', lw=1.3, label='median')]

fig, (axA, axB, axC) = plt.subplots(1, 3, figsize=(7.15, 2.55),
                                    gridspec_kw={'width_ratios': [0.9, 2.05, 2.05]})

# ---- Panel a ----
violins(axA, [dist[k] for k in SUBS], [FILL[k] for k in SUBS], [EDGE[k] for k in SUBS])
axA.set_xticks([1, 2, 3, 4])
axA.set_xticklabels([r'$S_{method}$', r'$S_{label}$', r'$S_{trans}$', r'$S_{time}$'], rotation=45, ha='right')
axA.axhline(0.5, ls=':', color='0.6', lw=0.6)
axA.set_ylim(-0.03, 1.10); axA.set_ylabel('score')
axA.set_title('$\\mathbf{a}$  Effectiveness\nsub-scores', loc='center', fontsize=8.5, pad=5)

# ---- Panel b: per-model S_label (rose) ----
violins(axB, [per[m]['slabel'] for m in order], [FILL['s_label']] * len(order), [EDGE['s_label']] * len(order))
axB.set_ylim(-0.03, 1.10); axB.set_ylabel(r'$S_{label}$')
axB.set_xticks(np.arange(1, len(order) + 1)); axB.set_xticklabels(disp, rotation=45, ha='right')
axB.set_title(r'$\mathbf{b}$   Per-model $S_{label}$ (labeling)', loc='center', fontsize=8.5, pad=5)
axB.legend(handles=_lg, loc='upper left', fontsize=7, frameon=False, ncol=1,
           handlelength=1.2, labelspacing=0.3, borderpad=0.25)

# ---- Panel c: per-model S_time (sky) ----
violins(axC, [per[m]['stime'] for m in order], [FILL['s_time']] * len(order), [EDGE['s_time']] * len(order))
axC.set_ylim(-0.03, 1.05); axC.set_ylabel(r'$S_{time}$')
axC.set_xticks(np.arange(1, len(order) + 1)); axC.set_xticklabels(disp, rotation=45, ha='right')
axC.set_title(r'$\mathbf{c}$   Per-model $S_{time}$ (timing)', loc='center', fontsize=8.5, pad=5)

fig.tight_layout(w_pad=1.2)
for _ext in ('pdf', 'png'):
    fig.savefig(os.path.join(HERE, f'failure_localization.{_ext}'))
print('saved failure_localization.{pdf,png} | models=', len(order))
