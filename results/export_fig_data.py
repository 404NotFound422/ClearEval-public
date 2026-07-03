import json, glob, math, os
import numpy as np
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

# ---------- Fig 3 heatmap: model x method usage (%) + entropy ----------
per = {}; total = {}
for f in FILES:
    base = f.split('evaluation_results_')[1].rsplit('_1-shot',1)[0].rsplit('_0-shot',1)[0]
    per.setdefault(base, {})
    for it in json.load(open(f, encoding='utf-8')):
        m = canon(it.get('evaluation',{}).get('meta_data',{}).get('target_method',''))
        if m:
            per[base][m] = per[base].get(m,0)+1; total[m] = total.get(m,0)+1
top = [m for m,_ in sorted(total.items(), key=lambda x:-x[1])[:7]]
methods = [SHORT.get(m,m) for m in top] + ['Other']
rows = []
for base, dist in per.items():
    n = sum(dist.values())
    if n == 0: continue
    ent = -sum((c/n)*math.log2(c/n) for c in dist.values() if c > 0)
    frac = [dist.get(m,0)/n for m in top]; frac.append(1-sum(frac))
    rows.append((DISP.get(base,base), round(ent,2), [round(x*100,1) for x in frac]))
rows.sort(key=lambda r: -r[1])

OUT = ROOT + '/article/BIBM/figures/fig_data'
os.makedirs(OUT, exist_ok=True)
json.dump({'description':'Clearing-method selection per model (% of that model choices). H = Shannon entropy of the choice distribution (bits). Rows pre-sorted most-diverse (high H) to most-anchored (low H).',
           'x_methods': methods,
           'models': [{'name':d,'entropy_H':e,'pct':p} for d,e,p in rows]},
          open(OUT+'/fig3_heatmap.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

# ---------- Fig 4 violin: Effectiveness sub-metric per-protocol distributions ----------
MAXS = {'s_method':2.5,'s_label':6,'s_trans':3,'s_time':3}
vals = {k: [] for k in MAXS}
for f in FILES:
    for it in json.load(open(f, encoding='utf-8')):
        eff = it.get('evaluation',{}).get('scores',{}).get('effectiveness',{})
        for k in MAXS:
            v = eff.get(k, {})
            if isinstance(v, dict) and v.get('score') is not None:
                nn = float(v['score'])/MAXS[k]
                if k == 's_method': nn = (nn+1)/2
                vals[k].append(round(max(0.0, min(1.0, nn)), 4))
LAB = {'s_method':'S_method','s_label':'S_label','s_trans':'S_trans','s_time':'S_time'}
json.dump({'description':'Per-protocol Effectiveness sub-metric scores, pooled over all 253 scenarios x 13 models. Normalized to [0,1]. NOTE: S_method is the SIGNED metric [-1,1] rescaled to [0,1] via (x+1)/2 (0.5 = neutral fit); the other three are natively [0,1].',
           'order': ['S_method','S_label','S_trans','S_time'],
           'means': {LAB[k]: round(float(np.mean(vals[k])),3) for k in MAXS},
           'n': {LAB[k]: len(vals[k]) for k in MAXS},
           'values': {LAB[k]: vals[k] for k in MAXS}},
          open(OUT+'/fig4_violin.json','w',encoding='utf-8'), ensure_ascii=False)

print('WROTE', OUT+'/fig3_heatmap.json', 'and fig4_violin.json')
print('\n=== FIG 3 heatmap (model x method %, sorted by entropy H) ===')
print('model'.ljust(16), 'H   ', '  '.join(m[:7].rjust(7) for m in methods))
for d,e,p in rows:
    print(d.ljust(16), f'{e:<4}', '  '.join(f'{x:7.0f}' for x in p))
print('\n=== FIG 4 violin means (normalized [0,1]) ===')
for k in MAXS:
    print(f'  {LAB[k]:10} mean={np.mean(vals[k]):.3f}  n={len(vals[k])}')
