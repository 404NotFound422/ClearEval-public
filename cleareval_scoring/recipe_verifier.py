"""Unit- and version-aware checking of explicit named-formulation claims."""
import json,re
from pathlib import Path
from . import recipe_extensions as extensions
CATALOG=json.loads((Path(__file__).parent/'recipe_catalog.json').read_text('utf8'))
INGREDIENTS={
 'urea':r'\burea\b|尿素','sorbitol':r'(?:D[-–]\s*)?sorbitol|山梨醇','glycerol':r'glycerol|甘油',
 'triton_x100':r'Triton[-\s]*X[-\s]*100','dmso':r'\bDMSO\b|dimethyl\s*sulfoxide',
 'quadrol':r'Quadrol|N,N,N[′\']?,N[′\']?[-\s]*[Tt]etrakis\s*\([^)]*\)\s*ethylenediamine',
 'sucrose':r'sucrose|蔗糖','triethanolamine':r'triethanolamine|三乙醇胺',
 'butyldiethanolamine':r'N[-\s]*butyldiethanolamine|butyldiethanolamine',
 'antipyrine':r'antipyrine','nicotinamide':r'(?<!methyl[-\s])(?<!methyl)nicotinamide',
 'methylnicotinamide':r'N[-\s]*methylnicotinamide',
 'methyl_beta_cyclodextrin':r'methyl[-\s]*(?:beta|β|b)[-\s]*cyclodextrin',
 'gamma_cyclodextrin':r'(?:gamma|γ|g)[-\s]*cyclodextrin',
 'acetyl_hydroxyproline':r'N[-\s]*acetyl[-\s]*L[-\s]*hydroxyproline',
 'tert_butanol':r'(?:tert|t)[-\s\u2010-\u2015]*butanol|叔丁醇',
 'benzyl_benzoate':r'benzyl\s+benzoate|苯甲酸苄酯',
 'pegmma':r'PEG(?:[-\s]*MMA|[-\s]*methacrylate)(?:\s*500)?|poly(?:\(|\s*)ethylene\s+glycol\)?\s*methacrylate',
 'nma':r'N[-\s]*methylacetamide|NMA\b','histodenz':r'Histodenz',
}
NUM=r'\d+(?:\.\d+)?'
QUANTITY=re.compile(r'(?<![\w.])('+NUM+r')\s*(%\s*(?:\(?\s*(?:wt|w|weight|vol|v|volume)\s*/\s*(?:wt|w|weight|vol|v|volume)\s*\)?)?|(?:wt|vol)\s*%|mM\b|M\b)',re.I)
def unit(raw):
    raw=re.sub(r'[\s()]','',raw).lower().replace('weight','wt').replace('volume','vol')
    if raw=='m':return 'M'
    if raw=='mm':return 'mM'
    if raw=='wt%':return '%w/w'
    if raw=='vol%':return '%v/v'
    if re.search(r'(?:wt|w)/(?:vol|v)',raw):return '%w/v'
    if re.search(r'(?:wt|w)/(?:wt|w)',raw):return '%w/w'
    if re.search(r'(?:vol|v)/(?:vol|v)',raw):return '%v/v'
    return '%unspecified'
def ingredient_mentions(text,ingredients=None):
    matches=[]
    for name,pattern in (INGREDIENTS if ingredients is None else ingredients).items():
        for m in re.finditer(pattern,text,re.I):matches.append(dict(id=name,start=m.start(),end=m.end(),text=m[0]))
    return sorted(matches,key=lambda m:m['start'])
def parse_claim(text,ingredients=None):
    text=re.split(r'(?:Temperature|Time|温度|时间)\s*[:：]',text,flags=re.I)[0]
    ms=ingredient_mentions(text,ingredients);qs=list(QUANTITY.finditer(text));fields={}
    for m in ms:
        values=[]
        before=[q for q in qs if q.end()<=m['start'] and m['start']-q.end()<45 and not any(x['start']>=q.end() and x['end']<=m['start'] for x in ms if x!=m)]
        if before:
            q=before[-1];between=text[q.end():m['start']]
            if not re.search(r'[+,;，；]|\b(?:and|with|in)\b',between,re.I):values.append(q)
        after=[q for q in qs if q.start()>=m['end'] and q.start()-m['end']<6 and not re.search(r'[+,;，；]',text[m['end']:q.start()])]
        if after:values.append(after[0])
        for q in values:
            value=dict(value=float(q[1]),unit=unit(q[2]),span=[q.start(),q.end()],literal=q[0])
            if value not in fields.setdefault(m['id'],[]):fields[m['id']].append(value)
    bound={tuple(v['span']) for vs in fields.values() for v in vs}
    unbound=[dict(literal=q[0],span=[q.start(),q.end()]) for q in qs if (q.start(),q.end()) not in bound]
    return dict(fields=fields,mentioned=sorted({m['id'] for m in ms}),unbound_quantities=unbound,text=text)
def index_claims(answer,method,mention_fn):
    names={r['name'] for r in CATALOG['recipes']};index={}
    offset=0
    for line in answer.splitlines(keepends=True):
        named=[m for m in mention_fn(line,method) if m['id'] in names
               and not re.search(r'\bto (?:remove|wash)|洗去|去除|洗掉',line[max(0,m['start']-45):m['start']],re.I)]
        distinct=list(dict.fromkeys(m['id'] for m in named))
        if len(distinct)>1:
            # A multi-stock recipe requires action-level ownership, not broadcast.
            offset+=len(line);continue
        if named:
            claim=parse_claim(line)
            if claim['fields']:
                claim.update(answer_span=[offset,offset+len(line)],name=named[0]['id'])
                if named[0]['id']=='cubic_rplus':
                    variant=re.match(r'\s*\(([NM])\)',line[named[0]['end']:])
                    if variant:claim['explicit_variant']=variant[1]
                index.setdefault(named[0]['id'],[]).append(claim)
        offset+=len(line)
    extension_ingredients={k:v for k,v in {**INGREDIENTS,**extensions.INGREDIENTS}.items() if k!='histodenz'}
    index.update(extensions.declarations(answer,lambda text:parse_claim(text,extension_ingredients)))
    return index
def value_check(expected,actual):
    a,b=expected['value'],actual['value'];au,bu=expected['unit'],actual['unit']
    if au=='carrier':return 'PASS'
    if a==0:return 'FAIL' if b>0 else 'PASS'
    if au=='M' and bu=='mM':b/=1000;bu='M'
    if au=='mM' and bu=='M':b*=1000;bu='mM'
    if au!=bu or au=='%unspecified':return 'UNKNOWN'
    return 'PASS' if abs(a-b)<1e-7 else 'FAIL'
def check_variant(recipe,claim):
    checks={};fields=claim['fields'];present=set(claim['mentioned'])
    if claim.get('unbound_quantities'):checks['quantity_binding_coverage']='UNKNOWN'
    for name,expected in recipe['components'].items():
        if expected['unit']=='carrier':
            checks[name]='PASS' if name in present else 'UNKNOWN';continue
        actual=fields.get(name,[])
        if not actual:checks[name]='PASS' if expected['value']==0 else 'UNKNOWN';continue
        statuses=[value_check(expected,a) for a in actual]
        checks[name]='FAIL' if 'FAIL' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'PASS'
    for name,expected in recipe.get('optional_components',{}).items():
        actual=fields.get(name,[])
        if actual:
            statuses=[value_check(expected,a) for a in actual]
            checks['optional:'+name]='FAIL' if 'FAIL' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'PASS'
    if recipe['closed_components']:
        extras=present-set(recipe['components'])-set(recipe.get('optional_components',{}))
        for extra in extras:
            # Only explicitly quantified added ingredients assert a modification.
            if any(a['value']>0 for a in fields.get(extra,[])):checks['extra:'+extra]='FAIL'
    status='FAIL' if 'FAIL' in checks.values() else 'UNKNOWN' if 'UNKNOWN' in checks.values() else 'PASS'
    return dict(variant=recipe['variant'],status=status,checks=checks,evidence=recipe['evidence'])
def evaluate(name,reference_id,index):
    extended=extensions.evaluate(name,reference_id,index,value_check)
    if extended is not None:return extended
    recipes=[r for r in CATALOG['recipes'] if r['name']==name and r['reference_contains'].lower() in reference_id.lower()]
    if not recipes:return dict(status='UNSUPPORTED',name=name)
    claims=index.get(name,[])
    if not claims:return dict(status='NAME_ONLY',name=name,recipe_evidence=[r['evidence'] for r in recipes])
    evaluated=[]
    for claim in claims:
        eligible=[r for r in recipes if not claim.get('explicit_variant') or r['variant']==claim['explicit_variant']]
        variants=[check_variant(r,claim) for r in eligible]
        status='PASS' if any(v['status']=='PASS' for v in variants) else 'FAIL' if all(v['status']=='FAIL' for v in variants) else 'UNKNOWN'
        evaluated.append(dict(status=status,claim=claim,variants=variants))
    statuses=[c['status'] for c in evaluated]
    return dict(name=name,status='FAIL' if 'FAIL' in statuses else 'UNKNOWN' if 'UNKNOWN' in statuses else 'PASS',
                claims=evaluated,source_alternatives=len(recipes))
