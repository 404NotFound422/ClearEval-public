"""Compose the frozen benchmark's reviewed V6.2 checks into complete CCE scores.

No inference calls. Every provisional scalar retains its evidence interval and
provenance; it is never promoted to a confirmed observation by aggregation.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCHMARK = ROOT/'dataset/benchmark185/2026-11-03'
FORMAL_VERSION = 'cleareval-complete-20261105-v6.2'
VERSION = FORMAL_VERSION
MAXIMA = dict(c_step=2, c_param=3, co_order=3, co_method=2, co_param=2,
              co_chem=1, s_method=2.5, s_label=6, s_trans=3, s_time=3)
DEFAULT_INPUT = BENCHMARK/'inputs.json.gz'
DEFAULT_VERIFIED = ROOT/'dataset/benchmark185/2026-11-05-v6.2/verified_checks.json.gz'
DEFAULT_PREVIOUS = BENCHMARK/'previous_components.json.gz'
DEFAULT_OUTPUT = ROOT/'results/benchmark185/2026-11-05-v6.2'
POLICY_PATH = ROOT/'complete_scoring_policy.json'
KB_PATH = ROOT/'KnowledgeBase/time_kb.json'


def write_gzip(path, data):
    """Stable output bytes across machines and repeated runs."""
    with path.open('wb') as raw:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as stream:
            stream.write(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8'))


def repo_path(path):
    path=Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name


def verified_packets(cases, decisions, *, independent_claims=True):
    from cleareval_scoring import scoring_v5,scoring_v6,adjudication
    rows=[]
    for c in cases:
        for d in decisions:
            if d['id']==c['id']:
                # Review excerpts can concatenate non-adjacent source lines.
                assert all(line.strip() in c['answer'] for line in d['reviewed_candidate_text'].splitlines()
                           if line.strip()), (c['id'],'adjudicated text changed')
        packet=(scoring_v6.score_branch(c,decisions) if independent_claims
                else adjudication.apply(scoring_v5.score_branch(c),c,decisions))
        rows.append(dict(id=c['id'],branch=c['branch'],method=c['method'],packet=packet))
    return rows


def read(path):
    path = Path(path)
    with (gzip.open(path, 'rt', encoding='utf8') if path.suffix == '.gz'
          else path.open(encoding='utf8')) as stream:
        return json.load(stream)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def score(value, reason, *, bounds=None, status='DETERMINED', **evidence):
    bounds = list(bounds if bounds is not None else [value, value])
    assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in [value, *bounds])
    assert bounds[0]-1e-12 <= value <= bounds[1]+1e-12
    return dict(value=float(value), bounds=bounds, status=status, reason=reason, **evidence)


def provisional(low, high, reason, **evidence):
    return score((low+high)/2, reason, bounds=[low, high], status='PROVISIONAL',
                 point_rule='score_interval_midpoint_for_review_only', **evidence)


def previous_score(metric):
    if isinstance(metric.get('value'), (int, float)):
        return score(metric['value'], '沿用上一完整评测的已确定分项',
                     status='REUSED', previous_reason=metric.get('reason'))
    if metric.get('bounds') is not None:
        return provisional(*metric['bounds'], '上一完整评测只确定区间，本版用区间中点形成暂定分',
                           previous_reason=metric.get('reason'))
    raise ValueError('Unresolved metric requires an explicit resolution policy')


def compose(components):
    specs = {
        'Com': (['c_step', 'c_param'], lambda v: .4*v[0]/2+.6*v[1]/3),
        'Co': (['co_order','co_method','co_param','co_chem'],
               lambda v: (v[0]/3+v[1]/2+v[2]/2+v[3])/4),
        'Eff': (['s_method','s_label','s_trans','s_time'],
                lambda v: ((v[0]/2.5+1)/2+v[1]/6+v[2]/3+v[3]/3)/4),
    }
    result = {}
    for key, (deps, fn) in specs.items():
        nodes = [components[k] for k in deps]
        low, high = [fn([n['bounds'][i] for n in nodes]) for i in (0,1)]
        result[key] = score(fn([n['value'] for n in nodes]), '既定权重汇总',
                            bounds=[low,high], status='DETERMINED' if abs(high-low)<1e-12 else 'PROVISIONAL',
                            dependencies=deps)
    nodes = list(result.values())
    low, high = [min(n['bounds'][i] for n in nodes) for i in (0,1)]
    result['IA'] = score(min(n['value'] for n in nodes), 'min(Com, Co, Eff)',
                         bounds=[low,high], status='DETERMINED' if abs(high-low)<1e-12 else 'PROVISIONAL')
    return result


def recipe_dimension(packet, name):
    """A recipe defect has one root owner; it is not deducted in two dimensions."""
    human = [d for d in packet.get('human_adjudications', []) if d['field']=='declared_recipe:'+name]
    if human:
        return 'co_method' if human[0]['group_id']=='stock_omission' else 'co_param'
    audit = packet.get('correctness_recipe_audit', {}).get(name, {})
    failed = [k for c in audit.get('claims', []) for v in c.get('variants', [])
              for k,state in v.get('checks', {}).items() if state=='FAIL']
    return 'co_method' if any(k.startswith('extra:') for k in failed) else 'co_param'


def correctness(case, packet, previous, policy):
    findings = defaultdict(list)
    unknown = defaultdict(list)
    # Keep the previous order review for relations outside the new reference inventory.
    order = previous_score(previous['co_order'])
    # Parameter correctness is recomputed in the user-defined concentration scope;
    # the old teacher's time/temperature deductions must not leak into this score.
    method = previous_score(previous['co_method'])
    param = score(2, '关键浓度/配方比例检查未检出明确错误；时间和温度不参与正确性')
    for pair in packet['written']['pairs']:
        for key, state in pair['correctness_checks'].items():
            if key=='declared_recipe:independent_claim':continue  # Owned once below, including unmatched uses.
            if state not in {'FAIL','UNKNOWN'}:
                continue
            if key.startswith('concentration:') or key=='stock_dilution':
                owner, severity = 'co_param', 'LOCAL'
            elif key.startswith('declared_recipe:'):
                owner, severity = recipe_dimension(packet, key.split(':',1)[1]), 'LOCAL'
            elif key in {'reference_sequence','declared_process_order'}:
                owner, severity = 'co_order', 'CRITICAL' if key=='declared_process_order' else 'IMPORTANT'
            elif key in {'material_identity','action','polarity','internal_material_consistency','execution_branch'}:
                owner, severity = 'co_method', 'CRITICAL'
            else:
                raise ValueError('Unmapped correctness field: '+key)
            item = dict(candidate=pair['candidate'],reference=pair['reference'],field=key,severity=severity)
            (findings if state=='FAIL' else unknown)[owner].append(item)
    # An unmatched reference is usually an omission, not evidence that the nearest
    # candidate replaces it. Only promote an explicit dehydration solvent swap.
    reference_steps = {s['id']:s for s in case['reference_steps']}
    candidate_steps = {s['id']:s for s in packet['logical_candidate_steps']}
    for d in packet.get('unmatched_diagnostics', []):
        rs = reference_steps.get(d['reference'], {})
        cs = candidate_steps.get(d.get('best_candidate'), {})
        rt, ct = rs.get('text',''), cs.get('text','')
        explicit_phase = re.search(r'dehydrat|脱水', cs.get('heading','')+' '+ct, re.I)
        expected_tb = re.search(r'tert.?butanol|叔丁醇',rt,re.I)
        expected_thf = re.search(r'\bTHF\b|tetrahydrofuran',rt,re.I)
        substitute = (expected_tb and re.search(r'\bmethanol\b|\bethanol\b|\bTHF\b|tetrahydrofuran|甲醇|乙醇',ct,re.I)) or (
            expected_thf and re.search(r'\bmethanol\b|\bethanol\b|甲醇|乙醇',ct,re.I))
        if explicit_phase and substitute and d['checks'].get('material_identity')=='FAIL':
            findings['co_method'].append(dict(candidate=d['best_candidate'],reference=d['reference'],
                                               field='unmatched_material_identity',severity='CRITICAL'))
    if packet.get('process_audit', {}).get('failed_candidate_ids'):
        findings['co_order'].append(dict(field='declared_process_order',severity='CRITICAL',
                                         candidates=packet['process_audit']['failed_candidate_ids']))
    # Recipe checks may be attached to a use outside the matched subset.
    for f in packet.get('formulation_results', []):
        if f.get('scope')=='operation':continue  # Already attributed by candidate below.
        if f['status']=='FAIL' and f.get('used_by'):
            owner = recipe_dimension(packet, f['name'])
            if not any(x['field']=='declared_recipe:'+f['name'] for x in findings[owner]):
                findings[owner].append(dict(candidates=f['used_by'],field='declared_recipe:'+f['name'],severity='LOCAL'))
    for f in packet.get('independent_recipe_findings',[]):
        existing=[x for items in findings.values() for x in items]
        if any(x.get('candidate')==f['candidate'] and x['field'].startswith('declared_recipe:') for x in existing):
            continue
        findings[f['owner']].append(dict(f))
    for f in packet.get('independent_recipe_unresolved',[]):
        existing=[x for items in unknown.values() for x in items]
        if not any(x.get('candidate')==f['candidate'] and x['field'].startswith('declared_recipe:') for x in existing):
            unknown[f['owner']].append(dict(f))
    current = dict(co_order=order, co_method=method, co_param=param)
    for key, node in current.items():
        fs = findings[key]
        if fs:
            cap = 0 if any(f['severity']=='CRITICAL' for f in fs) else 1
            current[key] = score(min(node['value'], cap), '新版核验发现明确错误，按原等级规则扣分',
                                 findings=fs, previous_value=previous[key].get('value'))
        elif unknown[key]:
            current[key] = provisional(0, node['value'], '本维度存在未确定条件，暂定分保留完整区间',
                                       unresolved_checks=unknown[key])
        elif key in {'co_method','co_param'} and not packet['written']['pairs'] and node['value']>0:
            current[key] = provisional(0,node['value'],
                '新版未能将执行步骤与参考配对；旧版判断尚不足以确认此维度，暂定分保留区间',
                unresolved_type='no_verified_alignment')
    override = policy['order_resolutions'].get(case['id'])
    if override:
        current['co_order'] = score(min(current['co_order']['value'], override['value']), override['reason'],
                                    source=override['source'], prior_checks=current['co_order'])
    # Wrong method replaces the uDISCO gradient altogether. Missing correct reagent
    # gradients cannot be scored as a verified concentration match.
    if case['id']=='EXPAND_026' and case['method']=='uDISCO':
        missing = packet.get('unmatched_diagnostics', [])
        wrong_gradient = [d for d in missing if d['checks'].get('concentration:tert_butanol')=='UNKNOWN'
                          and d['checks'].get('material_identity')=='FAIL']
        if len(wrong_gradient)>=3:
            current['co_param'] = score(0, '用户已明确否定该uDISCO浓度梯度；按关键梯度错误计0/2',
                                        reference_steps=[d['reference'] for d in wrong_gradient])
    current['co_chem'] = previous_score(previous['co_chem'])
    return current


def time_value(actual, row):
    low, median, high = [row['clearing_time_'+k+'_h'] for k in ['min','median','max']]
    delta = max(low-actual,actual-high,0)
    tau = (.1 if actual>high else .2)*median
    return 3*math.exp(-.5*(delta/tau)**2)


def time_component(case, previous, policy, kb):
    ident = case['id']
    if ident in policy['unresolved_time']:
        return provisional(0,3,policy['unresolved_time'][ident], unresolved_type='reference_applicability')
    ledger = policy['time_ledgers'].get(ident)
    if not ledger:
        return previous_score(previous)
    source_steps = {s['id']:s for s in case['candidate_steps']}
    assert set(ledger['steps'])<=set(source_steps), (ident, set(ledger['steps'])-set(source_steps))
    tier = case['tissue_tier_code']
    scope_repair = ident in policy['pegasos_time_scope']['ids']
    if scope_repair:
        tier = next(r['tier_code'] for r in kb if r['method']=='PEGASOS' and r['tier_code'].startswith('T07B_'))
    row = next((r for r in kb if r['method']==case['method'] and r['tier_code']==tier), None)
    if not row:
        raise ValueError((ident,case['method'],tier,'missing time row'))
    low, high = [sum(v[i] for v in ledger['steps'].values()) for i in (0,1)]
    nominal = (low+high)/2
    points = [time_value(low,row),time_value(high,row)]
    if low<=row['clearing_time_max_h'] and high>=row['clearing_time_min_h']:
        points.append(3.)
    bounds = [0 if ledger.get('open_upper') else min(points), max(points)]
    evidence = dict(hours=[low,high], nominal_hours=nominal, open_upper=ledger.get('open_upper',False),
                    time_steps=[dict(id=k,hours=v,text=source_steps[k]['text']) for k,v in ledger['steps'].items()],
                    reference=dict(row), time_point_rule='score_at_nominal_duration_midpoint')
    if scope_repair:
        evidence['reference_scope_repair'] = policy['pegasos_time_scope']
    return score(time_value(nominal,row), ledger['note'], bounds=bounds,
                 status='DETERMINED' if abs(bounds[1]-bounds[0])<1e-12 else 'PROVISIONAL', **evidence)


def branch_score(case, packet, previous, policy, kb):
    if case['id'] in policy['incomplete_outputs']:
        assert not case['candidate_steps'], 'Completion gate must not discard an extracted protocol'
        components = {k:score(-2.5 if k=='s_method' else 0, '未形成最终可执行protocol，按未完成任务计分',
                             status='INCOMPLETE_OUTPUT') for k in MAXIMA}
        supplementary = {k:score(0,'无最终protocol，按未完成任务计分',status='INCOMPLETE_OUTPUT')
                         for k in ['cleareval_coverage','cleareval_sp_eligible','bio_sr','bio_sp','bio_f1']}
    else:
        m = packet['written']['metrics']
        # Presence and correctness are distinct: a wrong but matched step can be
        # present for completeness and fail the correctness checks.
        cov = m['operation_SR']
        components = dict(c_step=score(2*cov,'2 × 当前参考执行步骤覆盖率；独立配制不进入分母'))
        if case['id']=='EXPAND_174':
            base_cov = cov
            cov = base_cov*m['N_R']/(m['N_R']+2)
            components['c_step'] = score(2*cov, '用户确认缺少两次抗体后洗涤：完整性参考义务增加2项，已完成数不变',
                                          base_coverage=base_cov, reference_operations=m['N_R'],
                                          added_obligations=2, missing_operations=['post_primary_wash','post_secondary_wash'])
        repair = policy['parameter_resolutions'].get(case['id'])
        components['c_param'] = score(repair['value'],repair['reason']) if repair else previous_score(previous['c_param'])
        components.update(correctness(case,packet,previous,policy))
        for key in ['s_method','s_trans']:
            components[key] = previous_score(previous[key])
        if case['id'] in policy['unresolved_label']['ids']:
            components['s_label'] = provisional(0,6,policy['unresolved_label']['reason'],
                                                source_url=policy['unresolved_label']['source_url'])
        else:
            components['s_label'] = previous_score(previous['s_label'])
        components['s_time'] = time_component(case,previous['s_time'],policy,kb)
        supplementary = dict(cleareval_coverage=score(cov,'参考执行操作覆盖'),
                             cleareval_sp_eligible=score(m['operation_SP'],'候选操作匹配比例'))
        for key, source in [('bio_sr','correctness_Bio_SR'),('bio_sp','correctness_Bio_SP')]:
            lo,hi = m[source+'_lower'],m[source+'_upper']
            supplementary[key] = score(lo,'V5步骤与配方核验：已确认正确步骤比例' if packet['version'].endswith('-v5') else '执行步骤与独立配方核验：已确认正确步骤比例',bounds=[lo,hi],
                                        status='DETERMINED' if lo==hi else 'PROVISIONAL')
        den = m['N_R']+m['N_C']
        f1_low=2*m['confirmed_correct_credit']/den if den else 0
        f1_high=(2*(m['confirmed_correct_credit']+m['correctness_review_credit'])/den
                 if den and not packet['version'].endswith('-v5') else f1_low)
        supplementary['bio_f1'] = score(f1_low,
            '2×已确认正确匹配数/(参考执行步骤数+候选执行步骤数)',bounds=[f1_low,f1_high],
            status='DETERMINED' if f1_low==f1_high else 'PROVISIONAL')
    metrics = {**components,**supplementary,**compose(components)}
    return dict(id=case['id'],question_id=case['question_id'],branch=case['branch'],method=case['method'],
                version=VERSION, answer_sha256=case['answer_sha256'],metrics=metrics,
                generation_configuration=case['generation_configuration'])


def combine_branches(branches):
    metrics = {}
    for key in [*MAXIMA,'cleareval_coverage','cleareval_sp_eligible','bio_sr','bio_sp','bio_f1']:
        nodes = [b['metrics'][key] for b in branches]
        # Report the predeclared least favorable branch, with the envelope across
        # all declared alternatives; never choose a reference for its high score.
        lo,hi = min(n['bounds'][0] for n in nodes), max(n['bounds'][1] for n in nodes)
        value = min(n['value'] for n in nodes)
        chosen = next(n for n in nodes if n['value']==value)
        metrics[key] = dict(chosen)
        metrics[key].update(bounds=[lo,hi],status='PROVISIONAL' if abs(hi-lo)>1e-12 else chosen['status'])
        if len(nodes)>1:
            metrics[key]['branches'] = {b['branch']:b['metrics'][key]['value'] for b in branches}
            metrics[key]['branch_policy'] = 'minimum_per_component_then_recompute_aggregates'
    metrics.update(compose(metrics))
    incomplete = any(n['status']=='INCOMPLETE_OUTPUT' for n in metrics.values())
    uncertain = [k for k in MAXIMA if metrics[k]['status']=='PROVISIONAL']
    return dict(id=branches[0]['id'],question_id=branches[0]['question_id'],method=branches[0]['method'],
                generation_configuration=branches[0]['generation_configuration'],
                branches=[b['branch'] for b in branches],metrics=metrics,
                status='未完成作答，计0分' if incomplete else '含暂定分' if uncertain else '分项已确定',
                provisional_components=uncertain)


def write_csv(path, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        w = csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def build_page(path, rows, cases):
    byid = {c['id']:c for c in cases}
    # Include question, unmodified answer and reference text only; no historical
    # model traces or expanded scoring caches are embedded in the review page.
    data=[]
    grouped=defaultdict(list)
    for c in cases: grouped[c['id']].append(c)
    for r in rows:
        c=byid[r['id']]
        data.append(dict(**r,question=c['question'],answer=c['answer'],
                         references=[dict(branch=x['branch'],steps=[s['id']+' '+s['text'] for s in x['reference_steps']])
                                     for x in grouped[r['id']]]))
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    content='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ClearEval 完整评分</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{font:15px/1.6 system-ui;background:#f4f6f8;color:#203047;margin:32px auto;max-width:1400px;padding:0 20px}h1{margin-bottom:6px}p{color:#556375}input,select{padding:10px;border:1px solid #ccd4df;border-radius:6px;margin:0 8px 12px 0}table{width:100%;border-collapse:collapse;background:white}th,td{padding:9px;border-bottom:1px solid #e4e8ed;text-align:left;overflow-wrap:anywhere}th{background:#edf2f7;position:sticky;top:0}button{cursor:pointer;border:0;background:#e6efff;color:#1752a3;padding:6px 12px;border-radius:5px}.warn{color:#a45d00}dialog{width:min(1160px,94vw);max-height:90vh;border:1px solid #b9c6d5;border-radius:12px;padding:24px;overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fa;padding:16px}.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}.close{float:right}.small{font-size:13px}details{margin:10px 0;min-width:0}summary{cursor:pointer;font-weight:600}@media(max-width:700px){body{padding:0 10px;font-size:13px}.grid{grid-template-columns:minmax(0,1fr)}dialog{padding:12px}th,td{padding:5px}}</style>
<h1>ClearEval · 185例完整评分</h1><p>满分保持原定义。Com、Co、Eff和总分IA展示为百分制；IA取三维最低分。暂定分保留区间，便于先完成全量筛查。</p>
<input id="query" placeholder="搜索案例 / 方法"><select id="filter"><option value="">全部案例</option><option>分项已确定</option><option>含暂定分</option><option value="total_uncertain">总分有区间</option><option>未完成作答，计0分</option></select><span id="count"></span>
<table><thead><tr><th>案例</th><th>方法</th><th>完整性</th><th>正确性</th><th>有效性</th><th>总分</th><th>Bio-SR / SP</th><th>状态</th><th></th></tr></thead><tbody id="body"></tbody></table>
<dialog id="detail"><button class="close" onclick="document.getElementById('detail').close()">关闭</button><div id="inside"></div></dialog>
<script>const data=__DATA__;const maxima=__MAXIMA__;const names={c_step:'步骤完整性',c_param:'参数完整性',co_order:'顺序正确性',co_method:'方法/试剂正确性',co_param:'浓度/配方比例正确性',co_chem:'化学安全性',s_method:'方法适用性',s_label:'标记适用性',s_trans:'折射率匹配',s_time:'时间适用性'};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=x=>(x*100).toFixed(1);const num=x=>Number(x.toFixed(4));
function render(){let q=document.getElementById('query').value.toLowerCase(),f=document.getElementById('filter').value;let rows=data.filter(r=>(!q||(r.id+' '+r.method).toLowerCase().includes(q))&&(!f||(f==='total_uncertain'?r.metrics.IA.bounds[1]-r.metrics.IA.bounds[0]>1e-12:r.status===f)));document.getElementById('count').textContent=rows.length+' / 185';document.getElementById('body').innerHTML=rows.map(r=>`<tr><td>${esc(r.id)}</td><td>${esc(r.method)}</td>${['Com','Co','Eff','IA'].map(k=>`<td>${pct(r.metrics[k].value)}</td>`).join('')}<td>${pct(r.metrics.bio_sr.value)} / ${pct(r.metrics.bio_sp.value)}</td><td class="${r.provisional_components.length?'warn':''}">${esc(r.status)}</td><td><button onclick="show('${r.id}')">查看依据</button></td></tr>`).join('')}
function show(id){const r=data.find(x=>x.id===id);document.getElementById('inside').innerHTML=`<h2>${esc(id)} · ${esc(r.method)}</h2><p>${esc(r.status)} · 总分 ${pct(r.metrics.IA.value)}，区间 [${pct(r.metrics.IA.bounds[0])}, ${pct(r.metrics.IA.bounds[1])}]</p><table><tr><th>分项</th><th>得分 / 满分</th><th>区间</th><th>依据</th></tr>${Object.keys(maxima).map(k=>{let n=r.metrics[k];return `<tr><td>${names[k]}<br><small>${k}</small></td><td>${num(n.value)} / ${maxima[k]}</td><td>[${num(n.bounds[0])}, ${num(n.bounds[1])}]</td><td>${esc(n.reason)}${n.findings?'<br>'+esc([...new Set(n.findings.map(x=>(x.candidate||'')+': '+x.field))].join('；')):''}</td></tr>`}).join('')}</table><p class="small">Com=0.4×C_step/2+0.6×C_param/3；Co=四项归一化均值；Eff=四项归一化均值（S_method原始范围[-2.5,2.5]，映射到[0,1]）；IA=min(Com,Co,Eff)。${r.branches.length>1?'多参考：先对各分项取最低分，再汇总；区间保留分支差异。':''} 暂定分采用已知分数区间中点；新解析时间按名义时长计分并保留时间变化所对应区间。</p><details><summary>题目</summary><pre>${esc(r.question)}</pre></details><div class="grid"><details open><summary>原始回答</summary><pre>${esc(r.answer)}</pre></details><details open><summary>参考 protocol</summary>${r.references.map(x=>`<h4>${esc(x.branch)}</h4><pre>${esc(x.steps.join('\\n'))}</pre>`).join('')}</details></div><details><summary>本例评分数据</summary><pre>${esc(JSON.stringify(r.metrics,null,2))}</pre></details>`;document.getElementById('detail').showModal()}
document.getElementById('query').oninput=render;document.getElementById('filter').onchange=render;render();</script></html>'''
    path.write_text(content.replace('__DATA__',encoded).replace('__MAXIMA__',json.dumps(MAXIMA)),encoding='utf8')


def main(argv=None):
    global VERSION
    VERSION=FORMAL_VERSION
    ap=argparse.ArgumentParser(description=__doc__)
    for name,default in [('inputs',DEFAULT_INPUT),('verified',DEFAULT_VERIFIED),('previous',DEFAULT_PREVIOUS),
                         ('policy',POLICY_PATH),('time-kb',KB_PATH),('output',DEFAULT_OUTPUT)]:
        ap.add_argument('--'+name,type=Path,default=default)
    ap.add_argument('--cached-checks',action='store_true',help='Replay the frozen verified checks instead of recomputing them')
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument('--independent-claims',action='store_true',help='Compatibility alias: independent operation claims are enabled by default in V6.2')
    mode.add_argument('--legacy-v5',action='store_true',help='Replay the archived V5 checks and scores without rerunning the old engine')
    args=ap.parse_args(argv)
    from cleareval_scoring.scoring_v6 import VERSION as expected_step_version
    if args.legacy_v5:
        VERSION='cleareval-complete-20261103-v1'
        expected_step_version='cleareval-correctness-20261103-v5'
        args.cached_checks=True
        if args.verified==DEFAULT_VERIFIED:args.verified=BENCHMARK/'verified_checks.json.gz'
        if args.output==DEFAULT_OUTPUT:args.output=ROOT/'benchmark-reports/legacy-v5'
    args.independent_claims=not args.legacy_v5
    policy=read(args.policy); cases=read(args.inputs)['cases']
    old=read(args.previous);kb=read(args.time_kb)['rows']
    receipt=args.verified.with_name('run_receipt.json')
    assert read(receipt)['input_sha256']==sha(args.inputs), 'Verified checks belong to a different input snapshot'
    if args.cached_checks:
        assert read(receipt)['version']==expected_step_version, 'Cached checks use a different scoring version; select the matching versioned cache'
        if args.independent_claims:
            assert read(receipt)['verified_sha256']==sha(args.verified), 'Verified cache fingerprint changed'
    decisions_path=args.inputs.with_name('adjudications.json')
    verified=read(args.verified) if args.cached_checks else verified_packets(cases,read(decisions_path),independent_claims=args.independent_claims)
    packet_map={(r['id'],r['branch']):r['packet'] for r in verified}
    previous_map={(r['input_id'],b['branch']):b['metrics'] for r in old for b in r['branches']}
    assert len(packet_map)==len(cases)==193 and len({c['id'] for c in cases})==185
    assert set(packet_map)==set(previous_map)=={(c['id'],c['branch']) for c in cases}
    branches=[]; grouped=defaultdict(list)
    for c in cases:
        assert hashlib.sha256(c['answer'].encode('utf8')).hexdigest()==c['answer_sha256'],c['id']
        p=packet_map[c['id'],c['branch']]
        assert p['version']==expected_step_version
        row=branch_score(c,p,previous_map[c['id'],c['branch']],policy,kb)
        branches.append(row);grouped[c['id']].append(row)
    rows=[combine_branches(grouped[key]) for key in sorted(grouped)]
    for r in rows:
        for k,n in r['metrics'].items():
            lo=-2.5 if k=='s_method' else 0;hi=MAXIMA.get(k,1)
            assert lo-1e-9<=n['bounds'][0]<=n['value']<=n['bounds'][1]+1e-9<=hi+2e-9,(r['id'],k,n)
    args.output.mkdir(exist_ok=True,parents=True)
    for name,items in [('scores185.json.gz',rows),('scores193.json.gz',branches)]:
        write_gzip(args.output/name,items)
    fields=[*MAXIMA,'cleareval_coverage','cleareval_sp_eligible','bio_sr','bio_sp','bio_f1','Com','Co','Eff','IA']
    table=[]
    for r in rows:
        row=dict(案例=r['id'],题号=r['question_id'],生成条件=r['generation_configuration'],方法=r['method'],状态=r['status'],
                 总分是否确定='是' if r['metrics']['IA']['bounds'][0]==r['metrics']['IA']['bounds'][1] else '否',
                 暂定分项=';'.join(r['provisional_components']))
        row.update({k:r['metrics'][k]['value'] for k in fields})
        row.update({k+'_满分':v for k,v in MAXIMA.items()})
        row.update({k+suffix:r['metrics'][k]['bounds'][i] for k in fields for i,suffix in enumerate(['_下界','_上界'])})
        row['IA_百分制']=100*r['metrics']['IA']['value'];table.append(row)
    write_csv(args.output/'185例完整评分.csv',table)
    issues=[dict(案例=r['id'],分项=k,暂定得分=r['metrics'][k]['value'],下界=r['metrics'][k]['bounds'][0],
                 上界=r['metrics'][k]['bounds'][1],原因=r['metrics'][k]['reason']) for r in rows for k in r['provisional_components']]
    if issues:write_csv(args.output/'待细化分项.csv',issues)
    # Export the existing main evaluation schema and run the shared aggregator.
    from results.oeq_metrics import METRIC_BLOCKS, protocol_scores, aggregate_items
    evaluations=[];by_configuration=defaultdict(list)
    for r in rows:
        item=dict(case_id=r['id'],question_id=r['question_id'],generation_configuration=r['generation_configuration'],
                  scoring_version=VERSION,scoring_status=r['status'],evaluation=dict(scores={
                      block:{k:dict(score=r['metrics'][k]['value'],bounds=r['metrics'][k]['bounds'],
                                    status=r['metrics'][k]['status'],reason=r['metrics'][k]['reason']) for k in definitions}
                      for block,definitions in METRIC_BLOCKS.items()}))
        shared=protocol_scores(item)
        for key,alias in [('Com','Com'),('Co','Cor'),('Eff','Eff'),('IA','I_A')]:
            assert abs(shared[alias]-r['metrics'][key]['value'])<1e-12,(r['id'],key,'main aggregation mismatch')
        evaluations.append(item);by_configuration[r['generation_configuration']].append(item)
    write_gzip(args.output/'evaluations185.json.gz',evaluations)
    main_table=[]
    for config,items in sorted(by_configuration.items()):
        aggregated=aggregate_items(items)
        assert not aggregated['excluded_items'],(config,aggregated['excluded_items'])
        matched=[r for r in rows if r['generation_configuration']==config]
        main_table.append(dict(generation_configuration=config,sample_count=len(items),
            question_ids=sorted(x['question_id'] for x in items),
            Com=aggregated['indices']['Com'],Co=aggregated['indices']['Cor'],Eff=aggregated['indices']['Eff'],
            IA=aggregated['application_index'],
            IA_bounds=[statistics.mean(r['metrics']['IA']['bounds'][i] for r in matched) for i in (0,1)],
            provisional_answers=sum(bool(r['provisional_components']) for r in matched),
            incomplete_answers=sum(r['status']=='未完成作答，计0分' for r in matched)))
    (args.output/'main_table.json').write_text(json.dumps(main_table,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    summary=dict(version=VERSION,answers=len(rows),branches=len(branches),all_numeric=len(rows),
                 statuses=dict(Counter(r['status'] for r in rows)),
                 means={k:statistics.mean(r['metrics'][k]['value'] for r in rows) for k in fields},
                 provisional_answers=sum(bool(r['provisional_components']) for r in rows),
                 provisional_components=dict(Counter(x['分项'] for x in issues)),
                 total_score_point_identified=sum(r['metrics']['IA']['bounds'][0]==r['metrics']['IA']['bounds'][1] for r in rows),
                 prior_all_point_answers=sum(r.get('all_17_point',False) for r in old),
                 original_answers_unchanged=True,new_model_calls=0)
    summary['mean_IA_bounds']=[statistics.mean(r['metrics']['IA']['bounds'][i] for r in rows) for i in (0,1)]
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    build_page(args.output/'完整评分审核.html',rows,cases)
    text=f'''# ClearEval 全量评分 · {VERSION}

185份原始回答、193个参考分支全部得到10个基础分项、Bio-SR/SP/F1及Com/Co/Eff/IA。原始回答及8项人工裁决保持不变。

- 分项已确定：{summary['statuses'].get('分项已确定',0)}例。
- 含暂定分：{summary['provisional_answers']}例；每项保留区间、原因和分数来源。
- 未完成作答：EXPAND_011、012、015，按任务未完成记0分，保留原始输出。
- 当前全185例总分均值：{100*summary['means']['IA']:.2f}/100；区间包络为[{100*summary['mean_IA_bounds'][0]:.2f}, {100*summary['mean_IA_bounds'][1]:.2f}]。
- {summary['total_score_point_identified']}例的总分已不受当前分项区间影响。区间是信息不足/分支差异的范围，不是统计置信区间。

## 打开文件

`完整评分审核.html` 可直接打开、搜索案例、按状态筛选，并查看题目、原答案、参考protocol、分项满分和计分依据。
`185例完整评分.csv` 是完整主表；`待细化分项.csv` 只列仍有区间的分项。
`scores185.json.gz` 和 `scores193.json.gz` 是紧凑机器可读结果，分别按回答和参考分支保存。

## 满分及公式

| 维度 | 分项及原始范围 |
|---|---|
| 完整性 | 步骤完整性 C_step 0–2；参数完整性 C_param 0–3 |
| 正确性 | 顺序 Co_order 0–3；方法/试剂 Co_method 0–2；浓度/配方比例 Co_param 0–2；化学安全 Co_chem 0–1 |
| 有效性 | 方法适用性 S_method −2.5–2.5；标记 S_label 0–6；RI匹配 S_trans 0–3；时间 S_time 0–3 |

Com = 0.4 C_step/2 + 0.6 C_param/3。
Co = (Co_order/3 + Co_method/2 + Co_param/2 + Co_chem)/4。
Eff = ((S_method/2.5+1)/2 + S_label/6 + S_trans/3 + S_time/3)/4。
IA = min(Com, Co, Eff)。CSV中的聚合分范围0–1，网页展示百分制。

## 本版实际接入的内容

1. 执行步骤、试剂、浓度、配方和顺序检查进入正确性分项，再参与Co与IA。Bio-SR/SP/F1同时保留为可验证步骤指标。Co仍是原有四项平均，不能与Bio-F1当作同一个指标。
2. C_step采用当前执行操作覆盖率×2，沿用最新完整评测中Com的0.4/0.6权重。这是连续覆盖率口径，并非最早的人工0/1/2模块等级。多参考案例先逐分项取最低分再汇总，并保留所有分支区间。
3. 纯试剂配制从执行步骤分母中分离；已写出的错误配方继续影响使用该配方的正确性。PBS防腐不进入扣分。
4. 时间与温度参考比较不进入正确性。重新核算12例时间缺项：其中4例PEGASOS重新匹配硬组织层级并纠正参考范围文字。其余已有时间点/区间继续沿用。
5. 参数完整性补齐024、130、161、184，其他已有参数判定继续复用。方法适用性、RI和已有标记判定也继续复用；这次没有重新调用大模型对185例做第二轮全面审查。
6. EXPAND_026：DBE计3h，透明处理共11.25h；顺序/方法/关键梯度各计0分。EXPAND_022采纳DAPI在漂白前的重要顺序错误。EXPAND_174增加用户明确指出的两项抗体后洗涤义务，降低完整性。

## 暂定分如何得到

已知分项只存在分数区间时，当前主表用区间中点作为暂定分；新解析的有界时间段在名义时长中点计算S_time，同时保留整个时间区间对应的得分范围。写明“至少”的时间用已明示最低时间形成名义分，上界未限定所带来的分数范围仍保留。多参考取最低分的规则优先于区间中点。

7例缺乏适用时间参考（098、110、131、152、153、154、157）暂定1.5/3，保留[0,3]；FlyClear的102、103标记相容性暂定3/6，保留[0,6]。这些值是待细化的计算占位，不是已验证的实测或专家评分，也不把缺参考判为生物学错误。未能配对任何执行步骤的案例，不再仅凭旧版评分给方法/浓度满分，保留其待核验区间。

FlyClear原始论文主要验证内源荧光，未找到本次Alexa标记组合的直接依据：[原始论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC6226481/)。PEGASOS硬组织时间范围仍采用既有经验窗口168/288/336h，按原始流程纠正计时范围描述：[原始论文 Methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC6082844/)。

## 评分入口和复现

正式主入口：`python OEQ_run_grading_new.py --cached-checks`，复用冻结的步骤检查并完成主评分；省略`--cached-checks`可重新计算步骤检查。当前步骤版本为`{expected_step_version}`。历史模型生成/旧评分通过`--legacy-generation`进入；`--legacy-v5`可单独复现归档的V5评分。
原始输入位于`dataset/benchmark185/2026-11-03/`；本次步骤缓存为`{repo_path(args.verified)}`。知识库为`KnowledgeBase/`，汇总策略为`complete_scoring_policy.json`，均位于仓库内，不调用新模型。
本次结果位于`{repo_path(args.output)}/`；`python results/calculate_main_table_score.py`默认输出`CURRENT_SCORING.json`指定的正式版本，按19种生成条件分别列出样本数和CCE/IA均值。5例和35例配置的题目覆盖不同，列出题号以便后续配对比较。
`evaluations185.json.gz`同时提供原有主评分结构，全部185例均经过`results/oeq_metrics.py`核对；总分使用逐案例最低值的均值。
`manifest.json`记录各输入和结果哈希；输入快照和缓存版本在运行前核对。`tests/test_complete_scoring.py`覆盖11项离线回归及全193→185例汇总验证。
'''
    if args.independent_claims:
        text+='''
## V6.2 正式版更新

句中配方与执行操作分别解析：括号、containing从句和独立配制说明不额外增加执行步骤分母。工作浓度与母液浓度分别读取，并核验明确的稀释算术。试剂配方按实际使用位置绑定，独立配方核查覆盖未匹配的执行步骤；临时染色添加物、洗涤去除对象和否定句不再改写试剂配方。数字名称、N/M变体、嵌套单位括号和被动配制句同步修正。

Bio-SR=K/N_R，Bio-SP=K/N_C，Bio-F1=2K/(N_R+N_C)。K为通过正确性核查的匹配操作数；含U个待定操作时，上界分别将K替换为K+U。试剂配制不计入执行步骤分母，明确错误仍进入相应正确性分项。

全185例/193分支复测已完成；78例应用配方与执行条件分离，16例评分值或状态变化。原始答案、分项满分、CCE权重及有效性评分均保留。详细修复及逐例差异见`experiments/formal_claims_20261105/README.md`。
'''
    (args.output/'评分说明.md').write_text(text,encoding='utf8')
    sources=[args.inputs,args.verified,receipt,decisions_path,args.previous,args.policy,args.time_kb,Path(__file__),
             ROOT/'OEQ_run_grading_new.py',ROOT/'results/oeq_metrics.py',ROOT/'results/calculate_main_table_score.py',
             ROOT/'CURRENT_SCORING.json',ROOT/'requirements-scoring.txt']
    sources+=sorted((ROOT/'cleareval_scoring').glob('*.py'))+[ROOT/'cleareval_scoring/recipe_catalog.json']
    sources+=[ROOT/'KnowledgeBase/operation_claim_rules.json']
    sources+=[ROOT/s['path'] for s in read(ROOT/'KnowledgeBase/operation_claim_rules.json')['sources'].values()]
    manifest=dict(version=VERSION,entry='OEQ_run_grading_new.py',policy=repo_path(args.policy),
                  inputs_sha256={repo_path(p):sha(p) for p in sources},
                  outputs_sha256={p.name:sha(p) for p in args.output.iterdir() if p.is_file() and p.name!='manifest.json'},
                  branch_aggregation='minimum_per_component_then_recompute_aggregates',
                  unknown_point_policy='explicitly provisional interval midpoint, not an observed score')
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
