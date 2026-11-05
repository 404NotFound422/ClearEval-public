"""Typed bilingual pilot representation. No case IDs or annotation lookup.

Literal spans and inferred ranking features are distinguished. Exact formula,
sample-state and full biological correctness are not certified by this parser.
"""
import math
import re

DASH = r'[-\s\u2010-\u2015]?'
MATERIALS = {
    'tert_butanol': [r'tert' + DASH + r'butanol', r't' + DASH + r'butanol', '叔丁醇'],
    'methanol': [r'methanol', r'(?<!\w)MeOH(?:_\d+)?', '甲醇'],
    'ethanol': [r'(?<!m)ethanol', r'(?<!\w)EtOH', '乙醇'],
    'dcm': [r'dichloromethane', r'(?<!\w)DCM(?:100)?', '二氯甲烷'],
    'dbe': [r'di' + DASH + r'benzyl' + DASH + r'ether', r'(?<!\w)DBE(?:100)?', '二苄醚'],
    'thf': [r'tetrahydrofuran', r'(?<!\w)THF(?!\w)', '四氢呋喃'],
    'babb_d4': [r'BABB' + DASH + r'D4(?!\d)'],
    'babb_d10': [r'BABB' + DASH + r'D10(?!\d)'],
    'babb_d15': [r'BABB' + DASH + r'D15(?!\d)'],
    'babb': [r'BABB(?!' + DASH + r'D\d)'],
    'bb_peg': [r'BB' + DASH + r'PEG'],
    'tb_peg': [r'tB' + DASH + r'PEG'],
    'edta': [r'(?<!\w)EDTA(?!\w)'],
    'quadrol': [r'Quadrol'],
    'ammonium': [r'ammonium', '氨水'],
    'pbs': [r'(?<!\w)PBS(?:T|\(–\)|\(-\))?(?!\w)', r'phosphate.buffered saline'],
    'ptwh': [r'(?<!\w)PTwH(?!\w)'],
    'ptx2': [r'(?<!\w)PTx2(?!\w)'],
    'water': [r'(?<!\w)(?:water|ddH2O|dH2O|H2O)(?!\w)', '去离子水', '蒸馏水'],
    'formamide': [r'(?<!dimethyl)formamide', '甲酰胺'],
    'peg': [r'(?<![\w-])PEG\s*(?:8000)?(?!\w)', r'polyethylene glycol'],
    'fructose': [r'fructose', '果糖'],
    'saponin': [r'saponin', '皂苷'],
    'sds': [r'(?<!\w)SDS(?!\w)', r'sodium dodecyl sulfate'],
    'dmso': [r'(?<!\w)DMSO(?!\w)', r'dimethyl sulfoxide'],
    'dmf': [r'(?<!\w)DMF(?!\w)', r'dimethylformamide'],
    'urea': [r'urea', '尿素'],
    'glycerol': [r'glycerol', '甘油'],
    'sorbitol': [r'sorbitol', '山梨醇'],
    'hydrogen_peroxide': [r'H[2₂]O[2₂]', r'hydrogen peroxide'],
    'triton_x100': [r'Triton' + DASH + r'X' + DASH + r'100'],
    'tween20': [r'Tween' + DASH + r'20'],
    'tde': [r'(?<!\w)TDE(?!\w)', r'thiodiethanol'],
    'dapi': [r'(?<!\w)DAPI(?!\w)'],
    'hoechst': [r'Hoechst(?:\s*33342)?'],
    'antibody': [r'antibod(?:y|ies)', '一抗', '二抗', '一次抗体', '二次抗体'],
    'ce3d': [r'Ce3D'],
    'focm': [r'FOCM'],
    'boneclear': [r'BoneClear solution'],
    'seedb2g': [r'SeeDB2' + DASH + r'G'],
    'seedb2s': [r'SeeDB2' + DASH + r'S'],
}
for k in ['0', '1', '2', '3', '4D25', '4D2.5']:
    MATERIALS['scales' + k.lower()] = [r'Sca(?:_l_e|le)S' + re.escape(k) + r'(?![\dD.])']
MATERIALS['cubic_r1'] = [r'CUBIC' + DASH + r'R1(?!\w)']
MATERIALS['cubic_r2'] = [r'CUBIC' + DASH + r'R2(?!\w)']
FORMULATIONS = {k for k in MATERIALS if k.startswith(('scales', 'cubic_', 'seedb2'))} | {'ce3d', 'focm', 'boneclear', 'bb_peg', 'tb_peg', 'babb', 'babb_d4', 'babb_d10', 'babb_d15'}
NUM = r'\d+(?:\.\d+)?'
PERCENT = re.compile(r'(' + NUM + r')\s*(?:(?:vol|wt)\s*)?%', re.I)
TIME = re.compile(r'(' + NUM + r')(?:\s*[-–—]\s*(' + NUM + r'))?\s*(hours?|hrs?|h|minutes?|mins?|min|days?|d|seconds?|secs?|s)\b', re.I)
TEMP = re.compile(r'(-?' + NUM + r')(?:\s*[-–—]\s*(-?' + NUM + r'))?\s*(?:°\s*C|℃|ºC|degrees?\s*C(?:elsius)?|\bC\b)', re.I)


def norm(text):
    return re.sub(r'\s+', ' ', text).strip()


def nominal_normalize(text):
    # Surface-only diagnostic: no translation, chemical or parameter rewrite.
    return re.sub(r'\bIncubation\b', 'Incubate', text, flags=re.I)


def mentions(text, method):
    patterns = dict(MATERIALS)
    if method == 'CUBIC':
        patterns['cubic_r1'] = patterns['cubic_r1'] + [r'reagent' + DASH + r'1(?!\w)']
        patterns['cubic_r2'] = patterns['cubic_r2'] + [r'reagent' + DASH + r'2(?!\w)']
    if method == 'SeeDB2':
        patterns['seedb2_solution1'] = [r'solution\s*1']
        patterns['seedb2_solution2'] = [r'solution\s*2']
    found = []
    for ident, expressions in patterns.items():
        for expression in expressions:
            for m in re.finditer(expression, text, re.I):
                found.append({'id': ident, 'start': m.start(), 'end': m.end(), 'text': m[0]})
    unique = {(m['id'], m['start'], m['end']): m for m in found}
    found = sorted(unique.values(), key=lambda m: (m['start'], -(m['end'] - m['start'])))
    return [m for m in found if not any(o['start'] <= m['start'] and o['end'] >= m['end'] and o['end'] - o['start'] > m['end'] - m['start'] for o in found)]


def parameter(text, name):
    # Explicit labeled fields take precedence over duplicate prose and incidental timings.
    label = 'Time' if name == 'duration' else 'Temperature'
    m = re.search(label + r'\s*:\s*([^\n)）;；]+)', text, re.I)
    segment, offset = (m[1], m.start(1)) if m else (text, 0)
    regex = TIME if name == 'duration' else TEMP
    hits = list(regex.finditer(segment))
    if name == 'temperature' and not hits:
        sym = re.search(r'\bRT\b|room temperature', segment, re.I)
        if sym:
            return {'value': 'RT', 'evidence': {'start': offset + sym.start(), 'end': offset + sym.end(), 'text': sym[0]}}
    if not hits:
        return {'value': None, 'evidence': None}
    values = []
    for hit in hits:
        factor = 1
        if name == 'duration':
            u = hit[3].lower()
            factor = 1440 if u.startswith('d') else 60 if u.startswith('h') else 1 / 60 if u.startswith('s') else 1
        a, b = float(hit[1]) * factor, float(hit[2] or hit[1]) * factor
        prefix = segment[:hit.start()].rstrip()
        if prefix.endswith(('<', '>', '≤', '≥')) or re.search(r'at least|at most|up to', prefix, re.I):
            return {'value': None, 'qualifier': 'bounded_or_qualified', 'evidence': {'start': offset + hit.start(), 'end': offset + hit.end(), 'text': hit[0]}}
        values.append([round(a, 8), round(b, 8)])
    if any(v != values[0] for v in values):
        return {'value': None, 'qualifier': 'multiple_or_conditional_values', 'evidence': None}
    hit = hits[0]
    return {'value': values[0], 'evidence': {'start': offset + hit.start(), 'end': offset + hit.end(), 'text': hit[0]},
            'repeat_expression': bool(re.search(r'\d\s*[×x]\s*\d|repeat|times|次', segment, re.I))}


def action(text, heading=''):
    main = re.split(r'[（(]\s*Temperature\s*:', text, flags=re.I)[0]
    if re.search(r'\b(?:store|stored|storage)\b|保存', main, re.I) and not re.search(r'\bincubat', main[:45], re.I):
        return 'store', 'literal_action'
    if re.search(r'\b(?:mount|mounting|image|imaging)\b|装片|装载|成像装', main[:70], re.I):
        return 'mount', 'literal_action'
    if re.search(r'deScaling|restore sample|复水', main, re.I):
        return 'rehydrate', 'literal_action'
    if re.search(r'\bwash(?:ing)?\b|\brinse\b|漂洗|清洗|洗涤', main[:100], re.I):
        return 'wash', 'literal_action'
    if re.search(r'\bincubat|\bimmerse|\bdehydrat|\btreatment\b|\bthermally clear|\brotate|\breplace|\brefresh|\btransfer|\btransition|孵育|浸没|置换|更换|强去脂|轻摇|静置', main, re.I):
        return 'incubate', 'literal_or_contact_action'
    if re.search(r'\b(?:antibody|staining|labeling)\b|一抗|二抗|核染', main, re.I):
        return 'label', 'literal_action'
    if heading and (PERCENT.search(main) or mentions(main, '')) and parameter(text, 'duration')['value'] is not None:
        return 'incubate', 'inferred_from_medium_duration_and_heading'
    return None, 'unresolved'


def phase(text, heading, primary, act):
    if act == 'store':
        return 'storage'
    if act == 'mount':
        return 'mounting'
    if act == 'rehydrate':
        return 'rehydration'
    if re.search(r'immuno|pre.label|labeling|stain|一抗|二抗|免疫|核染|封闭|permeabil|渗透/封闭', heading, re.I):
        return 'labeling'
    if re.search(r'pre.?treat|pre.?stain|预处理|预脱水', heading, re.I):
        return 'pretreatment'
    if primary & {'edta'}:
        return 'decalcification'
    if primary & {'methanol', 'ethanol', 'tert_butanol', 'thf', 'dcm'}:
        return 'solvent_processing'
    if primary & {'dbe', 'babb', 'babb_d4', 'babb_d10', 'babb_d15', 'bb_peg', 'seedb2g', 'seedb2s', 'tde'}:
        return 'ri_matching'
    if re.search(r'refractive|\bRI\b|折射率', heading, re.I):
        return 'ri_matching'
    if primary & {'quadrol', 'ammonium', 'hydrogen_peroxide'}:
        return 'decolorization'
    if act == 'wash':
        return 'washing'
    if primary:
        return 'clearing'
    return 'unknown'


def typed_operation(text, heading, method):
    ms = mentions(text, method)
    act, action_origin = action(text, heading)
    # Material arguments exclude chemicals mentioned only as what gets removed.
    stop = re.search(r'\bto (?:remove|wash)\b|洗去|去除', text, re.I)
    eligible = [m for m in ms if stop is None or m['start'] < stop.start()]
    materials = {m['id'] for m in eligible}
    named = {k for k in materials if k in FORMULATIONS or k.startswith('seedb2_solution')}
    primary = named or materials
    if len(primary) > 1:
        primary = primary - {'water', 'pbs', 'triton_x100', 'tween20', 'urea', 'glycerol', 'sorbitol', 'antibody', 'dapi', 'hoechst', 'saponin'} or primary
    if act == 'wash':
        primary = materials & {'pbs', 'ptwh', 'ptx2', 'water', 'methanol', 'ethanol', 'dcm'} or primary
    concentrations = {}
    concentration_spans = []
    for mention in eligible:
        if mention['id'] not in primary:
            continue
        prefix = text[max(0, mention['start'] - 45):mention['start']]
        found = list(PERCENT.finditer(prefix))
        if found:
            last = found[-1]
            tail = prefix[last.end():]
            if not re.search(r'[,，;+]|\b(?:and|in|with)\b', tail, re.I) and len(tail) < 30:
                concentrations[mention['id']] = float(last[1])
                offset = max(0, mention['start'] - 45)
                concentration_spans.append({'start': offset + last.start(), 'end': offset + last.end(), 'text': last[0]})
        after = text[mention['end']:mention['end'] + 12]
        trailing = re.match(r'\s*(' + NUM + r')\s*%', after)
        if trailing:
            concentrations[mention['id']] = float(trailing[1])
    # Stock dilution is a ranking feature, separate from verified recipe values.
    stock_fraction = None
    if named:
        if re.search(r'\bfull\b|undiluted', text, re.I):
            stock_fraction = 1.0
        elif re.search(r'\bhalf\b|1/2', text, re.I):
            stock_fraction = 0.5
        else:
            stock_fraction = 1.0
    return {'action': act, 'action_origin': action_origin, 'primary_materials': sorted(primary),
        'all_materials': sorted(materials), 'material_spans': ms,
        'concentrations': concentrations, 'concentration_spans': concentration_spans,
        'stock_fraction_ranking_feature': stock_fraction,
        'stock_origin': 'explicit_or_unqualified_named_stock_ranking_only' if named else None,
        'duration': parameter(text, 'duration'), 'temperature': parameter(text, 'temperature'),
        'phase': phase(text, heading, primary, act),
        'exchange': bool(re.search(r'replace|refresh|fresh|更换|新鲜|新液', text, re.I)),
        'polarity': 'NEGATED' if re.search(r'^(?:do not|never)\b|^不要|^不进行', text, re.I) else 'AFFIRMED',
        'optional': bool(re.search(r'optional|if |若|可选|必要时', text, re.I)),
        'repeat_or_endpoint': [m[0] for m in re.finditer(r'repeat[^).]*|\d\s*[×x]\s*\d[^).]*|until[^).]*|直到[^。]*|更换\s*\d[^。]*', text, re.I)]}


def ledger_operation(text, prediction, method, heading=''):
    entities = {e['id']: e for e in prediction['entities']}
    actions = sorted([e for e in entities.values() if e['label'] == 'Action'], key=lambda e: e['start'])
    if not actions:
        return {'action': None, 'primary_materials': [], 'concentrations': {}, 'duration': {'value': None},
                'temperature': {'value': None}, 'phase': 'unknown', 'exchange': False, 'polarity': 'UNKNOWN',
                'action_origin': 'no_predicted_Action', 'stock_fraction_ranking_feature': None}
    act_entity = actions[0]
    selected = {act_entity['id']}
    # Preserve directed arguments and their Measure edges, never scan missing nodes.
    linked_material_ids = set()
    parameter_ids = set()
    for rel in prediction['relations']:
        if rel['head'] in selected:
            if rel['label'] in ('Acts-on', 'Site', 'Using'):
                linked_material_ids.add(rel['tail'])
            if rel['label'] in ('Setting', 'Measure', 'Mod-Link'):
                parameter_ids.add(rel['tail'])
    for rel in prediction['relations']:
        if rel['head'] in linked_material_ids and rel['label'] == 'Measure':
            parameter_ids.add(rel['tail'])
    mats = set()
    for ident in linked_material_ids:
        e = entities[ident]
        mats.update(m['id'] for m in mentions(e['text'], method))
    named = mats & FORMULATIONS
    primary = named or (mats - {'water', 'pbs', 'triton_x100', 'tween20', 'urea', 'glycerol', 'sorbitol'} if len(mats) > 1 else mats)
    act, _ = action(act_entity['text'])
    conc = {}
    for rel in prediction['relations']:
        if rel['head'] in linked_material_ids and rel['label'] == 'Measure':
            tail = entities[rel['tail']]
            if tail['label'] == 'Concentration':
                number = PERCENT.search(tail['text'])
                if number:
                    for m in mentions(entities[rel['head']]['text'], method):
                        conc[m['id']] = float(number[1])
    values = {}
    for name, label in [('duration', 'Time'), ('temperature', 'Temperature')]:
        vals = [parameter(entities[k]['text'], name)['value'] for k in parameter_ids if entities[k]['label'] == label]
        good = [v for v in vals if v is not None]
        values[name] = {'value': good[0] if good and all(v == good[0] for v in good) else None}
    return {'action': act, 'primary_materials': sorted(primary), 'concentrations': conc, **values,
            'phase': phase('', heading, primary, act), 'exchange': act_entity['text'].lower() in ('replace', 'refresh'),
            'polarity': 'NEGATED' if re.match(r'do not|never', text, re.I) else 'AFFIRMED',
            'action_origin': 'ProtocolLedger_predicted_Action_and_arguments', 'stock_fraction_ranking_feature': None}


def signature(op):
    parts = [f"Action: {op['action'] or 'unknown'}", 'Medium: ' + (', '.join(op['primary_materials']) or 'unknown')]
    parts += [f'Concentration of {k}: {v:g} percent' for k, v in sorted(op['concentrations'].items())]
    if op.get('stock_fraction_ranking_feature') is not None:
        parts.append(f"Stock fraction: {op['stock_fraction_ranking_feature']:g}")
    for name, unit in [('duration', 'min'), ('temperature', 'C')]:
        v = op[name]['value']
        if v is not None:
            parts.append(f'{name}: {v} {unit}')
    parts += [f"Phase: {op['phase']}", f"Exchange: {op['exchange']}", f"Polarity: {op['polarity']}"]
    return '. '.join(parts) + '.'


def containment(reference, candidate):
    a, b = reference['value'], candidate['value']
    if a is None or b is None:
        return 'UNKNOWN'
    if isinstance(a, str) or isinstance(b, str):
        return 'PASS' if a == b else 'UNKNOWN'
    return 'PASS' if a[0] - 1e-8 <= b[0] and b[1] <= a[1] + 1e-8 else 'FAIL'


def field_score(a, b, variant='joint'):
    am, bm = set(a['primary_materials']), set(b['primary_materials'])
    chemistry = len(am & bm) / len(am | bm) if am and bm else 0.0
    action_match = float(a['action'] is not None and a['action'] == b['action'])
    if variant == 'identity':
        return .8 * chemistry + .2 * action_match
    common = set(a['concentrations']) & set(b['concentrations'])
    if common:
        concentration = sum(max(0, 1 - abs(a['concentrations'][k] - b['concentrations'][k]) / 100) for k in common) / len(common)
    elif a.get('stock_fraction_ranking_feature') is not None and b.get('stock_fraction_ranking_feature') is not None:
        concentration = 1 - abs(a['stock_fraction_ranking_feature'] - b['stock_fraction_ranking_feature'])
    else:
        concentration = .5
    same_phase = a['phase'] != 'unknown' and a['phase'] == b['phase']
    score = .55 * chemistry + .15 * action_match + .2 * concentration + .1 * same_phase
    if a['phase'] != 'unknown' and b['phase'] != 'unknown' and not same_phase:
        score -= .25
    if variant == 'strict':
        if chemistry < 1 or not action_match or any(containment(a[f], b[f]) != 'PASS' for f in ('duration', 'temperature')):
            return -1.0
        if common and any(a['concentrations'][k] != b['concentrations'][k] for k in common):
            return -1.0
    return score
