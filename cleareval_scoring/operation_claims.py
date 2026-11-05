"""Check explicit stock claims even when no reference operation was aligned.

FAIL means contradiction with the bound published route, not proof that an
unlisted experimental formulation can never work. Missing definitions remain
UNKNOWN. No case identifiers, model outputs or timing parameters are rules.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib,json,re
from pathlib import Path
from . import component,policy,preparation,resolution,recipe_scope

ROOT=Path(__file__).resolve().parents[1]
INGREDIENTS=dict(
    mxda=r'\bMXDA\b|m[-\s]*xylylenediamine',
    sds=r'\bSDS\b|sodium dodecyl sulfate',
    bsa=r'\bBSA\b|bovine serum albumin',
    benzyl_alcohol=r'benzyl\s+alcohol',
    thf=r'\bTHF\b|tetrahydrofuran',dbe=r'\bDBE\b|dibenzyl\s*ether')
STOCKS={
 'CUBIC':re.compile(r'\bCUBIC[-\s\u2010-\u2015]*(R\d+|R\+|RA|R|L)(?!\w)(?:\s*\(([NM])\))?',re.I),
 'FDISCO':re.compile(r'\bFDISCO(?:[-\s\u2010-\u2015]*(R\d+))?(?!\w)',re.I),
 'BoneClear':re.compile(r'\bBoneClear\s+Solution\s+([A-Z])(?!\w)',re.I)}

@lru_cache(maxsize=1)
def rulebook():
    book=json.loads((ROOT/'KnowledgeBase/operation_claim_rules.json').read_text('utf8'))
    for source in book['sources'].values():
        raw=(ROOT/source['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source['sha256']:
            raise ValueError('Operation-claim source fingerprint changed: '+source['path'])
        text=raw.decode('utf8');a,b=source['span']
        if text[a:b]!=source['quote']:raise ValueError('Operation-claim source span changed')
    return book

def stock_names(text,method):
    pattern=STOCKS.get(method)
    output=[]
    for m in pattern.finditer(text) if pattern else []:
        suffix=m[1] or ''
        name=method.lower()+('_'+suffix.lower() if suffix else '')
        if method=='CUBIC':name=name.replace('r+','rplus')
        variant=m[2].upper() if method=='CUBIC' and m[2] else None
        output.append({'name':name,'variant':variant,'literal':m[0],'span':[m.start(),m.end()]})
    for m in component.op.mentions(text,method):
        if m['id'] not in component.op.FORMULATIONS:continue
        if any(a['span'][0]<=m['start'] and a['span'][1]>=m['end'] for a in output):continue
        output.append(dict(name=m['id'],variant=None,literal=m['text'],span=[m['start'],m['end']]))
    return sorted(output,key=lambda a:a['span'])


def contact_names(text,method):
    removal=re.search(r'\bto\s+(?:remove|wash)\b|洗去|去除|洗掉',text,re.I)
    return [n for n in stock_names(text,method) if not removal or n['span'][0]<removal.start()]

def _eligible(case):
    rules=[r for r in rulebook()['recipes'] if r['method']==case['method']
            and r['reference_contains'].lower() in case['reference_id'].lower()]
    prefixes={'ScaleS':('scales',),'FOCM':('focm',),'Ce3D':('ce3d',),
              'PEGASOS':('tb_peg','bb_peg'),'ClearSee':('clearsee',),'CUBIC':('cubic_',)}
    for r in component.recipes.CATALOG['recipes']:
        if not r['name'].startswith(prefixes.get(case['method'],())):continue
        if r['reference_contains'].lower() not in case['reference_id'].lower():continue
        if any(x['name']==r['name'] and x['variant']==r['variant'] for x in rules):continue
        rules.append(dict(r,source_id=r['evidence']))
    for name in component.recipes.extensions.NAMES:
        bound=component.recipes.extensions.evaluate(name,case['reference_id'],{},component.recipes.value_check)
        if bound:
            rules.append(dict(name=name,variant=name,extension=True,source_id=bound['recipe_evidence'][0]))
    return rules

def _claim(text,name):
    ingredients={**component.recipes.INGREDIENTS,**component.recipes.extensions.INGREDIENTS,**INGREDIENTS}
    if name['name'].startswith('seedb'):ingredients.pop('histodenz',None)
    # A stock's parenthetical composition owns its quantities; incubation
    # buffers or wash reagents outside those parentheses do not redefine it.
    diluted=bool(re.search(r'(?:half(?:[-\s]+diluted)?|diluted|稀释)\s*$',text[:name['span'][0]],re.I))
    declared=recipe_scope.declaration(text,name['span'][1])
    segment=declared['text'] if declared else ''
    # A prohibition is not an instruction to add the quantified ingredient.
    # Keep offsets and stop at the next clause so a later positive addition
    # remains visible. Decimal points do not terminate a clause.
    negative=re.compile(r"\b(?:do\s+not\s+add|don['’]t\s+add|never\s+add|without)\b|(?:不要|不得|勿|不)(?:添加|加入)|不含",re.I)
    terminator=re.compile(r'[,，;；!。\n]|\.(?!\d)|\b(?:but|then|instead)\b',re.I)
    masked=list(segment)
    for match in negative.finditer(segment):
        end=terminator.search(segment,match.end())
        stop=end.start() if end else len(segment)
        masked[match.start():stop]=' '*(stop-match.start())
    claim=component.recipes.parse_claim(''.join(masked),ingredients)
    claim['source_text']=segment
    claim['diluted_definition']=diluted
    return claim


def _owned_definitions(step,definitions,positions):
    """Bind an inline recipe locally, otherwise resolve the stock in sequence."""
    origin=step.get('original_id',step['id'])
    local=[d for d in definitions if d[0]['id']==origin]
    if local:return local,'inline'
    pos=positions.get(origin)
    preceding=[d for d in definitions if pos is not None and positions[d[0]['id']]<pos]
    if preceding:
        return [max(preceding,key=lambda d:positions[d[0]['id']])],'preceding_definition'
    # A separately headed recipe appendix can define a stock before its use in
    # document order. A later execution step cannot redefine an earlier use.
    prepared=[d for d in definitions if preparation.role(d[0])=='reagent_preparation']
    return prepared,'preparation_definition' if prepared else 'unbound'

def _variants(claim,recipes):
    results=[]
    for recipe in recipes:
        if recipe.get('extension'):
            ext=component.recipes.extensions
            checks=(ext.check_babb(recipe['name'],claim,component.recipes.value_check)
                    if recipe['name'].startswith('babb') else ext.check_seedb(recipe['name'],claim))
            checks={k:v for k,v in checks.items() if k not in policy.PROPERTY_FIELDS}
            checked=dict(checks=checks,status=policy.combine(list(checks.values())))
        else:
            checked=component.recipes.check_variant(recipe,claim)
            if claim.get('diluted_definition'):
                for key,expected in recipe['components'].items():
                    if expected['unit']!='carrier' and expected['value']!=0 and checked['checks'].get(key)=='FAIL':
                        checked['checks'][key]='UNKNOWN'
                checked['status']=policy.combine(list(checked['checks'].values()))
        results.append({'stock':recipe['name'],'variant':recipe['variant'],
                        'status':checked['status'],'checks':checked['checks'],
                        'source_id':recipe['source_id']})
    return results

def audit(case,packet):
    # Load the same chemical aliases used by the formal verifier. In particular,
    # a cached-packet replay must not depend on a prior score_branch() call.
    resolution.install(component)
    preparation.install(component)
    recipes=_eligible(case);method=case['method'];index={};excluded_label_definitions=set()
    positions={s['id']:i for i,s in enumerate(case['candidate_steps'])}
    # Parsed execution/preparation statements only; free prose and the model's
    # justification do not define stock compositions.
    for step in case['candidate_steps']:
        names=contact_names(step['text'],method)
        head=component.domain_heading(step.get('heading',''))
        labeling=component.LABEL.search(head) and (not component.CORE.search(head) or component.LABEL.search(step['text']))
        if labeling and preparation.role(step)!='reagent_preparation':
            excluded_label_definitions.update(n['name'] for n in names)
            continue
        alias_end=None
        if len(names)==2 and preparation.role(step)=='reagent_preparation':
            first,second=names
            if re.fullmatch(r'\s*[(（]\s*',step['text'][first['span'][1]:second['span'][0]]):
                closing=re.match(r'\s*[)）](?=\s*[:：])',step['text'][second['span'][1]:])
                if closing:alias_end=second['span'][1]+closing.end()
        for name in names:
            binding_name=dict(name,span=[name['span'][0],alias_end]) if alias_end else name
            claim=_claim(step['text'],binding_name)
            if alias_end:
                claim['declared_identity_conflict']=preparation.incompatible_aliases([n['name'] for n in names],component.recipes.CATALOG)
            if not (claim['mentioned'] or claim['unbound_quantities']):continue
            index.setdefault(name['name'],[]).append((step,name,claim))
    output=[]
    for step in packet['logical_candidate_steps']:
        names=contact_names(step['text'],method)
        names=list({(n['name'],n.get('variant')):n for n in names}.values())
        if len(names)!=1:
            reason='MULTIPLE_STOCKS_NEED_BINDING' if names else 'NO_BOUND_STOCK_CLAIM'
            output.append({'candidate':step['id'],'status':'UNKNOWN','reason':reason})
            continue
        name=names[0];definitions=index.get(name['name'],[])
        named=[r for r in recipes if r['name']==name['name']]
        identity={'stock':name['literal'],'stock_name':name['name'],
                  'scoped_recipe_check':bool(named),
                  'definition_inventory_present':bool(definitions) or name['name'] in excluded_label_definitions}
        if name.get('variant'):
            definitions=[d for d in definitions if d[1].get('variant') in {None,name['variant']}]
        definitions,binding=_owned_definitions(step,definitions,positions)
        if not definitions:
            output.append({'candidate':step['id'],**identity,
                           'status':'UNKNOWN','reason':'STOCK_DEFINITION_MISSING'})
            continue
        route_name=name['name'].startswith(method.lower()+'_') or name['name']==method.lower()
        eligible=named or (recipes if route_name else [])
        if name.get('variant'):eligible=[r for r in eligible if r['variant']==name['variant']]
        if not eligible:
            output.append({'candidate':step['id'],**identity,
                           'status':'UNKNOWN','reason':'NO_BOUND_RECIPE_RULE'})
            continue
        claims=[]
        for defining_step,declared,claim in definitions:
            defined_recipes=[r for r in eligible if not declared.get('variant') or r['variant']==declared['variant']]
            if not defined_recipes:continue
            variants=_variants(claim,defined_recipes)
            state='PASS' if any(v['status']=='PASS' for v in variants) else 'FAIL' if all(v['status']=='FAIL' for v in variants) else 'UNKNOWN'
            claims.append({'definition_candidate':defining_step['id'],
                           'source_span':defining_step.get('source_span',defining_step.get('span')),
                           'status':state,'variants':variants})
        state=policy.combine([c['status'] for c in claims]) if claims else 'UNKNOWN'
        ambiguous=False
        if len(claims)>1 and binding=='preparation_definition':
            # Multiple appendix definitions have no unique owner. If their
            # checks disagree, do not assign the wrong one to a bare use.
            signatures={json.dumps(c['variants'],sort_keys=True) for c in claims}
            if len(signatures)>1:state='UNKNOWN';ambiguous=True
        # Composition equivalence alone does not establish an unknown name's
        # identity or authorize an extra execution step.
        if state=='PASS' and not named:state='UNKNOWN'
        reason='EXPLICIT_RECIPE_CONFLICT' if state=='FAIL' else 'RECIPE_VERIFIED' if state=='PASS' else 'RECIPE_OR_ALIAS_UNRESOLVED'
        if ambiguous:reason='AMBIGUOUS_STOCK_DEFINITION'
        output.append({'candidate':step['id'],**identity,
                       'status':state,'reason':reason,'binding':binding,'claims':claims})
    return output

def classify_additions(additions,audits):
    by_id={a['candidate']:a for a in audits};output=deepcopy(additions)
    for addition in output:
        finding=by_id.get(addition['candidate'])
        if not finding:continue
        addition['claim_reason']=finding['reason']
        if finding['status']=='FAIL':
            addition['status']='CONFLICTING_ADDITION'
            addition['claim_audit_candidate']=finding['candidate']
    return output

def compact_audits(audits):
    """Intern repeated condition vectors, keeping each original definition span."""
    output=deepcopy(audits);evidence={}
    for finding in output:
        for claim in finding.get('claims',[]):
            variants=claim.pop('variants')
            encoded=json.dumps(variants,sort_keys=True,separators=(',',':'))
            key='E'+hashlib.sha256(encoded.encode()).hexdigest()[:16]
            evidence[key]=variants;claim['checks_id']=key
    return output,evidence

def enrich(packet,case):
    packet=deepcopy(packet);audits=audit(case,packet);by_id={a['candidate']:a for a in audits}
    for mode in ['written','occurrence']:
        for pair in packet[mode]['pairs']:
            finding=by_id.get(pair['candidate'])
            if finding and finding['status']=='FAIL':
                pair['correctness_checks']['declared_recipe:independent_claim']='FAIL'
                pair['correctness_status']='FAIL'
        pairs=packet[mode]['pairs'];m=packet[mode]['metrics']
        for key,status in [('confirmed_correct_credit','PASS'),('correctness_review_credit','REVIEW'),('explicit_wrong_credit','FAIL')]:
            m[key]=sum(p['count'] for p in pairs if p['correctness_status']==status)
    packet['operation_claim_audit']=audits
    return packet
