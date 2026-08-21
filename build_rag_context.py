"""
build_rag_context.py
====================
Builds per-scenario, NON-LEAKY KB-RAG context cards for the 253 ClearEval Application
OEQs -- one JSON per question, identical across models. Consumed by the inference-time
KB-RAG / KB-RAG+self-check baselines in OEQ_run_grading_new.py
(shot_types '1-shot+KB-RAG' and '1-shot+KB-RAG+self-check').

Design: docs/superpowers/specs/2026-07-01-kb-rag-selfcheck-baseline-design.md

Leakage policy
--------------
EXPOSED (qualitative domain records):
  * method family / sample-tier support / one-line strengths-limits
  * target -> marker CANDIDATE sets (category-level; the gold marker is present in the
    set but is NOT singled out -- "Balanced" setting)
  * marker<->fluorophore and method<->fluorophore compatibility as {compatible/caution/avoid}
  * per-tier feasibility + coarse relative clearing speed
WITHHELD (evaluator numeric answer keys -- never written into prompt_block):
  * exact [t_min, t_max] / median clearing time, tau, sigma_RI
  * per-method RI_ref values, tissue native RI values
  * marker specificity tiers (0/3/6), gold/reference protocol, "best method" label,
    prior model outputs, expert scores

Retrieval is keyed ONLY on OEQ metadata (never a model parse), so it is identical for
every model. Candidate-method ranking uses a COARSE sign-based rule filter over the
demand axes + a hard sample-tier-support filter -- it deliberately does NOT reuse the
evaluator's S_method weighted-RBF formula.

Usage
-----
  python build_rag_context.py                # build all 253 -> dataset/Q+AR/rag_context/
  python build_rag_context.py --sample 3     # build all + print 3 rendered prompt_blocks
  python build_rag_context.py --qids 1 117   # build only these ids (also prints them)
  python build_rag_context.py --check-leakage# assert no withheld numeric appears in prompt_block
"""
import argparse
import json
import os
import re
import statistics

SRC_DIR = 'dataset/Q+AR/src'
KB_DIR = 'KnowledgeBase'
OUT_DIR = 'dataset/Q+AR/rag_context'


def _load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Load sources
# ---------------------------------------------------------------------------
QUESTIONS = _load(f'{SRC_DIR}/question_final.json')
DEMAND = _load(f'{SRC_DIR}/demand_vectors_all.json')
TISSUE = _load(f'{KB_DIR}/tissue.json')
METHOD_FLUOR = _load(f'{KB_DIR}/method_fluro_compati.json')
RI_REF = _load(f'{KB_DIR}/method_ri_ref.json')['ri_ref']
SIGNED = _load(f'{SRC_DIR}/model_space_signed.json')['methods']
TIME_LOOKUP = _load(f'{KB_DIR}/time_kb.json').get('lookup', {})  # {method: {tier_code: {...}}}


def _norm(s):
    return re.sub(r'[^a-z0-9+]', '', str(s or '').lower())


# Canonical method universe = the 18 methods in method_ri_ref.json.
METHODS = list(RI_REF.keys())

# canonical method -> model_space_signed key (only the 3 differ)
_SIGNED_KEY = {
    'CUBIC': 'CUBIC', 'ScaleS': 'SCALE (ScaleS)', 'MACS': 'MACS', 'iDISCO+': 'iDISCO (iDISCO+)',
    'FDISCO': 'FDISCO', 'SOLID': 'SOLID', 'SeeDB2': 'seeDB2', 'PEGASOS': 'PEGASOS',
    'BoneClear': 'BoneClear', 'Ce3D': 'Ce3D', 'TDE': 'TDE', 'ClearT2': 'ClearT2',
    'ClearSee': 'ClearSee', 'EyeCi': 'EyeCi', 'FOCM': 'FOCM', 'SWITCH': 'SWITCH',
    'uDISCO': 'uDISCO', 'FlyClear': 'FlyClear',
}
FAMILY = {
    'CUBIC': 'aqueous', 'ScaleS': 'aqueous', 'MACS': 'aqueous', 'SeeDB2': 'aqueous',
    'Ce3D': 'aqueous', 'TDE': 'aqueous', 'ClearT2': 'aqueous', 'ClearSee': 'aqueous (plant)',
    'EyeCi': 'aqueous', 'FOCM': 'aqueous', 'SWITCH': 'aqueous/hydrogel', 'FlyClear': 'aqueous (insect)',
    'iDISCO+': 'solvent (organic)', 'FDISCO': 'solvent (FP-preserving)', 'SOLID': 'solvent',
    'PEGASOS': 'solvent (high-RI, dense/bone)', 'BoneClear': 'solvent (high-RI, bone)',
    'uDISCO': 'solvent (high-RI, whole-body)',
}

# Coarse RI band per method (0=low ~1.45-1.47, 1=mid ~1.49-1.50, 2=high ~1.52-1.56).
# Used ONLY to re-rank candidates by tissue-RI-family match; exact RI values never exposed.
METHOD_RI_BAND = {
    'CUBIC': 0, 'ScaleS': 0, 'MACS': 0, 'SeeDB2': 0, 'TDE': 0, 'ClearT2': 0, 'EyeCi': 0,
    'FOCM': 0, 'SWITCH': 0, 'FlyClear': 0, 'iDISCO+': 0, 'FDISCO': 0, 'SOLID': 0, 'ClearSee': 0,
    'Ce3D': 1, 'uDISCO': 1, 'PEGASOS': 2, 'BoneClear': 2,
}
RI_BAND_LABEL = {
    0: 'aqueous / low-RI media (soft neural or low-density tissue)',
    1: 'moderate-RI media (soft viscera)',
    2: 'high-RI solvent media (dense, hard, or whole-body tissue)',
}


def _tissue_ri_band(tissue):
    """Coarse RI band for a tissue from its Chinese label (domain rule, not the RI answer key)."""
    s = str(tissue or '')
    if any(k in s for k in ('骨', '牙', '耳蜗', '颅')):
        return 2  # mineralized / hard tissue
    if any(k in s for k in ('皮肤', '肌', '心')):
        return 2  # dense muscle / skin
    if any(k in s for k in ('肝', '肾', '脾', '肺', '胰', '肠', '胃', '肿瘤', '淋巴', '乳腺',
                            '前列腺', '全身', '胎盘', '睾丸', '脂肪')):
        return 1  # soft viscera
    return 0  # brain / CNS / eye / embryo / plant / organoid -> low-RI


def _cap(method):
    """Signed capability dict for a canonical method (or {} if absent)."""
    return SIGNED.get(_SIGNED_KEY.get(method, method), {})


def _tier_supported(method, tier_code):
    """Mirror the evaluator applicability gate: is (method, tier_code) in time_kb.lookup?"""
    if not tier_code:
        return False
    return bool(TIME_LOOKUP.get(method, {}).get(tier_code))


# ---- fluorophore families exposed as compatibility records --------------------
# tissue.json compat column  ->  (display label, representative method_fluro_compati key)
FLUOR_COLS = [
    ('GFP/YFP', 'GFP/YFP', 'GFP'),
    ('tdTomato/RFP ', 'tdTomato/RFP', 'tdTomato'),
    ('DAPI/Hoechst', 'DAPI/Hoechst', 'DAPI'),
    ('PI/Draq5 ', 'PI/Draq5', 'Propidium iodide'),
    ('AlexaFluor 488', 'AlexaFluor 488', 'Alexa Fluor 488'),
    ('AlexaFluor 568/Cy3', 'AlexaFluor 568 / Cy3', 'Alexa Fluor 568'),
    ('AlexaFluor 647/Cy5 ', 'AlexaFluor 647 / Cy5', 'Alexa Fluor 647'),
    ('Lectin', 'Lectin', 'Lectin'),
]
_MF_BY_METHOD = {_norm(r['method']): r for r in METHOD_FLUOR}

# demand axis -> (signed capability key, higher-is-better?, human-readable requirement)
AXES = [
    ('fluorescence_protein_preservation', 'F_fp', True,
     'Preserve endogenous fluorescent-protein signal (GFP/YFP/tdTomato) -- avoid FP-quenching solvent clearing.'),
    ('dye_permeability', 'P_dye', True,
     'Deep antibody / dye penetration into thick or dense tissue is required.'),
    ('clearing_challenge', 'C_opt', True,
     'High clearing difficulty (large / dense / lipid- or pigment-rich) -- strong clearing power needed.'),
    ('geometry_preference', 'M_geo', True,
     'Preserve morphology / geometry (minimal shrinkage or distortion).'),
    ('operational_economy', 'E_ops', True,
     'Speed / cost / protocol simplicity is a priority.'),
    ('safety_compatibility', 'S_safe', True,
     'Prefer low-toxicity, lab-safe reagents.'),
]


# ---------------------------------------------------------------------------
# Card A: scenario slot
# ---------------------------------------------------------------------------
def _demanded_axes(qid):
    """Return list of (axis_key, requirement_text) for axes the question actually cares
    about (weight > 0 and target >= 0.5). Empty if no demand vector for this qid."""
    dv = DEMAND.get(str(qid))
    if not dv:
        return []
    out = []
    for axis, _capkey, _hib, text in AXES:
        cell = dv.get(axis, {})
        if float(cell.get('weight', 0) or 0) > 0 and float(cell.get('target', 0) or 0) >= 0.5:
            out.append((axis, text))
    return out


def _scenario_card(q):
    th = q.get('tissue_hierarchy_from_tissue_xlsx', {})
    targets = []
    for t in q.get('marker_query_targets', []):
        targets.append({
            'labeling_target': t.get('structure_or_cell_subtype', ''),
            'major_category': t.get('major_category', ''),
            'subcategory': t.get('subcategory', ''),
            'query_path': t.get('query_path', ''),
        })
    dem = _demanded_axes(q['question_id'])
    return {
        'tissue': th.get('tissue_inferred', ''),
        'sample_tier_code': th.get('tissue_tier_code', ''),
        'sample_tier_label': th.get('tissue_tier_label', ''),
        'targets': targets,
        'requirements': [text for _axis, text in dem],
        'requirements_source': 'demand_vector' if dem else 'tissue_tier_only',
    }


# ---------------------------------------------------------------------------
# Card B: target -> marker candidates (Balanced)
# ---------------------------------------------------------------------------
def _target_marker_card(target):
    major = target.get('major_category', '')
    sub = target.get('subcategory', '')
    gold = [m for m in (target.get('marker_name'),) if m]
    # rows in the same major category, subcategory first
    same_cat = [r for r in TISSUE if r.get('大类', '') == major]
    same_cat.sort(key=lambda r: 0 if r.get('亚类', '') == sub else 1)
    candidates = []
    for r in same_cat:
        for k in ('推荐标志物 1', '推荐标志物 2'):
            v = (r.get(k) or '').strip()
            if v and v not in candidates:
                candidates.append(v)
        if len(candidates) >= 10:
            break
    # guarantee the gold marker(s) are present within the set (not singled out)
    for g in gold:
        g = g.strip()
        if g and g not in candidates:
            candidates.append(g)
    # generic + category-aware false-friends (no leakage of the specific gold)
    false_friends = [
        'A structural / pan-lineage marker does not substitute for a target-specific marker.',
        'Nuclear counterstains (DAPI, Hoechst, PI) are not target-specific labeling.',
    ]
    if major == '中枢神经':
        false_friends.insert(0, 'Pan-neuronal markers (NeuN, beta-III tubulin) do not identify a functional/subtype-specific target.')
    return {
        'labeling_target': target.get('structure_or_cell_subtype', ''),
        'category': f'{major} > {sub}' if sub else major,
        'candidate_markers': candidates,
        'valid_labeling_strategy': 'target-specific immunostaining (anti-<marker>) or a matching genetic reporter',
        'false_friends': false_friends,
    }


# ---------------------------------------------------------------------------
# Card C: method mini-index + top-5 candidate cards
# ---------------------------------------------------------------------------
def _method_oneliner(method, tier=None):
    cap = _cap(method)
    bits = [FAMILY.get(method, '')]
    f = cap.get('F_fp', 0)
    if f >= 0.3:
        bits.append('FP-friendly')
    elif f <= -0.3:
        bits.append('quenches endogenous FPs (use antibodies/dyes)')
    if cap.get('P_dye', 0) >= 0.3:
        bits.append('good dye penetration')
    elif cap.get('P_dye', 0) <= -0.3:
        bits.append('limited dye penetration')
    if cap.get('C_opt', 0) >= 0.85:
        bits.append('strong clearing')
    if cap.get('S_safe', 0) <= -0.5:
        bits.append('hazardous solvents')
    if tier:  # per-method clearing-time hint for this tier (replaces the misleading E_ops "faster" tag)
        bits.append(f'clearing time {_method_time_bucket(method, tier)}')
    ps = RI_REF.get(method, {}).get('primary_sample', '')
    return f"{method}: " + '; '.join([b for b in bits if b]) + (f" (typical: {ps})" if ps else '')


def _rank_methods(q, ri_aware=False):
    """Coarse rule-based top-5 retrieval. Hard filter: tier-supported. Rank: coarse
    sign-match count over demanded axes (NOT the S_method RBF). Tie-break: clearing power.
    If ri_aware, the PRIMARY key is RI-family match to the tissue class (recovers
    transparency validity on soft tissue) via a coarse 3-band domain rule -- not the RI
    answer key."""
    tissue = q.get('tissue_hierarchy_from_tissue_xlsx', {}).get('tissue_inferred', '')
    tier = q.get('tissue_hierarchy_from_tissue_xlsx', {}).get('tissue_tier_code', '')
    tband = _tissue_ri_band(tissue)
    supported = [m for m in METHODS if _tier_supported(m, tier)]
    dv = DEMAND.get(str(q['question_id']))
    demanded = []
    if dv:
        for axis, capkey, _hib, _t in AXES:
            cell = dv.get(axis, {})
            if float(cell.get('weight', 0) or 0) > 0 and float(cell.get('target', 0) or 0) >= 0.5:
                demanded.append(capkey)

    def pts_of(m):
        cap = _cap(m)
        pts = 0
        for capkey in demanded:
            v = cap.get(capkey, 0)
            if capkey == 'C_opt':
                pts += 1 if v >= 0.85 else (0 if v >= 0.6 else -1)
            else:
                pts += 1 if v >= 0.3 else (-1 if v <= -0.3 else 0)
        return pts

    def score(m):
        cap = _cap(m)
        if ri_aware:
            ri_match = -abs(METHOD_RI_BAND.get(m, 1) - tband)  # 0 best, then -1, -2
            return (ri_match, pts_of(m), cap.get('C_opt', 0))
        return (pts_of(m), cap.get('C_opt', 0))

    supported.sort(key=score, reverse=True)
    return supported[:5], supported


def _method_full_card(method, tier):
    cap = _cap(method)
    ri = RI_REF.get(method, {})
    strengths, limits = [], []
    if cap.get('F_fp', 0) >= 0.3:
        strengths.append('preserves endogenous fluorescent proteins')
    if cap.get('P_dye', 0) >= 0.3:
        strengths.append('supports deep antibody/dye penetration')
    if cap.get('C_opt', 0) >= 0.85:
        strengths.append('high clearing power for dense/large tissue')
    if cap.get('M_geo', 0) >= 0.3:
        strengths.append('preserves morphology')
    if cap.get('S_safe', 0) >= 0.3:
        strengths.append('low-toxicity reagents')
    if cap.get('F_fp', 0) <= -0.3:
        limits.append('quenches endogenous fluorescent proteins (label with antibodies/dyes)')
    if cap.get('P_dye', 0) <= -0.3:
        limits.append('poor deep-dye penetration')
    if cap.get('M_geo', 0) <= -0.3:
        limits.append('tissue shrinkage/distortion risk')
    if cap.get('S_safe', 0) <= -0.5:
        limits.append('hazardous organic solvents (fume hood)')
    return {
        'method': method,
        'family': FAMILY.get(method, ''),
        'typical_sample': ri.get('primary_sample', ''),
        'established_for_this_tier': _tier_supported(method, tier),
        'strengths': strengths,
        'limitations': limits,
        'time_scale': _method_time_bucket(method, tier),
        'ri_medium_summary': f'{FAMILY.get(method, "")} clearing medium (qualitative; numeric RI withheld)',
        'evidence': ri.get('source', ''),
    }


# ---------------------------------------------------------------------------
# Card D: method x fluorophore compatibility records (status)
# ---------------------------------------------------------------------------
def _status_from_score(v):
    if v is None:
        return None
    if v >= 0.7:
        return 'compatible'
    if v >= 0.45:
        return 'caution'
    return 'avoid'


def _compat_records(top_methods, target_cards):
    records = []
    for m in top_methods:
        row = _MF_BY_METHOD.get(_norm(m), {})
        per = {}
        for _col, label, mfkey in FLUOR_COLS:
            st = _status_from_score(row.get(mfkey))
            if st:
                per[label] = st
        records.append({'method': m, 'fluorophore_status': per})
    # marker-level "avoid" notes from tissue.json 0-cells for candidate markers
    marker_cautions = []
    seen = set()
    cand_markers = {mk for tc in target_cards for mk in tc['candidate_markers']}
    tissue_by_marker = {}
    for r in TISSUE:
        for k in ('推荐标志物 1', '推荐标志物 2'):
            v = (r.get(k) or '').strip()
            if v:
                tissue_by_marker.setdefault(v, r)
    for mk in cand_markers:
        r = tissue_by_marker.get(mk)
        if not r:
            continue
        avoid = [label for col, label, _mf in FLUOR_COLS if r.get(col) == 0]
        if avoid and mk not in seen:
            seen.add(mk)
            marker_cautions.append({'marker': mk, 'avoid_fluorophores': avoid})
    return {'method_fluorophore': records, 'marker_fluorophore_cautions': marker_cautions[:12]}


# ---------------------------------------------------------------------------
# Card E: RI / timing / tier feasibility (qualitative only)
# ---------------------------------------------------------------------------
def _tier_timing_bucket(tier_code):
    """Coarse order-of-magnitude label for a tier, from the median of supported-method
    median times. The raw hour values are NEVER written out -- only the 4-way label."""
    meds = []
    for m in METHODS:
        cell = TIME_LOOKUP.get(m, {}).get(tier_code)
        if cell and cell.get('clearing_time_median_h'):
            meds.append(float(cell['clearing_time_median_h']))
    if not meds:
        return 'unknown'
    med = statistics.median(meds)
    if med < 8:
        return 'a few hours'
    if med < 36:
        return 'overnight to ~1 day'
    if med < 168:
        return 'several days'
    return 'about one to several weeks'


_PARENT_SUB_T = {
    'T07_HARD_TISSUE_BONE_TOOTH_COCHLEA': ['T07A_SMALL_HARD_TISSUE_BONE_TOOTH', 'T07B_LARGE_HARD_TISSUE_BONE_COCHLEA'],
    'T11_PLANT_WHOLE_SEEDLING': ['T11A_PLANT_LEAF_SMALL_SEEDLING', 'T11B_PLANT_WHOLE_SEEDLING_ROOT'],
}


def _method_median_h(method, tier_code):
    """This method's median clearing time for the tier (parent-tier T07/T11 fallback)."""
    cell = TIME_LOOKUP.get(method, {}).get(tier_code)
    if cell and cell.get('clearing_time_median_h') is not None:
        return float(cell['clearing_time_median_h'])
    meds = [float(TIME_LOOKUP[method][s]['clearing_time_median_h'])
            for s in _PARENT_SUB_T.get(tier_code, [])
            if TIME_LOOKUP.get(method, {}).get(s, {}).get('clearing_time_median_h') is not None]
    return min(meds) if meds else None


def _method_time_bucket(method, tier_code):
    """Per-method qualitative clearing-time hint for THIS tier (no exact hours exposed)."""
    med = _method_median_h(method, tier_code)
    if med is None:
        return 'timing not established for this tier'
    if med < 8:
        return 'about a few hours'
    if med < 24:
        return 'about overnight (~1 day)'
    if med < 72:
        return 'about 1-3 days'
    if med < 168:
        return 'about several days to a week'
    if med < 336:
        return 'about 1-2 weeks'
    return 'about 2+ weeks'


def _feasibility_card(top_methods, tier_code):
    per_method_time = {m: _method_time_bucket(m, tier_code) for m in top_methods}
    return {
        'sample_tier': tier_code,
        'established_methods_for_tier': [m for m in top_methods if _tier_supported(m, tier_code)],
        'per_method_clearing_time': per_method_time,
        'timing_caution': 'Match your stated TOTAL clearing time to the per-method hint for the method you choose '
                          '(aqueous methods are generally slower than organic-solvent methods for the same sample).',
        'withheld': ['exact [t_min, t_max]', 'exact clearing tolerance', 'gold protocol time', 'numeric RI targets'],
    }


# ---------------------------------------------------------------------------
# Render compact prompt block
# ---------------------------------------------------------------------------
def _render(scn, target_cards, mini_index, method_cards, compat, feas, ri_guidance=None):
    L = []
    L.append('=== Retrieved Knowledge-Base Context (domain records; numeric RI/time answer keys withheld) ===')
    # A
    L.append(f"[Scenario] Tissue: {scn['tissue']} | Sample tier: {scn['sample_tier_label']} ({scn['sample_tier_code']})")
    tnames = '; '.join(f"{t['labeling_target']} ({t['query_path']})" for t in scn['targets'])
    L.append(f"Labeling target(s): {tnames}")
    if scn['requirements']:
        L.append('Requirements: ' + ' '.join('- ' + r for r in scn['requirements']))
    if ri_guidance:
        L.append(f"RI guidance: this tissue class is best matched by {ri_guidance}; prefer a "
                 f"clearing method in that family for refractive-index validity unless deep "
                 f"penetration into dense tissue forces a stronger solvent.")
    # B
    L.append('')
    L.append('[Target -> marker candidates] (pick a target-specific marker from these; a valid answer is within each set)')
    for tc in target_cards:
        L.append(f"- {tc['labeling_target']} [{tc['category']}]: {', '.join(tc['candidate_markers'])}")
        L.append(f"  strategy: {tc['valid_labeling_strategy']}; caution: {' '.join(tc['false_friends'])}")
    # C
    L.append('')
    _order = 'ordered by RI-family match to this tissue and sample-tier support' if ri_guidance else 'top matches by qualitative fit'
    L.append(f'[Candidate clearing methods for this sample tier] ({_order}; you MAY choose any method established for this tier)')
    for i, mc in enumerate(method_cards, 1):
        tag = 'established for this tier' if mc['established_for_this_tier'] else 'NOT established for this tier'
        strengths = ', '.join(mc['strengths']) or 'general-purpose'
        limits = ('; limits: ' + ', '.join(mc['limitations'])) if mc['limitations'] else ''
        tsc = f"; clearing time {mc['time_scale']}" if mc.get('time_scale') else ''
        L.append(f"{i}. {mc['method']} [{mc['family']}] ({tag}): {strengths}{limits}{tsc}")
    L.append('Mini-index (all methods, escape hatch): ' + ' | '.join(mini_index))
    # D
    L.append('')
    L.append('[Method x fluorophore compatibility] (status)')
    for rec in compat['method_fluorophore']:
        pairs = ', '.join(f"{k}={v}" for k, v in rec['fluorophore_status'].items())
        L.append(f"- {rec['method']}: {pairs}")
    if compat['marker_fluorophore_cautions']:
        groups = {}
        order = []
        for c in compat['marker_fluorophore_cautions']:
            key = ', '.join(c['avoid_fluorophores'])
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(c['marker'])
        mc = '; '.join(f"avoid {fl} for: {', '.join(groups[fl])}" for fl in order)
        L.append('Marker-level cautions: ' + mc)
    # E
    L.append('')
    est = ', '.join(feas['established_methods_for_tier']) or '(none of the above)'
    _hard = (' Choose ONLY a method established for this tier; methods not established for it '
             'are scored zero on transparency and timing.') if ri_guidance else ''
    times = '; '.join(f"{m}: {t}" for m, t in feas.get('per_method_clearing_time', {}).items())
    L.append(f"[Feasibility] Established methods for tier {feas['sample_tier']}: {est}. "
             f"Per-method clearing-time hint (match your stated total clearing time to your chosen method): {times}. "
             f"{feas['timing_caution']}{_hard}")
    return '\n'.join(L)


# ---------------------------------------------------------------------------
# Build one question
# ---------------------------------------------------------------------------
def build_one(q, ri_aware=False):
    qid = q['question_id']
    th = q.get('tissue_hierarchy_from_tissue_xlsx', {})
    tier = th.get('tissue_tier_code', '')
    scn = _scenario_card(q)
    # Dedup targets that share the same subtype+category (avoids repeated identical cards).
    target_cards = []
    _seen_t = set()
    for t in q.get('marker_query_targets', []):
        key = (t.get('structure_or_cell_subtype', ''), t.get('major_category', ''), t.get('subcategory', ''))
        if key in _seen_t:
            continue
        _seen_t.add(key)
        target_cards.append(_target_marker_card(t))
    top5, _all_supported = _rank_methods(q, ri_aware=ri_aware)
    method_cards = [_method_full_card(m, tier) for m in top5]
    mini_index = [_method_oneliner(m, tier) for m in METHODS]
    compat = _compat_records(top5, target_cards)
    feas = _feasibility_card(top5, tier)
    ri_guidance = None
    if ri_aware:
        ri_guidance = RI_BAND_LABEL[_tissue_ri_band(th.get('tissue_inferred', ''))]
        feas['ri_family_guidance'] = ri_guidance
    prompt_block = _render(scn, target_cards, mini_index, method_cards, compat, feas, ri_guidance)
    return {
        'question_id': qid,
        'leakage_policy': 'method properties + compatibility records exposed as qualitative status; '
                          'numeric RI/time answer keys, marker specificity tiers, and gold protocol withheld',
        'retrieval': 'metadata-keyed (model-agnostic); candidate methods via coarse tier-support + '
                     'demand-axis sign filter, NOT the evaluator S_method formula',
        'scenario_slot_card': scn,
        'target_marker_cards': target_cards,
        'method_mini_index': mini_index,
        'candidate_method_cards': method_cards,
        'compatibility_records': compat,
        'feasibility_card': feas,
        'prompt_block': prompt_block,
    }


# Numeric answer-key strings that must NOT appear in any prompt_block.
# Returns (ri_decimal_terms, multi_digit_time_terms). Single-digit integers are NOT
# guarded individually (they collide with tissue labels like "5-12mm", marker names like
# "PGP9.5", tier codes like "T04"); a standalone hour count is caught by the units regex.
def _leak_terms():
    ri_terms = {f"{v['ri']}" for v in RI_REF.values()}
    time_terms = set()
    for _m, tiers in TIME_LOOKUP.items():
        for _tc, cell in tiers.items():
            for key in ('clearing_time_min_h', 'clearing_time_median_h', 'clearing_time_max_h'):
                val = cell.get(key)
                if val is not None:
                    s = f"{val}"
                    if len(re.sub(r'\D', '', s)) >= 2:  # only 2+ digit windows (e.g. 168, 252)
                        time_terms.add(s)
    return ri_terms, time_terms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sample', type=int, default=0, help='print N rendered prompt_blocks after building')
    ap.add_argument('--qids', nargs='*', type=int, default=None, help='build only these question ids')
    ap.add_argument('--check-leakage', action='store_true', help='assert no withheld numeric appears in prompt_block')
    ap.add_argument('--outdir', default=OUT_DIR, help='output directory for rag_context_*.json')
    ap.add_argument('--ri-aware', action='store_true',
                    help='v2: rank candidate methods by RI-family match to the tissue class + harden tier-support guidance')
    args = ap.parse_args()

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    qs = QUESTIONS if not args.qids else [q for q in QUESTIONS if q['question_id'] in set(args.qids)]

    built = []
    for q in qs:
        card = build_one(q, ri_aware=args.ri_aware)
        path = os.path.join(outdir, f"rag_context_{card['question_id']}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(card, f, indent=2, ensure_ascii=False)
        built.append(card)
    print(f"Built {len(built)} rag_context files (ri_aware={args.ri_aware}) -> {outdir}/")

    if args.check_leakage:
        ri_terms, time_terms = _leak_terms()
        hits = []
        for c in built:
            block = c['prompt_block']
            # explicit hour counts (e.g. "252 h", "168 hours") must never appear
            if re.search(r'\d+(?:\.\d+)?\s*(?:h|hr|hrs|hour|hours)\b', block, re.I):
                hits.append((c['question_id'], 'explicit-hour-count'))
            # exact RI decimals and 2+ digit time windows, only as standalone tokens
            for t in list(ri_terms) + list(time_terms):
                if re.search(r'(?<![\w.])' + re.escape(t) + r'(?![\w.])', block):
                    hits.append((c['question_id'], t))
        if hits:
            print(f"LEAKAGE CHECK FAILED: {len(hits)} answer-key hits, e.g. {hits[:10]}")
        else:
            print(f"LEAKAGE CHECK PASSED: no withheld RI/time numeric "
                  f"({len(ri_terms)} RI + {len(time_terms)} time terms guarded) in any prompt_block.")

    for c in built[:args.sample]:
        print('\n' + '=' * 90)
        print(f"question_id = {c['question_id']}")
        print('=' * 90)
        print(c['prompt_block'])


if __name__ == '__main__':
    main()
