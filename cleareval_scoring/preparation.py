"""Separate solution manufacture from specimen operations; retain recipe evidence."""
from copy import deepcopy
import re

VERSION = 'preparation-scope-20261103-v1'
CLEARSEE_SOURCE = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8579160/'
# Headings alone (e.g. Imaging Preparation) never establish a reagent-making act.
START = re.compile(r'^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?(?:\*\*)?(?:prepare\b|preparing\b|dissolve\b|mix\b|配制|配液|溶解)', re.I)
REAGENT = re.compile(r'\b(?:solution|buffer|reagent|stock|water|PBS|ClearSee|CUBIC|lectin|antibody)\b|工作液|溶液|配方|试剂|抗体|一抗|二抗|漂白液', re.I)
SAMPLE_ACTION = re.compile(r'\b(?:incubat\w*|immers\w*|soak\w*|perfus\w*|wash\w*|bleach\w*|dehydrat\w*|transfer\w*)\b|孵育|浸泡|浸没|漂洗|清洗|灌注|脱水|将.{0,30}(?:组织|样本|样品|切片).{0,15}(?:置于|加入|转入)', re.I)
SPECIMEN = re.compile(r'\b(?:tissue|sample|specimen|organoid|section|seedling|brain)\b|组织|样本|样品|切片|幼苗', re.I)

def role(step):
    text=step['text'].replace('**','')
    if not START.search(text) or not REAGENT.search(text):return 'execution_or_other'
    # "for incubation" describes a stock's purpose, not contact with the specimen.
    action_text=re.sub(r'\b(?:for|prior to)\s+(?:subsequent\s+)?(?:incubation|washing|clearing|staining)\b','',text,flags=re.I)
    if SAMPLE_ACTION.search(action_text) or SPECIMEN.search(text):return 'mixed_or_specimen'
    return 'reagent_preparation'

def partition(case):
    result=deepcopy(case); separated={}
    for key in ['candidate_steps','reference_steps']:
        separated[key]=[deepcopy(s) for s in case[key] if role(s)=='reagent_preparation']
        result[key]=[s for s in result[key] if role(s)!='reagent_preparation']
    return result,separated

def incompatible_aliases(names,catalog):
    """Only assert a conflict when named recipes share no component-set variant."""
    signatures=[]
    for name in names:
        sig={frozenset(k for k,v in r['components'].items() if v['value']!=0)
             for r in catalog['recipes'] if r['name']==name}
        if not sig:return False
        signatures.append(sig)
    return len(signatures)>1 and not set.intersection(*signatures)

def install(e):
    if getattr(e,'preparation_scope_version',None)==VERSION:return
    e.preparation_scope_version=VERSION;r=e.recipes
    r.INGREDIENTS.update(xylitol=r'\bxylitol\b|木糖醇',sodium_deoxycholate=r'\bsodium\s+deoxycholate\b|脱氧胆酸钠')
    if not any(x['name']=='clearsee' for x in r.CATALOG['recipes']):
        r.CATALOG['recipes'].append(dict(name='clearsee',reference_contains='CLEARSEE_2015',variant='original',
            components={k:dict(value=v,unit='%w/v') for k,v in [('xylitol',10),('sodium_deoxycholate',15),('urea',25)]},
            closed_components=True,evidence=CLEARSEE_SOURCE))
    old_index=r.index_claims
    def index_claims(answer,method,mention_fn):
        index=old_index(answer,method,mention_fn);offset=0
        names={x['name'] for x in r.CATALOG['recipes']}
        for line in answer.splitlines(keepends=True):
            # Explicit A (B): recipe syntax asserts one stock with two names.
            # General multi-stock instructions remain owned by the original parser.
            named=[m for m in mention_fn(line,method) if m['id'] in names]
            if len(named)==2 and START.search(line.replace('**','')):
                a,b=named
                paren=re.fullmatch(r'\s*\(\s*',line[a['end']:b['start']])
                close=re.match(r'\s*\)\s*[:：]',line[b['end']:])
                if a['id']!=b['id'] and paren and close:
                    claim=r.parse_claim(line)
                    if claim['fields']:
                        for name in [a['id'],b['id']]:
                            c=deepcopy(claim);c.update(name=name,answer_span=[offset,offset+len(line)],
                                asserted_aliases=[a['id'],b['id']],
                                declared_identity_conflict=incompatible_aliases([a['id'],b['id']],r.CATALOG))
                            index.setdefault(name,[]).append(c)
            offset+=len(line)
        return index
    r.index_claims=index_claims
    old_variant=r.check_variant
    def check_variant(recipe,claim):
        result=old_variant(recipe,claim)
        if claim.get('declared_identity_conflict'):
            result['checks']['declared_stock_identity']='FAIL'
            result['status']='FAIL'
        return result
    r.check_variant=check_variant
