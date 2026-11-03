"""BABB nested ratios and SeeDB2 variant/batch facts from author protocols.

Mass per added solvent volume is retained as a batch ratio, never relabelled w/v.
Only explicitly declared recipe facts trigger checks; a name alone is a name.
"""
import re

N = r'\d+(?:\.\d+)?'
NAMES = {
    'babb_d4': r'BABB[-\s]*D4(?!\d)', 'babb_d15': r'BABB[-\s]*D15(?!\d)',
    'seedb2g': r'SeeDB2[-\s]*G(?![A-Za-z])', 'seedb2s': r'SeeDB2[-\s]*S(?![A-Za-z])',
    'seedb2_generic': r'SeeDB2(?![-\s]*[GS]\b)',
}
INGREDIENTS = {
    'benzyl_alcohol': r'benzyl\s+alcohol|苄醇',
    'benzyl_benzoate': r'benzyl\s+benzoate|[苯苄]甲酸苄酯',
    'diphenyl_ether': r'diphenyl\s+ether|\bDPE\b|二苯醚',
    'vitamin_e': r'vitamin\s*E|(?:DL[-\s]*)?(?:alpha[-\s]*)?tocopherol|维生素\s*E',
    'iohexol': r'iohexol|Histodenz|碘海醇',
    'omnipaque350': r'Omnipaque\s*350',
    'saponin': r'saponin|皂苷', 'tris_edta': r'Tris[-\s]*EDTA',
    'pbs': r'\bPBS\b', 'fructose': r'(?:D[-\s]*)?fructose|果糖',
    'sucrose': r'sucrose|蔗糖', 'sorbitol': r'(?:D[-\s]*)?sorbitol|山梨醇',
    'glycerol': r'glycerol|甘油', 'thioglycerol': r'(?:alpha[-\s]*)?thioglycerol',
}


def combine(states):
    return 'FAIL' if 'FAIL' in states else 'UNKNOWN' if 'UNKNOWN' in states else 'PASS'


def declarations(answer, parse_claim):
    index = {}
    for line_no, line in enumerate(answer.splitlines(), 1):
        # Discussion of an alternative method is not a preparation instruction.
        if re.search(r'Justification|选择理由|^\s*理由', line, re.I):
            continue
        for name, pattern in NAMES.items():
            match = re.search(pattern, line, re.I)
            if not match:
                continue
            tail = line[match.end():]
            declaration_tail=tail.replace('**','').lstrip()
            # A composition must modify the named medium. A later gel, wash,
            # or mounting instruction on the same line is not its formulation.
            if not re.match(r'(?:(?:stock\s+)?solution(?:\s+[ABC])?\s*)?(?:stock\s*)?[(（\[:：=]',declaration_tail,re.I):
                continue
            # A bracketed stock composition is distinct from the diluted working solution.
            stock = re.search(r'stock\s*\[([^\]]+)\]', tail, re.I)
            payload = stock[1] if stock else tail
            # Conditions and later instructions are outside the declared composition.
            payload = re.split(r'(?:Temperature|Time|温度|时间)\s*[:：]', payload, flags=re.I)[0]
            facts = parse_claim(payload)
            ri = re.search(r'\bRI\s*(?:[≈~=：:]|is)?\s*(' + N + r')(?:\s*[-–]\s*(' + N + r'))?', payload, re.I)
            ratios = re.findall(r'(' + N + r')\s*[:：]\s*(' + N + r')', payload)
            batch = bool(re.search(r'\b(?:g|ml|μl|µl)\b', payload, re.I) and re.search(INGREDIENTS['iohexol'], payload, re.I))
            # Mounting gel and preservatives are not asserted stock compositions.
            if not facts['fields'] and not ri and not ratios and not batch:
                continue
            facts.update(name=name, line=line_no, text=payload, original_line=line,
                         ri=[float(ri[1]), float(ri[2] or ri[1])] if ri else None)
            index.setdefault(name, []).append(facts)
    return index


def ordered_ratio(text, left, right):
    lp, rp = '(?:'+left+')', '(?:'+right+')'
    join = r'\s*(?:[:/+]\s*|\band\s+)'
    numbers = r'[^\n;；]{0,28}?(' + N + r')\s*[:：]\s*(' + N + r')'
    for a,b,invert in [(lp,rp,False),(rp,lp,True)]:
        match = re.search(a+join+b+numbers, text, re.I)
        if match and float(match[1]) and float(match[2]):
            x,y = float(match[1]), float(match[2])
            return y/x if invert else x/y
    return None


def check_babb(name, claim, value_check):
    text = claim['text']; checks = {}
    inner = ordered_ratio(text, INGREDIENTS['benzyl_alcohol'], INGREDIENTS['benzyl_benzoate'])
    outer = ordered_ratio(text, r'\bBABB(?![-\s]*D\d)', INGREDIENTS['diphenyl_ether'])
    checks['BA_to_BB_volume_ratio'] = 'UNKNOWN' if inner is None else 'PASS' if abs(inner-.5)<1e-7 else 'FAIL'
    ratio = 4 if name=='babb_d4' else 15
    checks['BABB_to_DPE_volume_ratio'] = 'UNKNOWN' if outer is None else 'PASS' if abs(outer-ratio)<1e-7 else 'FAIL'
    vitamin = claim['fields'].get('vitamin_e', [])
    checks['vitamin_E'] = combine([value_check(dict(value=.4, unit='%v/v'), x) for x in vitamin]) if vitamin else 'UNKNOWN'
    return checks


def batch_check(text, name):
    # Recipe quantities refer to added solvent, not final solution volume.
    m = re.search(r'(' + N + r')\s*g\s*(?:Histodenz|iohexol)', text, re.I)
    v = re.search(r'(' + N + r')\s*(m[lL]|[uμµ][lL])\s*(?:Tris[-\s]*EDTA)', text, re.I)
    if not m or not v:
        return 'UNKNOWN'
    vol = float(v[1])/(1000 if v[2].lower()!='ml' else 1)
    # With saponin: the added saponin-stock volume is part of the solvent batch.
    sap = re.search(r'(' + N + r')\s*(m[lL]|[uμµ][lL])\s*20\s*%\s*saponin', text, re.I)
    if sap:
        sap_volume=float(sap[1])/(1000 if sap[2].lower()!='ml' else 1)
        if name=='seedb2s' and (abs(sap_volume/float(m[1])-.042)>1e-7 or abs(vol/float(m[1])-.378)>1e-7):
            return 'FAIL'
        if name=='seedb2g':return 'UNKNOWN'
        vol += sap_volume
    expected = 7.5 if name=='seedb2g' else 4.2
    return 'PASS' if abs(vol/float(m[1])-expected/10)<1e-7 else 'FAIL'


def check_seedb(name, claim):
    checks = {}; ri = claim.get('ri'); fields = claim['fields']; text = claim['text']
    if ri:
        target = 1.46 if name=='seedb2g' else 1.52
        checks['refractive_index_variant'] = 'PASS' if all(abs(x-target)<.005 for x in ri) else 'FAIL' if ri[1]<target-.005 or ri[0]>target+.005 else 'UNKNOWN'
    for ingredient in set(fields)-{'iohexol','omnipaque350','saponin','tris_edta','pbs'}:
        if any(x['value']>0 for x in fields.get(ingredient, [])):
            checks['incompatible_base:'+ingredient] = 'FAIL'
    explicit_formula = bool(fields) or re.search(r'\b(?:Histodenz|iohexol|Omnipaque\s*350)\b', text, re.I)
    if explicit_formula:
        checks['iohexol_base'] = 'PASS' if re.search(INGREDIENTS['iohexol']+'|'+INGREDIENTS['omnipaque350'], text, re.I) else 'UNKNOWN'
        # Omnipaque350 is directly allowed for G; a bare w/v percentage does not
        # establish equivalence with the author's g per added-buffer recipe.
        checks['batch_composition'] = 'PASS' if name=='seedb2g' and re.search(INGREDIENTS['omnipaque350'], text, re.I) else batch_check(text, name)
        if fields.get('iohexol'):
            checks['iohexol_concentration_units']='UNKNOWN'
        if fields.get('saponin'):
            native_stock=re.search(r'(?:m[lL]|[uμµ][lL])\s*20\s*%\s*saponin',text,re.I)
            checks['saponin_claim']=checks['batch_composition'] if native_stock else 'UNKNOWN'
        if claim.get('unbound_quantities'):
            checks['quantity_binding_coverage']='UNKNOWN'
        if name=='seedb2s' and re.search(r'\bPBS\b', text, re.I):
            checks['buffer_identity'] = 'FAIL'
    return checks


def evaluate(name, reference_id, index, value_check):
    if name not in NAMES or name=='seedb2_generic':
        return None
    if name.startswith('babb') and 'udisco2016' not in reference_id.lower():
        return None
    if name.startswith('seedb') and 'seedb2-author-protocol-2018' not in reference_id.lower():
        return None
    claims = index.get(name, []) + (index.get('seedb2_generic', []) if name.startswith('seedb') else [])
    source = 'udisco2016_solutions_p3' if name.startswith('babb') else 'seedb2_2018_recipes_p12_and_variant_p5'
    if not claims:
        return dict(name=name, status='NAME_ONLY', recipe_evidence=[source])
    evaluated = []
    for claim in claims:
        checks = check_babb(name, claim, value_check) if name.startswith('babb') else check_seedb(name, claim)
        evaluated.append(dict(status=combine(list(checks.values())), claim=claim,
                              variants=[dict(variant=name, checks=checks, evidence=source)]))
    return dict(name=name, status=combine([x['status'] for x in evaluated]), claims=evaluated,
                recipe_evidence=[source], scope='explicit_recipe_and_variant_claims')
