import json, glob, math, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.lines import Line2D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _norm(s):
    s = str(s or '').lower()
    for ch in ' -_/()':
        s = s.replace(ch, '')
    return s.replace('+', '')

MS = json.load(open(ROOT + '/dataset/Q+AR/src/model_space_signed.json', encoding='utf-8'))['methods']

def canon(name):
    nl = _norm(name)
    if not nl: return None
    for k in MS:
        kl = _norm(k)
        if (nl in kl or kl in nl) and min(len(nl), len(kl)) >= 3: return k
    for kw, c in (('3disco','3DISCO'),('thf','3DISCO'),('dbe','3DISCO'),('dcm','3DISCO'),
                  ('babb','BABB'),('benzyl','BABB'),('ethylcinnamate','BABB'),
                  ('idisco','iDISCO (iDISCO+)'),('solvent','3DISCO')):
        if kw in nl: return c
    return None

SHORT = {'iDISCO (iDISCO+)':'iDISCO+','SCALE (ScaleS)':'ScaleS'}
DISP = {'openai_gpt-5.2-fast':'GPT-5.2-Fast','openai_gpt-5.2-thinking':'GPT-5.2-Think',
        'gemini-3-flash':'Gemini-3-Flash','gemini-3-pro':'Gemini-3-Pro',
        'openai_claude-sonnet-4.6':'Claude-4.6','glm4.7-unthinking':'GLM-4.7',
        'glm4.7-thinking':'GLM-4.7-Think','openai_deepseek-chat':'DeepSeek',
        'openai_deepseek-reasoner':'DeepSeek-Think','openai_qwen3-max':'Qwen3-Max',
        'openai_qwen3-235b':'Qwen3-235B','openai_qwen3-32b':'Qwen3-32B','openai_qwen3-14b':'Qwen3-14B'}

FILES = glob.glob(ROOT + '/dataset/Q+AR/result/evaluation_results_*_*shot.json')
plt.rcParams.update({'font.family':'sans-serif',
                     'font.sans-serif':['Arial','Liberation Sans','DejaVu Sans'],
                     'axes.linewidth':0.8,'figure.dpi':300,'savefig.dpi':300})

# ======================= FIG: method-usage heatmap (column, light Blues) =======================
per = {}; total = {}
for f in FILES:
    base = f.split('evaluation_results_')[1].rsplit('_1-shot',1)[0].rsplit('_0-shot',1)[0]
    per.setdefault(base, {})
    for it in json.load(open(f, encoding='utf-8')):
        m = canon(it.get('evaluation',{}).get('meta_data',{}).get('target_method',''))
        if m:
            per[base][m] = per[base].get(m,0)+1; total[m] = total.get(m,0)+1

top = [m for m,_ in sorted(total.items(), key=lambda x:-x[1])[:7]]
methods = top + ['Other']
rows = []
for base, dist in per.items():
    n = sum(dist.values())
    if n == 0: continue
    ent = -sum((c/n)*math.log2(c/n) for c in dist.values() if c > 0)
    frac = [dist.get(m,0)/n for m in top]; frac.append(1-sum(frac))
    rows.append((DISP.get(base,base), ent, frac))
rows.sort(key=lambda r: -r[1])
models = [f'{d}  ($H$={e:.2f})' for d,e,_ in rows]
M = np.array([f for _,_,f in rows])

fig, ax = plt.subplots(figsize=(7.4, 4.5))
cmap = sns.color_palette('Blues', as_cmap=True)
im = ax.imshow(M, aspect='auto', cmap=cmap, vmin=0, vmax=1)
ax.set_yticks(range(len(models))); ax.set_yticklabels(models, fontsize=10)
ax.set_xticks(range(len(methods)))
ax.set_xticklabels([SHORT.get(m,m) for m in methods], fontsize=10, rotation=35, ha='right', rotation_mode='anchor')
ax.set_xticks(np.arange(-.5, len(methods), 1), minor=True)
ax.set_yticks(np.arange(-.5, len(models), 1), minor=True)
ax.grid(which='minor', color='white', linewidth=1.4); ax.tick_params(which='minor', length=0)
for i in range(M.shape[0]):
    for j in range(M.shape[1]):
        v = M[i,j]
        if v >= 0.05:
            ax.text(j, i, f'{v*100:.0f}', ha='center', va='center', fontsize=8.5,
                    color='white' if v > 0.62 else '#1a1a1a',
                    fontweight='bold' if v >= 0.4 else 'normal')
cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
cb.set_label('share of choices', fontsize=9); cb.ax.tick_params(labelsize=8)
plt.tight_layout()
out1 = ROOT + '/article/BIBM/figures/method_usage.png'
plt.savefig(out1, facecolor='white', bbox_inches='tight'); plt.close()
print('saved', out1, 'shape', M.shape)

# ======================= FIG: violin (Effectiveness sub-metrics ONLY) =======================
MAXS = {'s_method':2.5,'s_label':6,'s_trans':3,'s_time':3}
vals = {k: [] for k in MAXS}
for f in FILES:
    for it in json.load(open(f, encoding='utf-8')):
        eff = it.get('evaluation',{}).get('scores',{}).get('effectiveness',{})
        for k in MAXS:
            v = eff.get(k, {})
            if isinstance(v, dict) and v.get('score') is not None:
                n = float(v['score'])/MAXS[k]
                if k == 's_method': n = (n+1)/2
                vals[k].append(max(0.0, min(1.0, n)))
means = {k: float(np.mean(v)) for k,v in vals.items()}
EFF = [('s_method',r'$S_{\mathrm{method}}$'),('s_label',r'$S_{\mathrm{label}}$'),
       ('s_trans',r'$S_{\mathrm{trans}}$'),('s_time',r'$S_{\mathrm{time}}$')]

fig, ax = plt.subplots(figsize=(6.2, 6.4))
COLORS = ['#8a5fa0', '#5786a6', '#5fbd85', '#f2d84a']  # viridis-like: purple, steel, green, yellow
data = [vals[k] for k,_ in EFF]
pos = list(range(1, len(EFF)+1))

# solid violins (reference style: no jitter/box/diamond)
parts = ax.violinplot(data, positions=pos, showextrema=False, widths=0.82, bw_method=0.3)
for i, b in enumerate(parts['bodies']):
    b.set_facecolor(COLORS[i]); b.set_alpha(1.0); b.set_edgecolor('none')

# black mean bar + bold mean label (the paper's headline numbers)
for i, (k, _) in enumerate(EFF):
    m = means[k]
    ax.hlines(m, pos[i]-0.34, pos[i]+0.34, color='black', lw=3, zorder=4)
    ax.text(pos[i], 1.05, f'{m:.2f}', ha='center', va='bottom', fontsize=17, fontweight='bold', color='black')

ax.axhline(0.0, ls='--', color='0.6', lw=1.2, zorder=1)
ax.set_xticks(pos); ax.set_xticklabels([lab for _, lab in EFF], fontsize=18)
ax.set_ylim(-0.04, 1.16); ax.set_yticks([0, .2, .4, .6, .8, 1.0]); ax.tick_params(labelsize=13)
for sp in ('top', 'right'): ax.spines[sp].set_visible(False)
ax.set_ylabel('Normalized score  [0,1]', fontsize=14)
ax.set_title('Effectiveness sub-metrics', fontsize=17, fontweight='bold', pad=26)
plt.tight_layout()
out2 = ROOT + '/article/BIBM/figures/violin_plots.png'
plt.savefig(out2, facecolor='white', bbox_inches='tight'); plt.close()
print('saved', out2, 'means', {k:round(means[k],2) for k in MAXS})
